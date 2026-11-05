from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amba_ai.governance.distribution import DistributionDisposition
from amba_ai.governance.execution import ExecutionStatus
from amba_ai.governance.models import to_canonical_json
from amba_ai.institutional.coordination import InstitutionalCoordinationResult
from amba_ai.institutional.models import InstitutionalContextProjection
from amba_ai.scenarios.models import EvidenceReleaseEnvelope, ScenarioConfigurationError
from amba_ai.services.policy_agent_service import PolicyAgentResponse
from amba_ai.standards.y3172_models import PipelineNodeStatus, Y3172Node


@dataclass(frozen=True, slots=True)
class ScenarioInvariantEvidence:
    releases: tuple[EvidenceReleaseEnvelope, ...]
    projections: tuple[InstitutionalContextProjection, ...]
    coordination: InstitutionalCoordinationResult
    policy_agent_responses: tuple[PolicyAgentResponse, ...]

    def __post_init__(self) -> None:
        expected = (
            ("releases", EvidenceReleaseEnvelope),
            ("projections", InstitutionalContextProjection),
            ("policy_agent_responses", PolicyAgentResponse),
        )
        for field_name, item_type in expected:
            value = getattr(self, field_name)
            if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
                raise TypeError(f"{field_name} must be a tuple of {item_type.__name__} objects")
        if not isinstance(self.coordination, InstitutionalCoordinationResult):
            raise TypeError("coordination must be an InstitutionalCoordinationResult")


@dataclass(frozen=True, slots=True)
class ScenarioInvariantReport:
    valid: bool
    checked_release_count: int
    checked_projection_count: int
    checked_assessment_count: int
    checked_response_count: int

    def __post_init__(self) -> None:
        if type(self.valid) is not bool:
            raise TypeError("valid must be a strict Boolean")
        to_canonical_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "checked_release_count": self.checked_release_count,
            "checked_projection_count": self.checked_projection_count,
            "checked_assessment_count": self.checked_assessment_count,
            "checked_response_count": self.checked_response_count,
        }


class ScenarioInvariantVerifier:
    def verify(self, evidence: ScenarioInvariantEvidence) -> ScenarioInvariantReport:
        if not isinstance(evidence, ScenarioInvariantEvidence):
            raise TypeError("evidence must be ScenarioInvariantEvidence")
        releases_by_digest = {item.release_digest: item for item in evidence.releases}
        projections_by_id = {item.projection_id: item for item in evidence.projections}
        if len(releases_by_digest) != len(evidence.releases):
            raise ScenarioConfigurationError("release digests must be unique")
        if len(projections_by_id) != len(evidence.projections):
            raise ScenarioConfigurationError("projection identifiers must be unique")
        for projection in evidence.projections:
            release = releases_by_digest.get(projection.source_release_digest)
            if release is None:
                raise ScenarioConfigurationError("projection does not reference a supplied release")
            if projection.source_release_id != release.release_id:
                raise ScenarioConfigurationError("projection release identity mismatch")
            if projection.scenario_id != release.scenario_id or projection.stage is not release.stage:
                raise ScenarioConfigurationError("projection scenario or stage broadened from release")
            if projection.recipient_id != release.recipient_id:
                raise ScenarioConfigurationError("projection recipient scope broadened")
            if projection.fact_ids != release.fact_ids:
                raise ScenarioConfigurationError("projection fact scope differs from release")
            if any(fact.release_stage > projection.stage for fact in projection.facts):
                raise ScenarioConfigurationError("future fact leaked into projection")
        assessed_projection_ids: list[str] = []
        for assessment in evidence.coordination.assessments:
            projection = projections_by_id.get(assessment.projection_id)
            if projection is None:
                raise ScenarioConfigurationError("assessment does not reference a supplied projection")
            if not set(assessment.assessed_fact_ids).issubset(projection.fact_ids):
                raise ScenarioConfigurationError("assessment references a fact outside its projection")
            assessed_projection_ids.append(assessment.projection_id)
        expected_projection_ids = set(projections_by_id)
        if set(assessed_projection_ids) != expected_projection_ids:
            raise ScenarioConfigurationError(
                "coordination did not preserve one assessment for every projection"
            )
        if len(assessed_projection_ids) != len(set(assessed_projection_ids)):
            raise ScenarioConfigurationError(
                "coordination contains duplicate assessments for a projection"
            )
        if any(conflict.resolved or not conflict.preserved for conflict in evidence.coordination.conflicts):
            raise ScenarioConfigurationError("coordination resolved or discarded an institutional conflict")
        for response in evidence.policy_agent_responses:
            self._verify_response(response)
        return ScenarioInvariantReport(
            valid=True,
            checked_release_count=len(evidence.releases),
            checked_projection_count=len(evidence.projections),
            checked_assessment_count=len(evidence.coordination.assessments),
            checked_response_count=len(evidence.policy_agent_responses),
        )

    @staticmethod
    def _verify_response(response: PolicyAgentResponse) -> None:
        execution = response.execution_result
        effect = response.distribution_effect
        acknowledgment = execution.distribution_acknowledgment
        receipt = execution.execution_receipt
        review = execution.review_queue_receipt
        nodes = {item.node: item for item in response.y3172_trace.nodes}
        distributor = nodes[Y3172Node.D]
        sink = nodes[Y3172Node.SINK]
        if effect is not None and receipt is not None:
            if effect.destination_id != execution.request.destination_id and review is None:
                raise ScenarioConfigurationError("distribution effect destination does not match execution request")
        if effect is not None and effect.disposition is DistributionDisposition.PREVENTED and acknowledgment is not None:
            raise ScenarioConfigurationError("prevented distribution must not acknowledge delivery")
        if sink.status is PipelineNodeStatus.NOT_REACHED and acknowledgment is not None:
            raise ScenarioConfigurationError("NOT_REACHED sink must not contain acknowledgment")
        if sink.status is PipelineNodeStatus.COMPLETED and acknowledgment is None:
            raise ScenarioConfigurationError("COMPLETED sink requires acknowledgment")
        if review is not None and acknowledgment is not None:
            raise ScenarioConfigurationError("review routing must not acknowledge learner delivery")
        if receipt is not None and receipt.status is ExecutionStatus.NOT_ATTEMPTED and effect is not None:
            raise ScenarioConfigurationError("NOT_ATTEMPTED execution must not distribute")
        if distributor.status is PipelineNodeStatus.PREVENTED:
            if effect is None or effect.disposition is not DistributionDisposition.PREVENTED:
                raise ScenarioConfigurationError("PREVENTED distributor node requires prevented effect")
        if response.y3172_trace.execution_receipt_id is not None:
            if receipt is None or response.y3172_trace.execution_receipt_id != receipt.receipt_id:
                raise ScenarioConfigurationError("trace execution receipt identity mismatch")
        if response.y3172_trace.review_queue_receipt_id is not None:
            if review is None or response.y3172_trace.review_queue_receipt_id != review.receipt_id:
                raise ScenarioConfigurationError("trace review receipt identity mismatch")
        if response.y3172_trace.distribution_acknowledgment_id is not None:
            if acknowledgment is None or response.y3172_trace.distribution_acknowledgment_id != acknowledgment.acknowledgment_id:
                raise ScenarioConfigurationError("trace acknowledgment identity mismatch")
