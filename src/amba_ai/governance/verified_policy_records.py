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

_SOURCE_ID = "ITU-T-Y3172-2019"
_VERSION_ID = "1.0"
_ARTIFACT_SHA256 = "e42f9a3be3f951d3e19b9007f876f0b389c81b4693f0d8576e18185a1acfe67b"
_DOCUMENT_TITLE = "Architectural framework for machine learning in future networks including IMT-2020"
_AUTHORITY = "International Telecommunication Union Telecommunication Standardization Sector"
_JURISDICTION = "International technical standard"
_SCOPE = "Architecture mapping for Amba-Gov; no Ethiopian legal authority or formal conformance claim"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _record(
    *,
    record_id: str,
    locator: str,
    normative_text: str,
    reviewed_summary: str,
    regulated_actor: str,
    protected_subject: str,
) -> PolicyRecord:
    return PolicyRecord(
        identity=PolicyRecordIdentity(
            record_id=record_id,
            version_id=_VERSION_ID,
            source_id=_SOURCE_ID,
        ),
        document_title=_DOCUMENT_TITLE,
        authority=_AUTHORITY,
        jurisdiction=_JURISDICTION,
        scope=_SCOPE,
        binding_level=BindingLevel.TECHNICAL_STANDARD,
        official_locator=locator,
        page_start=None,
        page_end=None,
        normative_text=normative_text,
        reviewed_summary=reviewed_summary,
        regulated_actor=regulated_actor,
        protected_subject=protected_subject,
        conditions={
            "architecture_mapping_only": True,
            "formal_conformance_claim": False,
            "ethiopian_legal_authority": False,
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
        artifact_sha256=_ARTIFACT_SHA256,
        normative_unit_sha256=_sha256(normative_text),
        eligible_for_project_enforcement=False,
        eligible_for_national_legal_finding=False,
        national_binding_status=False,
        synthetic_only=False,
        legal_effect=False,
        eligible_for_citation=True,
    )


def verified_itu_y3172_records() -> tuple[PolicyRecord, ...]:
    records = (
        _record(
            record_id="ITU-Y3172-ML-SANDBOX-DEFINITION",
            locator="Clause 3.2.6",
            normative_text="Clause 3.2.6 defines the ML sandbox.",
            reviewed_summary="Verified structural locator for the ML sandbox definition.",
            regulated_actor="ML architecture implementers",
            protected_subject="ML pipeline isolation and experimentation boundary",
        ),
        _record(
            record_id="ITU-Y3172-DECLARATIVE-ML-SPECIFICATION",
            locator="Clause 7.4",
            normative_text="Clause 7.4 addresses declarative ML application specifications and ML intent.",
            reviewed_summary="Verified structural locator for declarative ML application specifications and ML intent.",
            regulated_actor="ML application designers",
            protected_subject="Declarative ML application specification and intent",
        ),
        _record(
            record_id="ITU-Y3172-ML-PIPELINE-COMPONENTS",
            locator="Clause 8.1",
            normative_text="The required ML pipeline is SRC -> C -> PP -> M -> P -> D -> SINK.",
            reviewed_summary="Verified high-level ML pipeline component sequence.",
            regulated_actor="ML pipeline architects",
            protected_subject="High-level ML pipeline component mapping",
        ),
        _record(
            record_id="ITU-Y3172-ARCHITECTURE-SANDBOX-COMPONENTS",
            locator="Clauses 8.1 and 8.2",
            normative_text="Clauses 8.1 and 8.2 address architectural and sandbox components.",
            reviewed_summary="Verified structural locators for architectural and sandbox components.",
            regulated_actor="ML architecture and sandbox implementers",
            protected_subject="Architecture and sandbox component mapping",
        ),
        _record(
            record_id="ITU-Y3172-SECURITY-CONSIDERATIONS",
            locator="Clause 9",
            normative_text="Clause 9 contains security considerations.",
            reviewed_summary="Verified structural locator for security considerations.",
            regulated_actor="ML system architects and operators",
            protected_subject="ML architecture security considerations",
        ),
    )
    identities = tuple(record.identity for record in records)
    if len(identities) != len(set(identities)):
        raise RuntimeError("verified ITU-T Y.3172 PolicyRecord identities must be unique")
    return records


def register_verified_itu_y3172_records(
    registry: PolicyRecordRegistry,
) -> tuple[PolicyRecord, ...]:
    if not isinstance(registry, PolicyRecordRegistry):
        raise TypeError("registry must be a PolicyRecordRegistry")
    records = verified_itu_y3172_records()
    for record in records:
        registry.register(record)
    return records
