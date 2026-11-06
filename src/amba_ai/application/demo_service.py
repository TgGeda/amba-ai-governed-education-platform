from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amba_ai.application.providers import ProviderRegistry
from amba_ai.governance.models import to_canonical_json
from amba_ai.governance.operation_registry import DestinationRegistry, OperationRegistry
from amba_ai.institutional.context_projection import InstitutionalContextProjectionService
from amba_ai.institutional.coordination import InstitutionalCoordinationService
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.demo_definition import (
    SCENARIO_ID,
    STAGE_TIMESTAMPS,
    create_four_stage_education_scenario,
)
from amba_ai.scenarios.evidence_release import EvidenceReleaseService
from amba_ai.scenarios.invariant_verifier import ScenarioInvariantVerifier
from amba_ai.scenarios.models import (
    ScenarioConfigurationError,
    ScenarioStage,
    require_identifier,
    require_sha256,
    require_timestamp,
    sha256_canonical,
)
from amba_ai.scenarios.repository import ScenarioRepository
from amba_ai.scenarios.runner import FourStageScenarioRunner, ScenarioRunResult
from amba_ai.scenarios.validator import ScenarioValidator
from amba_ai.services.audit_service import AuditService
from amba_ai.services.policy_agent_service import PolicyAgentResponse, PolicyAgentService
from amba_ai.standards.y3172_models import PipelineNodeStatus, Y3172Node

_FIXED_LIMITATIONS = (
    "Application-level interpreted mapping of ITU-T Y.3172 (06/2019); no formal conformance claimed.",
    "Not certified by ITU or any national authority.",
    "All scenario facts, learner profiles, transactions, and inference signals are synthetic.",
    "The demonstration creates no Ethiopian legal determination and has no legal effect.",
    "The local audit chain is tamper-evident within verified scope and has no external timestamp anchor.",
    "Distribution and audit persistence are not represented as one transactional commit.",
)
_APPROVAL_STATES = frozenset(
    {"not_required", "required_not_supplied", "approved", "rejected"}
)


