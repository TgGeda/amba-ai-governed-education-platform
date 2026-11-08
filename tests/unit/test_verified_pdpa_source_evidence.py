from __future__ import annotations

import pytest

from amba_ai.governance.verified_pdpa_source_evidence import (
    EvidenceActivationStatus,
    PDPASourceEvidenceError,
    VerificationStatus,
    assert_binding_finding_not_activatable,
    verified_pdpa_source_evidence,
)


def test_pdpa_source_identity_and_classification_are_exact() -> None:
    evidence = verified_pdpa_source_evidence()
    assert evidence.source_id == "ETH-PDPA-1321-2024"
    assert evidence.version_id == "1321-2024"
    assert evidence.canonical_title == "Personal Data Protection Proclamation No. 1321/2024"
    assert evidence.jurisdiction == "Ethiopia"
    assert evidence.source_class == "primary_legislation"
    assert evidence.binding_level == "primary_legislation"
    assert evidence.artifact_sha256 == (
        "f4e1eb0c4a6948d34accc3a93dbe32010af851f6cfb7f4b17a66ba94e2df0bf6"
    )
    assert evidence.activation_status is EvidenceActivationStatus.VERIFIED_SOURCE_BOUNDARY


def test_pdpa_bilingual_boundary_prevents_translation_overclaim() -> None:
    evidence = verified_pdpa_source_evidence()
    assert evidence.extraction_profile == "ethiopian_bilingual_columns_v1"
    assert evidence.physical_page_association_preserved is True
    assert evidence.languages == ("am", "en")
    assert evidence.left_column_language == "am"
    assert evidence.right_column_language == "en"
    assert evidence.cross_language_merge_permitted is False
    assert evidence.translation_equivalence_claimed is False
    assert evidence.translation_status is VerificationStatus.NOT_VERIFIED
    assert evidence.official_translation_verified is False


def test_pdpa_locator_legal_review_and_applicability_remain_unresolved() -> None:
    evidence = verified_pdpa_source_evidence()
    assert evidence.metadata_verification_status is VerificationStatus.VERIFIED
    assert evidence.locator_verification_status is VerificationStatus.NOT_ASSESSED
    assert evidence.exact_excerpt_verification_status is VerificationStatus.NOT_ASSESSED
    assert evidence.legal_review_status is VerificationStatus.NOT_PERFORMED
    assert evidence.applicability_status is VerificationStatus.UNRESOLVED
    assert evidence.official_locator is None
    assert evidence.page_start is None and evidence.page_end is None
    assert evidence.exact_source_excerpt is None
    assert evidence.exact_source_excerpt_sha256 is None
    assert evidence.regulated_actor is None
    assert evidence.processing_operation is None
    assert evidence.applicable_effective_date is None
    assert evidence.exceptions_reviewed is False
    assert evidence.applicability_evaluation_completed is False


def test_pdpa_eligibility_and_prohibited_claims_fail_closed() -> None:
    evidence = verified_pdpa_source_evidence()
    assert evidence.eligible_for_legal_context is True
    assert evidence.eligible_for_readiness_evidence is True
    assert evidence.eligible_for_binding_legal_findings is False
    assert evidence.eligible_for_project_enforcement is False
    assert evidence.eligible_for_citation is False
    assert evidence.binding_finding_activation_ready is False
    assert len(evidence.binding_finding_requirements) == 9
    assert evidence.legal_review_completed is False
    assert evidence.automatic_legal_violation is False
    assert evidence.automatic_statutory_block is False
    assert evidence.earlier_prototype_articles_authoritative is False


def test_pdpa_binding_activation_fails_closed() -> None:
    with pytest.raises(PDPASourceEvidenceError, match="all nine exact-evidence"):
        assert_binding_finding_not_activatable(verified_pdpa_source_evidence())
