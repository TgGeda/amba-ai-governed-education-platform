from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from amba_ai.governance.models import to_canonical_json
from amba_ai.institutional.assessment import (
    InstitutionalAssessment,
)
from amba_ai.scenarios.models import (
    ScenarioConfigurationError,
    normalize_identifiers,
    require_identifier,
    require_text,
)


class InstitutionalConflictKind(str, Enum):
    OBSERVATION_STATUS_DIVERGENCE = (
        "observation_status_divergence"
    )
    CONFIDENCE_DIVERGENCE = "confidence_divergence"
    CATEGORY_DIVERGENCE = "category_divergence"


@dataclass(frozen=True, slots=True)
class SourcedQuestion:
    institution_id: str
    mandate_id: str
    assessment_id: str
    question: str

    def __post_init__(self) -> None:
        for field_name in (
            "institution_id",
            "mandate_id",
            "assessment_id",
        ):
            object.__setattr__(
                self,
                field_name,
                require_identifier(
                    getattr(self, field_name),
                    field_name,
                ),
            )
        object.__setattr__(
            self,
            "question",
            require_text(self.question, "question"),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "institution_id": self.institution_id,
            "mandate_id": self.mandate_id,
            "assessment_id": self.assessment_id,
            "question": self.question,
        }


@dataclass(frozen=True, slots=True)
class InstitutionalConflict:
    conflict_id: str
    kind: InstitutionalConflictKind
    assessment_ids: tuple[str, ...]
    institution_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    category: str | None
    descriptions: tuple[str, ...]
    preserved: bool = True
    resolved: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "conflict_id",
            require_identifier(
                self.conflict_id,
                "conflict_id",
            ),
        )
        if not isinstance(
            self.kind,
            InstitutionalConflictKind,
        ):
            raise TypeError(
                "kind must be an InstitutionalConflictKind"
            )
        for field_name in (
            "assessment_ids",
            "institution_ids",
        ):
            values = normalize_identifiers(
                getattr(self, field_name),
                field_name,
            )
            if len(values) < 2:
                raise ScenarioConfigurationError(
                    f"{field_name} must identify at least two sources"
                )
            object.__setattr__(self, field_name, values)
        object.__setattr__(
            self,
            "fact_ids",
            normalize_identifiers(
                self.fact_ids,
                "fact_ids",
            ),
        )
        if self.category is not None:
            object.__setattr__(
                self,
                "category",
                require_identifier(
                    self.category,
                    "category",
                ),
            )
        if not isinstance(self.descriptions, tuple):
            raise TypeError(
                "descriptions must be a tuple"
            )
        descriptions = tuple(
            require_text(item, "description")
            for item in self.descriptions
        )
        if len(descriptions) != len(
            set(descriptions)
        ):
            raise ScenarioConfigurationError(
                "descriptions must not contain duplicates"
            )
        if len(descriptions) < 2:
            raise ScenarioConfigurationError(
                "a conflict must preserve at least two descriptions"
            )
        object.__setattr__(
            self,
            "descriptions",
            descriptions,
        )
        if type(self.preserved) is not bool:
            raise TypeError(
                "preserved must be a strict Boolean"
            )
        if type(self.resolved) is not bool:
            raise TypeError(
                "resolved must be a strict Boolean"
            )
        if not self.preserved or self.resolved:
            raise ScenarioConfigurationError(
                "institutional conflicts must remain preserved "
                "and unresolved at coordination time"
            )
        to_canonical_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "kind": self.kind.value,
            "assessment_ids": list(
                self.assessment_ids
            ),
            "institution_ids": list(
                self.institution_ids
            ),
            "fact_ids": list(self.fact_ids),
            "category": self.category,
            "descriptions": list(
                self.descriptions
            ),
            "preserved": self.preserved,
            "resolved": self.resolved,
        }