@dataclass(frozen=True, slots=True)
class JudgeEventSummary:
    event_id: str
    operation_id: str
    destination_id: str
    recommended_action: str
    approval_status: str
    execution_status: str
    execution_receipt_id: str | None
    review_queue_receipt_id: str | None
    distribution_disposition: str | None
    acknowledgment_id: str | None
    distributor_status: str
    sink_status: str
    audit_block_index: int
    evidence_ids: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "event_id", "operation_id", "destination_id", "recommended_action",
            "execution_status", "distributor_status", "sink_status",
        ):
            object.__setattr__(
                self,
                field_name,
                require_identifier(getattr(self, field_name), field_name),
            )
        if self.approval_status not in _APPROVAL_STATES:
            raise ScenarioConfigurationError("approval_status is not recognized")
        for field_name in (
            "execution_receipt_id", "review_queue_receipt_id", "acknowledgment_id"
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, require_identifier(value, field_name))
        if self.distribution_disposition is not None:
            object.__setattr__(
                self,
                "distribution_disposition",
                require_identifier(self.distribution_disposition, "distribution_disposition"),
            )
        if isinstance(self.audit_block_index, bool) or not isinstance(self.audit_block_index, int):
            raise TypeError("audit_block_index must be an integer")
        if self.audit_block_index < 0:
            raise ScenarioConfigurationError("audit_block_index must be non-negative")
        object.__setattr__(self, "evidence_ids", _canonical_identifiers(self.evidence_ids, "evidence_ids"))
        object.__setattr__(self, "limitations", _canonical_text(self.limitations, "limitations"))
        if self.sink_status == PipelineNodeStatus.NOT_REACHED.value and self.acknowledgment_id is not None:
            raise ScenarioConfigurationError("NOT_REACHED sink cannot have acknowledgment")
        if self.sink_status == PipelineNodeStatus.COMPLETED.value and self.acknowledgment_id is None:
            raise ScenarioConfigurationError("COMPLETED sink requires acknowledgment")
        if self.distributor_status == PipelineNodeStatus.PREVENTED.value:
            if self.sink_status != PipelineNodeStatus.NOT_REACHED.value:
                raise ScenarioConfigurationError("PREVENTED D node requires NOT_REACHED sink")
            if self.acknowledgment_id is not None:
                raise ScenarioConfigurationError("PREVENTED distribution cannot be acknowledged")
        to_canonical_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "operation_id": self.operation_id,
            "destination_id": self.destination_id,
            "recommended_action": self.recommended_action,
            "approval_status": self.approval_status,
            "execution_status": self.execution_status,
            "execution_receipt_id": self.execution_receipt_id,
            "review_queue_receipt_id": self.review_queue_receipt_id,
            "distribution_disposition": self.distribution_disposition,
            "acknowledgment_id": self.acknowledgment_id,
            "distributor_status": self.distributor_status,
            "sink_status": self.sink_status,
            "audit_block_index": self.audit_block_index,
            "evidence_ids": list(self.evidence_ids),
            "limitations": list(self.limitations),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class JudgeStageSummary:
    stage: ScenarioStage
    timestamp: str
    released_fact_ids: tuple[str, ...]
    projection_ids: tuple[str, ...]
    institution_ids: tuple[str, ...]
    observation_count: int
    observation_codes: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    conflict_ids: tuple[str, ...]
    uncovered_fact_ids: tuple[str, ...]
    events: tuple[JudgeEventSummary, ...]
    source_stage_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.stage, ScenarioStage):
            raise TypeError("stage must be a ScenarioStage")
        object.__setattr__(self, "timestamp", require_timestamp(self.timestamp, "timestamp"))
        for field_name in (
            "released_fact_ids", "projection_ids", "institution_ids",
            "observation_codes", "conflict_ids", "uncovered_fact_ids",
        ):
            object.__setattr__(
                self,
                field_name,
                _canonical_identifiers(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "unresolved_questions",
            _canonical_text(self.unresolved_questions, "unresolved_questions"),
        )
        if isinstance(self.observation_count, bool) or not isinstance(self.observation_count, int):
            raise TypeError("observation_count must be an integer")
        if self.observation_count < len(self.observation_codes):
            raise ScenarioConfigurationError("observation_count cannot be smaller than observation_codes")
        if not isinstance(self.events, tuple) or not self.events:
            raise ScenarioConfigurationError("stage summary requires at least one event")
        if any(not isinstance(item, JudgeEventSummary) for item in self.events):
            raise TypeError("events must contain JudgeEventSummary objects")
        event_ids = tuple(item.event_id for item in self.events)
        if len(event_ids) != len(set(event_ids)):
            raise ScenarioConfigurationError("events must not contain duplicate event IDs")
        object.__setattr__(self, "source_stage_digest", require_sha256(self.source_stage_digest, "source_stage_digest"))
        to_canonical_json(self.to_dict())

    @property
    def audit_block_indexes(self) -> tuple[int, ...]:
        return tuple(item.audit_block_index for item in self.events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": int(self.stage),
            "timestamp": self.timestamp,
            "released_fact_ids": list(self.released_fact_ids),
            "projection_ids": list(self.projection_ids),
            "institution_ids": list(self.institution_ids),
            "observation_count": self.observation_count,
            "observation_codes": list(self.observation_codes),
            "unresolved_questions": list(self.unresolved_questions),
            "conflict_ids": list(self.conflict_ids),
            "uncovered_fact_ids": list(self.uncovered_fact_ids),
            "events": [item.to_dict() for item in self.events],
            "source_stage_digest": self.source_stage_digest,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class JudgeDemoSummary:
    run_id: str
    scenario_id: str
    summarized_at: str
    stages: tuple[JudgeStageSummary, ...]
    audit_valid: bool
    audited_block_count: int
    run_digest: str
    limitations: tuple[str, ...]
    summary_digest: str
    synthetic: bool = True
    legal_effect: bool = False
    formal_y3172_conformance_claimed: bool = False
    certification_claimed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_identifier(self.run_id, "run_id"))
        object.__setattr__(self, "scenario_id", require_identifier(self.scenario_id, "scenario_id"))
        object.__setattr__(self, "summarized_at", require_timestamp(self.summarized_at, "summarized_at"))
        if not isinstance(self.stages, tuple) or tuple(item.stage for item in self.stages) != tuple(ScenarioStage):
            raise ScenarioConfigurationError("judge summary requires all four stages in canonical order")
        if type(self.audit_valid) is not bool or not self.audit_valid:
            raise ScenarioConfigurationError("judge summary requires valid audit verification")
        if isinstance(self.audited_block_count, bool) or not isinstance(self.audited_block_count, int):
            raise TypeError("audited_block_count must be an integer")
        all_indexes = tuple(index for stage in self.stages for index in stage.audit_block_indexes)
        if len(all_indexes) != len(set(all_indexes)):
            raise ScenarioConfigurationError("audit block indexes must be unique")
        if all_indexes != tuple(sorted(all_indexes)):
            raise ScenarioConfigurationError("audit block indexes must be increasing")
        if len(all_indexes) != self.audited_block_count:
            raise ScenarioConfigurationError("summarized audit blocks do not match verified audit scope")
        object.__setattr__(self, "run_digest", require_sha256(self.run_digest, "run_digest"))
        object.__setattr__(self, "limitations", _canonical_text(self.limitations, "limitations"))
        object.__setattr__(self, "summary_digest", require_sha256(self.summary_digest, "summary_digest"))
        if type(self.synthetic) is not bool or type(self.legal_effect) is not bool:
            raise TypeError("synthetic and legal_effect must be strict Booleans")
        if not self.synthetic or self.legal_effect:
            raise ScenarioConfigurationError("demo summary must remain synthetic without legal effect")
        if self.formal_y3172_conformance_claimed or self.certification_claimed:
            raise ScenarioConfigurationError("demo summary must not claim formal conformance or certification")
        if self.summary_digest != self.compute_digest():
            raise ScenarioConfigurationError("summary_digest does not match summary contents")

    def digest_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "summarized_at": self.summarized_at,
            "stages": [item.to_dict() for item in self.stages],
            "audit_valid": self.audit_valid,
            "audited_block_count": self.audited_block_count,
            "run_digest": self.run_digest,
            "limitations": list(self.limitations),
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
            "formal_y3172_conformance_claimed": self.formal_y3172_conformance_claimed,
            "certification_claimed": self.certification_claimed,
        }

    def compute_digest(self) -> str:
        return sha256_canonical(self.digest_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.digest_payload(), "summary_digest": self.summary_digest}

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


