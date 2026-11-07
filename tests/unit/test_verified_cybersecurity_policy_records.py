from __future__ import annotations

import pytest

from amba_ai.governance.verified_cybersecurity_policy_records import (
    CandidateLocatorStatus,
    CandidateRecordStatus,
    CybersecurityPolicyRecordError,
    assert_not_promotable_to_policy_record,
    cybersecurity_policy_candidates_by_id,
    quarantined_cybersecurity_policy_candidates,
)


def test_candidate_set_contains_exactly_nine_verified_themes() -> None:
    records = quarantined_cybersecurity_policy_candidates()
    assert len(records) == 9
    assert {record.theme for record in records} == {
        "cybersecurity governance",
        "shared responsibility",
        "privacy and security balance",
        "data-lifecycle governance",
        "education and capacity building",
        "indigenous research",
        "critical-infrastructure resilience",
        "institutional coordination",
        "monitoring and evaluation",
    }


def test_candidates_preserve_policy_context_and_readiness_boundary() -> None:
    for record in quarantined_cybersecurity_policy_candidates():
        assert record.source_id == "ETH-CYBERSECURITY-POLICY-2024"
        assert record.version_id == "2024-06"
        assert record.publication_date == "June 2024"
        assert record.administering_authority == "Information Network Security Administration"
        assert record.source_class == "national_policy"
        assert record.binding_level == "national_policy"
        assert record.record_status is CandidateRecordStatus.HUMAN_REVIEW_REQUIRED
        assert record.locator_status is CandidateLocatorStatus.UNRESOLVED
        assert record.official_locator is None
        assert record.page_start is None and record.page_end is None
        assert record.exact_source_excerpt is None
        assert record.exact_source_excerpt_sha256 is None
        assert record.eligible_for_policy_context is True
        assert record.eligible_for_readiness_evidence is True
        assert record.eligible_for_binding_legal_findings is False
        assert record.eligible_for_citation is False
        assert record.national_binding_status is False
        assert record.legal_effect is False
        assert record.human_review_required is True
        assert len(record.boundary_sha256) == 64


def test_candidates_prohibit_unsupported_legal_and_technical_claims() -> None:
    for record in quarantined_cybersecurity_policy_candidates():
        rendered = record.to_dict()["prohibited_claims"]
        assert rendered == {
            "criminal_offence": False,
            "statutory_penalty": False,
            "valid_guardian_consent": False,
            "binding_technical_threshold": False,
            "automatic_statutory_block": False,
        }


def test_candidates_are_indexed_by_unique_id() -> None:
    by_id = cybersecurity_policy_candidates_by_id()
    assert len(by_id) == 9
    assert tuple(by_id) == tuple(
        record.candidate_id for record in quarantined_cybersecurity_policy_candidates()
    )


def test_unlocated_candidate_cannot_be_promoted() -> None:
    record = quarantined_cybersecurity_policy_candidates()[0]
    with pytest.raises(CybersecurityPolicyRecordError, match="cannot become a PolicyRecord"):
        assert_not_promotable_to_policy_record(record)
