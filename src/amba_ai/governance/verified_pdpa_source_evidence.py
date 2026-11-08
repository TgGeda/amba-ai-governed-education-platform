from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

SOURCE_ID = "ETH-PDPA-1321-2024"
VERSION_ID = "1321-2024"
CANONICAL_TITLE = "Personal Data Protection Proclamation No. 1321/2024"
JURISDICTION = "Ethiopia"
SOURCE_CLASS = "primary_legislation"
BINDING_LEVEL = "primary_legislation"
SOURCE_RELATIVE_PATH = "kb/sources/ethiopia/ETH_PDPA_1321_2024.pdf"
ARTIFACT_SHA256 = "f4e1eb0c4a6948d34accc3a93dbe32010af851f6cfb7f4b17a66ba94e2df0bf6"
EXTRACTION_PROFILE = "ethiopian_bilingual_columns_v1"


class PDPASourceEvidenceError(ValueError):
    pass


class EvidenceActivationStatus(str, Enum):
    VERIFIED_SOURCE_BOUNDARY = "verified_source_boundary"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    NOT_ASSESSED = "not_assessed"
    NOT_VERIFIED = "not_verified"
    NOT_PERFORMED = "not_performed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class VerifiedPDPASourceEvidence:
    """Verified PDPA artifact and bilingual extraction boundary.

    This object deliberately contains no provision-level locator, exact legal
    excerpt, regulated actor, processing operation, effective date, exception
    conclusion, or binding legal finding. Those require separate verified
    provision evidence and completed applicability review.
    """

    evidence_id: str
    source_id: str
    version_id: str
    canonical_title: str
    jurisdiction: str
    source_class: str
    binding_level: str
    source_path: str
    artifact_sha256: str
    artifact_integrity_status: VerificationStatus
    pdf_magic_header_status: VerificationStatus
    activation_status: EvidenceActivationStatus
    extraction_profile: str
    physical_page_association_preserved: bool
    languages: tuple[str, str]
    left_column_language: str
    right_column_language: str
    cross_language_merge_permitted: bool
    translation_equivalence_claimed: bool
    metadata_verification_status: VerificationStatus
    locator_verification_status: VerificationStatus
    exact_excerpt_verification_status: VerificationStatus
    translation_status: VerificationStatus
    legal_review_status: VerificationStatus
    applicability_status: VerificationStatus
    official_locator: None
    page_start: None
    page_end: None
    exact_source_excerpt: None
    exact_source_excerpt_sha256: None
    regulated_actor: None
    processing_operation: None
    applicable_effective_date: None
    exceptions_reviewed: bool
    applicability_evaluation_completed: bool
    eligible_for_legal_context: bool
    eligible_for_readiness_evidence: bool
    eligible_for_binding_legal_findings: bool
    eligible_for_project_enforcement: bool
    eligible_for_citation: bool
    legal_review_completed: bool
    official_translation_verified: bool
    specific_actor_applicability_established: bool
    specific_operation_applicability_established: bool
    specific_date_applicability_established: bool
    automatic_legal_violation: bool
    automatic_statutory_block: bool
    earlier_prototype_articles_authoritative: bool
    human_validation_required_for_binding_activation: bool

    def __post_init__(self) -> None:
        if self.evidence_id != "ETH-PDPA-VERIFIED-SOURCE-BOUNDARY":
            raise PDPASourceEvidenceError("unexpected evidence_id")
        if self.source_id != SOURCE_ID or self.version_id != VERSION_ID:
            raise PDPASourceEvidenceError("source identity is invalid")
        if self.canonical_title != CANONICAL_TITLE or self.jurisdiction != JURISDICTION:
            raise PDPASourceEvidenceError("document identity is invalid")
        if self.source_class != SOURCE_CLASS or self.binding_level != BINDING_LEVEL:
            raise PDPASourceEvidenceError("source classification is invalid")
        if self.source_path != SOURCE_RELATIVE_PATH:
            raise PDPASourceEvidenceError("source path is invalid")
        if self.artifact_sha256 != ARTIFACT_SHA256:
            raise PDPASourceEvidenceError("artifact digest is invalid")
        try:
            if len(self.artifact_sha256) != 64:
                raise ValueError
            int(self.artifact_sha256, 16)
        except ValueError as error:
            raise PDPASourceEvidenceError(
                "artifact_sha256 must be a 64-character hexadecimal digest"
            ) from error
        if self.artifact_integrity_status is not VerificationStatus.VERIFIED:
            raise PDPASourceEvidenceError("artifact integrity must be verified")
        if self.pdf_magic_header_status is not VerificationStatus.VERIFIED:
            raise PDPASourceEvidenceError("PDF magic header must be verified")
        if self.activation_status is not EvidenceActivationStatus.VERIFIED_SOURCE_BOUNDARY:
            raise PDPASourceEvidenceError("activation status must be verified_source_boundary")
        if self.extraction_profile != EXTRACTION_PROFILE:
            raise PDPASourceEvidenceError("bilingual extraction profile is invalid")
        if self.physical_page_association_preserved is not True:
            raise PDPASourceEvidenceError("physical page association must be preserved")
        if self.languages != ("am", "en"):
            raise PDPASourceEvidenceError("languages must be exactly ('am', 'en')")
        if self.left_column_language != "am" or self.right_column_language != "en":
            raise PDPASourceEvidenceError("column language mapping is invalid")
        if self.cross_language_merge_permitted is not False:
            raise PDPASourceEvidenceError("cross-language merge must be prohibited")
        if self.translation_equivalence_claimed is not False:
            raise PDPASourceEvidenceError("translation equivalence must not be claimed")
        expected_statuses = (
            (self.metadata_verification_status, VerificationStatus.VERIFIED),
            (self.locator_verification_status, VerificationStatus.NOT_ASSESSED),
            (self.exact_excerpt_verification_status, VerificationStatus.NOT_ASSESSED),
            (self.translation_status, VerificationStatus.NOT_VERIFIED),
            (self.legal_review_status, VerificationStatus.NOT_PERFORMED),
            (self.applicability_status, VerificationStatus.UNRESOLVED),
        )
        if any(actual is not expected for actual, expected in expected_statuses):
            raise PDPASourceEvidenceError("verification status boundary is invalid")
        nullable = (
            self.official_locator,
            self.page_start,
            self.page_end,
            self.exact_source_excerpt,
            self.exact_source_excerpt_sha256,
            self.regulated_actor,
            self.processing_operation,
            self.applicable_effective_date,
        )
        if any(value is not None for value in nullable):
            raise PDPASourceEvidenceError(
                "unverified locator, excerpt, actor, operation, and date fields must remain null"
            )
        required_true = (
            self.eligible_for_legal_context,
            self.eligible_for_readiness_evidence,
            self.human_validation_required_for_binding_activation,
        )
        if any(value is not True for value in required_true):
            raise PDPASourceEvidenceError(
                "legal context, readiness evidence, and human validation flags must be true"
            )
        required_false = (
            self.exceptions_reviewed,
            self.applicability_evaluation_completed,
            self.eligible_for_binding_legal_findings,
            self.eligible_for_project_enforcement,
            self.eligible_for_citation,
            self.legal_review_completed,
            self.official_translation_verified,
            self.specific_actor_applicability_established,
            self.specific_operation_applicability_established,
            self.specific_date_applicability_established,
            self.automatic_legal_violation,
            self.automatic_statutory_block,
            self.earlier_prototype_articles_authoritative,
        )
        if any(value is not False for value in required_false):
            raise PDPASourceEvidenceError(
                "binding, citation, applicability, translation, legal-review, and automatic-action claims must remain false"
            )

    @property
    def binding_finding_requirements(self) -> tuple[str, ...]:
        return (
            "verified source artifact",
            "verified document version",
            "exact verified locator",
            "exact verified excerpt",
            "applicable regulated actor",
            "applicable processing operation",
            "applicable effective date",
            "reviewed exceptions",
            "completed applicability evaluation and active binding-evidence status",
        )

    @property
    def binding_finding_activation_ready(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "version_id": self.version_id,
            "canonical_title": self.canonical_title,
            "jurisdiction": self.jurisdiction,
            "source_class": self.source_class,
            "binding_level": self.binding_level,
            "source_path": self.source_path,
            "artifact_sha256": self.artifact_sha256,
            "artifact_integrity_status": self.artifact_integrity_status.value,
            "pdf_magic_header_status": self.pdf_magic_header_status.value,
            "activation_status": self.activation_status.value,
            "bilingual_extraction": {
                "profile": self.extraction_profile,
                "physical_page_association_preserved": self.physical_page_association_preserved,
                "languages": list(self.languages),
                "column_mapping": {
                    "left": self.left_column_language,
                    "right": self.right_column_language,
                },
                "cross_language_merge_permitted": self.cross_language_merge_permitted,
                "translation_equivalence_claimed": self.translation_equivalence_claimed,
            },
            "verification_status": {
                "metadata": self.metadata_verification_status.value,
                "locator": self.locator_verification_status.value,
                "exact_excerpt": self.exact_excerpt_verification_status.value,
                "translation": self.translation_status.value,
                "legal_review": self.legal_review_status.value,
                "applicability": self.applicability_status.value,
            },
            "provision_evidence": {
                "official_locator": self.official_locator,
                "page_start": self.page_start,
                "page_end": self.page_end,
                "exact_source_excerpt": self.exact_source_excerpt,
                "exact_source_excerpt_sha256": self.exact_source_excerpt_sha256,
            },
            "applicability_boundary": {
                "regulated_actor": self.regulated_actor,
                "processing_operation": self.processing_operation,
                "applicable_effective_date": self.applicable_effective_date,
                "exceptions_reviewed": self.exceptions_reviewed,
                "applicability_evaluation_completed": self.applicability_evaluation_completed,
            },
            "eligibility": {
                "eligible_for_legal_context": self.eligible_for_legal_context,
                "eligible_for_readiness_evidence": self.eligible_for_readiness_evidence,
                "eligible_for_binding_legal_findings": self.eligible_for_binding_legal_findings,
                "eligible_for_project_enforcement": self.eligible_for_project_enforcement,
                "eligible_for_citation": self.eligible_for_citation,
            },
            "binding_finding_requirements": list(self.binding_finding_requirements),
            "binding_finding_activation_ready": self.binding_finding_activation_ready,
            "human_validation_required_for_binding_activation": self.human_validation_required_for_binding_activation,
            "prohibited_claims": {
                "legal_review_completed": self.legal_review_completed,
                "official_translation_verified": self.official_translation_verified,
                "specific_actor_applicability_established": self.specific_actor_applicability_established,
                "specific_operation_applicability_established": self.specific_operation_applicability_established,
                "specific_date_applicability_established": self.specific_date_applicability_established,
                "automatic_legal_violation": self.automatic_legal_violation,
                "automatic_statutory_block": self.automatic_statutory_block,
                "earlier_prototype_articles_authoritative": self.earlier_prototype_articles_authoritative,
            },
        }


