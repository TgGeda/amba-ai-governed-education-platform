from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import pytest


from amba_ai.db.approval_repository import (
    ApprovalRepository,
)
from amba_ai.db.execution_repository import (
    ExecutionRepository,
)
from amba_ai.db.governance_repository import (
    GovernanceRepository,
)
from amba_ai.governance.distribution import (
    DistributionBlockExecutor,
    DistributionPermitExecutor,
    ReviewQueueExecutor,
)
from amba_ai.governance.execution import (
    ExecutionGateway,
)

from amba_ai.governance.models import (
    EnforcementAction,
    GovernanceConfigurationError,
    PipelineEvent,
    PolicyEvaluationBundle,
    PolicyRecommendation,
    SequentialIdentifierProvider,
)
from amba_ai.governance.operation_registry import (
    DestinationRegistry,
)
from amba_ai.governance.principals import (
    FixedClock,
)
from amba_ai.services.execution_service import (
    ExecutionService,
)
from amba_ai.standards.y3172_models import (
    PipelineNodeStatus,
    Y3172Node,
)
from amba_ai.standards.y3172_registry import (
    Y3172Registry,
)
from amba_ai.standards.y3172_trace_coordinator import (
    Y3172TraceArtifacts,
    Y3172TraceCoordinator,
)


FIXED_TIME = "2026-11-04T06:00:00Z"
MIGRATION_002 = Path(
    "src/amba_ai/db/migrations/"
    "002_governance_records.sql"
)
MIGRATION_003 = Path(
    "src/amba_ai/db/migrations/"
    "003_approval_execution_audit.sql"
)
DESTINATIONS = Path(
    "config/destinations.yaml"
)
Y3172_MAPPING = Path(
    "kb/mappings/y3172_mapping.yaml"
)


def _event(
    *,
    event_id: str,
    operation_id: str,
    destination_id: str,
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
    action: EnforcementAction,
) -> PolicyEvaluationBundle:
    return PolicyEvaluationBundle(
        event_id=event.event_id,
        operation=None,
        findings=(),
        recommendation=PolicyRecommendation(
            recommendation_id=(
                f"RECOMMENDATION-{event.event_id}"
            ),
            event_id=event.event_id,
            recommended_action=action,
            mitigation_steps=(),
            requires_approval=False,
            escalation_role=None,
        ),
        unresolved_questions=(),
    )


def _node(trace, node: Y3172Node):
    return next(
        item
        for item in trace.nodes
        if item.node is node
    )


def _services(
    temp_directory: str,
):
    db_path = (
        Path(temp_directory)
        / "y3172_governance.db"
    )

    governance_repository = (
        GovernanceRepository(db_path)
    )
    governance_repository.apply_migration_file(
        MIGRATION_002
    )
    governance_repository.apply_migration_file(
        MIGRATION_003
    )

    destination_registry = (
        DestinationRegistry.load_from_yaml(
            DESTINATIONS
        )
    )

    execution_repository = (
        ExecutionRepository(db_path)
    )
    approval_repository = (
        ApprovalRepository(db_path)
    )

    execution_identifiers = (
        SequentialIdentifierProvider()
    )

    gateway = ExecutionGateway(
        execution_repository=execution_repository,
        destination_registry=destination_registry,
        approval_query=approval_repository,
        identifier_provider=execution_identifiers,
        clock=FixedClock(FIXED_TIME),
    )

    execution_service = ExecutionService(
        gateway
    )

    coordinator = Y3172TraceCoordinator(
        registry=Y3172Registry.load_from_yaml(
            Y3172_MAPPING,
            allowed_root=Path.cwd(),
        ),
        identifier_provider=(
            SequentialIdentifierProvider()
        ),
        clock=FixedClock(FIXED_TIME),
    )

    return (
        execution_service,
        coordinator,
    )


