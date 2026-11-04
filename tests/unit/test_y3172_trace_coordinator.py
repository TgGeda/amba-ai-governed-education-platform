from __future__ import annotations

import hashlib
from pathlib import Path
from dataclasses import replace

import pytest

from amba_ai.governance.distribution import (
    DistributionDisposition,
    DistributionEffect,
)
from amba_ai.governance.execution import (
    DistributionAcknowledgment,
    ExecutionReceipt,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ReviewQueueReceipt,
)
from amba_ai.governance.models import (
    EnforcementAction,
    PipelineEvent,
    PolicyEvaluationBundle,
    PolicyRecommendation,
    SequentialIdentifierProvider,
)
from amba_ai.governance.principals import (
    FixedClock,
)
from amba_ai.standards.y3172_models import (
    PipelineNodeStatus,
    Y3172Node,
    Y3172TraceError,
)
from amba_ai.standards.y3172_registry import (
    Y3172Registry,
)
from amba_ai.standards.y3172_trace_coordinator import (
    Y3172TraceArtifacts,
    Y3172TraceCoordinator,
)


FIXED_TIME = "2026-11-04T06:00:00Z"
OPERATION_ID = "commercial_purchase_request"
EVENT_ID = "EVENT-001"
DESTINATION_ID = "SYNTHETIC-PURCHASE-GATEWAY"


@pytest.fixture
def registry() -> Y3172Registry:
    return Y3172Registry.load_from_yaml(
        Path("kb/mappings/y3172_mapping.yaml"),
        allowed_root=Path.cwd(),
    )


