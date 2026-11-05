from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import threading
from typing import Any

from amba_ai.governance.audit_verifier import AuditVerificationResult
from amba_ai.governance.models import (
    AuthorizationBasis,
    AuthorizationBasisType,
    PipelineEvent,
    to_canonical_json,
)
from amba_ai.institutional.context_projection import InstitutionalContextProjectionService
from amba_ai.institutional.coordination import (
    InstitutionalCoordinationResult,
    InstitutionalCoordinationService,
)
from amba_ai.institutional.models import InstitutionalContextProjection
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.demo_definition import STAGE_TIMESTAMPS
from amba_ai.scenarios.evidence_release import EvidenceReleaseService
from amba_ai.scenarios.invariant_verifier import (
    ScenarioInvariantEvidence,
    ScenarioInvariantReport,
    ScenarioInvariantVerifier,
)
from amba_ai.scenarios.models import (
    EvidenceReleaseEnvelope,
    ScenarioConfigurationError,
    ScenarioStage,
    require_identifier,
    require_sha256,
    sha256_canonical,
)
from amba_ai.scenarios.repository import ScenarioDefinition, ScenarioRepository
from amba_ai.scenarios.validator import ScenarioValidationResult, ScenarioValidator
from amba_ai.services.audit_service import AuditService
from amba_ai.services.policy_agent_service import (
    PolicyAgentRequest,
    PolicyAgentResponse,
    PolicyAgentService,
)


@dataclass(frozen=True, slots=True)
class ScenarioStageResult:
    scenario_id: str
    stage: ScenarioStage
    release_envelopes: tuple[EvidenceReleaseEnvelope, ...]
    projections: tuple[InstitutionalContextProjection, ...]
    coordination: InstitutionalCoordinationResult
    policy_agent_responses: tuple[PolicyAgentResponse, ...]
    invariant_report: ScenarioInvariantReport
    stage_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", require_identifier(self.scenario_id, "scenario_id"))
        if not isinstance(self.stage, ScenarioStage):
            raise TypeError("stage must be a ScenarioStage")
        for name, expected in (
            ("release_envelopes", EvidenceReleaseEnvelope),
            ("projections", InstitutionalContextProjection),
            ("policy_agent_responses", PolicyAgentResponse),
        ):
            value = getattr(self, name)
            if not isinstance(value, tuple) or any(not isinstance(item, expected) for item in value):
                raise TypeError(f"{name} must be a tuple of {expected.__name__} objects")
        if not isinstance(self.coordination, InstitutionalCoordinationResult):
            raise TypeError("coordination must be an InstitutionalCoordinationResult")
        if not isinstance(self.invariant_report, ScenarioInvariantReport) or not self.invariant_report.valid:
            raise ScenarioConfigurationError("stage result requires a valid invariant report")
        object.__setattr__(self, "stage_digest", require_sha256(self.stage_digest, "stage_digest"))
        if self.stage_digest != self.compute_digest():
            raise ScenarioConfigurationError("stage_digest does not match stage contents")

    def digest_payload(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "stage": int(self.stage),
            "release_envelopes": [item.to_dict() for item in self.release_envelopes],
            "projections": [item.to_dict() for item in self.projections],
            "coordination": self.coordination.to_dict(),
            "policy_agent_responses": [item.to_dict() for item in self.policy_agent_responses],
            "invariant_report": self.invariant_report.to_dict(),
        }

    def compute_digest(self) -> str:
        return sha256_canonical(self.digest_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.digest_payload(), "stage_digest": self.stage_digest}


