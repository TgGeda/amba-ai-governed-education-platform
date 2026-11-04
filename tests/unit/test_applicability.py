from __future__ import annotations

import pytest

from amba_ai.governance.applicability import (
    PolicyApplicabilityEvaluation,
    aggregate_applicability,
)
from amba_ai.governance.errors import GovernanceApplicabilityError
from amba_ai.governance.models import ApplicabilityStatus


def _evaluation(status: ApplicabilityStatus, *, evaluator: str = "evaluator", record: str = "record", questions: tuple[str, ...] = ()) -> PolicyApplicabilityEvaluation:
    return PolicyApplicabilityEvaluation(
        evaluator_id=evaluator,
        event_id="event",
        policy_record_id=record,
        status=status,
        rationale_code="TEST",
        unresolved_questions=questions,
    )


def test_applicable_is_resolved() -> None:
    value = _evaluation(ApplicabilityStatus.APPLICABLE)
    value.require_resolved()
    assert aggregate_applicability((value,)) is ApplicabilityStatus.APPLICABLE


def test_unresolved_is_preserved_and_fails_closed() -> None:
    value = _evaluation(ApplicabilityStatus.UNRESOLVED, questions=("Resolve scope",))
    with pytest.raises(GovernanceApplicabilityError, match="unresolved"):
        value.require_resolved()
    assert aggregate_applicability((value,)) is ApplicabilityStatus.UNRESOLVED


def test_unresolved_dominates_mixed_results() -> None:
    values = (
        _evaluation(ApplicabilityStatus.APPLICABLE, evaluator="a"),
        _evaluation(ApplicabilityStatus.UNRESOLVED, evaluator="b", questions=("Question",)),
    )
    assert aggregate_applicability(values) is ApplicabilityStatus.UNRESOLVED


def test_empty_aggregation_fails_closed() -> None:
    assert aggregate_applicability(()) is ApplicabilityStatus.UNRESOLVED


def test_duplicate_evaluator_record_pair_is_rejected() -> None:
    value = _evaluation(ApplicabilityStatus.APPLICABLE)
    with pytest.raises((ValueError, GovernanceApplicabilityError)):
        aggregate_applicability((value, value))


def test_evaluation_serialization_is_deterministic() -> None:
    value = _evaluation(ApplicabilityStatus.UNRESOLVED, questions=(" B ", " A "))
    assert value.unresolved_questions == ("A", "B")
    assert value.to_canonical_json() == value.to_canonical_json()
