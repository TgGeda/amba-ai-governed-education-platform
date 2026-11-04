from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from amba_ai.governance.errors import (
    GovernanceApplicabilityError,
)
from amba_ai.governance.models import (
    ApplicabilityStatus,
    deep_freeze,
    to_canonical_json,
)


def _require_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(field_name, str):
        raise TypeError(
            "field_name must be a string"
        )

    normalized_field_name = field_name.strip()

    if not normalized_field_name:
        raise ValueError(
            "field_name must not be empty"
        )

    if not isinstance(value, str):
        raise TypeError(
            f"{normalized_field_name} must be a string"
        )

    normalized_value = value.strip()

    if not normalized_value:
        raise ValueError(
            f"{normalized_field_name} must not be empty"
        )

    return normalized_value


def _to_mutable_value(
    value: Any,
) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _to_mutable_value(nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, tuple):
        return [
            _to_mutable_value(item)
            for item in value
        ]

    if isinstance(value, list):
        return [
            _to_mutable_value(item)
            for item in value
        ]

    if isinstance(value, Enum):
        return value.value

    return value


@dataclass(frozen=True, slots=True)
class PolicyApplicabilityEvaluation:
    evaluator_id: str
    event_id: str
    policy_record_id: str
    status: ApplicabilityStatus
    rationale_code: str
    unresolved_questions: tuple[str, ...] = ()
    details: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        evaluator_id = _require_text(
            self.evaluator_id,
            "evaluator_id",
        )
        event_id = _require_text(
            self.event_id,
            "event_id",
        )
        policy_record_id = _require_text(
            self.policy_record_id,
            "policy_record_id",
        )
        rationale_code = _require_text(
            self.rationale_code,
            "rationale_code",
        )

        if not isinstance(
            self.status,
            ApplicabilityStatus,
        ):
            raise TypeError(
                "status must be an ApplicabilityStatus"
            )

        if not isinstance(
            self.unresolved_questions,
            tuple,
        ):
            raise TypeError(
                "unresolved_questions must be a tuple"
            )

        questions = tuple(
            _require_text(
                question,
                "unresolved_question",
            )
            for question in self.unresolved_questions
        )

        if len(questions) != len(set(questions)):
            raise ValueError(
                "unresolved_questions cannot contain "
                "duplicates"
            )

        normalized_questions = tuple(
            sorted(questions)
        )

        if (
            self.status
            is ApplicabilityStatus.UNRESOLVED
            and not normalized_questions
        ):
            raise ValueError(
                "unresolved applicability requires "
                "unresolved_questions"
            )

        if (
            self.status
            is not ApplicabilityStatus.UNRESOLVED
            and normalized_questions
        ):
            raise ValueError(
                "resolved applicability cannot contain "
                "unresolved_questions"
            )

        details: Mapping[str, Any]

        if self.details is None:
            details = {}
        else:
            details = self.details

        if not isinstance(details, Mapping):
            raise TypeError(
                "details must be a mapping"
            )

        frozen_details = deep_freeze(
            details
        )

        if not isinstance(
            frozen_details,
            MappingProxyType,
        ):
            raise TypeError(
                "deep_freeze must return an immutable "
                "mapping for details"
            )

        object.__setattr__(
            self,
            "evaluator_id",
            evaluator_id,
        )
        object.__setattr__(
            self,
            "event_id",
            event_id,
        )
        object.__setattr__(
            self,
            "policy_record_id",
            policy_record_id,
        )
        object.__setattr__(
            self,
            "rationale_code",
            rationale_code,
        )
        object.__setattr__(
            self,
            "unresolved_questions",
            normalized_questions,
        )
        object.__setattr__(
            self,
            "details",
            frozen_details,
        )

    @property
    def resolved(self) -> bool:
        return (
            self.status
            is not ApplicabilityStatus.UNRESOLVED
        )

    @property
    def applicable(self) -> bool:
        return (
            self.status
            is ApplicabilityStatus.APPLICABLE
        )

    def require_resolved(self) -> None:
        if not self.resolved:
            raise GovernanceApplicabilityError(
                "Applicability is unresolved for policy "
                f"record '{self.policy_record_id}'"
            )

    def require_applicable(self) -> None:
        if (
            self.status
            is ApplicabilityStatus.UNRESOLVED
        ):
            raise GovernanceApplicabilityError(
                "Applicability is unresolved for policy "
                f"record '{self.policy_record_id}'"
            )

        if (
            self.status
            is not ApplicabilityStatus.APPLICABLE
        ):
            raise GovernanceApplicabilityError(
                "Policy record "
                f"'{self.policy_record_id}' is not "
                f"applicable to event '{self.event_id}'"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluator_id": self.evaluator_id,
            "event_id": self.event_id,
            "policy_record_id": (
                self.policy_record_id
            ),
            "status": self.status.value,
            "rationale_code": self.rationale_code,
            "unresolved_questions": list(
                self.unresolved_questions
            ),
            "details": _to_mutable_value(
                self.details
            ),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(
            self.to_dict()
        )


def aggregate_applicability(
    evaluations: tuple[
        PolicyApplicabilityEvaluation,
        ...
    ],
) -> ApplicabilityStatus:
    if not isinstance(evaluations, tuple):
        raise TypeError(
            "evaluations must be a tuple"
        )

    if not evaluations:
        return ApplicabilityStatus.UNRESOLVED

    for evaluation in evaluations:
        if not isinstance(
            evaluation,
            PolicyApplicabilityEvaluation,
        ):
            raise TypeError(
                "evaluations must contain only "
                "PolicyApplicabilityEvaluation values"
            )

    event_ids = {
        evaluation.event_id
        for evaluation in evaluations
    }

    if len(event_ids) != 1:
        raise GovernanceApplicabilityError(
            "Applicability evaluations must belong "
            "to the same event"
        )

    evaluation_identities = tuple(
        (
            evaluation.evaluator_id,
            evaluation.policy_record_id,
        )
        for evaluation in evaluations
    )

    if len(evaluation_identities) != len(
        set(evaluation_identities)
    ):
        raise GovernanceApplicabilityError(
            "Applicability evaluations cannot contain "
            "duplicate evaluator and policy-record pairs"
        )

    if any(
        evaluation.status
        is ApplicabilityStatus.UNRESOLVED
        for evaluation in evaluations
    ):
        return ApplicabilityStatus.UNRESOLVED

    if any(
        evaluation.status
        is ApplicabilityStatus.APPLICABLE
        for evaluation in evaluations
    ):
        return ApplicabilityStatus.APPLICABLE

    return ApplicabilityStatus.NOT_APPLICABLE