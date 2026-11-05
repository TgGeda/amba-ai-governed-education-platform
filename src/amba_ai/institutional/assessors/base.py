from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from amba_ai.governance.models import IdentifierProvider
from amba_ai.institutional.assessment import (
    AssessmentConfidence,
    InstitutionalAssessment,
    InstitutionalObservation,
    ObservationStatus,
)
from amba_ai.institutional.models import InstitutionalContextProjection
from amba_ai.scenarios.clock import ScenarioClockProtocol
from amba_ai.scenarios.models import (
    ScenarioConfigurationError,
    ScenarioFact,
    require_identifier,
    require_text,
    sha256_canonical,
)


@dataclass(frozen=True, slots=True)
class ObservationDraft:
    fact_ids: tuple[str, ...]
    category: str
    status: ObservationStatus
    statement: str
    rationale_codes: tuple[str, ...]
    limitations: tuple[str, ...] = ()


@runtime_checkable
class InstitutionalAssessorProtocol(Protocol):
    institution_id: str
    mandate_id: str
    recipient_id: str

    def assess(
        self,
        projection: InstitutionalContextProjection,
    ) -> InstitutionalAssessment:
        ...


class BaseInstitutionalAssessor:
    institution_id: str
    mandate_id: str
    recipient_id: str
    relevant_fact_types: frozenset[str]

    def __init__(
        self,
        *,
        identifier_provider: IdentifierProvider,
        clock: ScenarioClockProtocol,
    ) -> None:
        if not callable(getattr(identifier_provider, "new_id", None)):
            raise TypeError("identifier_provider must provide new_id")
        if not isinstance(clock, ScenarioClockProtocol):
            raise TypeError("clock must implement ScenarioClockProtocol")
        self._identifier_provider = identifier_provider
        self._clock = clock
        for field_name in (
            "institution_id",
            "mandate_id",
            "recipient_id",
        ):
            require_identifier(getattr(self, field_name), field_name)
        if not self.relevant_fact_types:
            raise ScenarioConfigurationError(
                "relevant_fact_types must not be empty"
            )

    def assess(
        self,
        projection: InstitutionalContextProjection,
    ) -> InstitutionalAssessment:
        if not isinstance(projection, InstitutionalContextProjection):
            raise TypeError(
                "projection must be an InstitutionalContextProjection"
            )
        if projection.recipient_id != self.recipient_id:
            raise PermissionError(
                "projection recipient is outside the assessor mandate"
            )
        if projection.legal_effect or not projection.synthetic:
            raise ScenarioConfigurationError(
                "assessors accept only synthetic projections without legal effect"
            )
        facts = tuple(
            fact
            for fact in projection.facts
            if fact.fact_type in self.relevant_fact_types
        )
        drafts, unresolved, limitations = self._analyze(
            projection,
            facts,
        )
        observations = tuple(
            self._build_observation(projection, draft)
            for draft in drafts
        )
        assessed_fact_ids = tuple(fact.fact_id for fact in facts)
        confidence = self._confidence(
            facts=facts,
            observations=observations,
            unresolved=unresolved,
        )
        assessment_id = require_identifier(
            self._identifier_provider.new_id("assessment"),
            "generated assessment_id",
        )
        snapshot = self._clock.snapshot()
        metadata = {
            "projection_scope_preserved": True,
            "mandate_scope_preserved": True,
            "governance_recommendation_created": False,
            "approval_created": False,
            "execution_requested": False,
            "distribution_attempted": False,
            "national_legal_determination_created": False,
        }
        payload = {
            "assessment_id": assessment_id,
            "scenario_id": projection.scenario_id,
            "stage": int(projection.stage),
            "institution_id": self.institution_id,
            "mandate_id": self.mandate_id,
            "projection_id": projection.projection_id,
            "source_release_digest": projection.source_release_digest,
            "assessed_at": snapshot.timestamp,
            "assessed_fact_ids": list(assessed_fact_ids),
            "observations": [item.to_dict() for item in observations],
            "unresolved_questions": list(unresolved),
            "confidence_status": confidence.value,
            "limitations": list(limitations),
            "metadata": metadata,
            "synthetic": True,
            "legal_effect": False,
        }
        return InstitutionalAssessment(
            assessment_id=assessment_id,
            scenario_id=projection.scenario_id,
            stage=projection.stage,
            institution_id=self.institution_id,
            mandate_id=self.mandate_id,
            projection_id=projection.projection_id,
            source_release_digest=projection.source_release_digest,
            assessed_at=snapshot.timestamp,
            assessed_fact_ids=assessed_fact_ids,
            observations=observations,
            unresolved_questions=tuple(unresolved),
            confidence_status=confidence,
            limitations=tuple(limitations),
            metadata=metadata,
            assessment_digest=sha256_canonical(payload),
        )

    def _build_observation(
        self,
        projection: InstitutionalContextProjection,
        draft: ObservationDraft,
    ) -> InstitutionalObservation:
        if not set(draft.fact_ids).issubset(projection.fact_ids):
            raise ScenarioConfigurationError(
                "observation draft references a fact outside the projection"
            )
        return InstitutionalObservation(
            observation_id=require_identifier(
                self._identifier_provider.new_id("observation"),
                "generated observation_id",
            ),
            institution_id=self.institution_id,
            mandate_id=self.mandate_id,
            projection_id=projection.projection_id,
            source_release_digest=projection.source_release_digest,
            fact_ids=draft.fact_ids,
            category=draft.category,
            status=draft.status,
            statement=draft.statement,
            rationale_codes=draft.rationale_codes,
            limitations=draft.limitations,
        )

    @staticmethod
    def _fact_text(fact: ScenarioFact) -> str:
        return " ".join(
            (
                fact.fact_type,
                _flatten_values(fact.payload),
            )
        ).lower()

    @staticmethod
    def _confidence(
        *,
        facts: tuple[ScenarioFact, ...],
        observations: tuple[InstitutionalObservation, ...],
        unresolved: tuple[str, ...],
    ) -> AssessmentConfidence:
        if not facts:
            return AssessmentConfidence.INSUFFICIENT_EVIDENCE
        if unresolved:
            return AssessmentConfidence.LOW
        if any(
            item.status is ObservationStatus.POTENTIAL_CONCERN
            for item in observations
        ):
            return AssessmentConfidence.MODERATE
        return AssessmentConfidence.HIGH

    def _analyze(
        self,
        projection: InstitutionalContextProjection,
        facts: tuple[ScenarioFact, ...],
    ) -> tuple[
        tuple[ObservationDraft, ...],
        tuple[str, ...],
        tuple[str, ...],
    ]:
        raise NotImplementedError


def _flatten_values(value: object) -> str:
    if isinstance(value, Mapping):
        return " ".join(
            f"{key} {_flatten_values(item)}"
            for key, item in value.items()
        )
    if isinstance(value, (tuple, list)):
        return " ".join(_flatten_values(item) for item in value)
    return str(value)


def contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term.lower() in text for term in terms)
