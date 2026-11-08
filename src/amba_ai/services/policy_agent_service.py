from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
import math

from amba_ai.governance.approvals import ApprovalDecision
from amba_ai.governance.audit import AuditBlock
from amba_ai.governance.distribution import DistributionEffect
from amba_ai.governance.execution import ExecutionResult
from amba_ai.governance.models import (
    GovernanceConfigurationError,
    PipelineEvent,
    PolicyEvaluationBundle,
    deep_freeze,
    to_canonical_json,
)
from amba_ai.services.audit_service import AuditService
from amba_ai.services.distribution_service import DistributionService
from amba_ai.services.execution_service import ExecutionService
from amba_ai.services.governance_service import GovernanceService
from amba_ai.services.policy_kb_service import PolicyKBQueryResponse, PolicyKBService
from amba_ai.services.thematic_evidence_service import ThematicEvidenceRunContext, ThematicEvidenceService
from amba_ai.standards.y3172_models import Y3172PipelineTrace
from amba_ai.standards.y3172_trace_coordinator import (
    Y3172TraceArtifacts,
    Y3172TraceCoordinator,
)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


@dataclass(frozen=True, slots=True)
class PolicyAgentRequest:
    run_id: str
    scenario_id: str
    stage_id: str
    event: PipelineEvent
    policy_query: str
    idempotency_key: str
    distribution_payload: Mapping[str, Any]
    approval_decision: ApprovalDecision | None = None
    query_limit: int = 10
    min_similarity: float = 0.40

    def __post_init__(self) -> None:
        for name in ("run_id", "scenario_id", "stage_id", "policy_query", "idempotency_key"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.event, PipelineEvent):
            raise TypeError("event must be a PipelineEvent")
        if self.approval_decision is not None and not isinstance(
            self.approval_decision, ApprovalDecision
        ):
            raise TypeError("approval_decision must be an ApprovalDecision or None")
        if isinstance(self.query_limit, bool) or not isinstance(self.query_limit, int):
            raise TypeError("query_limit must be an integer")
        if self.query_limit < 1 or self.query_limit > 100:
            raise ValueError("query_limit must be between 1 and 100")
        if isinstance(self.min_similarity, bool) or not isinstance(
            self.min_similarity, (int, float)
        ):
            raise TypeError("min_similarity must be numeric")
        similarity = float(self.min_similarity)
        if not math.isfinite(similarity) or not 0.0 <= similarity <= 1.0:
            raise ValueError("min_similarity must be finite and between 0 and 1")
        object.__setattr__(self, "min_similarity", similarity)
        if not isinstance(self.distribution_payload, Mapping):
            raise TypeError("distribution_payload must be a mapping")
        object.__setattr__(
            self,
            "distribution_payload",
            deep_freeze(dict(self.distribution_payload)),
        )


@dataclass(frozen=True, slots=True)
class PolicyAgentResponse:
    run_id: str
    event_id: str
    kb_response: PolicyKBQueryResponse
    governance_bundle: PolicyEvaluationBundle
    execution_result: ExecutionResult
    distribution_effect: DistributionEffect | None
    y3172_trace: Y3172PipelineTrace
    audit_block: AuditBlock
    thematic_evidence_context: ThematicEvidenceRunContext
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id"))
        object.__setattr__(self, "event_id", _text(self.event_id, "event_id"))
        if not isinstance(self.kb_response, PolicyKBQueryResponse):
            raise TypeError("kb_response must be a PolicyKBQueryResponse")
        if not isinstance(self.governance_bundle, PolicyEvaluationBundle):
            raise TypeError("governance_bundle must be a PolicyEvaluationBundle")
        if not isinstance(self.execution_result, ExecutionResult):
            raise TypeError("execution_result must be an ExecutionResult")
        if self.distribution_effect is not None and not isinstance(
            self.distribution_effect, DistributionEffect
        ):
            raise TypeError("distribution_effect must be a DistributionEffect or None")
        if not isinstance(self.y3172_trace, Y3172PipelineTrace):
            raise TypeError("y3172_trace must be a Y3172PipelineTrace")
        if not isinstance(self.audit_block, AuditBlock):
            raise TypeError("audit_block must be an AuditBlock")
        if not isinstance(self.thematic_evidence_context, ThematicEvidenceRunContext):
            raise TypeError("thematic_evidence_context must be a ThematicEvidenceRunContext")
        if self.governance_bundle.event_id != self.event_id:
            raise GovernanceConfigurationError("governance bundle event mismatch")
        if self.execution_result.request.event_id != self.event_id:
            raise GovernanceConfigurationError("execution result event mismatch")
        if self.y3172_trace.run_id != self.run_id:
            raise GovernanceConfigurationError("trace run identifier mismatch")
        source_artifacts = self.y3172_trace.nodes[0].artifact_ids
        if source_artifacts and self.event_id not in source_artifacts:
            raise GovernanceConfigurationError(
                "trace source artifacts do not reference response event"
            )
        if (
            self.execution_result.distribution_acknowledgment is not None
            and self.distribution_effect is None
        ):
            raise GovernanceConfigurationError(
                "acknowledged execution requires a distribution effect"
            )
        if (
            self.execution_result.review_queue_receipt is not None
            and self.distribution_effect is None
        ):
            raise GovernanceConfigurationError(
                "review routing requires a distribution effect"
            )
        if not isinstance(self.limitations, tuple):
            raise TypeError("limitations must be a tuple")
        normalized = tuple(_text(item, "limitation") for item in self.limitations)
        object.__setattr__(self, "limitations", tuple(sorted(set(normalized))))
        to_canonical_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "event_id": self.event_id,
            "kb_response": self.kb_response.to_dict(),
            "governance_bundle": self.governance_bundle.to_dict(),
            "execution_result": self.execution_result.to_dict(),
            "distribution_effect": None if self.distribution_effect is None else self.distribution_effect.to_dict(),
            "y3172_trace": self.y3172_trace.to_dict(),
            "audit_block": self.audit_block.to_dict(),
            "thematic_evidence_context": self.thematic_evidence_context.to_dict(),
            "limitations": list(self.limitations),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


