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

from amba_ai.governance.verified_esdp_vi_records import (
    ARTIFACT_SHA256,
    CURRENT_CLASSIFICATION,
    DOCUMENT_TITLE,
    PROGRAMME_PERIOD,
    SOURCE_CLASS,
    SOURCE_ID,
    VERSION_ID,
    quarantined_esdp_vi_candidates,
)
from amba_ai.rag.policy_pdf_extractor import PolicyPdfExtractor

REVIEW_RECORD_ID = "AMBA-GOV-ACADEMIC-REVIEW-001"
SOURCE_RELATIVE_PATH = Path("kb/sources/ethiopia/ETH_ESDP_VI_2021.pdf")
SOURCE_PATH = REPOSITORY_ROOT / SOURCE_RELATIVE_PATH
OUTPUT_BASE = REPOSITORY_ROOT / "kb" / "records" / "ethiopian_esdp_vi_approved_historical_context_evidence"


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
        print("configuration_failure=verified ESDP VI PDF is missing")
        return 2
    data = SOURCE_PATH.read_bytes()
    if data[:5] != b"%PDF-":
        print("configuration_failure=ESDP VI PDF magic header is invalid")
        return 2
    if hashlib.sha256(data).hexdigest() != ARTIFACT_SHA256:
        print("configuration_failure=ESDP VI artifact SHA-256 mismatch")
        return 2

    pages = PolicyPdfExtractor().extract_pages(SOURCE_PATH, remove_repeated_marginal_lines=False)
    records = quarantined_esdp_vi_candidates()
    payload = {
        "schema_version": "2.0.0",
        "record_set_id": "AMBA-GOV-APPROVED-HISTORICAL-CONTEXT-ETH-ESDP-VI-2021",
        "source_id": SOURCE_ID,
        "version_id": VERSION_ID,
        "source_path": SOURCE_RELATIVE_PATH.as_posix(),
        "artifact_sha256": ARTIFACT_SHA256,
        "artifact_integrity_status": "verified",
        "pdf_magic_header_status": "verified",
        "document_title": DOCUMENT_TITLE,
        "programme_period": PROGRAMME_PERIOD,
        "source_class": SOURCE_CLASS,
        "current_classification": CURRENT_CLASSIFICATION,
        "extracted_page_count": len(pages),
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
        "historical_qualification_required": True,
        "current_after_2024_25": False,
        "verified_successor_identified": False,
        "claim_boundaries": {
            "historical_qualification_required": True,
            "current_after_2024_25": False,
            "verified_successor_identified": False,
            "eligible_for_historical_context": True,
            "eligible_for_policy_context": True,
            "eligible_for_readiness_evidence": True,
            "eligible_for_current_programme_claim": False,
            "eligible_for_source_citation": True,
            "eligible_for_provision_citation": False,
            "eligible_for_binding_legal_findings": False,
            "eligible_for_project_enforcement": False,
            "national_binding_status": False,
            "legal_effect": False,
            "deterministic_source_locator_established": False,
            "exact_source_excerpt_verified": False,
            "source_page_locator_verified": False,
            "human_review_required": False,
        },
        "prohibited_claims": {
            "current_national_education_programme": False,
            "binding_legal_obligation": False,
            "statutory_offence": False,
            "statutory_penalty": False,
            "automatic_project_authorization": False,
            "automatic_project_block": False,
            "aastu_institutional_approval": False,
            "formal_legal_opinion": False,
        },
        "remaining_requirements": [
            "historical qualification in every current project use",
            "deterministic source locator for provision-level citation",
            "exact source excerpt verification for provision-level citation",
            "project-specific applicability review for binding findings",
        ],
        "candidates": [record.to_dict() for record in records],
    }
    _write_outputs(payload)
    print(f"output_json={OUTPUT_BASE.with_suffix('.json').relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"output_yaml={OUTPUT_BASE.with_suffix('.yaml').relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"extracted_page_count={len(pages)}")
    print(f"candidate_count={len(records)}")
    print("human_review_status=approved")
    print("historical_qualification_required=true")
    print("eligible_for_current_programme_claim=false")
    print("provision_citation_eligible=false")
    print("binding_finding_eligible=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
