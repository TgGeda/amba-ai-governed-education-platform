from __future__ import annotations

import pytest

from amba_ai.governance.verified_unicef_records import (
    CandidateLocatorStatus,
    CandidateRecordStatus,
    UNICEFRecordError,
    assert_not_promotable_to_policy_record,
    quarantined_unicef_supporting_evidence_records,
    unicef_candidate_records_by_id,
)


def test_unicef_record_set_contains_exactly_eight_verified_themes() -> None:
    records = quarantined_unicef_supporting_evidence_records()
    assert len(records) == 8
    assert {record.theme for record in records} == {
        "child-centred AI safeguards",
        "privacy and data governance",
        "human oversight",
        "protection against commercial exploitation",
        "inclusion",
        "EdTech assessment",
        "local and offline operation",
        "child participation",
    }


def test_unicef_candidates_preserve_nonbinding_quarantine_boundary() -> None:
    for record in quarantined_unicef_supporting_evidence_records():
        assert record.source_id == "UNICEF-AI-CHILDREN-3.0"
        assert record.version_id == "3.0"
        assert record.publication_date == "December 2025"
        assert record.source_class == "international_guidance"
        assert record.binding_level == "international_guidance"
        assert record.record_status is CandidateRecordStatus.HUMAN_REVIEW_REQUIRED
        assert record.locator_status is CandidateLocatorStatus.UNRESOLVED
        assert record.official_locator is None
        assert record.page_start is None and record.page_end is None
        assert record.exact_source_excerpt is None
        assert record.exact_source_excerpt_sha256 is None
        assert record.national_binding_status is False
        assert record.eligible_for_binding_findings is False
        assert record.eligible_for_supporting_evidence is True
        assert record.eligible_for_citation is False
        assert record.independent_ethiopian_legal_violation is False
        assert record.human_review_required is True
        assert len(record.boundary_sha256) == 64


def test_unicef_candidates_are_indexed_by_unique_id() -> None:
    by_id = unicef_candidate_records_by_id()
    assert len(by_id) == 8
    assert tuple(by_id) == tuple(record.candidate_id for record in quarantined_unicef_supporting_evidence_records())


def test_unlocated_unicef_candidate_cannot_be_promoted() -> None:
    record = quarantined_unicef_supporting_evidence_records()[0]
    with pytest.raises(UNICEFRecordError, match="cannot become a PolicyRecord"):
        assert_not_promotable_to_policy_record(record)
