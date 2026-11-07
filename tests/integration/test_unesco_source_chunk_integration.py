from __future__ import annotations

from pathlib import Path

from amba_ai.governance.record_registry import PolicyRecordRegistry
from amba_ai.governance.verified_unesco_records import verified_unesco_ai_ethics_records
from amba_ai.rag.policy_chunk_record_linker import (
    ChunkRecordMatchStatus,
    ExcerptExactness,
    PolicyChunkRecordLinker,
    SourcePolicyChunk,
    build_link_report,
    write_link_report,
)
from amba_ai.rag.policy_pdf_extractor import PolicyPdfExtractor

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PDF_PATH = (
    REPOSITORY_ROOT
    / "kb"
    / "sources"
    / "international"
    / "UNESCO_AI_ETHICS_RECOMMENDATION.pdf"
)
SOURCE_ID = "UNESCO-AI-ETHICS-2021"
VERSION_ID = "2021"
ARTIFACT_SHA256 = "3a93a6006c591bf7600abc55e8beab883b6450b71638fea98148e4b08f005bf7"


def _source_chunks() -> tuple[SourcePolicyChunk, ...]:
    pages = PolicyPdfExtractor().extract_pages(
        PDF_PATH,
        remove_repeated_marginal_lines=False,
    )
    return tuple(
        SourcePolicyChunk.create(
            source_id=SOURCE_ID,
            version_id=VERSION_ID,
            artifact_sha256=ARTIFACT_SHA256,
            page_start=page.page_number,
            page_end=page.page_number,
            raw_text=page.normalized_text,
            ordinal=index,
        )
        for index, page in enumerate(pages)
    )


def test_unesco_paragraph_104_links_structurally_from_verified_pdf(
    tmp_path,
    monkeypatch,
) -> None:
    registry = PolicyRecordRegistry()
    record = verified_unesco_ai_ethics_records()[0]
    registry.register(record)
    chunks = _source_chunks()
    assert chunks
    linker = PolicyChunkRecordLinker(
        registry,
        locator_requirements={"Paragraph 104": ("104",)},
    )
    assessment = linker.assess_record(chunks, record.identity)
    assert assessment.match_status is ChunkRecordMatchStatus.STRUCTURAL_MATCH
    assert assessment.is_complete is True
    assert assessment.matched_locators == ("104",)
    assert assessment.registered_locator == "Paragraph 104"
    assert assessment.links
    assert all(
        link.excerpt_exactness is ExcerptExactness.SOURCE_DERIVED
        for link in assessment.links
    )
    assert all(
        link.source_page_start >= 1
        and link.source_page_end >= link.source_page_start
        for link in assessment.links
    )
    report = build_link_report(
        source_id=SOURCE_ID,
        version_id=VERSION_ID,
        artifact_sha256=ARTIFACT_SHA256,
        assessments=(assessment,),
    )
    report["claim_boundaries"] = {
        "international_supporting_evidence_only": True,
        "independent_ethiopian_legal_violation": False,
        "national_binding_status": False,
        "eligible_for_binding_findings": False,
        "exact_source_excerpt_verified": False,
        "source_page_locator_verified": False,
    }
    monkeypatch.chdir(tmp_path)
    output = write_link_report(
        Path("kb/artifacts/extraction_reports/unesco_paragraph_104_link_report.json"),
        report,
    )
    rendered = output.read_text(encoding="utf-8")
    assert '"verified_exact_excerpt_claimed": false' in rendered
    assert '"independent_ethiopian_legal_violation": false' in rendered
    assert "F:\\" not in rendered
    assert "E:\\" not in rendered