def test_delivered_execution_produces_completed_sink() -> None:
    with tempfile.TemporaryDirectory() as temp_directory:
        execution_service, coordinator = _services(
            temp_directory
        )

        event = _event(
            event_id="EVENT-DELIVERED",
            operation_id=(
                "classroom_instruction_delivery"
            ),
            destination_id=(
                "SYNTHETIC-TEACHER-UI"
            ),
        )
        bundle = _bundle(
            event,
            EnforcementAction.PROCEED,
        )

        result = execution_service.execute(
            event=event,
            recommendation=bundle.recommendation,
            approval_decision=None,
            idempotency_key=(
                "IDEMPOTENCY-DELIVERED"
            ),
            execution_details={
                "synthetic": True,
            },
        )

        effect = (
            DistributionPermitExecutor()
            .execute(
                event.destination_id,
                {
                    "request_id": (
                        result.request.request_id
                    ),
                },
            )
        )

        trace = coordinator.build_trace(
            run_id="RUN-DELIVERED",
            event=event,
            bundle=bundle,
            execution_result=result,
            distribution_effect=effect,
            artifacts=Y3172TraceArtifacts(
                collection_artifact_ids=(
                    "COLLECTION-DELIVERED",
                ),
                preprocessing_artifact_ids=(
                    "PREPROCESSING-DELIVERED",
                ),
                model_artifact_ids=(
                    "MODEL-DELIVERED",
                ),
                model_evidence_ids=(
                    "EVIDENCE-DELIVERED",
                ),
            ),
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
        assert trace.execution_receipt_id is not None
        assert (
            trace.distribution_acknowledgment_id
            is not None
        )
        assert trace.review_queue_receipt_id is None


def test_held_execution_does_not_reach_learner_sink() -> None:
    with tempfile.TemporaryDirectory() as temp_directory:
        execution_service, coordinator = _services(
            temp_directory
        )

        event = _event(
            event_id="EVENT-HELD",
            operation_id=(
                "commercial_purchase_request"
            ),
            destination_id=(
                "SYNTHETIC-PURCHASE-GATEWAY"
            ),
        )
        bundle = _bundle(
            event,
            EnforcementAction.HOLD_FOR_REVIEW,
        )

        result = execution_service.execute(
            event=event,
            recommendation=bundle.recommendation,
            approval_decision=None,
            idempotency_key="IDEMPOTENCY-HELD",
        )

        effect = ReviewQueueExecutor().execute(
            "SYNTHETIC-REVIEW-QUEUE",
            {
                "request_id": (
                    result.request.request_id
                ),
            },
        )

        trace = coordinator.build_trace(
            run_id="RUN-HELD",
            event=event,
            bundle=bundle,
            execution_result=result,
            distribution_effect=effect,
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
        assert trace.review_queue_receipt_id is not None
        assert trace.execution_receipt_id is None
        assert (
            trace.distribution_acknowledgment_id
            is None
        )


def test_blocked_execution_prevents_destination() -> None:
    with tempfile.TemporaryDirectory() as temp_directory:
        execution_service, coordinator = _services(
            temp_directory
        )

        event = _event(
            event_id="EVENT-BLOCKED",
            operation_id=(
                "targeted_advertising_delivery"
            ),
            destination_id=(
                "SYNTHETIC-ADVERTISING-ENDPOINT"
            ),
        )
        bundle = _bundle(
            event,
            EnforcementAction.BLOCK,
        )

        result = execution_service.execute(
            event=event,
            recommendation=bundle.recommendation,
            approval_decision=None,
            idempotency_key=(
                "IDEMPOTENCY-BLOCKED"
            ),
        )

        effect = (
            DistributionBlockExecutor()
            .execute(
                event.destination_id,
                {
                    "request_id": (
                        result.request.request_id
                    ),
                },
            )
        )

        trace = coordinator.build_trace(
            run_id="RUN-BLOCKED",
            event=event,
            bundle=bundle,
            execution_result=result,
            distribution_effect=effect,
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
        assert trace.execution_receipt_id is not None
        assert (
            trace.distribution_acknowledgment_id
            is None
        )


def test_conflicting_idempotency_reuse_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temp_directory:
        execution_service, _ = _services(
            temp_directory
        )

        event = _event(
            event_id="EVENT-IDEMPOTENCY-CONFLICT",
            operation_id=(
                "commercial_purchase_request"
            ),
            destination_id=(
                "SYNTHETIC-PURCHASE-GATEWAY"
            ),
        )
        bundle = _bundle(
            event,
            EnforcementAction.BLOCK,
        )

        execution_service.execute(
            event=event,
            recommendation=bundle.recommendation,
            approval_decision=None,
            idempotency_key=(
                "IDEMPOTENCY-CONFLICT"
            ),
        )

        with pytest.raises(
            GovernanceConfigurationError,
            match=(
                "idempotency key is associated "
                "with a different request identifier"
            ),
        ):
            execution_service.execute(
                event=event,
                recommendation=bundle.recommendation,
                approval_decision=None,
                idempotency_key=(
                    "IDEMPOTENCY-CONFLICT"
                ),
            )


def test_pre_gate_stop_never_executes_or_reaches_sink() -> None:
    with tempfile.TemporaryDirectory() as temp_directory:
        _, coordinator = _services(
            temp_directory
        )

        event = _event(
            event_id="EVENT-PRE-GATE",
            operation_id=(
                "targeted_advertising_delivery"
            ),
            destination_id=(
                "SYNTHETIC-ADVERTISING-ENDPOINT"
            ),
        )
        bundle = _bundle(
            event,
            EnforcementAction.BLOCK,
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
        assert trace.execution_receipt_id is None
        assert (
            trace.distribution_acknowledgment_id
            is None
        )
        assert trace.review_queue_receipt_id is None
