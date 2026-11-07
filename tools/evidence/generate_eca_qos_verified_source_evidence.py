from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = REPOSITORY_ROOT / "src"
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from amba_ai.governance.verified_eca_qos_source_evidence import (
    ARTIFACT_SHA256,
    SOURCE_RELATIVE_PATH,
    verified_eca_qos_source_evidence,
)
from amba_ai.rag.policy_pdf_extractor import PolicyPdfExtractor

SOURCE_PATH = REPOSITORY_ROOT / SOURCE_RELATIVE_PATH
OUTPUT_PATH = (
    REPOSITORY_ROOT
    / "kb"
    / "records"
    / "ethiopian_eca_qos_verified_source_evidence.json"
)


def main() -> int:
    if not SOURCE_PATH.is_file():
        print("configuration_failure=verified ECA QoS directive PDF is missing")
        return 2
    data = SOURCE_PATH.read_bytes()
    if data[:5] != b"%PDF-":
        print("configuration_failure=ECA QoS PDF magic header is invalid")
        return 2
    actual_sha256 = hashlib.sha256(data).hexdigest()
    if actual_sha256 != ARTIFACT_SHA256:
        print("configuration_failure=ECA QoS artifact SHA-256 mismatch")
        return 2
    pages = PolicyPdfExtractor().extract_pages(
        SOURCE_PATH,
        remove_repeated_marginal_lines=False,
    )
    evidence = verified_eca_qos_source_evidence()
    payload = {
        "schema_version": "1.0.0",
        "evidence_set_id": "AMBA-GOV-VERIFIED-SOURCE-ETH-ECA-QOS-794-2021",
        "extracted_page_count": len(pages),
        "evidence": evidence.to_dict(),
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
    print("artifact_integrity_status=verified")
    print("pdf_magic_header_status=verified")
    print("activation_status=verified_source_boundary")
    print("locator_verification_status=not_assessed")
    print("eligible_for_technical_context=true")
    print("eligible_for_readiness_evidence=true")
    print("eligible_for_binding_technical_findings=false")
    print("eligible_for_citation=false")
    print("threshold_activation_ready=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
