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
from amba_ai.rag.policy_chunk_models import (
    ChunkingProfile,
    PolicyChunk,
    PolicyChunkError,
    PolicyChunkIdentity,
)
from amba_ai.rag.policy_pdf_extractor import (
    ExtractedPolicyPage,
    PdfExtractionProfile,
    PolicyPdfExtractor,
    _matrix_position,
)
from amba_ai.rag.policy_structure_chunker import (
    PolicyStructureChunker,
    geez_to_int,
)


class WordCounter:
    def count(self, text: str) -> int:
        return len(text.split())


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


def _record(
    *,
    page_start: int = 1,
    page_end: int = 2,
) -> PolicyRecord:
    normative_text = "Personal data of a minor requires protection."
    return PolicyRecord(
        identity=PolicyRecordIdentity(
            record_id="ETH-PDPA-1321-2024",
            version_id="2024",
            source_id="ETH-PDPA-1321-2024",
        ),
        document_title=(
            "Personal Data Protection Proclamation No. 1321/2024"
        ),
        authority="Federal Democratic Republic of Ethiopia",
        jurisdiction="Ethiopia",
        scope="Personal data protection",
        binding_level=BindingLevel.PROJECT_CONTROL,
        official_locator="Proclamation No. 1321/2024",
        page_start=page_start,
        page_end=page_end,
        normative_text=normative_text,
        reviewed_summary="Bilingual proclamation fixture.",
        regulated_actor="Synthetic data controllers and processors",
        protected_subject="Synthetic data subjects",
        conditions={},
        prohibitions=(),
        exceptions=(),
        artifact_integrity_status=ArtifactIntegrityStatus.VERIFIED,
        metadata_verification_status=MetadataVerificationStatus.VERIFIED,
        locator_verification_status=(
            LocatorVerificationStatus.VERIFIED_STRUCTURAL
        ),
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


def _registry(record: PolicyRecord) -> PolicyRecordRegistry:
    registry = PolicyRecordRegistry()
    registry.register(record)
    return registry


def _page(
    page_number: int,
    text: str,
    *,
    language: str | None = None,
    column: str | None = None,
    parallel_unit_id: str | None = None,
) -> ExtractedPolicyPage:
    return ExtractedPolicyPage(
        page_number=page_number,
        normalized_text=text,
        character_count=len(text),
        language=language,
        column=column,
        parallel_unit_id=parallel_unit_id,
    )


def _bilingual_pages() -> tuple[ExtractedPolicyPage, ...]:
    return (
        _page(
            1,
            "አንቀጽ ፩\n\nየግል ዳታ ጥበቃ ዓላማ።",
            language="am",
            column="left",
            parallel_unit_id="physical-page-1",
        ),
        _page(
            1,
            "Article 1\n\nPurpose of personal data protection.",
            language="en",
            column="right",
            parallel_unit_id="physical-page-1",
        ),
        _page(
            2,
            "አንቀጽ ፲፩\n\nየአካለ መጠን ያልደረሰ ልጅ የግል ዳታ።",
            language="am",
            column="left",
            parallel_unit_id="physical-page-2",
        ),
        _page(
            2,
            "Article 11\n\nProcessing personal data of a minor.",
            language="en",
            column="right",
            parallel_unit_id="physical-page-2",
        ),
    )


def _chunker() -> PolicyStructureChunker:
    return PolicyStructureChunker(
        token_counter=WordCounter(),
        profile=ChunkingProfile(
            target_tokens=20,
            maximum_tokens=30,
            overlap_tokens=3,
            minimum_tokens=2,
        ),
    )


def test_geez_numeral_conversion() -> None:
    assert geez_to_int("፩") == 1
    assert geez_to_int("፲") == 10
    assert geez_to_int("፲፩") == 11
    assert geez_to_int("፳፬") == 24
    assert geez_to_int("፻") == 100
    assert geez_to_int("፪፻") == 200
    assert geez_to_int("፪፻፲፩") == 211
    assert geez_to_int("፩፼፶፮፻፳") == 15620
    assert geez_to_int("non-geez-characters") is None
    with pytest.raises(TypeError, match="must be a string"):
        geez_to_int(123)  # type: ignore[arg-type]


def test_matrix_position_applies_affine_transform() -> None:
    cm = (1.0, 0.0, 0.0, 1.0, 100.0, 200.0)
    tm = (1.0, 0.0, 0.0, 1.0, 20.0, 30.0)
    assert _matrix_position(cm, tm) == (120.0, 230.0)


def test_matrix_position_rejects_incomplete_matrices() -> None:
    with pytest.raises(PolicyChunkError, match="matrix is incomplete"):
        _matrix_position((1.0, 0.0), (1.0, 0.0))


def test_standard_profile_is_default_and_standard_page_has_no_language() -> None:
    assert (
        PolicyPdfExtractor.extract_pages.__kwdefaults__["profile"]
        is PdfExtractionProfile.STANDARD
    )
    page = _page(1, "Standard policy text.")
    assert page.language is None
    assert page.column is None
    assert page.parallel_unit_id is None


def test_language_column_and_parallel_identity_are_bound() -> None:
    with pytest.raises(PolicyChunkError, match="language and column"):
        _page(1, "Text", language="am")
    with pytest.raises(PolicyChunkError, match="parallel_unit_id"):
        _page(1, "Text", language="am", column="left")
    with pytest.raises(PolicyChunkError, match="must not define"):
        _page(1, "Text", parallel_unit_id="physical-page-1")


def test_standard_chunk_id_has_no_language_segment() -> None:
    record = _record(page_start=1, page_end=1)
    chunks = _chunker().chunk_pages(
        parent_record=record,
        artifact_path="kb/artifacts/standard policy.pdf",
        pages=(_page(1, "Article 1\n\nStandard policy text."),),
        registry=_registry(record),
        verify_artifact=False,
    )
    assert chunks
    assert chunks[0].language is None
    assert "@2024:p1-p1:" in chunks[0].identity.chunk_id
    assert "@2024:am:" not in chunks[0].identity.chunk_id
    assert "@2024:en:" not in chunks[0].identity.chunk_id
    assert chunks[0].parallel_unit_id is None


def test_bilingual_streams_never_merge_and_ids_include_language() -> None:
    record = _record()
    chunks = _chunker().chunk_pages(
        parent_record=record,
        artifact_path="kb/artifacts/ETH_PDPA_1321_2024.pdf",
        pages=_bilingual_pages(),
        registry=_registry(record),
        verify_artifact=False,
    )
    assert {chunk.language for chunk in chunks} == {"am", "en"}
    assert {chunk.column for chunk in chunks} == {"left", "right"}
    assert any("@2024:am:" in chunk.identity.chunk_id for chunk in chunks)
    assert any("@2024:en:" in chunk.identity.chunk_id for chunk in chunks)
    assert all(
        not (
            "Processing" in chunk.raw_text
            and "የግል" in chunk.raw_text
        )
        for chunk in chunks
    )
    assert all(chunk.parallel_unit_id is not None for chunk in chunks)


def test_one_sided_page_does_not_break_physical_page_coverage() -> None:
    record = _record()
    pages = (
        _page(
            1,
            "English-only front matter.",
            language="en",
            column="right",
            parallel_unit_id="physical-page-1",
        ),
        _page(
            2,
            "አንቀጽ ፩\n\nየግል ዳታ ጥበቃ።",
            language="am",
            column="left",
            parallel_unit_id="physical-page-2",
        ),
        _page(
            2,
            "Article 1\n\nPersonal data protection.",
            language="en",
            column="right",
            parallel_unit_id="physical-page-2",
        ),
    )
    chunks = _chunker().chunk_pages(
        parent_record=record,
        artifact_path="kb/artifacts/ETH_PDPA_1321_2024.pdf",
        pages=pages,
        registry=_registry(record),
        verify_artifact=False,
    )
    assert chunks
    assert {chunk.page_start for chunk in chunks}.issubset({1, 2})
    assert {chunk.language for chunk in chunks} == {"am", "en"}


def test_missing_registered_physical_page_fails_closed() -> None:
    record = _record()
    pages = tuple(
        page for page in _bilingual_pages() if page.page_number == 2
    )
    with pytest.raises(PolicyChunkError, match="physical page range"):
        _chunker().chunk_pages(
            parent_record=record,
            artifact_path="kb/artifacts/ETH_PDPA_1321_2024.pdf",
            pages=pages,
            registry=_registry(record),
            verify_artifact=False,
        )


def test_multiline_raw_text_preserves_digest_and_path_spaces() -> None:
    text = "Paragraph one.\n\nParagraph two."
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    chunk = PolicyChunk(
        identity=PolicyChunkIdentity(
            chunk_id=f"REC@v1:p1-p1:c0000:{digest[:12]}",
            record_id="REC",
            version_id="v1",
            source_id="SRC",
            chunk_index=0,
        ),
        artifact_sha256="b" * 64,
        artifact_path="kb/artifacts/policy  document.pdf",
        page_start=1,
        page_end=1,
        official_locator="Article 1",
        section_title=None,
        provision_numbers=(),
        raw_text=text,
        text_sha256=digest,
        token_count=4,
        chunking_version="amba-policy-v1",
    )
    assert chunk.raw_text == text
    assert chunk.artifact_path == "kb/artifacts/policy  document.pdf"


def test_language_metadata_survives_search_hit_and_authority_stays_registered() -> None:
    record = _record()
    registry = _registry(record)
    chunks = _chunker().chunk_pages(
        parent_record=record,
        artifact_path="kb/artifacts/ETH_PDPA_1321_2024.pdf",
        pages=_bilingual_pages(),
        registry=registry,
        verify_artifact=False,
    )
    index = PolicyChunkIndex(registry, FixedEncoder())
    index.rebuild(chunks)
    hits = index.search_hits("minor personal data", min_score=0.0)
    assert hits
    assert {hit.language for hit in hits}.issubset({"am", "en"})
    assert all(hit.parallel_unit_id is not None for hit in hits)
    results = index.search("minor personal data", min_score=0.0)
    assert results
    assert all(
        result.policy_record == record
        for result in results
    )
    assert all(
        result.metadata["authority_derived_from_score"] is False
        for result in results
    )
    assert all(
        result.policy_record.national_binding_status is False
        for result in results
    )
