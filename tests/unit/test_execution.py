from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
from typing import Any

import pytest

from amba_ai.db.approval_repository import ApprovalRepository
from amba_ai.db.execution_repository import ExecutionRepository
from amba_ai.db.governance_repository import GovernanceRepository
from amba_ai.governance.approvals import (
    ApprovalDecision,
    ApprovalRequest,
    approval_decision_semantic_material,
)
from amba_ai.governance.execution import (
    DistributionAcknowledgment,
    ExecutionGateway,
    ExecutionReceipt,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ReviewQueueReceipt,
    SyntheticMitigationExecutor,
)
from amba_ai.governance.models import (
    EnforcementAction,
    GovernanceConfigurationError,
    PipelineEvent,
    PolicyRecommendation,
    SequentialIdentifierProvider,
    to_canonical_json,
)
from amba_ai.governance.operation_registry import DestinationRegistry
from amba_ai.governance.principals import FixedClock


MIGRATION_002 = Path(
    "src/amba_ai/db/migrations/002_governance_records.sql"
)
MIGRATION_003 = Path(
    "src/amba_ai/db/migrations/003_approval_execution_audit.sql"
)
REPO_DESTINATIONS = Path("config/destinations.yaml")
FIXED_TIME = "2026-06-01T10:00:00Z"
OPERATION_ID = "commercial_purchase_request"
REVIEW_DESTINATION = "SYNTHETIC-REVIEW-QUEUE"


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def make_approval_decision_digest(
    *,
    decision_id: str,
    request_id: str,
    principal_id: str,
    mandate_id: str,
    approved: bool,
    rationale: str,
    decided_at: str,
    request_digest: str,
    synthetic: bool = True,
    legal_effect: bool = False,
) -> str:
    normalized_decided_at = decided_at.replace(
        "Z",
        "+00:00",
    )
    material = approval_decision_semantic_material(
        decision_id=decision_id,
        request_id=request_id,
        principal_id=principal_id,
        mandate_id=mandate_id,
        approved=approved,
        rationale=rationale,
        decided_at=normalized_decided_at,
        request_digest=request_digest,
        synthetic=synthetic,
        legal_effect=legal_effect,
    )
    return sha256(
        to_canonical_json(material).encode("utf-8")
    )


def make_request(
    *,
    request_id: str = "EXREQ-001",
    event_id: str = "EVT-001",
    action: EnforcementAction = EnforcementAction.BLOCK,
    destination_id: str = REVIEW_DESTINATION,
    approval_decision_id: str | None = None,
    idempotency_key: str = "IDEM-EXEC-001",
) -> ExecutionRequest:
    return ExecutionRequest.create(
        request_id=request_id,
        event_id=event_id,
        operation_id=OPERATION_ID,
        recommended_action=action,
        destination_id=destination_id,
        precondition_digest=sha256(f"precondition:{event_id}".encode()),
        recommendation_digest=sha256(f"recommendation:{event_id}".encode()),
        approval_decision_id=approval_decision_id,
        idempotency_key=idempotency_key,
        created_at=FIXED_TIME,
    )


def make_execution_receipt(
    request: ExecutionRequest,
    *,
    receipt_id: str = "EXRCPT-001",
    action: EnforcementAction | None = None,
    status: ExecutionStatus = ExecutionStatus.SUCCEEDED,
    details: dict[str, Any] | None = None,
) -> ExecutionReceipt:
    executed_action = action or request.recommended_action
    return ExecutionReceipt(
        receipt_id=receipt_id,
        request_id=request.request_id,
        event_id=request.event_id,
        operation_id=request.operation_id,
        action_executed=executed_action,
        status=status,
        executor_id="EXECUTOR-001",
        execution_effect="Execution outcome recorded",
        executed_at=FIXED_TIME,
        receipt_digest=sha256(f"receipt:{receipt_id}".encode()),
        details=details or {"result": "recorded"},
        synthetic=True,
        legal_effect=False,
    )


