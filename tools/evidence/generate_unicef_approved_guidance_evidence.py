from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import yaml

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

REVIEW_RECORD_ID = "AMBA-GOV-ACADEMIC-REVIEW-001"
SOURCE_RELATIVE_PATH = Path("kb/sources/international/UNICEF_AI_CHILDREN_V3_2025.pdf")
SOURCE_PATH = REPOSITORY_ROOT / SOURCE_RELATIVE_PATH
OUTPUT_BASE = REPOSITORY_ROOT / "kb" / "records" / "unicef_ai_children_approved_guidance_evidence"


def _write_outputs(payload: dict[str, object]) -> None:
    OUTPUT_BASE.parent.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_BASE.with_suffix(".json")
    yaml_path = OUTPUT_BASE.with_suffix(".yaml")
    json_tmp = json_path.with_suffix(".json.tmp")
    yaml_tmp = yaml_path.with_suffix(".yaml.tmp")
    json_tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    yaml_tmp.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=True, default_flow_style=False, width=110), encoding="utf-8", newline="\n")
    json_tmp.replace(json_path)
    yaml_tmp.replace(yaml_path)


def main() -> int:
    if not SOURCE_PATH.is_file():
        print("configuration_failure=verified UNICEF PDF is missing")
        return 2
    data = SOURCE_PATH.read_bytes()
    if data[:5] != b"%PDF-":
        print("configuration_failure=UNICEF PDF magic header is invalid")
        return 2
    if hashlib.sha256(data).hexdigest() != ARTIFACT_SHA256:
        print("configuration_failure=UNICEF artifact SHA-256 mismatch")
        return 2

    records = quarantined_unicef_supporting_evidence_records()
    payload = {
        "schema_version": "2.0.0",
        "record_set_id": "AMBA-GOV-APPROVED-GUIDANCE-UNICEF-AI-CHILDREN-3.0",
        "source_id": SOURCE_ID,
        "version_id": VERSION_ID,
        "source_path": SOURCE_RELATIVE_PATH.as_posix(),
        "artifact_sha256": ARTIFACT_SHA256,
        "artifact_integrity_status": "verified",
        "pdf_magic_header_status": "verified",
        "document_title": DOCUMENT_TITLE,
        "publication_date": PUBLICATION_DATE,
        "source_class": SOURCE_CLASS,
        "candidate_count": len(records),
        "human_review_status": "approved",
        "approval_record_id": REVIEW_RECORD_ID,
        "approval_method": "active_shared_document_review",
        "review_record_status": "active",
        "approval_record_owner": "Birhan Abuhay Jemere",
        "activation_status": "human_review_approved_for_defined_scope",
        "source_citation_eligible": True,
        "contextual_evidence_eligible": True,
        "provision_citation_eligible": False,
        "binding_finding_eligible": False,
        "binding_finding_status": "requires_project_specific_applicability_review",
        "national_binding_status": False,
        "legal_effect": False,
        "claim_boundaries": {
            "international_supporting_evidence_only": True,
            "national_binding_status": False,
            "legal_effect": False,
            "eligible_for_source_citation": True,
            "eligible_for_provision_citation": False,
            "eligible_for_binding_findings": False,
            "independent_ethiopian_legal_violation": False,
            "deterministic_source_locator_established": False,
            "exact_source_excerpt_verified": False,
            "source_page_locator_verified": False,
            "human_review_required": False,
        },
        "prohibited_claims": {
            "ethiopian_legislation": False,
            "ethiopian_regulatory_approval": False,
            "automatic_project_authorization": False,
            "automatic_project_block": False,
            "aastu_institutional_approval": False,
            "formal_legal_opinion": False,
        },
        "remaining_requirements": [
            "deterministic source locator for provision-level citation",
            "exact source excerpt verification for provision-level citation",
            "project-specific applicability review for binding findings",
        ],
        "candidates": [record.to_dict() for record in records],
    }
    _write_outputs(payload)
    print(f"output_json={OUTPUT_BASE.with_suffix('.json').relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"output_yaml={OUTPUT_BASE.with_suffix('.yaml').relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"candidate_count={len(records)}")
    print("human_review_status=approved")
    print("international_supporting_evidence_only=true")
    print("source_citation_eligible=true")
    print("provision_citation_eligible=false")
    print("binding_finding_eligible=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
