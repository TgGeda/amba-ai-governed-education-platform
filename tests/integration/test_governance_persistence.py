from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import tempfile

import pytest

from amba_ai.db.approval_repository import ApprovalRepository
from amba_ai.db.audit_repository import AuditRepository
from amba_ai.db.execution_repository import ExecutionRepository
from amba_ai.db.governance_repository import GovernanceRepository
from amba_ai.governance.approvals import (
    ApprovalDecision,
    ApprovalRequest,
    approval_decision_semantic_material,
)
from amba_ai.governance.execution import (
    ExecutionRequest,
    ExecutionResult,
    ReviewQueueReceipt,
)
from amba_ai.governance.models import (
    EnforcementAction,
    GovernanceConfigurationError,
    to_canonical_json,
)


MIGRATION_002 = Path(
    "src/amba_ai/db/migrations/002_governance_records.sql"
)
MIGRATION_003 = Path(
    "src/amba_ai/db/migrations/003_approval_execution_audit.sql"
)


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
    normalized_decided_at = decided_at.replace("Z", "+00:00")
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
    return sha256(to_canonical_json(material).encode("utf-8"))


def apply_governance_migrations(db_path: Path) -> None:
    repository = GovernanceRepository(db_path)
    repository.apply_migration_file(MIGRATION_002)
    repository.apply_migration_file(MIGRATION_003)


def test_full_governance_persistence_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "governance_full.db"
        apply_governance_migrations(db_path)

        approval_repository = ApprovalRepository(db_path)
        context_digest = sha256(b"context")
        approval_request = ApprovalRequest.create(
            request_id="REQ-FULL-01",
            event_id="EVT-01",
            recommendation_id="REC-01",
            operation_id="commercial_purchase_request",
            requested_decision="approve_review_queue",
            target_role="school_administrator",
            mandate_id="MANDATE-01",
            context_digest=context_digest,
            created_at="2026-06-01T10:00:00Z",
            expires_at="2026-06-01T12:00:00Z",
            idempotency_key="IDEM-APP-FULL",
        )

        decision_id = "DEC-FULL-01"
        principal_id = "PRINCIPAL-01"
        rationale = "Board passed"
        decided_at = "2026-06-01T10:30:00Z"
        decision_digest = make_approval_decision_digest(
            decision_id=decision_id,
            request_id=approval_request.request_id,
            principal_id=principal_id,
            mandate_id=approval_request.mandate_id,
            approved=True,
            rationale=rationale,
            decided_at=decided_at,
            request_digest=approval_request.request_digest,
        )
        approval_decision = ApprovalDecision(
            decision_id=decision_id,
            request_id=approval_request.request_id,
            principal_id=principal_id,
            mandate_id=approval_request.mandate_id,
            approved=True,
            rationale=rationale,
            decided_at=decided_at,
            request_digest=approval_request.request_digest,
            decision_digest=decision_digest,
            synthetic=True,
            legal_effect=False,
        )
        approval_repository.store_request_and_decision(
            approval_request,
            approval_decision,
        )

        execution_repository = ExecutionRepository(db_path)
        execution_request = ExecutionRequest.create(
            request_id="EXREQ-01",
            event_id="EVT-01",
            operation_id="commercial_purchase_request",
            recommended_action=EnforcementAction.HOLD_FOR_REVIEW,
            destination_id="SYNTHETIC-REVIEW-QUEUE",
            precondition_digest=sha256(b"precond"),
            recommendation_digest=sha256(b"recom"),
            approval_decision_id=approval_decision.decision_id,
            idempotency_key="IDEM-EXEC-FULL",
            created_at="2026-06-01T10:35:00Z",
        )
        review_receipt = ReviewQueueReceipt(
            receipt_id="EXRCPT-01",
            request_id=execution_request.request_id,
            event_id=execution_request.event_id,
            queue_destination_id="SYNTHETIC-REVIEW-QUEUE",
            enqueued_at="2026-06-01T10:35:00Z",
            receipt_digest=sha256(b"rcpt"),
            reason_code="POLICY_HOLD",
            details={"queue": "SYNTHETIC-REVIEW-QUEUE"},
        )
        execution_result = ExecutionResult(
            request=execution_request,
            execution_receipt=None,
            review_queue_receipt=review_receipt,
            distribution_acknowledgment=None,
            duplicate=False,
        )
        execution_repository.execute_transaction(
            execution_request,
            lambda _: execution_result,
        )

        audit_repository = AuditRepository(db_path)
        block = audit_repository.append_atomic(
            run_id="RUN-PERSIST-01",
            scenario_id="SCENARIO-01",
            stage_id="STAGE-1",
            event_id="EVT-01",
            operation_id="commercial_purchase_request",
            event_type="APPROVAL_AND_EXECUTION",
            timestamp="2026-06-01T10:35:00Z",
            payload={
                "request_id": approval_request.request_id,
                "decision_id": approval_decision.decision_id,
            },
            schema_version="1.0.0",
        )
        assert block.block_index == 1

        reopened_approval = ApprovalRepository(db_path)
        reopened_execution = ExecutionRepository(db_path)
        reopened_audit = AuditRepository(db_path)

        loaded_decision = reopened_approval.get_decision_by_request(
            approval_request.request_id
        )
        assert loaded_decision is not None
        assert loaded_decision.approved is True
        assert loaded_decision == approval_decision

        loaded_execution = (
            reopened_execution.get_execution_result_by_idempotency_key(
                execution_request.idempotency_key
            )
        )
        assert loaded_execution is not None
        assert loaded_execution.request.request_id == "EXREQ-01"
        assert loaded_execution.execution_receipt is None
        assert loaded_execution.review_queue_receipt is not None
        assert loaded_execution.review_queue_receipt.receipt_id == "EXRCPT-01"

        loaded_block = reopened_audit.get_block("RUN-PERSIST-01", 1)
        assert loaded_block is not None
        assert loaded_block.audit_event.operation_id == (
            "commercial_purchase_request"
        )