def make_review_receipt(
    request: ExecutionRequest,
    *,
    receipt_id: str = "QRCPT-001",
    details: dict[str, Any] | None = None,
) -> ReviewQueueReceipt:
    return ReviewQueueReceipt(
        receipt_id=receipt_id,
        request_id=request.request_id,
        event_id=request.event_id,
        queue_destination_id=REVIEW_DESTINATION,
        enqueued_at=FIXED_TIME,
        receipt_digest=sha256(f"review:{receipt_id}".encode()),
        reason_code="POLICY_HOLD",
        details=details or {"queue": REVIEW_DESTINATION},
    )


def make_acknowledgment(
    request: ExecutionRequest,
    receipt: ExecutionReceipt,
    *,
    acknowledgment_id: str = "ACK-001",
    receipt_id: str | None = None,
    destination_id: str | None = None,
) -> DistributionAcknowledgment:
    return DistributionAcknowledgment(
        acknowledgment_id=acknowledgment_id,
        execution_receipt_id=receipt_id or receipt.receipt_id,
        destination_id=destination_id or request.destination_id,
        disposition="DELIVERED",
        acknowledged_at=FIXED_TIME,
        acknowledgment_digest=sha256(
            f"ack:{acknowledgment_id}".encode()
        ),
    )


def make_event(
    *,
    event_id: str = "EVT-001",
    destination_id: str = REVIEW_DESTINATION,
    operation_id: str = OPERATION_ID,
) -> PipelineEvent:
    return PipelineEvent(
        event_id=event_id,
        timestamp=FIXED_TIME,
        operation_id=operation_id,
        source_node="TEST-SOURCE",
        destination_id=destination_id,
        payload_type="test_payload",
        payload={},
    )


def make_recommendation(
    event: PipelineEvent,
    *,
    recommendation_id: str = "REC-001",
    action: EnforcementAction = (
        EnforcementAction.HOLD_FOR_REVIEW
    ),
    requires_approval: bool = False,
    event_id: str | None = None,
    escalation_role: str | None = None,
) -> PolicyRecommendation:
    resolved_escalation_role = escalation_role
    if (
        requires_approval
        and resolved_escalation_role is None
    ):
        resolved_escalation_role = "compliance_officer"
    if not requires_approval:
        resolved_escalation_role = None
    return PolicyRecommendation(
        recommendation_id=recommendation_id,
        event_id=event_id or event.event_id,
        recommended_action=action,
        mitigation_steps=(),
        requires_approval=requires_approval,
        escalation_role=resolved_escalation_role,
    )


def persist_approval(
    repository: ApprovalRepository,
    *,
    event_id: str,
    recommendation_id: str,
    approved: bool = True,
    request_id: str = "APPREQ-001",
    decision_id: str = "APPDEC-001",
) -> ApprovalDecision:
    request = ApprovalRequest.create(
        request_id=request_id,
        event_id=event_id,
        recommendation_id=recommendation_id,
        operation_id=OPERATION_ID,
        requested_decision="approve_review_queue",
        target_role="school_administrator",
        mandate_id="MANDATE-001",
        context_digest=sha256(b"approval-context"),
        created_at="2026-06-01T09:00:00Z",
        expires_at="2026-06-01T12:00:00Z",
        idempotency_key=f"IDEM-{request_id}",
    )
    principal_id = "PRINCIPAL-001"
    rationale = "Approval test decision"
    decided_at = "2026-06-01T09:30:00Z"
    synthetic = True
    legal_effect = False
    decision_digest = make_approval_decision_digest(
        decision_id=decision_id,
        request_id=request.request_id,
        principal_id=principal_id,
        mandate_id=request.mandate_id,
        approved=approved,
        rationale=rationale,
        decided_at=decided_at,
        request_digest=request.request_digest,
        synthetic=synthetic,
        legal_effect=legal_effect,
    )
    decision = ApprovalDecision(
        decision_id=decision_id,
        request_id=request.request_id,
        principal_id=principal_id,
        mandate_id=request.mandate_id,
        approved=approved,
        rationale=rationale,
        decided_at=decided_at,
        request_digest=request.request_digest,
        decision_digest=decision_digest,
        synthetic=synthetic,
        legal_effect=legal_effect,
    )
    repository.store_request_and_decision(
        request,
        decision,
    )
    return decision


