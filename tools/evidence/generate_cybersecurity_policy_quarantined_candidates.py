from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = REPOSITORY_ROOT / "src"
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from amba_ai.governance.verified_cybersecurity_policy_records import (
    ADMINISTERING_AUTHORITY,
    ARTIFACT_SHA256,
    DOCUMENT_TITLE,
    PUBLICATION_DATE,
    SOURCE_CLASS,
    SOURCE_ID,
    VERSION_ID,
    quarantined_cybersecurity_policy_candidates,
)
from amba_ai.rag.policy_pdf_extractor import PolicyPdfExtractor

SOURCE_RELATIVE_PATH = Path(
    "kb/sources/ethiopia/ETH_NATIONAL_CYBERSECURITY_POLICY_2024.pdf"
)
SOURCE_PATH = REPOSITORY_ROOT / SOURCE_RELATIVE_PATH
OUTPUT_PATH = (
    REPOSITORY_ROOT
    / "kb"
    / "records"
    / "ethiopian_cybersecurity_policy_quarantined_candidates.json"
)


def main() -> int:
    if not SOURCE_PATH.is_file():
        print("configuration_failure=verified cybersecurity policy PDF is missing")
        return 2
    data = SOURCE_PATH.read_bytes()
    if data[:5] != b"%PDF-":
        print("configuration_failure=cybersecurity policy PDF magic header is invalid")
        return 2
    actual_sha256 = hashlib.sha256(data).hexdigest()
    if actual_sha256 != ARTIFACT_SHA256:
        print("configuration_failure=cybersecurity policy artifact SHA-256 mismatch")
        return 2
    pages = PolicyPdfExtractor().extract_pages(
        SOURCE_PATH,
        remove_repeated_marginal_lines=False,
    )
    records = quarantined_cybersecurity_policy_candidates()
    payload = {
        "schema_version": "1.0.0",
        "record_set_id": "AMBA-GOV-QUARANTINED-ETH-CYBERSECURITY-POLICY-2024",
        "source_id": SOURCE_ID,
        "version_id": VERSION_ID,
        "source_path": SOURCE_RELATIVE_PATH.as_posix(),
        "artifact_sha256": ARTIFACT_SHA256,
        "artifact_integrity_status": "verified",
        "pdf_magic_header_status": "verified",
        "document_title": DOCUMENT_TITLE,
        "publication_date": PUBLICATION_DATE,
        "administering_authority": ADMINISTERING_AUTHORITY,
        "source_class": SOURCE_CLASS,
        "extracted_page_count": len(pages),
        "candidate_count": len(records),
        "claim_boundaries": {
            "eligible_for_policy_context": True,
            "eligible_for_readiness_evidence": True,
            "eligible_for_binding_legal_findings": False,
            "eligible_for_citation": False,
            "national_binding_status": False,
            "legal_effect": False,
            "deterministic_source_locator_established": False,
            "exact_source_excerpt_verified": False,
            "source_page_locator_verified": False,
            "human_review_required": True,
        },
        "prohibited_independent_claims": {
            "criminal_offence": False,
            "statutory_penalty": False,
            "valid_guardian_consent": False,
            "binding_technical_threshold": False,
            "automatic_statutory_block": False,
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
    print(f"extracted_page_count={len(pages)}")
    print(f"candidate_count={len(records)}")
    print("artifact_integrity_status=verified")
    print("record_status=human_review_required")
    print("locator_status=unresolved")
    print("eligible_for_policy_context=true")
    print("eligible_for_readiness_evidence=true")
    print("eligible_for_binding_legal_findings=false")
    print("eligible_for_citation=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