class ComposedFourStageDemoService:
    def __init__(self, providers: ProviderRegistry) -> None:
        if not isinstance(providers, ProviderRegistry):
            raise TypeError("providers must be a ProviderRegistry")
        self._providers = providers
        self._executed = False

    def run(self, *, run_id: str) -> JudgeDemoSummary:
        if self._executed:
            raise ScenarioConfigurationError(
                "ComposedFourStageDemoService supports one run per test/demo provider composition"
            )
        run_key = require_identifier(run_id, "run_id")
        repository = self._providers.get("scenario_repository", ScenarioRepository)
        scenario = create_four_stage_education_scenario(
            operation_registry=self._providers.get("operation_registry", OperationRegistry),
            destination_registry=self._providers.get("destination_registry", DestinationRegistry),
        )
        repository.register(scenario)
        runner = FourStageScenarioRunner(
            scenario_repository=repository,
            scenario_validator=self._providers.get("scenario_validator", ScenarioValidator),
            scenario_clock=self._providers.get("scenario_clock", DeterministicScenarioClock),
            evidence_release_service=self._providers.get("evidence_release_service", EvidenceReleaseService),
            projection_service=self._providers.get(
                "institutional_context_projection_service", InstitutionalContextProjectionService
            ),
            coordination_service=self._providers.get(
                "institutional_coordination_service", InstitutionalCoordinationService
            ),
            policy_agent_service=self._providers.get("policy_agent_service", PolicyAgentService),
            invariant_verifier=self._providers.get("scenario_invariant_verifier", ScenarioInvariantVerifier),
            audit_service=self._providers.get("audit_service", AuditService),
        )
        result = runner.run(scenario_id=SCENARIO_ID, run_id=run_key)
        summary = self._summarize(result)
        self._executed = True
        return summary

    @staticmethod
    def _summarize(result: ScenarioRunResult) -> JudgeDemoSummary:
        stages = tuple(_summarize_stage(item) for item in result.stages)
        verification = result.final_audit_verification
        limitations = tuple(
            sorted(
                {
                    *_FIXED_LIMITATIONS,
                    *(item for stage in stages for event in stage.events for item in event.limitations),
                }
            )
        )
        summarized_at = result.stages[-1].coordination.coordinated_at
        payload = {
            "run_id": result.run_id,
            "scenario_id": result.scenario_id,
            "summarized_at": summarized_at,
            "stages": [item.to_dict() for item in stages],
            "audit_valid": verification.valid,
            "audited_block_count": verification.verified_block_count,
            "run_digest": result.run_digest,
            "limitations": list(limitations),
            "synthetic": True,
            "legal_effect": False,
            "formal_y3172_conformance_claimed": False,
            "certification_claimed": False,
        }
        return JudgeDemoSummary(
            run_id=result.run_id,
            scenario_id=result.scenario_id,
            summarized_at=summarized_at,
            stages=stages,
            audit_valid=verification.valid,
            audited_block_count=verification.verified_block_count,
            run_digest=result.run_digest,
            limitations=limitations,
            summary_digest=sha256_canonical(payload),
        )