def test_conflicting_execution_idempotency_rejected() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "persist_conflict.db"
        apply_governance_migrations(db_path)

        execution_repository = ExecutionRepository(db_path)
        first_request = ExecutionRequest.create(
            request_id="EXREQ-A",
            event_id="EVT-01",
            operation_id="commercial_purchase_request",
            recommended_action=EnforcementAction.HOLD_FOR_REVIEW,
            destination_id="SYNTHETIC-REVIEW-QUEUE",
            precondition_digest=sha256(b"precond"),
            recommendation_digest=sha256(b"recom"),
            approval_decision_id=None,
            idempotency_key="IDEM-SHARED",
            created_at="2026-06-01T10:00:00Z",
        )
        first_receipt = ReviewQueueReceipt(
            receipt_id="EXRCPT-A",
            request_id=first_request.request_id,
            event_id=first_request.event_id,
            queue_destination_id="SYNTHETIC-REVIEW-QUEUE",
            enqueued_at="2026-06-01T10:00:00Z",
            receipt_digest=sha256(b"rcpt-a"),
            reason_code="POLICY_HOLD",
            details={"queue": "SYNTHETIC-REVIEW-QUEUE"},
        )
        first_result = ExecutionResult(
            request=first_request,
            execution_receipt=None,
            review_queue_receipt=first_receipt,
            distribution_acknowledgment=None,
            duplicate=False,
        )
        execution_repository.execute_transaction(
            first_request,
            lambda _: first_result,
        )

        second_request = ExecutionRequest.create(
            request_id="EXREQ-B",
            event_id="EVT-02",
            operation_id="commercial_purchase_request",
            recommended_action=EnforcementAction.HOLD_FOR_REVIEW,
            destination_id="SYNTHETIC-REVIEW-QUEUE",
            precondition_digest=sha256(b"precond"),
            recommendation_digest=sha256(b"recom"),
            approval_decision_id=None,
            idempotency_key="IDEM-SHARED",
            created_at="2026-06-01T10:05:00Z",
        )
        second_receipt = ReviewQueueReceipt(
            receipt_id="EXRCPT-B",
            request_id=second_request.request_id,
            event_id=second_request.event_id,
            queue_destination_id="SYNTHETIC-REVIEW-QUEUE",
            enqueued_at="2026-06-01T10:05:00Z",
            receipt_digest=sha256(b"rcpt-b"),
            reason_code="POLICY_HOLD",
            details={"queue": "SYNTHETIC-REVIEW-QUEUE"},
        )
        second_result = ExecutionResult(
            request=second_request,
            execution_receipt=None,
            review_queue_receipt=second_receipt,
            distribution_acknowledgment=None,
            duplicate=False,
        )

        with pytest.raises(
            GovernanceConfigurationError,
            match="Conflicting execution request",
        ):
            execution_repository.execute_transaction(
                second_request,
                lambda _: second_result,
            )


def test_forced_result_factory_failure_rolls_back_all_tables() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "persist_rollback.db"
        apply_governance_migrations(db_path)

        execution_repository = ExecutionRepository(db_path)
        execution_request = ExecutionRequest.create(
            request_id="EXREQ-FORCED-FAIL-01",
            event_id="EVT-FAIL-01",
            operation_id="commercial_purchase_request",
            recommended_action=EnforcementAction.HOLD_FOR_REVIEW,
            destination_id="SYNTHETIC-REVIEW-QUEUE",
            precondition_digest=sha256(b"precond"),
            recommendation_digest=sha256(b"recom"),
            approval_decision_id=None,
            idempotency_key="IDEM-FORCED-FAIL-01",
            created_at="2026-06-01T10:00:00Z",
        )

        def failing_factory(_: ExecutionRequest) -> ExecutionResult:
            raise RuntimeError("Forced result_factory failure")

        with pytest.raises(
            RuntimeError,
            match="Forced result_factory failure",
        ):
            execution_repository.execute_transaction(
                execution_request,
                failing_factory,
            )

        def assert_zero_matching_rows(
            connection: sqlite3.Connection,
        ) -> None:
            assert connection.execute(
                "SELECT COUNT(*) FROM execution_requests "
                "WHERE request_id = ?",
                (execution_request.request_id,),
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM execution_idempotency "
                "WHERE request_id = ?",
                (execution_request.request_id,),
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM execution_receipts "
                "WHERE request_id = ?",
                (execution_request.request_id,),
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM review_queue_receipts "
                "WHERE request_id = ?",
                (execution_request.request_id,),
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM distribution_acknowledgments"
            ).fetchone()[0] == 0

        with execution_repository._conn() as connection:
            assert_zero_matching_rows(connection)

        reopened_execution = ExecutionRepository(db_path)
        with reopened_execution._conn() as connection:
            assert_zero_matching_rows(connection)
