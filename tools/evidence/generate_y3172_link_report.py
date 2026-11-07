from __future__ import annotations

import os
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = REPOSITORY_ROOT / "src"

if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))


from amba_ai.governance.record_registry import (
    PolicyRecordRegistry,
)
from amba_ai.governance.verified_policy_records import (
    verified_itu_y3172_records,
)
from amba_ai.rag.policy_chunk_record_linker import (
    PolicyChunkRecordLinker,
    SourcePolicyChunk,
    build_link_report,
    write_link_report,
)
from amba_ai.rag.policy_pdf_extractor import (
    PolicyPdfExtractor,
)


ARTIFACT_SHA256 = (
    "e42f9a3be3f951d3e19b9007f876f0b"
    "389c81b4693f0d8576e18185a1acfe67b"
)

SOURCE_ID = "ITU-T-Y3172-2019"
VERSION_ID = "1.0"

SOURCE_RELATIVE_PATH = Path(
    "kb/sources/international/"
    "ITU_T_Y3172_2019.pdf"
)

REPORT_RELATIVE_PATH = Path(
    "kb/artifacts/extraction_reports/"
    "itu_y3172_link_report.json"
)


def _build_source_chunks() -> tuple[SourcePolicyChunk, ...]:
    source_path = REPOSITORY_ROOT / SOURCE_RELATIVE_PATH

    if not source_path.is_file():
        raise FileNotFoundError(
            "Verified ITU-T Y.3172 source PDF was not found: "
            f"{SOURCE_RELATIVE_PATH.as_posix()}"
        )

    pages = PolicyPdfExtractor().extract_pages(
        source_path,
        remove_repeated_marginal_lines=False,
    )

    if not pages:
        raise RuntimeError(
            "ITU-T Y.3172 extraction produced no pages"
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


def main() -> int:
    registry = PolicyRecordRegistry()
    records = verified_itu_y3172_records()

    for record in records:
        registry.register(record)

    chunks = _build_source_chunks()

    linker = PolicyChunkRecordLinker(registry)

    assessments = linker.assess_records(
        chunks,
        (
            record.identity
            for record in records
        ),
    )

    report = build_link_report(
        source_id=SOURCE_ID,
        version_id=VERSION_ID,
        artifact_sha256=ARTIFACT_SHA256,
        assessments=assessments,
    )

    previous_directory = Path.cwd()

    try:
        os.chdir(REPOSITORY_ROOT)

        output = write_link_report(
            REPORT_RELATIVE_PATH,
            report,
        )
    finally:
        os.chdir(previous_directory)

    incomplete = tuple(
        assessment
        for assessment in assessments
        if not assessment.is_complete
    )

    print(
        "report="
        f"{REPORT_RELATIVE_PATH.as_posix()}"
    )
    print(f"source_chunk_count={len(chunks)}")
    print(f"record_count={len(assessments)}")
    print(
        "complete_count="
        f"{len(assessments) - len(incomplete)}"
    )
    print(f"incomplete_count={len(incomplete)}")

    if incomplete:
        for assessment in incomplete:
            missing_locators = tuple(
                locator
                for locator
                in assessment.required_locators
                if locator
                not in assessment.matched_locators
            )

            print(
                "incomplete="
                f"{assessment.record_identity.record_id}:"
                f"{assessment.match_status.value}:"
                f"missing={','.join(missing_locators)}"
            )

        return 1

    print(
        "verified_exact_excerpt_claimed=false"
    )
    print(
        "formal_y3172_conformance_claimed=false"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())