@pytest.fixture
def coordinator(
    registry: Y3172Registry,
) -> Y3172TraceCoordinator:
    return Y3172TraceCoordinator(
        registry=registry,
        identifier_provider=(
            SequentialIdentifierProvider()
        ),
        clock=FixedClock(FIXED_TIME),
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def _event(
    *,
    event_id: str = EVENT_ID,
    operation_id: str = OPERATION_ID,
    destination_id: str = DESTINATION_ID,
) -> PipelineEvent:
    return PipelineEvent(
        event_id=event_id,
        timestamp=FIXED_TIME,
        operation_id=operation_id,
        source_node="SYNTHETIC-SOURCE",
        destination_id=destination_id,
        payload_type="synthetic_event",
        payload={
            "synthetic": True,
        },
    )


def _bundle(
    event: PipelineEvent,
    *,
    action: EnforcementAction,
) -> PolicyEvaluationBundle:
    recommendation = PolicyRecommendation(
        recommendation_id="RECOMMENDATION-001",
        event_id=event.event_id,
        recommended_action=action,
        mitigation_steps=(),
        requires_approval=False,
        escalation_role=None,
    )

    return PolicyEvaluationBundle(
        event_id=event.event_id,
        operation=None,
        findings=(),
        recommendation=recommendation,
        unresolved_questions=(),
    )


def _request(
    event: PipelineEvent,
    *,
    action: EnforcementAction,
) -> ExecutionRequest:
    return ExecutionRequest.create(
        request_id="EXECUTION-REQUEST-001",
        event_id=event.event_id,
        operation_id=event.operation_id,
        recommended_action=action,
        destination_id=event.destination_id,
        precondition_digest=_sha256(
            "precondition"
        ),
        recommendation_digest=_sha256(
            "recommendation"
        ),
        approval_decision_id=None,
        idempotency_key="IDEMPOTENCY-001",
        created_at=FIXED_TIME,
    )


def _execution_receipt(
    request: ExecutionRequest,
    *,
    action: EnforcementAction,
    status: ExecutionStatus = (
        ExecutionStatus.SUCCEEDED
    ),
) -> ExecutionReceipt:
    return ExecutionReceipt(
        receipt_id="EXECUTION-RECEIPT-001",
        request_id=request.request_id,
        event_id=request.event_id,
        operation_id=request.operation_id,
        action_executed=action,
        status=status,
        executor_id="EXECUTOR-001",
        execution_effect="Execution recorded",
        executed_at=FIXED_TIME,
        receipt_digest=_sha256(
            "execution-receipt"
        ),
        details={
            "synthetic": True,
        },
        synthetic=True,
        legal_effect=False,
    )


def _acknowledgment(
    request: ExecutionRequest,
    receipt: ExecutionReceipt,
) -> DistributionAcknowledgment:
    return DistributionAcknowledgment(
        acknowledgment_id="ACKNOWLEDGMENT-001",
        execution_receipt_id=receipt.receipt_id,
        destination_id=request.destination_id,
        disposition="DELIVERED",
        acknowledged_at=FIXED_TIME,
        acknowledgment_digest=_sha256(
            "acknowledgment"
        ),
    )


def _review_receipt(
    request: ExecutionRequest,
) -> ReviewQueueReceipt:
    return ReviewQueueReceipt(
        receipt_id="REVIEW-RECEIPT-001",
        request_id=request.request_id,
        event_id=request.event_id,
        queue_destination_id=(
            "SYNTHETIC-REVIEW-QUEUE"
        ),
        enqueued_at=FIXED_TIME,
        receipt_digest=_sha256(
            "review-receipt"
        ),
        reason_code="POLICY_HOLD",
        details={
            "synthetic": True,
        },
    )


def _delivery_result(
    event: PipelineEvent,
) -> ExecutionResult:
    request = _request(
        event,
        action=EnforcementAction.PROCEED,
    )
    receipt = _execution_receipt(
        request,
        action=EnforcementAction.PROCEED,
    )

    return ExecutionResult(
        request=request,
        execution_receipt=receipt,
        review_queue_receipt=None,
        distribution_acknowledgment=(
            _acknowledgment(
                request,
                receipt,
            )
        ),
        duplicate=False,
    )


def _block_result(
    event: PipelineEvent,
) -> ExecutionResult:
    request = _request(
        event,
        action=EnforcementAction.BLOCK,
    )

    return ExecutionResult(
        request=request,
        execution_receipt=_execution_receipt(
            request,
            action=EnforcementAction.BLOCK,
        ),
        review_queue_receipt=None,
        distribution_acknowledgment=None,
        duplicate=False,
    )


def _review_result(
    event: PipelineEvent,
) -> ExecutionResult:
    request = _request(
        event,
        action=(
            EnforcementAction.HOLD_FOR_REVIEW
        ),
    )

    return ExecutionResult(
        request=request,
        execution_receipt=None,
        review_queue_receipt=(
            _review_receipt(request)
        ),
        distribution_acknowledgment=None,
        duplicate=False,
    )


def _effect(
    *,
    destination_id: str,
    disposition: DistributionDisposition,
) -> DistributionEffect:
    return DistributionEffect(
        executor_id="DISTRIBUTION-EXECUTOR-001",
        destination_id=destination_id,
        disposition=disposition,
        effect_code=(
            f"EFFECT-{disposition.value.upper()}"
        ),
        details={
            "synthetic": True,
            "legal_effect": False,
        },
    )


def _node(
    trace,
    node: Y3172Node,
):
    return next(
        item
        for item in trace.nodes
        if item.node is node
    )


def test_constructor_requires_registry() -> None:
    with pytest.raises(
        TypeError,
        match="registry",
    ):
        Y3172TraceCoordinator(
            registry=object(),
            identifier_provider=(
                SequentialIdentifierProvider()
            ),
            clock=FixedClock(FIXED_TIME),
        )


def test_constructor_requires_identifier_provider(
    registry: Y3172Registry,
) -> None:
    with pytest.raises(
        TypeError,
        match="identifier_provider",
    ):
        Y3172TraceCoordinator(
            registry=registry,
            identifier_provider=None,
            clock=FixedClock(FIXED_TIME),
        )


def test_constructor_requires_clock(
    registry: Y3172Registry,
) -> None:
    with pytest.raises(
        TypeError,
        match="clock",
    ):
        Y3172TraceCoordinator(
            registry=registry,
            identifier_provider=(
                SequentialIdentifierProvider()
            ),
            clock=object(),
        )


def test_artifacts_reject_duplicates() -> None:
    with pytest.raises(
        Exception,
        match="duplicates",
    ):
        Y3172TraceArtifacts(
            model_artifact_ids=(
                "MODEL-001",
                "MODEL-001",
            ),
        )

def test_duplicate_flag_is_preserved_in_distributor_trace(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event()
    bundle = _bundle(
        event,
        action=EnforcementAction.BLOCK,
    )

    original_result = _block_result(event)

    duplicate_result = replace(
        original_result,
        duplicate=True,
    )

    trace = coordinator.build_trace(
        run_id="RUN-DUPLICATE",
        event=event,
        bundle=bundle,
        execution_result=duplicate_result,
        distribution_effect=_effect(
            destination_id=event.destination_id,
            disposition=(
                DistributionDisposition.PREVENTED
            ),
        ),
    )

    distributor = _node(
        trace,
        Y3172Node.D,
    )

    assert (
        distributor.status
        is PipelineNodeStatus.PREVENTED
    )

    assert (
        distributor.details[
            "duplicate_execution"
        ]
        is True
    )

    assert (
        trace.distribution_acknowledgment_id
        is None
    )

def test_delivered_trace(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event()
    bundle = _bundle(
        event,
        action=EnforcementAction.PROCEED,
    )
    result = _delivery_result(event)

    trace = coordinator.build_trace(
        run_id="RUN-001",
        event=event,
        bundle=bundle,
        execution_result=result,
        distribution_effect=_effect(
            destination_id=event.destination_id,
            disposition=(
                DistributionDisposition.DELIVERED
            ),
        ),
        artifacts=Y3172TraceArtifacts(
            collection_artifact_ids=(
                "COLLECTION-001",
            ),
            preprocessing_artifact_ids=(
                "PREPROCESSING-001",
            ),
            model_artifact_ids=(
                "MODEL-001",
            ),
            model_evidence_ids=(
                "EVIDENCE-001",
            ),
        ),
    )

    assert (
        _node(
            trace,
            Y3172Node.P,
        ).status
        is PipelineNodeStatus.COMPLETED
    )
    assert (
        _node(
            trace,
            Y3172Node.D,
        ).status
        is PipelineNodeStatus.COMPLETED
    )
    assert (
        _node(
            trace,
            Y3172Node.SINK,
        ).status
        is PipelineNodeStatus.COMPLETED
    )
    assert trace.execution_receipt_id == (
        "EXECUTION-RECEIPT-001"
    )
    assert (
        trace.distribution_acknowledgment_id
        == "ACKNOWLEDGMENT-001"
    )
    assert trace.review_queue_receipt_id is None


def test_held_trace(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event(
        destination_id="SYNTHETIC-LEARNER-UI"
    )
    bundle = _bundle(
        event,
        action=(
            EnforcementAction.HOLD_FOR_REVIEW
        ),
    )
    result = _review_result(event)

    trace = coordinator.build_trace(
        run_id="RUN-HOLD",
        event=event,
        bundle=bundle,
        execution_result=result,
        distribution_effect=_effect(
            destination_id="SYNTHETIC-REVIEW-QUEUE",
            disposition=(
                DistributionDisposition
                .QUEUED_FOR_REVIEW
            ),
        ),
    )

    assert (
        _node(
            trace,
            Y3172Node.D,
        ).status
        is PipelineNodeStatus.HELD
    )
    assert (
        _node(
            trace,
            Y3172Node.SINK,
        ).status
        is PipelineNodeStatus.NOT_REACHED
    )
    assert trace.review_queue_receipt_id == (
        "REVIEW-RECEIPT-001"
    )
    assert trace.execution_receipt_id is None
    assert (
        trace.distribution_acknowledgment_id
        is None
    )


def test_prevented_trace(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event()
    bundle = _bundle(
        event,
        action=EnforcementAction.BLOCK,
    )
    result = _block_result(event)

    trace = coordinator.build_trace(
        run_id="RUN-BLOCK",
        event=event,
        bundle=bundle,
        execution_result=result,
        distribution_effect=_effect(
            destination_id=event.destination_id,
            disposition=(
                DistributionDisposition.PREVENTED
            ),
        ),
    )

    assert (
        _node(
            trace,
            Y3172Node.D,
        ).status
        is PipelineNodeStatus.PREVENTED
    )
    assert (
        _node(
            trace,
            Y3172Node.SINK,
        ).status
        is PipelineNodeStatus.NOT_REACHED
    )
    assert trace.execution_receipt_id == (
        "EXECUTION-RECEIPT-001"
    )
    assert (
        trace.distribution_acknowledgment_id
        is None
    )


def test_pre_gate_stop(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event()
    bundle = _bundle(
        event,
        action=EnforcementAction.BLOCK,
    )

    trace = coordinator.build_trace(
        run_id="RUN-PRE-GATE",
        event=event,
        bundle=bundle,
        execution_result=None,
        distribution_effect=None,
        pre_gate_stopped=True,
    )

    assert (
        _node(
            trace,
            Y3172Node.M,
        ).status
        is PipelineNodeStatus.NOT_REACHED
    )
    assert (
        _node(
            trace,
            Y3172Node.P,
        ).status
        is PipelineNodeStatus.COMPLETED
    )
    assert (
        _node(
            trace,
            Y3172Node.D,
        ).status
        is PipelineNodeStatus.NOT_REACHED
    )
    assert (
        _node(
            trace,
            Y3172Node.SINK,
        ).status
        is PipelineNodeStatus.NOT_REACHED
    )


def test_failed_closed_trace(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event()
    bundle = _bundle(
        event,
        action=(
            EnforcementAction.HOLD_FOR_REVIEW
        ),
    )

    trace = coordinator.build_trace(
        run_id="RUN-FAILED",
        event=event,
        bundle=bundle,
        execution_result=None,
        distribution_effect=None,
        failed_closed=True,
    )

    assert (
        _node(
            trace,
            Y3172Node.D,
        ).status
        is PipelineNodeStatus.FAILED_CLOSED
    )
    assert (
        _node(
            trace,
            Y3172Node.SINK,
        ).status
        is PipelineNodeStatus.NOT_REACHED
    )
    assert (
        trace.distribution_acknowledgment_id
        is None
    )


def test_bundle_event_must_match(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event(
        event_id="EVENT-A"
    )
    other = _event(
        event_id="EVENT-B"
    )
    bundle = _bundle(
        other,
        action=EnforcementAction.BLOCK,
    )

    with pytest.raises(
        Y3172TraceError,
        match="bundle event identifier",
    ):
        coordinator.build_trace(
            run_id="RUN-MISMATCH",
            event=event,
            bundle=bundle,
            execution_result=None,
            distribution_effect=None,
            pre_gate_stopped=True,
        )


def test_execution_request_must_match_event(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event(
        event_id="EVENT-A"
    )
    bundle = _bundle(
        event,
        action=EnforcementAction.BLOCK,
    )
    other_event = _event(
        event_id="EVENT-B"
    )
    result = _block_result(other_event)

    with pytest.raises(
        Y3172TraceError,
        match="execution request event identifier",
    ):
        coordinator.build_trace(
            run_id="RUN-MISMATCH",
            event=event,
            bundle=bundle,
            execution_result=result,
            distribution_effect=None,
        )


def test_execution_action_must_match_recommendation(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event()
    bundle = _bundle(
        event,
        action=EnforcementAction.BLOCK,
    )
    result = _delivery_result(event)

    with pytest.raises(
        Y3172TraceError,
        match="action does not match",
    ):
        coordinator.build_trace(
            run_id="RUN-MISMATCH",
            event=event,
            bundle=bundle,
            execution_result=result,
            distribution_effect=None,
        )


def test_delivery_effect_must_match(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event()
    bundle = _bundle(
        event,
        action=EnforcementAction.PROCEED,
    )

    with pytest.raises(
        Y3172TraceError,
        match="DELIVERED distribution effect",
    ):
        coordinator.build_trace(
            run_id="RUN-BAD-EFFECT",
            event=event,
            bundle=bundle,
            execution_result=(
                _delivery_result(event)
            ),
            distribution_effect=_effect(
                destination_id=event.destination_id,
                disposition=(
                    DistributionDisposition.PREVENTED
                ),
            ),
        )


def test_prevention_effect_must_match(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event()
    bundle = _bundle(
        event,
        action=EnforcementAction.BLOCK,
    )

    with pytest.raises(
        Y3172TraceError,
        match="PREVENTED distribution effect",
    ):
        coordinator.build_trace(
            run_id="RUN-BAD-EFFECT",
            event=event,
            bundle=bundle,
            execution_result=_block_result(event),
            distribution_effect=_effect(
                destination_id=event.destination_id,
                disposition=(
                    DistributionDisposition.DELIVERED
                ),
            ),
        )


def test_effect_destination_must_match(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event()
    bundle = _bundle(
        event,
        action=EnforcementAction.BLOCK,
    )

    with pytest.raises(
        Y3172TraceError,
        match="effect destination",
    ):
        coordinator.build_trace(
            run_id="RUN-BAD-DESTINATION",
            event=event,
            bundle=bundle,
            execution_result=_block_result(event),
            distribution_effect=_effect(
                destination_id="OTHER-DESTINATION",
                disposition=(
                    DistributionDisposition.PREVENTED
                ),
            ),
        )


def test_pre_gate_stop_rejects_execution_result(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event()
    bundle = _bundle(
        event,
        action=EnforcementAction.BLOCK,
    )

    with pytest.raises(
        Y3172TraceError,
        match="cannot contain an execution result",
    ):
        coordinator.build_trace(
            run_id="RUN-INVALID",
            event=event,
            bundle=bundle,
            execution_result=_block_result(event),
            distribution_effect=None,
            pre_gate_stopped=True,
        )


def test_pre_gate_stop_rejects_proceed(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event()
    bundle = _bundle(
        event,
        action=EnforcementAction.PROCEED,
    )

    with pytest.raises(
        Y3172TraceError,
        match="non-proceed recommendation",
    ):
        coordinator.build_trace(
            run_id="RUN-INVALID",
            event=event,
            bundle=bundle,
            execution_result=None,
            distribution_effect=None,
            pre_gate_stopped=True,
        )


def test_coordinator_generates_deterministic_trace_id(
    registry: Y3172Registry,
) -> None:
    coordinator = Y3172TraceCoordinator(
        registry=registry,
        identifier_provider=(
            SequentialIdentifierProvider()
        ),
        clock=FixedClock(FIXED_TIME),
    )
    event = _event()
    bundle = _bundle(
        event,
        action=EnforcementAction.BLOCK,
    )

    first = coordinator.build_trace(
        run_id="RUN-001",
        event=event,
        bundle=bundle,
        execution_result=None,
        distribution_effect=None,
        pre_gate_stopped=True,
    )
    second = coordinator.build_trace(
        run_id="RUN-002",
        event=event,
        bundle=bundle,
        execution_result=None,
        distribution_effect=None,
        pre_gate_stopped=True,
    )

    assert first.trace_id == (
        "y3172trace_000001"
    )
    assert second.trace_id == (
        "y3172trace_000002"
    )


def test_trace_preserves_claim_boundary(
    coordinator: Y3172TraceCoordinator,
) -> None:
    event = _event()
    bundle = _bundle(
        event,
        action=EnforcementAction.BLOCK,
    )

    trace = coordinator.build_trace(
        run_id="RUN-CLAIMS",
        event=event,
        bundle=bundle,
        execution_result=None,
        distribution_effect=None,
        pre_gate_stopped=True,
    )

    assert trace.formal_conformance_claimed is False
    assert trace.certification_claimed is False
    assert trace.to_canonical_json()