@dataclass(frozen=True, slots=True)
class ScenarioRunResult:
    run_id: str
    scenario_id: str
    validation: ScenarioValidationResult
    stages: tuple[ScenarioStageResult, ...]
    final_audit_verification: AuditVerificationResult
    run_digest: str
    synthetic: bool = True
    legal_effect: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_identifier(self.run_id, "run_id"))
        object.__setattr__(self, "scenario_id", require_identifier(self.scenario_id, "scenario_id"))
        if not isinstance(self.validation, ScenarioValidationResult) or not self.validation.valid:
            raise ScenarioConfigurationError("run requires successful scenario validation")
        if not isinstance(self.stages, tuple) or any(not isinstance(item, ScenarioStageResult) for item in self.stages):
            raise TypeError("stages must be a tuple of ScenarioStageResult objects")
        expected = tuple(ScenarioStage(value) for value in range(1, len(self.stages) + 1))
        if tuple(item.stage for item in self.stages) != expected:
            raise ScenarioConfigurationError("run stages must be complete and sequential")
        if not isinstance(self.final_audit_verification, AuditVerificationResult):
            raise TypeError("final_audit_verification must be an AuditVerificationResult")
        if not self.final_audit_verification.valid:
            raise ScenarioConfigurationError("run requires valid audit verification")
        if type(self.synthetic) is not bool or type(self.legal_effect) is not bool:
            raise TypeError("synthetic and legal_effect must be strict Booleans")
        if not self.synthetic or self.legal_effect:
            raise ScenarioConfigurationError("scenario run must be synthetic without legal effect")
        object.__setattr__(self, "run_digest", require_sha256(self.run_digest, "run_digest"))
        if self.run_digest != self.compute_digest():
            raise ScenarioConfigurationError("run_digest does not match run contents")

    def digest_payload(self) -> dict[str, Any]:
        verification = self.final_audit_verification
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "validation": self.validation.to_dict(),
            "stages": [item.to_dict() for item in self.stages],
            "final_audit_verification": {
                "run_id": verification.run_id,
                "valid": verification.valid,
                "verified_block_count": verification.verified_block_count,
                "failure_block_index": verification.failure_block_index,
                "failure_code": verification.failure_code,
            },
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }

    def compute_digest(self) -> str:
        return sha256_canonical(self.digest_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.digest_payload(), "run_digest": self.run_digest}

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


