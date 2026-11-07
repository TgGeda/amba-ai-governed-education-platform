from __future__ import annotations

import hashlib

from amba_ai.governance.models import (
    ActivationStatus,
    ApplicabilityStatus,
    ArtifactIntegrityStatus,
    BindingLevel,
    LegalReviewStatus,
    LocatorVerificationStatus,
    MetadataVerificationStatus,
    PolicyRecord,
    PolicyRecordIdentity,
    TranslationStatus,
)
from amba_ai.governance.record_registry import PolicyRecordRegistry

SOURCE_ID = "UNESCO-AI-ETHICS-2021"
VERSION_ID = "2021"
ARTIFACT_SHA256 = "3a93a6006c591bf7600abc55e8beab883b6450b71638fea98148e4b08f005bf7"
DOCUMENT_TITLE = "Recommendation on the Ethics of Artificial Intelligence"
ADOPTION_DATE = "2021-11-23"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verified_unesco_ai_ethics_records() -> tuple[PolicyRecord, ...]:
    """Return the structurally verified UNESCO supporting-evidence records.

    The canonical statement is a reviewed factual summary from the Amba-Gov
    authoritative boundary. It is not represented as a verbatim quotation.
    """

    statement = (
        "Paragraph 104 is relevant to educational AI, learner monitoring, "
        "learner behaviour, sensitive information, and non-commercial misuse "
        "of learner interaction data."
    )
    record = PolicyRecord(
        identity=PolicyRecordIdentity(
            record_id="UNESCO-AI-ETHICS-PARAGRAPH-104",
            version_id=VERSION_ID,
            source_id=SOURCE_ID,
        ),
        document_title=DOCUMENT_TITLE,
        authority="United Nations Educational, Scientific and Cultural Organization",
        jurisdiction="International guidance",
        scope=(
            "International supporting evidence for educational AI ethics; "
            "no independent Ethiopian legal effect"
        ),
        binding_level=BindingLevel.INTERNATIONAL_GUIDANCE,
        official_locator="Paragraph 104",
        page_start=None,
        page_end=None,
        normative_text=statement,
        reviewed_summary=(
            "Structurally verified supporting-evidence locator for educational "
            "AI, learner monitoring, learner behaviour, sensitive information, "
            "and non-commercial misuse of learner interaction data."
        ),
        regulated_actor="AI designers, deployers, and education stakeholders",
        protected_subject="Learners and other persons affected by educational AI",
        conditions={
            "supporting_evidence_only": True,
            "independent_ethiopian_legal_violation": False,
            "exact_source_excerpt_verified": False,
            "source_page_locator_verified": False,
            "adoption_date": ADOPTION_DATE,
        },
        prohibitions=(),
        exceptions=(),
        artifact_integrity_status=ArtifactIntegrityStatus.VERIFIED,
        metadata_verification_status=MetadataVerificationStatus.VERIFIED,
        locator_verification_status=LocatorVerificationStatus.VERIFIED_STRUCTURAL,
        translation_status=TranslationStatus.NOT_APPLICABLE,
        legal_review_status=LegalReviewStatus.NOT_APPLICABLE,
        applicability_status=ApplicabilityStatus.APPLICABLE,
        activation_status=ActivationStatus.ACTIVE,
        artifact_sha256=ARTIFACT_SHA256,
        normative_unit_sha256=_sha256(statement),
        eligible_for_project_enforcement=False,
        eligible_for_national_legal_finding=False,
        national_binding_status=False,
        synthetic_only=False,
        legal_effect=False,
        eligible_for_citation=True,
    )
    return (record,)


def register_verified_unesco_ai_ethics_records(
    registry: PolicyRecordRegistry,
) -> tuple[PolicyRecord, ...]:
    if not isinstance(registry, PolicyRecordRegistry):
        raise TypeError("registry must be a PolicyRecordRegistry")
    records = verified_unesco_ai_ethics_records()
    for record in records:
        registry.register(record)
    return records
