from __future__ import annotations

from dataclasses import replace
import hashlib

import numpy as np
import pytest

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
from amba_ai.rag.policy_chunk_models import ChunkingProfile, PolicyChunkError
from amba_ai.rag.policy_pdf_extractor import ExtractedPolicyPage
from amba_ai.rag.policy_structure_chunker import PolicyStructureChunker
from amba_ai.rag.policy_text_normalizer import PolicyTextNormalizer


class WordCounter:
    def count(self, text: str) -> int:
        return len(text.split())


class FakeEncoder:
    dimension = 4

    def encode(self, texts):
        rows = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            rows.append([digest[0] + 1, digest[1] + 1, digest[2] + 1, digest[3] + 1])
        return np.asarray(rows, dtype=np.float32)


def record(**changes) -> PolicyRecord:
    text = "Approved supervised classroom use."
    value = PolicyRecord(
        identity=PolicyRecordIdentity("PROJECT-CONTROL-CLASSROOM", "1.0.0", "AMBA-GOV-SAFEGUARDS"),
        document_title="Amba-Gov Sandbox Safeguards",
        authority="Amba-Gov Architecture Team",
        jurisdiction="project_sandbox",
        scope="Synthetic educational AI demonstration",
        binding_level=BindingLevel.PROJECT_CONTROL,
        official_locator="/controls/classroom_use",
        page_start=1,
        page_end=2,
        normative_text=text,
        reviewed_summary="Classroom supervision control",
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
        normative_unit_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        eligible_for_project_enforcement=True,
        eligible_for_national_legal_finding=False,
        national_binding_status=False,
        synthetic_only=True,
        legal_effect=False,
        eligible_for_citation=True,
    )
    return replace(value, **changes)


def pages():
    page_one = "SECTION ONE\n\n1. Purpose\nApproved classroom use."
    page_two = "SECTION ONE\n\n2. Supervision\nTeacher supervision is required."
    return (
        ExtractedPolicyPage(1, page_one, len(page_one)),
        ExtractedPolicyPage(2, page_two, len(page_two)),
    )


def test_normalizer_preserves_numbers_and_removes_only_proven_repetition():
    values = PolicyTextNormalizer.remove_repeated_marginal_lines(
        (
            "Gazette Header\n\n1\nArticle text\nFooter",
            "Gazette Header\n\n2\nDifferent text\nFooter",
            "Gazette Header\n\n3\nMore text\nFooter",
        )
    )
    assert all("Gazette Header" not in value for value in values)
    assert all("Footer" not in value for value in values)
    assert "1" in values[0]


def test_chunker_binds_record_version_pages_and_digests():
    parent = record()
    registry = PolicyRecordRegistry()
    registry.register(parent)
    chunker = PolicyStructureChunker(
        token_counter=WordCounter(),
        profile=ChunkingProfile(target_tokens=8, maximum_tokens=12, overlap_tokens=2, minimum_tokens=2),
    )
    chunks = chunker.chunk_pages(
        parent_record=parent,
        artifact_path="kb/artifacts/safeguards.pdf",
        pages=pages(),
        registry=registry,
        verify_artifact=False,
    )
    assert chunks
    assert all(chunk.identity.version_id == "1.0.0" for chunk in chunks)
    assert all(chunk.artifact_sha256 == parent.artifact_sha256 for chunk in chunks)
    assert all(chunk.token_count <= 12 for chunk in chunks)
    assert all(chunk.identity.chunk_id.endswith(chunk.text_sha256[:12]) for chunk in chunks)


def test_unregistered_record_fails_closed():
    with pytest.raises(Exception, match="not registered"):
        PolicyStructureChunker(token_counter=WordCounter()).chunk_pages(
            parent_record=record(),
            artifact_path="kb/artifacts/safeguards.pdf",
            pages=pages(),
            registry=PolicyRecordRegistry(),
            verify_artifact=False,
        )


def test_inactive_record_fails_closed():
    parent = replace(
        record(),
        activation_status=ActivationStatus.QUARANTINED,
        eligible_for_project_enforcement=False,
        eligible_for_citation=False,
    )
    registry = PolicyRecordRegistry()
    registry.register(parent)
    with pytest.raises(PolicyChunkError, match="active"):
        PolicyStructureChunker(token_counter=WordCounter()).chunk_pages(
            parent_record=parent,
            artifact_path="kb/artifacts/safeguards.pdf",
            pages=pages(),
            registry=registry,
            verify_artifact=False,
        )


def test_index_rebuild_is_idempotent_and_authority_is_registry_derived():
    parent = record()
    registry = PolicyRecordRegistry()
    registry.register(parent)
    chunks = PolicyStructureChunker(token_counter=WordCounter()).chunk_pages(
        parent_record=parent,
        artifact_path="kb/artifacts/safeguards.pdf",
        pages=pages(),
        registry=registry,
        verify_artifact=False,
    )
    index = PolicyChunkIndex(registry, FakeEncoder())
    assert index.rebuild((*chunks, *chunks)) == len(chunks)
    results = index.search("classroom supervision", min_score=0.0)
    assert results
    assert results[0].policy_record.binding_level is BindingLevel.PROJECT_CONTROL
    assert results[0].eligible_for_project_enforcement is True
    assert results[0].eligible_for_binding_findings is False
    assert results[0].policy_record.national_binding_status is False


def test_conflicting_duplicate_chunk_fails_closed():
    parent = record()
    registry = PolicyRecordRegistry()
    registry.register(parent)
    chunks = PolicyStructureChunker(token_counter=WordCounter()).chunk_pages(
        parent_record=parent,
        artifact_path="kb/artifacts/safeguards.pdf",
        pages=pages(),
        registry=registry,
        verify_artifact=False,
    )
    conflict = replace(chunks[0], artifact_path="different.pdf")
    with pytest.raises(PolicyChunkError, match="conflicting chunk identity"):
        PolicyChunkIndex(registry, FakeEncoder()).rebuild((chunks[0], conflict))
