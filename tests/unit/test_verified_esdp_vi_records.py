from __future__ import annotations

import pytest

from amba_ai.governance.verified_esdp_vi_records import (
    CandidateLocatorStatus,
    CandidateRecordStatus,
    ESDPVIRecordError,
    assert_not_promotable_to_policy_record,
    esdp_vi_candidates_by_id,
    quarantined_esdp_vi_candidates,
)


def test_esdp_vi_candidate_set_contains_exactly_seven_verified_themes() -> None:
    records = quarantined_esdp_vi_candidates()
    assert len(records) == 7
    assert {record.theme for record in records} == {
        "education-sector context",
        "digitization context",
        "quality and equity analysis",
        "curriculum reform",
        "teacher development",
        "infrastructure analysis",
        "project-level readiness evidence",
    }


def test_esdp_vi_candidates_preserve_historical_boundary() -> None:
    for record in quarantined_esdp_vi_candidates():
        assert record.source_id == "ETH-ESDP-VI-2021"
        assert record.version_id == "2021"
        assert record.programme_period == "2020/21–2024/25"
        assert record.current_classification == "historical_or_completed"
        assert record.source_class == "sector_strategy"
        assert record.binding_level == "national_policy"
        assert record.record_status is CandidateRecordStatus.HUMAN_REVIEW_REQUIRED
        assert record.locator_status is CandidateLocatorStatus.UNRESOLVED
        assert record.official_locator is None
        assert record.page_start is None and record.page_end is None
        assert record.exact_source_excerpt is None
        assert record.exact_source_excerpt_sha256 is None
        assert record.eligible_for_historical_context is True
        assert record.eligible_for_policy_context is True
        assert record.eligible_for_readiness_evidence is True
        assert record.eligible_for_current_programme_claim is False
        assert record.eligible_for_binding_legal_findings is False
        assert record.eligible_for_project_enforcement is False
        assert record.eligible_for_citation is False
        assert record.national_binding_status is False
        assert record.legal_effect is False
        assert record.human_review_required is True
        assert record.historical_qualification_required is True
        assert record.current_after_2024_25 is False
        assert record.verified_successor_identified is False
        assert len(record.boundary_sha256) == 64


def test_esdp_vi_candidates_prohibit_current_and_binding_claims() -> None:
    for record in quarantined_esdp_vi_candidates():
        assert record.to_dict()["prohibited_claims"] == {
            "current_national_education_programme": False,
            "binding_legal_obligation": False,
            "statutory_offence": False,
            "statutory_penalty": False,
            "automatic_project_authorization": False,
            "automatic_project_block": False,
        }


def test_esdp_vi_candidates_are_indexed_by_unique_id() -> None:
    by_id = esdp_vi_candidates_by_id()
    assert len(by_id) == 7
    assert tuple(by_id) == tuple(
        record.candidate_id for record in quarantined_esdp_vi_candidates()
    )


def test_unlocated_esdp_vi_candidate_cannot_be_promoted() -> None:
    record = quarantined_esdp_vi_candidates()[0]
    with pytest.raises(ESDPVIRecordError, match="cannot become a PolicyRecord"):
        assert_not_promotable_to_policy_record(record)
