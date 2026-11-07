from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = REPOSITORY_ROOT / "src"
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from amba_ai.governance.verified_stme_context_evidence import (
    ARTIFACT_SHA256,
    DOCUMENT_SUBTITLE,
    DOCUMENT_TITLE,
    FORMAL_ADOPTION_STATUS,
    SOURCE_CLASS,
    SOURCE_ID,
    VERSION_ID,
    verified_stme_context_evidence,
)
from amba_ai.rag.policy_pdf_extractor import PolicyPdfExtractor

SOURCE_RELATIVE_PATH = Path("kb/sources/ethiopia/ETH_STME_POLICY_FULL.pdf")
SOURCE_PATH = REPOSITORY_ROOT / SOURCE_RELATIVE_PATH
OUTPUT_PATH = (
    REPOSITORY_ROOT
    / "kb"
    / "records"
    / "ethiopian_stme_verified_context_evidence.json"
)


def main() -> int:
    if not SOURCE_PATH.is_file():
        print("configuration_failure=verified STME source PDF is missing")
        return 2
    data = SOURCE_PATH.read_bytes()
    if data[:5] != b"%PDF-":
        print("configuration_failure=STME PDF magic header is invalid")
        return 2
    actual_sha256 = hashlib.sha256(data).hexdigest()
    if actual_sha256 != ARTIFACT_SHA256:
        print("configuration_failure=STME artifact SHA-256 mismatch")
        return 2
    pages = PolicyPdfExtractor().extract_pages(
        SOURCE_PATH,
        remove_repeated_marginal_lines=False,
    )
    evidence = verified_stme_context_evidence()
    payload = {
        "schema_version": "1.0.0",
        "evidence_set_id": "AMBA-GOV-VERIFIED-CONTEXT-ETH-STME",
        "source_id": SOURCE_ID,
        "version_id": VERSION_ID,
        "source_path": SOURCE_RELATIVE_PATH.as_posix(),
        "artifact_sha256": ARTIFACT_SHA256,
        "artifact_integrity_status": "verified",
        "pdf_magic_header_status": "verified",
        "document_title": DOCUMENT_TITLE,
        "document_subtitle": DOCUMENT_SUBTITLE,
        "source_class": SOURCE_CLASS,
        "formal_adoption_status": FORMAL_ADOPTION_STATUS,
        "extracted_page_count": len(pages),
        "evidence_count": len(evidence),
        "claim_boundaries": {
            "activation_status": "verified_context_boundary",
            "locator_verification_status": "not_assessed",
            "eligible_for_policy_context": True,
            "eligible_for_readiness_evidence": True,
            "eligible_for_binding_findings": False,
            "eligible_for_project_enforcement": False,
            "eligible_for_citation": False,
            "national_binding_status": False,
            "legal_effect": False,
            "formal_adoption_claimed": False,
            "deterministic_source_locator_established": False,
            "exact_source_excerpt_verified": False,
            "source_page_locator_verified": False,
            "human_validation_required_for_locator_activation": True,
        },
        "activation_requirements": [
            "deterministic source locator",
            "source-derived excerpt",
            "excerpt SHA-256",
            "human validation",
        ],
        "evidence": [record.to_dict() for record in evidence],
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
    print(f"evidence_count={len(evidence)}")
    print("artifact_integrity_status=verified")
    print("activation_status=verified_context_boundary")
    print("formal_adoption_status=unverified")
    print("eligible_for_policy_context=true")
    print("eligible_for_readiness_evidence=true")
    print("eligible_for_binding_findings=false")
    print("eligible_for_citation=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