class PolicyAgentService:
    def __init__(
        self,
        *,
        policy_kb_service: PolicyKBService,
        governance_service: GovernanceService,
        execution_service: ExecutionService,
        distribution_service: DistributionService,
        trace_coordinator: Y3172TraceCoordinator,
        thematic_evidence_service: ThematicEvidenceService,
        audit_service: AuditService,
    ) -> None:
        dependencies = (
            ("policy_kb_service", policy_kb_service, PolicyKBService),
            ("governance_service", governance_service, GovernanceService),
            ("execution_service", execution_service, ExecutionService),
            ("distribution_service", distribution_service, DistributionService),
            ("trace_coordinator", trace_coordinator, Y3172TraceCoordinator),
            ("thematic_evidence_service", thematic_evidence_service, ThematicEvidenceService),
            ("audit_service", audit_service, AuditService),
        )
        for name, value, expected in dependencies:
            if not isinstance(value, expected):
                raise TypeError(f"{name} must be a {expected.__name__}")
        self._policy_kb_service = policy_kb_service
        self._governance_service = governance_service
        self._execution_service = execution_service
        self._distribution_service = distribution_service
        self._trace_coordinator = trace_coordinator
        self._thematic_evidence_service = thematic_evidence_service
        self._audit_service = audit_service

    def run(self, request: PolicyAgentRequest) -> PolicyAgentResponse:
        if not isinstance(request, PolicyAgentRequest):
            raise TypeError("request must be a PolicyAgentRequest")
        thematic_context = self._thematic_evidence_service.for_stage(request.stage_id)
        kb_response = self._policy_kb_service.query(
            request.policy_query,
            limit=request.query_limit,
            min_similarity=request.min_similarity,
        )
        evaluation = self._governance_service.evaluate(request.event)
        bundle = evaluation.bundle
        execution_details = {
            "policy_query_digest": kb_response.query_digest,
            "resolved_evidence_count": kb_response.summary.resolved_count,
            "evidence_gaps": kb_response.evidence_gaps,
            "verified_passage_ids": thematic_context.passage_ids,
            "theme_ids": thematic_context.theme_ids,
            "gap_ids": thematic_context.gap_ids,
        }
        execution_result = self._execution_service.execute(
            event=request.event,
            recommendation=bundle.recommendation,
            approval_decision=request.approval_decision,
            idempotency_key=request.idempotency_key,
            execution_details=execution_details,
        )
        distribution_effect = self._distribution_service.distribute(
            event=request.event,
            execution_result=execution_result,
            payload=request.distribution_payload,
        )
        evidence_ids = tuple(
            result.provenance.policy_record_id
            for result in kb_response.results
            if result.provenance is not None
        )
        trace = self._trace_coordinator.build_trace(
            run_id=request.run_id,
            event=request.event,
            bundle=bundle,
            execution_result=execution_result,
            distribution_effect=distribution_effect,
            artifacts=Y3172TraceArtifacts(
                collection_artifact_ids=(request.event.event_id,),
                preprocessing_artifact_ids=(kb_response.query_digest,),
                model_artifact_ids=(),
                model_evidence_ids=tuple(sorted(set(evidence_ids))),
            ),
        )
        audit_payload = {
            "query_digest": kb_response.query_digest,
            "recommended_action": bundle.recommendation.recommended_action.value,
            "evidence_gap_count": len(kb_response.evidence_gaps),
            "execution_request_id": execution_result.request.request_id,
            "distribution_disposition": None if distribution_effect is None else distribution_effect.disposition.value,
            "trace_id": trace.trace_id,
            "verified_passage_ids": list(thematic_context.passage_ids),
            "theme_ids": list(thematic_context.theme_ids),
            "gap_ids": list(thematic_context.gap_ids),
        }
        audit_block = self._audit_service.append(
            run_id=request.run_id,
            scenario_id=request.scenario_id,
            stage_id=request.stage_id,
            event_id=request.event.event_id,
            operation_id=request.event.operation_id,
            event_type="POLICY_AGENT_COMPLETED",
            payload=audit_payload,
        )
        limitations = tuple(
            sorted(
                set(
                    kb_response.limitations
                    + kb_response.evidence_gaps
                    + tuple(f"thematic_evidence_gap:{gap_id}" for gap_id in thematic_context.gap_ids)
                    + ("distribution_and_audit_not_transactionally_atomic",)
                )
            )
        )
        return PolicyAgentResponse(
            run_id=request.run_id,
            event_id=request.event.event_id,
            kb_response=kb_response,
            governance_bundle=bundle,
            execution_result=execution_result,
            distribution_effect=distribution_effect,
            y3172_trace=trace,
            audit_block=audit_block,
            thematic_evidence_context=thematic_context,
            limitations=limitations,
        )
