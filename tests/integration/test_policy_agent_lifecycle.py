from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from amba_ai.governance.execution import (
    ExecutionStatus,
)
from amba_ai.application.health import HealthRegistry
from amba_ai.application.lifecycle import ApplicationLifecycle
from amba_ai.application.provider_installation import (
    install_application_providers,
)
from amba_ai.application.providers import ProviderRegistry
from amba_ai.application.settings import (
    ApplicationProfile,
    default_settings,
)
from amba_ai.governance.audit import AuditBlock
from amba_ai.governance.distribution import (
    DistributionDisposition,
)
from amba_ai.governance.models import (
    EnforcementAction,
    PipelineEvent,
)
from amba_ai.services.audit_service import AuditService
from amba_ai.services.distribution_service import (
    DistributionService,
    build_default_distribution_service,
)
from amba_ai.services.execution_service import ExecutionService
from amba_ai.services.governance_service import GovernanceService
from amba_ai.services.policy_agent_service import (
    PolicyAgentRequest,
    PolicyAgentResponse,
    PolicyAgentService,
)
from amba_ai.services.policy_kb_service import PolicyKBService
from amba_ai.standards.y3172_models import (
    PipelineNodeStatus,
    Y3172Node,
)
from amba_ai.standards.y3172_trace_coordinator import (
    Y3172TraceCoordinator,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

CONFIGURATION_ROOT = (
    PROJECT_ROOT
    / "config"
)

KNOWLEDGE_BASE_ROOT = (
    PROJECT_ROOT
    / "kb"
)

MIGRATIONS_ROOT = (
    PROJECT_ROOT
    / "src"
    / "amba_ai"
    / "db"
    / "migrations"
)

FIXED_TIME = "2026-11-04T12:00:00Z"


class RAGEngineStub:
    def __init__(
        self,
        results: list[Any] | None = None,
    ) -> None:
        self.results = (
            []
            if results is None
            else list(results)
        )
        self.calls: list[
            tuple[str, int, float]
        ] = []

    def search(
        self,
        query: str,
        top_k: int = 10,
        min_similarity: float = 0.40,
    ) -> list[Any]:
        self.calls.append(
            (
                query,
                top_k,
                min_similarity,
            )
        )

        return list(
            self.results[:top_k]
        )


def _providers(
    tmp_path: Path,
) -> ProviderRegistry:
    settings = default_settings(
        ApplicationProfile.TEST,
        project_root=tmp_path,
        overrides={
            "configuration_root": CONFIGURATION_ROOT,
            "knowledge_base_root": KNOWLEDGE_BASE_ROOT,
            "migrations_root": MIGRATIONS_ROOT,
            "verify_knowledge_base": False,
        },
    )

    providers = ProviderRegistry()

    providers.register_instance(
        "settings",
        settings,
    )

    providers.register_instance(
        "lifecycle",
        ApplicationLifecycle(),
    )

    providers.register_instance(
        "health_registry",
        HealthRegistry(),
    )

    install_application_providers(
        providers,
        settings,
    )

    providers.register_instance(
        "rag_engine",
        RAGEngineStub(),
        replace=True,
    )

    return providers


def _agent(
    providers: ProviderRegistry,
) -> PolicyAgentService:
    return PolicyAgentService(
        policy_kb_service=providers.get(
            "policy_kb_service",
            PolicyKBService,
        ),
        governance_service=providers.get(
            "governance_service",
            GovernanceService,
        ),
        execution_service=providers.get(
            "execution_service",
            ExecutionService,
        ),
        distribution_service=(
            build_default_distribution_service()
        ),
        trace_coordinator=providers.get(
            "y3172_trace_coordinator",
            Y3172TraceCoordinator,
        ),
        audit_service=providers.get(
            "audit_service",
            AuditService,
        ),
    )


def _event(
    *,
    event_id: str,
    operation_id: str,
    destination_id: str,
    payload: dict[str, Any],
) -> PipelineEvent:
    return PipelineEvent(
        event_id=event_id,
        timestamp=FIXED_TIME,
        operation_id=operation_id,
        source_node="SYNTHETIC-SCENARIO-SOURCE",
        destination_id=destination_id,
        payload_type="synthetic_event",
        payload=payload,
        authorization_basis=None,
        synthetic_flag=True,
    )


def _node(
    response: PolicyAgentResponse,
    node: Y3172Node,
):
    return next(
        node_trace
        for node_trace
        in response.y3172_trace.nodes
        if node_trace.node is node
    )


def test_policy_agent_unregistered_operation_fails_closed_without_approval(
    tmp_path: Path,
) -> None:
    providers = _providers(
        tmp_path
    )

    try:
        agent = _agent(
            providers
        )

        event = _event(
            event_id="EVENT-AGENT-REVIEW",
            operation_id=(
                "targeted_advertising_delivery"
            ),
            destination_id=(
                "SYNTHETIC-ADVERTISING-ENDPOINT"
            ),
            payload={
                "synthetic": True,
                "advertising": {
                    "targeted": True,
                    "learner_profile_used": True,
                },
            },
        )

        response = agent.run(
            PolicyAgentRequest(
                run_id="RUN-AGENT-REVIEW",
                scenario_id="SCENARIO-AGENT",
                stage_id="STAGE-4",
                event=event,
                policy_query=(
                    "targeted advertising learner "
                    "data safeguards"
                ),
                idempotency_key=(
                    "IDEMPOTENCY-AGENT-REVIEW"
                ),
                distribution_payload={
                    "event_id": event.event_id,
                    "synthetic": True,
                },
                approval_decision=None,
            )
        )

        assert isinstance(
            response,
            PolicyAgentResponse,
        )

        assert response.run_id == (
            "RUN-AGENT-REVIEW"
        )

        assert response.event_id == (
            "EVENT-AGENT-REVIEW"
        )

        recommendation = (
            response.governance_bundle
            .recommendation
        )

        assert (
            recommendation.recommended_action
            is EnforcementAction.HOLD_FOR_REVIEW
        )

        assert recommendation.requires_approval is True

        assert recommendation.escalation_role == (
            "compliance_officer"
        )

        assert (
            response.governance_bundle.operation
            is None
        )

        assert (
            "The operation configuration must be resolved."
            in response.governance_bundle
            .unresolved_questions
        )

        execution_result = (
            response.execution_result
        )

        assert (
            execution_result.execution_receipt
            is not None
        )

        assert (
            execution_result.execution_receipt.status
            is ExecutionStatus.NOT_ATTEMPTED
        )

        assert (
            execution_result
            .execution_receipt
            .action_executed
            is EnforcementAction.HOLD_FOR_REVIEW
        )

        assert (
            execution_result.review_queue_receipt
            is None
        )

        assert (
            execution_result
            .distribution_acknowledgment
            is None
        )

        assert response.distribution_effect is None

        assert (
            _node(
                response,
                Y3172Node.P,
            ).status
            is PipelineNodeStatus.COMPLETED
        )

        assert (
            _node(
                response,
                Y3172Node.D,
            ).status
            is PipelineNodeStatus.FAILED_CLOSED
        )

        assert (
            _node(
                response,
                Y3172Node.SINK,
            ).status
            is PipelineNodeStatus.NOT_REACHED
        )

        assert (
            response.y3172_trace
            .execution_receipt_id
            == (
                execution_result
                .execution_receipt
                .receipt_id
            )
        )

        assert (
            response.y3172_trace
            .review_queue_receipt_id
            is None
        )

        assert (
            response.y3172_trace
            .distribution_acknowledgment_id
            is None
        )

        assert isinstance(
            response.audit_block,
            AuditBlock,
        )

        assert response.audit_block.run_id == (
            "RUN-AGENT-REVIEW"
        )

        audit_event = (
            response.audit_block.audit_event
        )

        assert audit_event.run_id == (
            "RUN-AGENT-REVIEW"
        )

        assert audit_event.scenario_id == (
            "SCENARIO-AGENT"
        )

        assert audit_event.stage_id == (
            "STAGE-4"
        )

        assert audit_event.event_id == (
            event.event_id
        )

        assert audit_event.operation_id == (
            event.operation_id
        )

        assert audit_event.event_type == (
            "POLICY_AGENT_COMPLETED"
        )

        assert audit_event.payload[
            "recommended_action"
        ] == (
            EnforcementAction
            .HOLD_FOR_REVIEW
            .value
        )

        assert audit_event.payload[
            "execution_request_id"
        ] == (
            execution_result
            .request
            .request_id
        )

        assert audit_event.payload[
            "distribution_disposition"
        ] is None

        assert audit_event.payload[
            "trace_id"
        ] == response.y3172_trace.trace_id

        assert response.audit_block.block_index >= 1

        assert (
            "distribution_and_audit_not_transactionally_atomic"
            in response.limitations
        )

        assert (
            response.kb_response.metadata[
                "governance_decision_created"
            ]
            is False
        )

        rag_engine = providers.get(
            "rag_engine"
        )

        assert rag_engine.calls == [
            (
                "targeted advertising learner "
                "data safeguards",
                10,
                0.40,
            )
        ]

    finally:
        providers.close()

def test_policy_agent_uses_composed_singletons(
    tmp_path: Path,
) -> None:
    providers = _providers(
        tmp_path
    )

    try:
        agent = _agent(
            providers
        )

        policy_kb_service = providers.get(
            "policy_kb_service",
            PolicyKBService,
        )

        governance_service = providers.get(
            "governance_service",
            GovernanceService,
        )

        execution_service = providers.get(
            "execution_service",
            ExecutionService,
        )

        trace_coordinator = providers.get(
            "y3172_trace_coordinator",
            Y3172TraceCoordinator,
        )

        audit_service = providers.get(
            "audit_service",
            AuditService,
        )

        assert (
            agent._policy_kb_service
            is policy_kb_service
        )

        assert (
            agent._governance_service
            is governance_service
        )

        assert (
            agent._execution_service
            is execution_service
        )

        assert (
            agent._trace_coordinator
            is trace_coordinator
        )

        assert (
            agent._audit_service
            is audit_service
        )

        assert isinstance(
            agent._distribution_service,
            DistributionService,
        )

    finally:
        providers.close()


def test_policy_agent_kb_failure_stops_lifecycle(
    tmp_path: Path,
) -> None:
    providers = _providers(
        tmp_path
    )

    class FailingRAGEngine:
        def search(
            self,
            query: str,
            top_k: int = 10,
            min_similarity: float = 0.40,
        ) -> list[Any]:
            raise RuntimeError(
                "synthetic search failure"
            )

    try:
        providers.register_instance(
            "rag_engine",
            FailingRAGEngine(),
            replace=True,
        )

        agent = _agent(
            providers
        )

        event = _event(
            event_id="EVENT-KB-FAILURE",
            operation_id=(
                "targeted_advertising_delivery"
            ),
            destination_id=(
                "SYNTHETIC-ADVERTISING-ENDPOINT"
            ),
            payload={
                "synthetic": True,
            },
        )

        with pytest.raises(
            Exception,
            match=(
                "policy knowledge-base search failed"
            ),
        ):
            agent.run(
                PolicyAgentRequest(
                    run_id="RUN-KB-FAILURE",
                    scenario_id="SCENARIO-AGENT",
                    stage_id="STAGE-4",
                    event=event,
                    policy_query=(
                        "targeted advertising"
                    ),
                    idempotency_key=(
                        "IDEMPOTENCY-KB-FAILURE"
                    ),
                    distribution_payload={
                        "synthetic": True,
                    },
                )
            )

        execution_repository = providers.get(
            "execution_repository"
        )

        assert (
            execution_repository
            .get_execution_result_by_idempotency_key(
                "IDEMPOTENCY-KB-FAILURE"
            )
            is None
        )

    finally:
        providers.close()
