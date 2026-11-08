from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_all_readiness_mapping_references_resolve() -> None:
    mapping = yaml.safe_load(
        (ROOT / "config" / "readiness_evidence_mapping.yaml").read_text(
            encoding="utf-8"
        )
    )
    catalog = json.loads(
        (ROOT / "kb" / "passages" / "verified_passage_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    y3172 = yaml.safe_load(
        (ROOT / "kb" / "records" / "itu_y3172_verified_records.yaml").read_text(
            encoding="utf-8"
        )
    )

    passage_ids = {row["passage_id"] for row in catalog["passages"]}
    y3172_ids = {row["record_id"] for row in y3172["records"]}

    missing_passages: dict[str, list[str]] = {}
    missing_y3172: dict[str, list[str]] = {}
    for row in mapping["mappings"]:
        mapping_id = row[0]
        passages = row[6]
        records = row[7]
        unresolved_passages = sorted(set(passages) - passage_ids)
        unresolved_records = sorted(set(records) - y3172_ids)
        if unresolved_passages:
            missing_passages[mapping_id] = unresolved_passages
        if unresolved_records:
            missing_y3172[mapping_id] = unresolved_records

    assert not missing_passages, f"unresolved readiness passage IDs: {missing_passages}"
    assert not missing_y3172, f"unresolved Y.3172 record IDs: {missing_y3172}"


def test_readiness_mapping_uses_only_approved_passages() -> None:
    mapping = yaml.safe_load(
        (ROOT / "config" / "readiness_evidence_mapping.yaml").read_text(
            encoding="utf-8"
        )
    )
    catalog = json.loads(
        (ROOT / "kb" / "passages" / "verified_passage_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    by_id = {row["passage_id"]: row for row in catalog["passages"]}

    referenced = {pid for row in mapping["mappings"] for pid in row[6]}
    assert referenced
    assert all(by_id[pid]["human_review_status"] == "approved" for pid in referenced)
    assert all(by_id[pid]["provision_citation_eligible"] is True for pid in referenced)
    assert all(by_id[pid]["binding_finding_eligible"] is False for pid in referenced)
