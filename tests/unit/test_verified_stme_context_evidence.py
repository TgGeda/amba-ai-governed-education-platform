from __future__ import annotations

import pytest

from amba_ai.governance.verified_stme_context_evidence import (
    EvidenceActivationStatus,
    LocatorVerificationStatus,
    STMEContextEvidenceError,
    assert_not_eligible_for_policy_record_activation,
    stme_context_evidence_by_id,
    verified_stme_context_evidence,
)


def test_stme_context_evidence_contains_exactly_seven_verified_themes() -> None:
    records = verified_stme_context_evidence()
    assert len(records) == 7
    assert {record.theme for record in records} == {
        "science, technology, and mathematics education context",
        "curriculum-reform context",
        "teacher-development context",
        "educational-resource analysis",
        "inclusion",
        "monitoring and evaluation",
        "stakeholder partnerships",
    }


def test_stme_evidence_preserves_adoption_and_authority_boundaries() -> None:
    for record in verified_stme_context_evidence():
        assert record.source_id == "ETH-STME-POLICY"
        assert record.version_id == "undated-main-document"
        assert record.source_class == "strategic_policy_supporting_document"
        assert record.binding_level == "policy_context"
        assert record.formal_adoption_status == "unverified"
        assert record.activation_status is EvidenceActivationStatus.VERIFIED_CONTEXT_BOUNDARY
        assert record.locator_verification_status is LocatorVerificationStatus.NOT_ASSESSED
        assert record.official_locator is None
        assert record.page_start is None and record.page_end is None
        assert record.exact_source_excerpt is None
        assert record.exact_source_excerpt_sha256 is None
        assert record.eligible_for_policy_context is True
        assert record.eligible_for_readiness_evidence is True
        assert record.eligible_for_binding_findings is False
        assert record.eligible_for_project_enforcement is False
        assert record.eligible_for_citation is False
        assert record.national_binding_status is False
        assert record.legal_effect is False
        assert record.formal_adoption_claimed is False
        assert record.human_validation_required_for_locator_activation is True
        assert len(record.boundary_sha256) == 64


def test_stme_context_evidence_is_indexed_by_unique_id() -> None:
    by_id = stme_context_evidence_by_id()
    assert len(by_id) == 7
    assert tuple(by_id) == tuple(
        record.evidence_id for record in verified_stme_context_evidence()
    )


def test_stme_context_evidence_cannot_activate_without_locator_validation() -> None:
    with pytest.raises(STMEContextEvidenceError, match="cannot be activated"):
        assert_not_eligible_for_policy_record_activation(
            verified_stme_context_evidence()[0]
        )
