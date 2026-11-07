from __future__ import annotations

import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = REPOSITORY_ROOT / "src"
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from amba_ai.governance.verified_unicef_records import (
    ARTIFACT_SHA256,
    DOCUMENT_TITLE,
    PUBLICATION_DATE,
    SOURCE_ID,
    SOURCE_CLASS,
    VERSION_ID,
    quarantined_unicef_supporting_evidence_records,
)

OUTPUT_PATH = REPOSITORY_ROOT / "kb" / "records" / "unicef_ai_children_quarantined_candidates.json"


def main() -> int:
    records = quarantined_unicef_supporting_evidence_records()
    payload = {
        "schema_version": "1.0.0",
        "record_set_id": "AMBA-GOV-QUARANTINED-UNICEF-AI-CHILDREN-3.0",
        "source_id": SOURCE_ID,
        "version_id": VERSION_ID,
        "source_path": "kb/sources/international/UNICEF_AI_CHILDREN_V3_2025.pdf",
        "artifact_sha256": ARTIFACT_SHA256,
        "document_title": DOCUMENT_TITLE,
        "publication_date": PUBLICATION_DATE,
        "source_class": SOURCE_CLASS,
        "candidate_count": len(records),
        "claim_boundaries": {
            "international_supporting_evidence_only": True,
            "national_binding_status": False,
            "eligible_for_binding_findings": False,
            "eligible_for_citation": False,
            "independent_ethiopian_legal_violation": False,
            "deterministic_source_locator_established": False,
            "exact_source_excerpt_verified": False,
            "source_page_locator_verified": False,
            "human_review_required": True,
        },
        "promotion_requirements": [
            "deterministic source locator",
            "source-derived excerpt",
            "excerpt SHA-256",
            "human review",
        ],
        "candidates": [record.to_dict() for record in records],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(OUTPUT_PATH)
    print(f"output={OUTPUT_PATH.relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"candidate_count={len(records)}")
    print("record_status=human_review_required")
    print("locator_status=unresolved")
    print("eligible_for_citation=false")
    print("eligible_for_binding_findings=false")
    print("independent_ethiopian_legal_violation=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
