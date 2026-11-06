from __future__ import annotations

from dataclasses import replace
import hashlib

import numpy as np

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
from amba_ai.rag.policy_chunk_indexer import PolicyChunkIndex
from amba_ai.rag.policy_chunk_models import (
    PolicyChunk,
    PolicyChunkIdentity,
)
from amba_ai.rag.policy_query import PolicySourceReference


class FixedEncoder:
    dimension = 4

    def encode(self, texts):
        rows = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            rows.append(
                [
                    digest[0] + 1,
                    digest[1] + 1,
                    digest[2] + 1,
                    digest[3] + 1,
                ]
            )
        return np.asarray(rows, dtype=np.float32)


def policy_record() -> PolicyRecord:
    normative_text = "Classroom use requires teacher supervision."
    return PolicyRecord(
        identity=PolicyRecordIdentity(
            "PROJECT-CONTROL-CLASSROOM",
            "1.0.0",
            "AMBA-GOV-SAFEGUARDS",
        ),
        document_title="Amba-Gov Sandbox Safeguards",
        authority="Amba-Gov Architecture Team",
        jurisdiction="project_sandbox",
        scope="Synthetic educational AI demonstration",
        binding_level=BindingLevel.PROJECT_CONTROL,
        official_locator="/controls/classroom_use",
        page_start=1,
        page_end=1,
        normative_text=normative_text,
        reviewed_summary="Teacher-supervised classroom use.",
        regulated_actor="Amba-Gov sandbox components",
        protected_subject="synthetic education participants",
        conditions={},
        prohibitions=(),
        exceptions=(),
        artifact_integrity_status=ArtifactIntegrityStatus.VERIFIED,
        metadata_verification_status=MetadataVerificationStatus.VERIFIED,
        locator_verification_status=LocatorVerificationStatus.VERIFIED_STRUCTURAL,
        translation_status=TranslationStatus.NOT_APPLICABLE,
        legal_review_status=LegalReviewStatus.NOT_APPLICABLE,
        applicability_status=ApplicabilityStatus.APPLICABLE,
        activation_status=ActivationStatus.ACTIVE,
        artifact_sha256="a" * 64,
        normative_unit_sha256=hashlib.sha256(
            normative_text.encode("utf-8")
        ).hexdigest(),
        eligible_for_project_enforcement=True,
        eligible_for_national_legal_finding=False,
        national_binding_status=False,
        synthetic_only=True,
        legal_effect=False,
        eligible_for_citation=True,
    )


def policy_chunk(record: PolicyRecord) -> PolicyChunk:
    text = "Teacher supervision is required for classroom use."
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return PolicyChunk(
        identity=PolicyChunkIdentity(
            chunk_id=(
                "PROJECT-CONTROL-CLASSROOM@1.0.0:"
                f"p1-p1:c0000:{digest[:12]}"
            ),
            record_id=record.identity.record_id,
            version_id=record.identity.version_id,
            source_id=record.identity.source_id,
            chunk_index=0,
        ),
        artifact_sha256=record.artifact_sha256,
        artifact_path="kb/artifacts/safeguards.pdf",
        page_start=1,
        page_end=1,
        official_locator=(
            "/controls/classroom_use | p.1 | "
            "SECTION ONE | provisions 1"
        ),
        section_title="SECTION ONE",
        provision_numbers=("1",),
        raw_text=text,
        text_sha256=digest,
        token_count=8,
        chunking_version="amba-policy-v1",
    )


def test_search_routes_hits_through_policy_query_adapter() -> None:
    record = policy_record()
    registry = PolicyRecordRegistry()
    registry.register(record)
    index = PolicyChunkIndex(registry, FixedEncoder())
    assert index.rebuild((policy_chunk(record),)) == 1

    hits = index.search_hits(
        "classroom supervision",
        min_score=0.0,
    )
    assert len(hits) == 1
    reference = PolicySourceReference.parse(hits[0].source_ref)
    assert reference.identity == record.identity
    assert reference.locator == record.official_locator
    assert hits[0].chunk_locator != reference.locator

    results = index.search(
        "classroom supervision",
        min_score=0.0,
    )
    assert len(results) == 1
    result = results[0]
    assert result.source_reference_resolved is True
    assert result.locator_matches_registered_record is True
    assert result.policy_record == record
    assert result.eligible_for_project_enforcement is True
    assert result.eligible_for_binding_findings is False
    assert result.eligible_for_supporting_evidence is True
    assert result.metadata["authority_derived_from_score"] is False
    assert (
        "project_control_has_no_national_legal_effect"
        in result.limitations
    )


def test_inactive_record_is_not_indexed() -> None:
    inactive = replace(
        policy_record(),
        activation_status=ActivationStatus.QUARANTINED,
        eligible_for_project_enforcement=False,
        eligible_for_citation=False,
    )
    registry = PolicyRecordRegistry()
    registry.register(inactive)
    index = PolicyChunkIndex(registry, FixedEncoder())

    assert index.rebuild((policy_chunk(inactive),)) == 0
    assert index.search(
        "classroom supervision",
        min_score=0.0,
    ) == ()


def test_semantic_score_does_not_create_national_authority() -> None:
    record = policy_record()
    registry = PolicyRecordRegistry()
    registry.register(record)
    index = PolicyChunkIndex(registry, FixedEncoder())
    index.rebuild((policy_chunk(record),))

    result = index.search(
        "classroom supervision",
        min_score=0.0,
    )[0]
    assert result.retrieval_score >= 0.0
    assert result.policy_record.binding_level is BindingLevel.PROJECT_CONTROL
    assert result.policy_record.national_binding_status is False
    assert result.eligible_for_binding_findings is False
