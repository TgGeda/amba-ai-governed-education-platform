from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from amba_ai.governance.models import deep_freeze, to_canonical_json
from amba_ai.scenarios.models import (
    ScenarioAccessError,
    ScenarioConfigurationError,
    ScenarioStage,
    normalize_identifiers,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    sha256_canonical,
)


class AssessmentConfidence(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ObservationStatus(str, Enum):
    OBSERVED = "observed"
    POTENTIAL_CONCERN = "potential_concern"
    UNRESOLVED = "unresolved"
    NOT_OBSERVED = "not_observed"


@dataclass(frozen=True, slots=True)
class InstitutionalObservation:
    observation_id: str
    institution_id: str
    mandate_id: str
    projection_id: str
    source_release_digest: str
    fact_ids: tuple[str, ...]
    category: str
    status: ObservationStatus
    statement: str
    rationale_codes: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    synthetic: bool = True
    legal_effect: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "observation_id",
            "institution_id",
            "mandate_id",
            "projection_id",
            "category",
        ):
            object.__setattr__(
                self,
                field_name,
                require_identifier(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "source_release_digest",
            require_sha256(
                self.source_release_digest,
                "source_release_digest",
            ),
        )
        fact_ids = normalize_identifiers(self.fact_ids, "fact_ids")
        if not fact_ids:
            raise ScenarioConfigurationError("fact_ids must not be empty")
        object.__setattr__(self, "fact_ids", fact_ids)
        if not isinstance(self.status, ObservationStatus):
            raise TypeError("status must be an ObservationStatus")
        object.__setattr__(
            self,
            "statement",
            require_text(self.statement, "statement"),
        )
        rationale_codes = normalize_identifiers(
            self.rationale_codes,
            "rationale_codes",
        )
        if not rationale_codes:
            raise ScenarioConfigurationError(
                "rationale_codes must not be empty"
            )
        object.__setattr__(self, "rationale_codes", rationale_codes)
        object.__setattr__(
            self,
            "limitations",
            _normalize_text_tuple(self.limitations, "limitations"),
        )
        _require_synthetic_scope(self.synthetic, self.legal_effect)
        to_canonical_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "institution_id": self.institution_id,
            "mandate_id": self.mandate_id,
            "projection_id": self.projection_id,
            "source_release_digest": self.source_release_digest,
            "fact_ids": list(self.fact_ids),
            "category": self.category,
            "status": self.status.value,
            "statement": self.statement,
            "rationale_codes": list(self.rationale_codes),
            "limitations": list(self.limitations),
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class InstitutionalAssessment:
    assessment_id: str
    scenario_id: str
    stage: ScenarioStage
    institution_id: str
    mandate_id: str
    projection_id: str
    source_release_digest: str
    assessed_at: str
    assessed_fact_ids: tuple[str, ...]
    observations: tuple[InstitutionalObservation, ...]
    unresolved_questions: tuple[str, ...]
    confidence_status: AssessmentConfidence
    limitations: tuple[str, ...]
    metadata: Mapping[str, Any]
    assessment_digest: str
    synthetic: bool = True
    legal_effect: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "assessment_id",
            "scenario_id",
            "institution_id",
            "mandate_id",
            "projection_id",
        ):
            object.__setattr__(
                self,
                field_name,
                require_identifier(getattr(self, field_name), field_name),
            )
        if not isinstance(self.stage, ScenarioStage):
            raise TypeError("stage must be a ScenarioStage")
        object.__setattr__(
            self,
            "source_release_digest",
            require_sha256(
                self.source_release_digest,
                "source_release_digest",
            ),
        )
        object.__setattr__(
            self,
            "assessed_at",
            require_timestamp(self.assessed_at, "assessed_at"),
        )
        assessed_fact_ids = normalize_identifiers(
            self.assessed_fact_ids,
            "assessed_fact_ids",
        )
        object.__setattr__(self, "assessed_fact_ids", assessed_fact_ids)
        if not isinstance(self.observations, tuple):
            raise TypeError("observations must be a tuple")
        if any(
            not isinstance(item, InstitutionalObservation)
            for item in self.observations
        ):
            raise TypeError(
                "observations must contain InstitutionalObservation objects"
            )
        observation_ids = tuple(
            item.observation_id for item in self.observations
        )
        if len(observation_ids) != len(set(observation_ids)):
            raise ScenarioConfigurationError(
                "observations must not contain duplicate identifiers"
            )
        for observation in self.observations:
            if observation.institution_id != self.institution_id:
                raise ScenarioConfigurationError(
                    "observation institution does not match assessment"
                )
            if observation.mandate_id != self.mandate_id:
                raise ScenarioConfigurationError(
                    "observation mandate does not match assessment"
                )
            if observation.projection_id != self.projection_id:
                raise ScenarioConfigurationError(
                    "observation projection does not match assessment"
                )
            if observation.source_release_digest != self.source_release_digest:
                raise ScenarioConfigurationError(
                    "observation release digest does not match assessment"
                )
            if not set(observation.fact_ids).issubset(assessed_fact_ids):
                raise ScenarioAccessError(
                    "observation references a fact outside the assessed projection"
                )
        object.__setattr__(
            self,
            "unresolved_questions",
            _normalize_text_tuple(
                self.unresolved_questions,
                "unresolved_questions",
            ),
        )
        if not isinstance(self.confidence_status, AssessmentConfidence):
            raise TypeError(
                "confidence_status must be an AssessmentConfidence"
            )
        object.__setattr__(
            self,
            "limitations",
            _normalize_text_tuple(self.limitations, "limitations"),
        )
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        metadata = deep_freeze(self.metadata)
        prohibited = {
            "recommended_action",
            "approval_decision",
            "authorization_result",
            "distribution_disposition",
            "national_legal_finding",
        }
        if prohibited.intersection(metadata):
            raise ScenarioConfigurationError(
                "assessment metadata must not contain governance decisions"
            )
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(
            self,
            "assessment_digest",
            require_sha256(self.assessment_digest, "assessment_digest"),
        )
        _require_synthetic_scope(self.synthetic, self.legal_effect)
        if self.assessment_digest != self.compute_digest():
            raise ScenarioConfigurationError(
                "assessment_digest does not match assessment contents"
            )
        to_canonical_json(self.to_dict())

    def digest_payload(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "scenario_id": self.scenario_id,
            "stage": int(self.stage),
            "institution_id": self.institution_id,
            "mandate_id": self.mandate_id,
            "projection_id": self.projection_id,
            "source_release_digest": self.source_release_digest,
            "assessed_at": self.assessed_at,
            "assessed_fact_ids": list(self.assessed_fact_ids),
            "observations": [item.to_dict() for item in self.observations],
            "unresolved_questions": list(self.unresolved_questions),
            "confidence_status": self.confidence_status.value,
            "limitations": list(self.limitations),
            "metadata": self.metadata,
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }

    def compute_digest(self) -> str:
        return sha256_canonical(self.digest_payload())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.digest_payload(),
            "assessment_digest": self.assessment_digest,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


def _normalize_text_tuple(
    value: object,
    field_name: str,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    normalized = tuple(
        require_text(item, f"{field_name} item")
        for item in value
    )
    if len(normalized) != len(set(normalized)):
        raise ScenarioConfigurationError(
            f"{field_name} must not contain duplicates"
        )
    return normalized


def _require_synthetic_scope(
    synthetic: object,
    legal_effect: object,
) -> None:
    if type(synthetic) is not bool or type(legal_effect) is not bool:
        raise TypeError(
            "synthetic and legal_effect must be strict Booleans"
        )
    if not synthetic:
        raise ScenarioConfigurationError(
            "institutional assessments must remain synthetic"
        )
    if legal_effect:
        raise ScenarioConfigurationError(
            "institutional assessments must not create legal effect"
        )