def _summarize_stage(stage_result: Any) -> JudgeStageSummary:
    coordination = stage_result.coordination
    events = tuple(_summarize_event(response) for response in stage_result.policy_agent_responses)
    observation_codes = tuple(
        sorted(
            {
                code
                for assessment in coordination.assessments
                for observation in assessment.observations
                for code in observation.rationale_codes
            }
        )
    )
    observation_count = sum(
        len(assessment.observations) for assessment in coordination.assessments
    )
    return JudgeStageSummary(
        stage=stage_result.stage,
        timestamp=STAGE_TIMESTAMPS[stage_result.stage],
        released_fact_ids=tuple(
            sorted(
                {
                    fact_id
                    for envelope in stage_result.release_envelopes
                    for fact_id in envelope.fact_ids
                }
            )
        ),
        projection_ids=tuple(sorted(item.projection_id for item in stage_result.projections)),
        institution_ids=tuple(sorted(item.institution_id for item in coordination.assessments)),
        observation_count=observation_count,
        observation_codes=observation_codes,
        unresolved_questions=tuple(item.question for item in coordination.unresolved_questions),
        conflict_ids=tuple(item.conflict_id for item in coordination.conflicts),
        uncovered_fact_ids=coordination.uncovered_fact_ids,
        events=events,
        source_stage_digest=stage_result.stage_digest,
    )


def _summarize_event(response: PolicyAgentResponse) -> JudgeEventSummary:
    recommendation = response.governance_bundle.recommendation
    execution = response.execution_result
    request = execution.request
    receipt = execution.execution_receipt
    review = execution.review_queue_receipt
    acknowledgment = execution.distribution_acknowledgment
    effect = response.distribution_effect
    nodes = {item.node: item for item in response.y3172_trace.nodes}
    evidence_ids: set[str] = set()
    for item in response.kb_response.results:
        provenance = getattr(item, "provenance", None)
        evidence_id = None if provenance is None else getattr(provenance, "policy_record_id", None)
        if not evidence_id:
            evidence_id = getattr(item, "record_id", None) or getattr(item, "source_id", None)
        if not evidence_id:
            raise ScenarioConfigurationError(
                "policy query result lacks a resolvable policy evidence identifier"
            )
        evidence_ids.add(require_identifier(evidence_id, "policy_evidence_id"))
    event = getattr(request, "event", None)
    operation_id = getattr(event, "operation_id", None) or getattr(request, "operation_id", None)
    destination_id = getattr(event, "destination_id", None) or getattr(request, "destination_id", None)
    if operation_id is None or destination_id is None:
        raise ScenarioConfigurationError("execution request lacks operation or destination identity")
    return JudgeEventSummary(
        event_id=response.event_id,
        operation_id=operation_id,
        destination_id=destination_id,
        recommended_action=recommendation.recommended_action.value,
        approval_status=_approval_status(recommendation.requires_approval, request),
        execution_status=(
            receipt.status.value
            if receipt is not None
            else "review_queued"
            if review is not None
            else "no_execution_artifact"
        ),
        execution_receipt_id=None if receipt is None else receipt.receipt_id,
        review_queue_receipt_id=None if review is None else review.receipt_id,
        distribution_disposition=None if effect is None else effect.disposition.value,
        acknowledgment_id=None if acknowledgment is None else acknowledgment.acknowledgment_id,
        distributor_status=nodes[Y3172Node.D].status.value,
        sink_status=nodes[Y3172Node.SINK].status.value,
        audit_block_index=response.audit_block.block_index,
        evidence_ids=tuple(sorted(evidence_ids)),
        limitations=response.limitations,
    )


def _approval_status(requires_approval: bool, request: Any) -> str:
    if not requires_approval:
        return "not_required"
    decision = getattr(request, "approval_decision", None)
    if decision is None:
        return "required_not_supplied"
    approved = getattr(decision, "approved", None)
    if type(approved) is not bool:
        raise ScenarioConfigurationError("approval decision lacks a strict approved Boolean")
    return "approved" if approved else "rejected"


def _canonical_identifiers(values: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    normalized = tuple(require_identifier(item, f"{field_name} item") for item in values)
    if len(normalized) != len(set(normalized)):
        raise ScenarioConfigurationError(f"{field_name} must not contain duplicates")
    return tuple(sorted(normalized))


def _canonical_text(values: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    normalized = tuple(" ".join(str(item).split()) for item in values)
    if any(not item for item in normalized):
        raise ScenarioConfigurationError(f"{field_name} must not contain empty values")
    if len(normalized) != len(set(normalized)):
        raise ScenarioConfigurationError(f"{field_name} must not contain duplicates")
    return tuple(sorted(normalized))
