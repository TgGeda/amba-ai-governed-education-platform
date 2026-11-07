from __future__ import annotations

from pathlib import Path

from amba_ai.governance.record_registry import PolicyRecordRegistry
from amba_ai.governance.verified_policy_records import verified_itu_y3172_records
from amba_ai.rag.policy_chunk_record_linker import (
    ChunkRecordMatchStatus,
    PolicyChunkRecordLinker,
    SourcePolicyChunk,
    build_link_report,
    write_link_report,
)
from amba_ai.rag.policy_pdf_extractor import PolicyPdfExtractor

ARTIFACT = "e42f9a3be3f951d3e19b9007f876f0b389c81b4693f0d8576e18185a1acfe67b"
SOURCE = "ITU-T-Y3172-2019"
VERSION = "1.0"
PDF_PATH = Path("kb/sources/international/ITU_T_Y3172_2019.pdf")


def _source_chunks() -> tuple[SourcePolicyChunk, ...]:
    pages = PolicyPdfExtractor().extract_pages(
        PDF_PATH,
        remove_repeated_marginal_lines=False,
    )
    return tuple(
        SourcePolicyChunk.create(
            source_id=SOURCE,
            version_id=VERSION,
            artifact_sha256=ARTIFACT,
            page_start=page.page_number,
            page_end=page.page_number,
            raw_text=page.normalized_text,
            ordinal=index,
        )
        for index, page in enumerate(pages)
    )


def test_verified_y3172_pdf_links_all_structural_records(tmp_path, monkeypatch) -> None:
    registry = PolicyRecordRegistry()
    records = verified_itu_y3172_records()
    for record in records:
        registry.register(record)
    chunks = _source_chunks()
    assert chunks
    assessments = PolicyChunkRecordLinker(registry).assess_records(
        chunks,
        (record.identity for record in records),
    )
    assert len(assessments) == 5
    assert all(
        assessment.match_status is ChunkRecordMatchStatus.STRUCTURAL_MATCH
        for assessment in assessments
    )
    assert all(assessment.is_complete for assessment in assessments)
    assert all(assessment.links for assessment in assessments)
    assert all(
        link.source_page_start >= 1 and link.source_page_end >= link.source_page_start
        for assessment in assessments
        for link in assessment.links
    )
    report = build_link_report(
        source_id=SOURCE,
        version_id=VERSION,
        artifact_sha256=ARTIFACT,
        assessments=assessments,
    )
    monkeypatch.chdir(tmp_path)
    output = write_link_report(Path("kb/artifacts/extraction_reports/itu_y3172_link_report.json"), report)
    assert output.is_file()
    rendered = output.read_text(encoding="utf-8")
    assert "verified_exact_excerpt_claimed" in rendered
    assert '"verified_exact_excerpt_claimed": false' in rendered
    assert "F:\\" not in rendered
    assert "E:\\" not in rendered
