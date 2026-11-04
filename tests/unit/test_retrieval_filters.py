from __future__ import annotations

from datetime import datetime, timezone
import pytest

from amba_ai.governance.models import ActivationStatus, BindingLevel
from amba_ai.rag.retrieval_filters import RetrievalFilter, filter_policy_records


def test_filter_validation() -> None:
    with pytest.raises(TypeError):
        RetrievalFilter(binding_levels=[BindingLevel.PROJECT_CONTROL])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        RetrievalFilter(binding_levels=(BindingLevel.PROJECT_CONTROL, BindingLevel.PROJECT_CONTROL))
    with pytest.raises(TypeError):
        RetrievalFilter(binding_use=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone-aware"):
        RetrievalFilter(effective_at=datetime(2026, 1, 1))


def test_empty_records_are_deterministic() -> None:
    assert filter_policy_records((), RetrievalFilter()) == ()


def test_invalid_record_values_are_rejected() -> None:
    with pytest.raises(TypeError, match="PolicyRecord"):
        filter_policy_records((object(),), RetrievalFilter())  # type: ignore[arg-type]


def test_string_and_mapping_are_not_record_iterables() -> None:
    with pytest.raises(TypeError):
        filter_policy_records("records", RetrievalFilter())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        filter_policy_records({}, RetrievalFilter())  # type: ignore[arg-type]


def test_filter_normalization() -> None:
    criteria = RetrievalFilter(jurisdiction=" Ethiopia ", language=" EN ", binding_levels=(BindingLevel.PROJECT_CONTROL,), effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert criteria.jurisdiction == "Ethiopia"
    assert criteria.language == "en"
    assert criteria.effective_at.tzinfo is not None