def verified_pdpa_source_evidence() -> VerifiedPDPASourceEvidence:
    return VerifiedPDPASourceEvidence(
        evidence_id="ETH-PDPA-VERIFIED-SOURCE-BOUNDARY",
        source_id=SOURCE_ID,
        version_id=VERSION_ID,
        canonical_title=CANONICAL_TITLE,
        jurisdiction=JURISDICTION,
        source_class=SOURCE_CLASS,
        binding_level=BINDING_LEVEL,
        source_path=SOURCE_RELATIVE_PATH,
        artifact_sha256=ARTIFACT_SHA256,
        artifact_integrity_status=VerificationStatus.VERIFIED,
        pdf_magic_header_status=VerificationStatus.VERIFIED,
        activation_status=EvidenceActivationStatus.VERIFIED_SOURCE_BOUNDARY,
        extraction_profile=EXTRACTION_PROFILE,
        physical_page_association_preserved=True,
        languages=("am", "en"),
        left_column_language="am",
        right_column_language="en",
        cross_language_merge_permitted=False,
        translation_equivalence_claimed=False,
        metadata_verification_status=VerificationStatus.VERIFIED,
        locator_verification_status=VerificationStatus.NOT_ASSESSED,
        exact_excerpt_verification_status=VerificationStatus.NOT_ASSESSED,
        translation_status=VerificationStatus.NOT_VERIFIED,
        legal_review_status=VerificationStatus.NOT_PERFORMED,
        applicability_status=VerificationStatus.UNRESOLVED,
        official_locator=None,
        page_start=None,
        page_end=None,
        exact_source_excerpt=None,
        exact_source_excerpt_sha256=None,
        regulated_actor=None,
        processing_operation=None,
        applicable_effective_date=None,
        exceptions_reviewed=False,
        applicability_evaluation_completed=False,
        eligible_for_legal_context=True,
        eligible_for_readiness_evidence=True,
        eligible_for_binding_legal_findings=False,
        eligible_for_project_enforcement=False,
        eligible_for_citation=False,
        legal_review_completed=False,
        official_translation_verified=False,
        specific_actor_applicability_established=False,
        specific_operation_applicability_established=False,
        specific_date_applicability_established=False,
        automatic_legal_violation=False,
        automatic_statutory_block=False,
        earlier_prototype_articles_authoritative=False,
        human_validation_required_for_binding_activation=True,
    )


def assert_binding_finding_not_activatable(
    evidence: VerifiedPDPASourceEvidence,
) -> None:
    if not isinstance(evidence, VerifiedPDPASourceEvidence):
        raise TypeError("evidence must be VerifiedPDPASourceEvidence")
    raise PDPASourceEvidenceError(
        "PDPA binding legal finding cannot be activated until all nine exact-evidence and applicability requirements are complete"
    )