class InstitutionalConflictDetector:
    def detect(
        self,
        assessments: tuple[
            InstitutionalAssessment,
            ...,
        ],
    ) -> tuple[InstitutionalConflict, ...]:
        if not isinstance(assessments, tuple):
            raise TypeError(
                "assessments must be a tuple"
            )
        if any(
            not isinstance(
                assessment,
                InstitutionalAssessment,
            )
            for assessment in assessments
        ):
            raise TypeError(
                "assessments must contain "
                "InstitutionalAssessment objects"
            )
        conflicts: list[InstitutionalConflict] = []
        ordered = tuple(
            sorted(
                assessments,
                key=lambda item: (
                    item.institution_id,
                    item.assessment_id,
                ),
            )
        )
        for left_index, left in enumerate(ordered):
            for right in ordered[left_index + 1 :]:
                conflicts.extend(
                    self._pair_conflicts(left, right)
                )
        return tuple(
            sorted(
                conflicts,
                key=lambda item: item.conflict_id,
            )
        )

    def _pair_conflicts(
        self,
        left: InstitutionalAssessment,
        right: InstitutionalAssessment,
    ) -> tuple[InstitutionalConflict, ...]:
        conflicts: list[InstitutionalConflict] = []
        shared_facts = tuple(
            sorted(
                set(left.assessed_fact_ids).intersection(
                    right.assessed_fact_ids
                )
            )
        )
        if (
            shared_facts
            and left.confidence_status
            is not right.confidence_status
        ):
            conflicts.append(
                self._conflict(
                    kind=(
                        InstitutionalConflictKind
                        .CONFIDENCE_DIVERGENCE
                    ),
                    left=left,
                    right=right,
                    fact_ids=shared_facts,
                    category=None,
                    descriptions=(
                        (
                            f"{left.institution_id}:"
                            f"{left.confidence_status.value}"
                        ),
                        (
                            f"{right.institution_id}:"
                            f"{right.confidence_status.value}"
                        ),
                    ),
                )
            )
        left_observations = {
            (fact_id, observation.category): observation
            for observation in left.observations
            for fact_id in observation.fact_ids
        }
        right_observations = {
            (fact_id, observation.category): observation
            for observation in right.observations
            for fact_id in observation.fact_ids
        }
        for key in sorted(
            set(left_observations).intersection(
                right_observations
            )
        ):
            left_observation = left_observations[key]
            right_observation = right_observations[key]
            if (
                left_observation.status
                is right_observation.status
                and left_observation.statement
                == right_observation.statement
            ):
                continue
            conflicts.append(
                self._conflict(
                    kind=(
                        InstitutionalConflictKind
                        .OBSERVATION_STATUS_DIVERGENCE
                    ),
                    left=left,
                    right=right,
                    fact_ids=(key[0],),
                    category=key[1],
                    descriptions=(
                        (
                            f"{left.institution_id}: "
                            f"{left_observation.status.value}: "
                            f"{left_observation.statement}"
                        ),
                        (
                            f"{right.institution_id}: "
                            f"{right_observation.status.value}: "
                            f"{right_observation.statement}"
                        ),
                    ),
                )
            )
        return tuple(conflicts)

    @staticmethod
    def _conflict(
        *,
        kind: InstitutionalConflictKind,
        left: InstitutionalAssessment,
        right: InstitutionalAssessment,
        fact_ids: tuple[str, ...],
        category: str | None,
        descriptions: tuple[str, ...],
    ) -> InstitutionalConflict:
        identity = "__".join(
            (
                kind.value,
                left.assessment_id,
                right.assessment_id,
                category or "none",
                *fact_ids,
            )
        )
        normalized = "".join(
            character
            if character.isalnum()
            else "_"
            for character in identity
        )
        return InstitutionalConflict(
            conflict_id=(
                f"conflict:{normalized[:110]}"
            ),
            kind=kind,
            assessment_ids=(
                left.assessment_id,
                right.assessment_id,
            ),
            institution_ids=(
                left.institution_id,
                right.institution_id,
            ),
            fact_ids=fact_ids,
            category=category,
            descriptions=descriptions,
        )