class FourStageScenarioRunner:
    def __init__(
        self,
        *,
        scenario_repository: ScenarioRepository,
        scenario_validator: ScenarioValidator,
        scenario_clock: DeterministicScenarioClock,
        evidence_release_service: EvidenceReleaseService,
        projection_service: InstitutionalContextProjectionService,
        coordination_service: InstitutionalCoordinationService,
        policy_agent_service: PolicyAgentService,
        invariant_verifier: ScenarioInvariantVerifier,
        audit_service: AuditService,
    ) -> None:
        dependencies = (
            (scenario_repository, ScenarioRepository, "scenario_repository"),
            (scenario_validator, ScenarioValidator, "scenario_validator"),
            (scenario_clock, DeterministicScenarioClock, "scenario_clock"),
            (evidence_release_service, EvidenceReleaseService, "evidence_release_service"),
            (projection_service, InstitutionalContextProjectionService, "projection_service"),
            (coordination_service, InstitutionalCoordinationService, "coordination_service"),
            (policy_agent_service, PolicyAgentService, "policy_agent_service"),
            (invariant_verifier, ScenarioInvariantVerifier, "invariant_verifier"),
            (audit_service, AuditService, "audit_service"),
        )
        for value, expected, name in dependencies:
            if not isinstance(value, expected):
                raise TypeError(f"{name} must be a {expected.__name__}")
        if evidence_release_service.clock is not scenario_clock:
            raise ScenarioConfigurationError("evidence release must share the runner scenario clock")
        if projection_service.clock is not scenario_clock:
            raise ScenarioConfigurationError("projection service must share the runner scenario clock")
        self._repository = scenario_repository
        self._validator = scenario_validator
        self._clock = scenario_clock
        self._release = evidence_release_service
        self._projection = projection_service
        self._coordination = coordination_service
        self._agent = policy_agent_service
        self._invariants = invariant_verifier
        self._audit = audit_service
        self._runs: dict[str, ScenarioRunResult] = {}
        self._run_scenarios: dict[str, str] = {}
        self._lock = threading.RLock()

    def run(self, *, scenario_id: str, run_id: str) -> ScenarioRunResult:
        scenario_key = require_identifier(scenario_id, "scenario_id")
        run_key = require_identifier(run_id, "run_id")
        with self._lock:
            existing = self._runs.get(run_key)
            if existing is not None:
                if existing.scenario_id != scenario_key:
                    raise ScenarioConfigurationError("run_id is already bound to another scenario")
                return existing
            if self._runs and run_key not in self._runs:
                raise ScenarioConfigurationError(
                    "FourStageScenarioRunner supports one scenario run "
                    "per deterministic clock instance"
                )
            prior = self._run_scenarios.get(run_key)
            if prior is not None and prior != scenario_key:
                raise ScenarioConfigurationError("run_id is already bound to another scenario")
            self._run_scenarios[run_key] = scenario_key
            scenario = self._repository.get(scenario_key)
            validation = self._validator.validate(scenario)
            if scenario.configured_stages != (
                ScenarioStage.STAGE_1,
                ScenarioStage.STAGE_2,
                ScenarioStage.STAGE_3,
                ScenarioStage.STAGE_4,
            ):
                raise ScenarioConfigurationError("four-stage runner requires exactly STAGE_1 through STAGE_4")
            self._release.register_facts(scenario.facts)
            results: list[ScenarioStageResult] = []
            for stage in scenario.configured_stages:
                self._advance_clock(stage)
                results.append(self._execute_stage(scenario, stage, run_key))
            verification = self._audit.verify(run_key)
            payload = {
                "run_id": run_key,
                "scenario_id": scenario_key,
                "validation": validation.to_dict(),
                "stages": [item.to_dict() for item in results],
                "final_audit_verification": {
                    "run_id": verification.run_id,
                    "valid": verification.valid,
                    "verified_block_count": verification.verified_block_count,
                    "failure_block_index": verification.failure_block_index,
                    "failure_code": verification.failure_code,
                },
                "synthetic": True,
                "legal_effect": False,
            }
            result = ScenarioRunResult(
                run_id=run_key,
                scenario_id=scenario_key,
                validation=validation,
                stages=tuple(results),
                final_audit_verification=verification,
                run_digest=sha256_canonical(payload),
            )
            self._runs[run_key] = result
            return result

    def _advance_clock(self, stage: ScenarioStage) -> None:
        timestamp = STAGE_TIMESTAMPS[stage]
        snapshot = self._clock.snapshot()
        target = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        current = datetime.fromisoformat(
            snapshot.timestamp.replace("Z", "+00:00")
        )
        if stage is ScenarioStage.STAGE_1:
            if snapshot.stage is not ScenarioStage.STAGE_1:
                raise ScenarioConfigurationError("runner clock is not at STAGE_1")
            delta = target - current
            if delta.total_seconds() < 0:
                raise ScenarioConfigurationError("runner clock is later than Stage 1 timestamp")
            if delta.total_seconds() > 0:
                self._clock.advance_time(delta)
            return
        self._clock.advance_stage(stage, at_time=timestamp)

    def _execute_stage(
        self,
        scenario: ScenarioDefinition,
        stage: ScenarioStage,
        run_id: str,
    ) -> ScenarioStageResult:
        recipients = tuple(
            sorted(
                {
                    recipient
                    for fact in scenario.facts
                    if fact.release_stage <= stage
                    for recipient in fact.recipient_ids
                }
            )
        )
        releases = tuple(
            self._release.release(
                scenario_id=scenario.scenario_id,
                recipient_id=recipient,
                stage=stage,
            )
            for recipient in recipients
        )
        projections = tuple(self._projection.project(item) for item in releases)
        coordination = self._coordination.coordinate(projections)
        events = tuple(item for item in scenario.events if item.stage is stage)
        responses = tuple(
            self._agent.run(
                PolicyAgentRequest(
                    run_id=run_id,
                    scenario_id=scenario.scenario_id,
                    stage_id=f"STAGE-{int(stage)}",
                    event=self._pipeline_event(scenario, event),
                    policy_query=self._policy_query(event.operation_id),
                    idempotency_key=f"{run_id}:{event.event_id}",
                    distribution_payload={
                        "event_id": event.event_id,
                        "scenario_id": scenario.scenario_id,
                        "stage": int(stage),
                        "synthetic": True,
                    },
                )
            )
            for event in events
        )
        report = self._invariants.verify(
            ScenarioInvariantEvidence(
                releases=releases,
                projections=projections,
                coordination=coordination,
                policy_agent_responses=responses,
            )
        )
        payload = {
            "scenario_id": scenario.scenario_id,
            "stage": int(stage),
            "release_envelopes": [item.to_dict() for item in releases],
            "projections": [item.to_dict() for item in projections],
            "coordination": coordination.to_dict(),
            "policy_agent_responses": [item.to_dict() for item in responses],
            "invariant_report": report.to_dict(),
        }
        return ScenarioStageResult(
            scenario_id=scenario.scenario_id,
            stage=stage,
            release_envelopes=releases,
            projections=projections,
            coordination=coordination,
            policy_agent_responses=responses,
            invariant_report=report,
            stage_digest=sha256_canonical(payload),
        )

    @staticmethod
    def _pipeline_event(
        scenario: ScenarioDefinition,
        event_definition: Any,
    ) -> PipelineEvent:
        facts_by_id = {item.fact_id: item for item in scenario.facts}
        selected = tuple(facts_by_id[fact_id] for fact_id in event_definition.fact_ids)
        if any(fact.release_stage > event_definition.stage for fact in selected):
            raise ScenarioConfigurationError("event attempted to consume future-stage evidence")
        payload: dict[str, Any] = {
            "fact_ids": list(event_definition.fact_ids),
            "facts": [fact.to_dict() for fact in selected],
            "synthetic": True,
        }
        for fact in selected:
            for key, value in fact.payload.items():
                if key in payload and payload[key] != value:
                    raise ScenarioConfigurationError(
                        "event fact payload collision for field "
                        f"{key}"
                    )
                payload[key] = value
        basis = None
        if event_definition.operation_id in {
            "classroom_exercise_telemetry",
            "classroom_instruction_delivery",
        }:
            basis = AuthorizationBasis(
                basis_id=f"AUTH-{event_definition.event_id}",
                basis_type=AuthorizationBasisType.PROJECT_FIXTURE,
                subject_category="synthetic_minor_learner",
                authority_reference="AMBA-GOV-SYNTHETIC-CLASSROOM",
                purposes=(event_definition.operation_id,),
                data_categories=("synthetic_education_context",),
                processing_operations=(event_definition.operation_id,),
                effective_from="2026-01-01T00:00:00Z",
                expires_at="2027-01-01T00:00:00Z",
                revoked_at=None,
                artifact_hash=hashlib.sha256(
                    f"{scenario.scenario_id}:{event_definition.event_id}".encode("utf-8")
                ).hexdigest(),
                verifier_id="AMBA-GOV-SYNTHETIC-VERIFIER",
                synthetic=True,
                legal_effect=False,
            )
        return PipelineEvent(
            event_id=event_definition.event_id,
            timestamp=STAGE_TIMESTAMPS[event_definition.stage],
            operation_id=event_definition.operation_id,
            source_node="SRC-SYNTHETIC-EDUCATION-SCENARIO",
            destination_id=event_definition.destination_id,
            payload_type="scenario_fact_bundle",
            payload=payload,
            authorization_basis=basis,
            synthetic_flag=True,
        )

    @staticmethod
    def _policy_query(operation_id: str) -> str:
        queries = {
            "classroom_exercise_telemetry": "synthetic classroom educational processing safeguards",
            "classroom_instruction_delivery": "classroom instructional delivery learner safeguards",
            "commercial_purchase_request": "commercial purchase learner protection disclosure safeguards",
            "targeted_ad_dispatch": "targeted advertising learner profiling prohibition",
        }
        return queries[operation_id]
