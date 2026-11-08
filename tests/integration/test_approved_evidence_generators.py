from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / "kb" / "records"

CASES = {
    "ethiopian_cybersecurity_policy_approved_context_evidence": {
        "applicability_status": "unresolved",
    },
    "ethiopian_esdp_vi_approved_historical_context_evidence": {
        "historical_qualification_required": True,
        "current_after_2024_25": False,
    },
    "unicef_ai_children_approved_guidance_evidence": {
        "national_binding_status": False,
        "legal_effect": False,
    },
}


def test_approved_generator_outputs_are_equivalent_and_fail_closed() -> None:
    for stem, expected in CASES.items():
        json_path = RECORDS / f"{stem}.json"
        yaml_path = RECORDS / f"{stem}.yaml"
        assert json_path.is_file(), json_path
        assert yaml_path.is_file(), yaml_path
        json_data = json.loads(json_path.read_text(encoding="utf-8"))
        yaml_data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert json_data == yaml_data
        assert json_data["human_review_status"] == "approved"
        assert json_data["approval_record_id"] == "AMBA-GOV-ACADEMIC-REVIEW-001"
        assert json_data["approval_method"] == "active_shared_document_review"
        assert json_data["source_citation_eligible"] is True
        assert json_data["contextual_evidence_eligible"] is True
        assert json_data["provision_citation_eligible"] is False
        assert json_data["binding_finding_eligible"] is False
        assert json_data["claim_boundaries"]["human_review_required"] is False
        for key, value in expected.items():
            assert json_data[key] == value


def test_obsolete_review_required_outputs_are_absent() -> None:
    obsolete = [
        "ethiopian_cybersecurity_policy_review_required_evidence.json",
        "ethiopian_cybersecurity_policy_review_required_evidence.yaml",
        "ethiopian_esdp_vi_review_required_evidence.json",
        "ethiopian_esdp_vi_review_required_evidence.yaml",
        "unicef_ai_children_review_required_evidence.json",
        "unicef_ai_children_review_required_evidence.yaml",
    ]
    assert not [name for name in obsolete if (RECORDS / name).exists()]