@pytest.fixture
def exec_setup():
    assert REPO_DESTINATIONS.exists()
    destination_registry = DestinationRegistry.load_from_yaml(
        REPO_DESTINATIONS
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_execution.db"
        governance_repository = GovernanceRepository(db_path)
        governance_repository.apply_migration_file(MIGRATION_002)
        governance_repository.apply_migration_file(MIGRATION_003)

        approval_repository = ApprovalRepository(db_path)
        execution_repository = ExecutionRepository(db_path)
        gateway = ExecutionGateway(
            execution_repository=execution_repository,
            destination_registry=destination_registry,
            approval_query=approval_repository,
            identifier_provider=SequentialIdentifierProvider(),
            clock=FixedClock(FIXED_TIME),
        )

        yield {
            "db_path": db_path,
            "approval_repository": approval_repository,
            "destination_registry": destination_registry,
            "execution_repository": execution_repository,
            "gateway": gateway,
        }


def test_gateway_requires_approval_query(exec_setup):
    with pytest.raises(
        GovernanceConfigurationError,
        match="Approval verification repository is required",
    ):
        ExecutionGateway(
            execution_repository=exec_setup["execution_repository"],
            destination_registry=exec_setup["destination_registry"],
            approval_query=None,  # type: ignore[arg-type]
            identifier_provider=SequentialIdentifierProvider(),
            clock=FixedClock(FIXED_TIME),
        )


@pytest.mark.parametrize(
    "dependency, expected_message",
    [
        ("execution_repository", "execution_repository is required"),
        ("destination_registry", "destination_registry is required"),
        ("identifier_provider", "identifier_provider is required"),
        ("clock", "clock is required"),
    ],
)
def test_gateway_rejects_missing_dependencies(
    exec_setup,
    dependency: str,
    expected_message: str,
):
    arguments = {
        "execution_repository": exec_setup["execution_repository"],
        "destination_registry": exec_setup["destination_registry"],
        "approval_query": exec_setup["approval_repository"],
        "identifier_provider": SequentialIdentifierProvider(),
        "clock": FixedClock(FIXED_TIME),
    }
    arguments[dependency] = None

    with pytest.raises(TypeError, match=expected_message):
        ExecutionGateway(**arguments)  # type: ignore[arg-type]


def test_gateway_rejects_empty_executor_id(exec_setup):
    with pytest.raises(ValueError, match="executor_id must not be empty"):
        ExecutionGateway(
            execution_repository=exec_setup["execution_repository"],
            destination_registry=exec_setup["destination_registry"],
            approval_query=exec_setup["approval_repository"],
            identifier_provider=SequentialIdentifierProvider(),
            clock=FixedClock(FIXED_TIME),
            executor_id=" ",
        )


def test_recommendation_must_belong_to_execution_event(exec_setup):
    event = make_event(event_id="EVT-A")
    recommendation = make_recommendation(event, event_id="EVT-B")

    with pytest.raises(
        GovernanceConfigurationError,
        match="Policy recommendation does not belong to the execution event",
    ):
        exec_setup["gateway"].execute(
            event,
            recommendation,
            approval_decision=None,
            idempotency_key="IDEM-EVENT-MISMATCH",
        )


def test_gateway_rejects_empty_idempotency_key(exec_setup):
    event = make_event()
    recommendation = make_recommendation(event)

    with pytest.raises(ValueError, match="idempotency_key must not be empty"):
        exec_setup["gateway"].execute(
            event,
            recommendation,
            approval_decision=None,
            idempotency_key=" ",
        )


def test_gateway_rejects_nonmapping_execution_details(exec_setup):
    event = make_event()
    recommendation = make_recommendation(event)

    with pytest.raises(TypeError, match="execution_details must be a mapping"):
        exec_setup["gateway"].execute(
            event,
            recommendation,
            approval_decision=None,
            idempotency_key="IDEM-BAD-DETAILS",
            execution_details=["invalid"],  # type: ignore[arg-type]
        )


def test_approval_binding_is_enforced_strictly(exec_setup):
    event = make_event(event_id="EVT-APPROVED")
    recommendation = make_recommendation(
        event,
        recommendation_id="REC-APPROVED",
        requires_approval=True,
    )
    decision = persist_approval(
        exec_setup["approval_repository"],
        event_id=event.event_id,
        recommendation_id=recommendation.recommendation_id,
    )

    result = exec_setup["gateway"].execute(
        event,
        recommendation,
        approval_decision=decision,
        idempotency_key="IDEM-APPROVED",
    )
    assert result.review_queue_receipt is not None

    mismatched_event = make_event(event_id="EVT-DIFFERENT")
    matching_recommendation = make_recommendation(
        mismatched_event,
        recommendation_id=recommendation.recommendation_id,
        requires_approval=True,
    )

    with pytest.raises(
        GovernanceConfigurationError,
        match="Approval request event does not match execution event",
    ):
        exec_setup["gateway"].execute(
            mismatched_event,
            matching_recommendation,
            approval_decision=decision,
            idempotency_key="IDEM-APPROVAL-MISMATCH",
        )


def test_forged_approval_decision_is_rejected(exec_setup):
    event = make_event(event_id="EVT-FORGED")
    recommendation = make_recommendation(
        event,
        recommendation_id="REC-FORGED",
        requires_approval=True,
    )
    persisted = persist_approval(
        exec_setup["approval_repository"],
        event_id=event.event_id,
        recommendation_id=recommendation.recommendation_id,
    )
    forged_decision_id = "APPDEC-FORGED"
    forged_rationale = "Forged approval"
    forged_digest = make_approval_decision_digest(
        decision_id=forged_decision_id,
        request_id=persisted.request_id,
        principal_id=persisted.principal_id,
        mandate_id=persisted.mandate_id,
        approved=True,
        rationale=forged_rationale,
        decided_at=persisted.decided_at,
        request_digest=persisted.request_digest,
        synthetic=True,
        legal_effect=False,
    )
    forged = ApprovalDecision(
        decision_id=forged_decision_id,
        request_id=persisted.request_id,
        principal_id=persisted.principal_id,
        mandate_id=persisted.mandate_id,
        approved=True,
        rationale=forged_rationale,
        decided_at=persisted.decided_at,
        request_digest=persisted.request_digest,
        decision_digest=forged_digest,
        synthetic=True,
        legal_effect=False,
    )
    with pytest.raises(
        GovernanceConfigurationError,
        match="does not match the persisted decision",
    ):
        exec_setup["gateway"].execute(
            event,
            recommendation,
            approval_decision=forged,
            idempotency_key="IDEM-FORGED",
        )


def test_denied_required_approval_holds_without_attaching_decision(exec_setup):
    event = make_event(event_id="EVT-DENIED")
    recommendation = make_recommendation(
        event,
        recommendation_id="REC-DENIED",
        requires_approval=True,
    )
    denied = persist_approval(
        exec_setup["approval_repository"],
        event_id=event.event_id,
        recommendation_id=recommendation.recommendation_id,
        approved=False,
    )

    result = exec_setup["gateway"].execute(
        event,
        recommendation,
        approval_decision=denied,
        idempotency_key="IDEM-DENIED",
    )

    assert result.request.approval_decision_id is None
    assert result.review_queue_receipt is not None
    assert result.review_queue_receipt.reason_code == "APPROVAL_REQUIRED"


@pytest.mark.parametrize(
    "action",
    [EnforcementAction.CONFIRM, EnforcementAction.MODIFY],
)
def test_unsupported_lifecycles_are_not_attempted(exec_setup, action):
    event = make_event(
        event_id=f"EVT-{action.value.upper()}",
        operation_id="classroom_instruction_delivery",
        destination_id="SYNTHETIC-TEACHER-UI",
    )
    recommendation = make_recommendation(
        event,
        recommendation_id=f"REC-{action.value.upper()}",
        action=action,
    )

    result = exec_setup["gateway"].execute(
        event,
        recommendation,
        approval_decision=None,
        idempotency_key=f"IDEM-{action.value.upper()}",
    )

    assert result.execution_receipt is not None
    assert result.execution_receipt.action_executed == action
    assert result.execution_receipt.status == ExecutionStatus.NOT_ATTEMPTED
    assert result.distribution_acknowledgment is None


def test_execution_result_requires_exactly_one_receipt():
    request = make_request()

    with pytest.raises(ValueError, match="exactly one"):
        ExecutionResult(
            request=request,
            execution_receipt=None,
            review_queue_receipt=None,
            distribution_acknowledgment=None,
            duplicate=False,
        )

    with pytest.raises(ValueError, match="exactly one"):
        ExecutionResult(
            request=request,
            execution_receipt=make_execution_receipt(request),
            review_queue_receipt=make_review_receipt(request),
            distribution_acknowledgment=None,
            duplicate=False,
        )


def test_execution_result_rejects_receipt_request_mismatch():
    request = make_request()
    different_request = make_request(
        request_id="EXREQ-DIFFERENT",
        event_id=request.event_id,
        idempotency_key="IDEM-DIFFERENT",
    )
    receipt = make_execution_receipt(different_request)

    with pytest.raises(ValueError, match="request identifier does not match"):
        ExecutionResult(
            request=request,
            execution_receipt=receipt,
            review_queue_receipt=None,
            distribution_acknowledgment=None,
            duplicate=False,
        )


def test_successful_proceed_requires_acknowledgment():
    request = make_request(
        action=EnforcementAction.PROCEED,
        destination_id="SYNTHETIC-PURCHASE-GATEWAY",
    )
    receipt = make_execution_receipt(
        request,
        action=EnforcementAction.PROCEED,
    )

    with pytest.raises(
        ValueError,
        match="Successful delivery requires a distribution acknowledgment",
    ):
        ExecutionResult(
            request=request,
            execution_receipt=receipt,
            review_queue_receipt=None,
            distribution_acknowledgment=None,
            duplicate=False,
        )


def test_successful_proceed_with_matching_acknowledgment_is_valid():
    request = make_request(
        action=EnforcementAction.PROCEED,
        destination_id="SYNTHETIC-PURCHASE-GATEWAY",
    )
    receipt = make_execution_receipt(
        request,
        action=EnforcementAction.PROCEED,
    )
    acknowledgment = make_acknowledgment(request, receipt)

    result = ExecutionResult(
        request=request,
        execution_receipt=receipt,
        review_queue_receipt=None,
        distribution_acknowledgment=acknowledgment,
        duplicate=False,
    )

    assert result.distribution_acknowledgment == acknowledgment


def test_acknowledgment_receipt_and_destination_must_match():
    request = make_request(
        action=EnforcementAction.PROCEED,
        destination_id="SYNTHETIC-PURCHASE-GATEWAY",
    )
    receipt = make_execution_receipt(
        request,
        action=EnforcementAction.PROCEED,
    )

    with pytest.raises(ValueError, match="does not reference"):
        ExecutionResult(
            request=request,
            execution_receipt=receipt,
            review_queue_receipt=None,
            distribution_acknowledgment=make_acknowledgment(
                request,
                receipt,
                receipt_id="OTHER-RECEIPT",
            ),
            duplicate=False,
        )

    with pytest.raises(ValueError, match="destination does not match"):
        ExecutionResult(
            request=request,
            execution_receipt=receipt,
            review_queue_receipt=None,
            distribution_acknowledgment=make_acknowledgment(
                request,
                receipt,
                destination_id="OTHER-DESTINATION",
            ),
            duplicate=False,
        )


def test_distribution_acknowledgment_rejects_non_delivered_disposition():
    with pytest.raises(ValueError, match="disposition must be DELIVERED"):
        DistributionAcknowledgment(
            acknowledgment_id="ACK-BAD",
            execution_receipt_id="EXRCPT-001",
            destination_id="DESTINATION-001",
            disposition="REJECTED",
            acknowledged_at=FIXED_TIME,
            acknowledgment_digest=sha256(b"bad-ack"),
        )


def test_nested_receipt_details_serialize_to_mutable_values():
    request = make_request()
    receipt = make_execution_receipt(
        request,
        details={"nested": {"items": [1, 2]}},
    )
    result = ExecutionResult(
        request=request,
        execution_receipt=receipt,
        review_queue_receipt=None,
        distribution_acknowledgment=None,
        duplicate=False,
    )

    serialized = result.to_dict()
    assert serialized["execution_receipt"]["details"] == {
        "nested": {"items": [1, 2]}
    }
    assert result.to_canonical_json()


def test_receipt_details_must_be_mapping():
    request = make_request()

    with pytest.raises(TypeError, match="details must be a mapping"):
        ExecutionReceipt(
            receipt_id="EXRCPT-BAD",
            request_id=request.request_id,
            event_id=request.event_id,
            operation_id=request.operation_id,
            action_executed=EnforcementAction.BLOCK,
            status=ExecutionStatus.SUCCEEDED,
            executor_id="EXECUTOR-001",
            execution_effect="Blocked",
            executed_at=FIXED_TIME,
            receipt_digest=sha256(b"receipt-bad-details"),
            details=["invalid"],  # type: ignore[arg-type]
            synthetic=True,
            legal_effect=False,
        )


def test_execution_request_rejects_semantic_digest_mismatch():
    valid = make_request()

    with pytest.raises(ValueError, match="semantic content"):
        ExecutionRequest(
            request_id=valid.request_id,
            event_id="EVT-TAMPERED",
            operation_id=valid.operation_id,
            recommended_action=valid.recommended_action,
            destination_id=valid.destination_id,
            precondition_digest=valid.precondition_digest,
            recommendation_digest=valid.recommendation_digest,
            approval_decision_id=valid.approval_decision_id,
            idempotency_key=valid.idempotency_key,
            idempotency_digest=valid.idempotency_digest,
            created_at=valid.created_at,
            synthetic=valid.synthetic,
            legal_effect=valid.legal_effect,
        )


def test_identical_execution_retry_returns_original_request_and_receipt(exec_setup):
    repository = exec_setup["execution_repository"]
    request = make_request(
        request_id="EXREQ-RETRY",
        event_id="EVT-RETRY",
        action=EnforcementAction.HOLD_FOR_REVIEW,
        idempotency_key="IDEM-RETRY",
    )
    review_receipt = make_review_receipt(
        request,
        receipt_id="QRCPT-RETRY",
    )
    result = ExecutionResult(
        request=request,
        execution_receipt=None,
        review_queue_receipt=review_receipt,
        distribution_acknowledgment=None,
        duplicate=False,
    )

    first = repository.execute_transaction(request, lambda _: result)
    second = repository.execute_transaction(request, lambda _: result)

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.request == request
    assert second.review_queue_receipt == review_receipt


def test_conflicting_execution_retry_is_rejected(exec_setup):
    repository = exec_setup["execution_repository"]
    first_request = make_request(
        request_id="EXREQ-CONFLICT-A",
        event_id="EVT-CONFLICT-A",
        idempotency_key="IDEM-CONFLICT",
    )
    first_result = ExecutionResult(
        request=first_request,
        execution_receipt=make_execution_receipt(first_request),
        review_queue_receipt=None,
        distribution_acknowledgment=None,
        duplicate=False,
    )
    repository.execute_transaction(first_request, lambda _: first_result)

    second_request = make_request(
        request_id="EXREQ-CONFLICT-B",
        event_id="EVT-CONFLICT-B",
        idempotency_key="IDEM-CONFLICT",
    )

    with pytest.raises(
        GovernanceConfigurationError,
        match="Conflicting execution request",
    ):
        repository.execute_transaction(
            second_request,
            lambda persisted: ExecutionResult(
                request=persisted,
                execution_receipt=make_execution_receipt(persisted),
                review_queue_receipt=None,
                distribution_acknowledgment=None,
                duplicate=False,
            ),
        )


@pytest.mark.parametrize(
    "stored_json, expected_message",
    [
        ("broken-json{{{", "not valid JSON"),
        ('["not", "a", "mapping"]', "must decode to a mapping"),
    ],
)
def test_corrupted_execution_details_are_rejected(
    exec_setup,
    stored_json: str,
    expected_message: str,
):
    repository = exec_setup["execution_repository"]
    request = make_request(
        request_id="EXREQ-CORRUPT",
        event_id="EVT-CORRUPT",
        action=EnforcementAction.BLOCK,
        idempotency_key="IDEM-CORRUPT",
    )
    result = ExecutionResult(
        request=request,
        execution_receipt=make_execution_receipt(
            request,
            receipt_id="EXRCPT-CORRUPT",
            action=EnforcementAction.BLOCK,
        ),
        review_queue_receipt=None,
        distribution_acknowledgment=None,
        duplicate=False,
    )
    repository.execute_transaction(request, lambda _: result)

    with repository._conn() as connection:
        connection.execute(
            """
            UPDATE execution_receipts
            SET details_json = ?
            WHERE request_id = ?;
            """,
            (stored_json, request.request_id),
        )

    with pytest.raises(GovernanceConfigurationError, match=expected_message):
        repository.get_execution_result_by_idempotency_key(
            request.idempotency_key
        )


def test_corrupted_review_details_are_rejected(exec_setup):
    repository = exec_setup["execution_repository"]
    request = make_request(
        request_id="EXREQ-CORRUPT-REVIEW",
        event_id="EVT-CORRUPT-REVIEW",
        action=EnforcementAction.HOLD_FOR_REVIEW,
        idempotency_key="IDEM-CORRUPT-REVIEW",
    )
    result = ExecutionResult(
        request=request,
        execution_receipt=None,
        review_queue_receipt=make_review_receipt(request),
        distribution_acknowledgment=None,
        duplicate=False,
    )
    repository.execute_transaction(request, lambda _: result)

    with repository._conn() as connection:
        connection.execute(
            """
            UPDATE review_queue_receipts
            SET details_json = ?
            WHERE request_id = ?;
            """,
            ("corrupted-json", request.request_id),
        )

    with pytest.raises(GovernanceConfigurationError, match="not valid JSON"):
        repository.get_execution_result_by_idempotency_key(
            request.idempotency_key
        )


def test_mitigation_postconditions_are_derived_from_actions(exec_setup):
    executor = exec_setup["gateway"].mitigation_executor

    first = executor.execute_mitigation(
        event_id="EVT-MIT-1",
        mandate_id="MANDATE-001",
        actions=("disable_commercial_sdk",),
    )
    assert first == {
        "commercial_sdk_active_after": False,
        "purchase_interface_visible_after": True,
        "vendor_review_queued": False,
    }

    second = executor.execute_mitigation(
        event_id="EVT-MIT-2",
        mandate_id="MANDATE-001",
        actions=(
            "disable_commercial_sdk",
            "prevent_purchase_ui_delivery",
            "queue_vendor_review",
        ),
    )
    assert second == {
        "commercial_sdk_active_after": False,
        "purchase_interface_visible_after": False,
        "vendor_review_queued": True,
    }


@pytest.mark.parametrize(
    "actions, expected_message",
    [
        ((), "must not be empty"),
        (("disable_commercial_sdk", "disable_commercial_sdk"), "duplicates"),
        (("unsupported_action",), "not permitted"),
        (("",), "empty value"),
    ],
)
def test_mitigation_rejects_invalid_action_sets(
    exec_setup,
    actions: tuple[str, ...],
    expected_message: str,
):
    with pytest.raises(GovernanceConfigurationError, match=expected_message):
        exec_setup["gateway"].mitigation_executor.execute_mitigation(
            event_id="EVT-MIT-BAD",
            mandate_id="MANDATE-001",
            actions=actions,
        )


def test_mitigation_executor_requires_dependencies(exec_setup):
    with pytest.raises(TypeError, match="repository is required"):
        SyntheticMitigationExecutor(
            None,  # type: ignore[arg-type]
            FixedClock(FIXED_TIME),
        )

    with pytest.raises(TypeError, match="clock is required"):
        SyntheticMitigationExecutor(
            exec_setup["execution_repository"],
            None,  # type: ignore[arg-type]
        )
