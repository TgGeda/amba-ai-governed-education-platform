from __future__ import annotations

import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = REPOSITORY_ROOT / "src"
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from amba_ai.governance.record_registry import PolicyRecordRegistry
from amba_ai.governance.verified_unesco_records import verified_unesco_ai_ethics_records
from amba_ai.rag.policy_chunk_record_linker import (
    PolicyChunkRecordLinker,
    SourcePolicyChunk,
    build_link_report,
)
from amba_ai.rag.policy_pdf_extractor import PolicyPdfExtractor

SOURCE_ID = "UNESCO-AI-ETHICS-2021"
VERSION_ID = "2021"
ARTIFACT_SHA256 = "3a93a6006c591bf7600abc55e8beab883b6450b71638fea98148e4b08f005bf7"
SOURCE_PATH = (
    REPOSITORY_ROOT
    / "kb"
    / "sources"
    / "international"
    / "UNESCO_AI_ETHICS_RECOMMENDATION.pdf"
)
OUTPUT_PATH = (
    REPOSITORY_ROOT
    / "kb"
    / "artifacts"
    / "extraction_reports"
    / "unesco_paragraph_104_link_report.json"
)


def main() -> int:
    if not SOURCE_PATH.is_file():
        print("configuration_failure=verified UNESCO source PDF is missing")
        return 2
    registry = PolicyRecordRegistry()
    record = verified_unesco_ai_ethics_records()[0]
    registry.register(record)
    pages = PolicyPdfExtractor().extract_pages(
        SOURCE_PATH,
        remove_repeated_marginal_lines=False,
    )
    chunks = tuple(
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
    assessment = PolicyChunkRecordLinker(
        registry,
        locator_requirements={"Paragraph 104": ("104",)},
    ).assess_record(chunks, record.identity)
    report = build_link_report(
        source_id=SOURCE_ID,
        version_id=VERSION_ID,
        artifact_sha256=ARTIFACT_SHA256,
        assessments=(assessment,),
    )
    report["source_path"] = (
        "kb/sources/international/UNESCO_AI_ETHICS_RECOMMENDATION.pdf"
    )
    report["claim_boundaries"] = {
        "international_supporting_evidence_only": True,
        "independent_ethiopian_legal_violation": False,
        "national_binding_status": False,
        "eligible_for_binding_findings": False,
        "exact_source_excerpt_verified": False,
        "source_page_locator_verified": False,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(OUTPUT_PATH)
    print(f"output={OUTPUT_PATH.relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"source_chunk_count={len(chunks)}")
    print("record_count=1")
    print(f"complete_count={1 if assessment.is_complete else 0}")
    print(f"incomplete_count={0 if assessment.is_complete else 1}")
    print("verified_exact_excerpt_claimed=false")
    print("source_page_locator_verified=false")
    print("independent_ethiopian_legal_violation=false")
    return 0 if assessment.is_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
