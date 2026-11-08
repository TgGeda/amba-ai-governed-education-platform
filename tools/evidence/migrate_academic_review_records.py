#!/usr/bin/env python3
"""Migrate AMBA-GOV kb/records after active shared-document academic approval.

Run from the repository root:
    python tools/evidence/migrate_academic_review_records.py --apply

The script:
- creates a timestamped backup of kb/records;
- renames the three former review_required evidence pairs;
- creates kb/records/academic_review_record.json;
- adds catalog-level academic-review metadata to all listed JSON/YAML records;
- preserves authority and legal-applicability boundaries;
- updates textual references to renamed files across the repository;
- validates the migrated records and writes a migration report;
- supports --dry-run and is idempotent.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "PyYAML is required. Install it with: python -m pip install PyYAML"
    ) from exc

REVIEW_ID = "AMBA-GOV-ACADEMIC-REVIEW-001"
REVIEWER_NAME = "Asrat Mulatu"
RECORD_OWNER = "Birhan Abuhay Jemere"
INSTITUTION = "Addis Ababa Science and Technology University"

RENAMES = {
    "ethiopian_cybersecurity_policy_review_required_evidence.json":
        "ethiopian_cybersecurity_policy_approved_context_evidence.json",
    "ethiopian_cybersecurity_policy_review_required_evidence.yaml":
        "ethiopian_cybersecurity_policy_approved_context_evidence.yaml",
    "ethiopian_esdp_vi_review_required_evidence.json":
        "ethiopian_esdp_vi_approved_historical_context_evidence.json",
    "ethiopian_esdp_vi_review_required_evidence.yaml":
        "ethiopian_esdp_vi_approved_historical_context_evidence.yaml",
    "unicef_ai_children_review_required_evidence.json":
        "unicef_ai_children_approved_guidance_evidence.json",
    "unicef_ai_children_review_required_evidence.yaml":
        "unicef_ai_children_approved_guidance_evidence.yaml",
}

TARGETS = {
    "ethiopian_cybersecurity_policy_approved_context_evidence.json",
    "ethiopian_cybersecurity_policy_approved_context_evidence.yaml",
    "ethiopian_eca_qos_verified_source_evidence.json",
    "ethiopian_eca_qos_verified_source_evidence.yaml",
    "ethiopian_esdp_vi_approved_historical_context_evidence.json",
    "ethiopian_esdp_vi_approved_historical_context_evidence.yaml",
    "ethiopian_pdpa_verified_source_evidence.json",
    "ethiopian_pdpa_verified_source_evidence.yaml",
    "ethiopian_stme_verified_context_evidence.json",
    "ethiopian_stme_verified_context_evidence.yaml",
    "itu_ai_readiness_2_verified_facts.json",
    "itu_ai_readiness_2_verified_facts.yaml",
    "itu_y3172_verified_records.yaml",
    "unesco_ai_ethics_verified_records.yaml",
    "unicef_ai_children_approved_guidance_evidence.json",
    "unicef_ai_children_approved_guidance_evidence.yaml",
}

TEXT_EXTENSIONS = {
    ".json", ".jsonl", ".yaml", ".yml", ".py", ".md", ".txt",
    ".toml", ".ini", ".cfg", ".sql", ".ps1", ".bat", ".cmd"
}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache"}

REVIEW_RECORD = {
    "review_record_id": REVIEW_ID,
    "review_type": "academic_advisor_review",
    "review_status": "approved",
    "record_status": "active",
    "reviewer_name": REVIEWER_NAME,
    "reviewer_title": "Professor",
    "reviewer_role": "Academic Advisor",
    "reviewer_institution": INSTITUTION,
    "reviewer_institution_abbreviation": "AASTU",
    "relationship_to_project": f"Academic advisor to {RECORD_OWNER}",
    "approval_method": "active_shared_document_review",
    "approved_passage_count": 90,
    "record_owner": RECORD_OWNER,
    "evidence": {
        "type": "active_shared_document",
        "version_history_location": "Microsoft 365 shared document",
        "reviewer_edits_present": True,
        "reviewer_identity_visible_in_version_history": True,
        "version_history_retained_externally": True,
        "email_confirmation_available": True,
    },
    "scope_boundary": {
        "catalog_inclusion": True,
        "source_grounded_retrieval": True,
        "contextual_analysis": True,
        "project_documentation": True,
        "aastu_institutional_approval": False,
        "formal_legal_opinion": False,
        "automatic_legal_applicability": False,
        "automatic_binding_finding": False,
    },
}

COMMON_APPROVAL = {
    "human_review_status": "approved",
    "approval_record_id": REVIEW_ID,
    "approval_method": "active_shared_document_review",
    "review_record_status": "active",
    "approval_record_owner": RECORD_OWNER,
    "activation_status": "human_review_approved_for_defined_scope",
    "source_citation_eligible": True,
    "contextual_evidence_eligible": True,
    "provision_citation_eligible": False,
    "binding_finding_eligible": False,
    "binding_finding_status": "requires_project_specific_applicability_review",
}

PER_FILE = {
    "ethiopian_cybersecurity_policy_approved_context_evidence": {
        "applicability_status": "unresolved",
        "national_binding_status": False,
        "legal_effect": False,
    },
    "ethiopian_esdp_vi_approved_historical_context_evidence": {
        "historical_qualification_required": True,
        "current_after_2024_25": False,
        "verified_successor_identified": False,
        "national_binding_status": False,
        "legal_effect": False,
    },
    "unicef_ai_children_approved_guidance_evidence": {
        "national_binding_status": False,
        "legal_effect": False,
    },
    "ethiopian_eca_qos_verified_source_evidence": {
        "applicability_status": "unresolved",
    },
    "ethiopian_pdpa_verified_source_evidence": {
        "applicability_status": "unresolved",
        "official_translation_verified": False,
        "translation_equivalence_claimed": False,
        "exceptions_reviewed": False,
    },
    "ethiopian_stme_verified_context_evidence": {
        "formal_adoption_status": "unverified",
        "national_binding_status": False,
        "legal_effect": False,
    },
    "itu_ai_readiness_2_verified_facts": {
        "national_ai_readiness_score": None,
        "overall_project_score": None,
        "score_status": "withheld_pending_methodology_and_evidence_coverage",
        "national_binding_status": False,
        "legal_effect": False,
    },
    "itu_y3172_verified_records": {
        "mapping_type": "application_level_interpreted_mapping",
        "formal_y3172_conformance": False,
        "itu_certification": False,
        "national_binding_status": False,
        "legal_effect": False,
    },
    "unesco_ai_ethics_verified_records": {
        "source_class": "international_recommendation",
        "national_binding_status": False,
        "legal_effect": False,
    },
}

# Only these containers receive per-item approval references. Other nested dictionaries
# such as locators, hashes, or scope boundaries are left untouched.
RECORD_CONTAINER_KEYS = {
    "records", "passages", "facts", "evidence_records", "verified_records",
    "verified_facts", "items", "entries"
}


def load_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def dump_document(path: Path, data: Any) -> str:
    if path.suffix.lower() == ".json":
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=110,
    )


def clean_review_required_values(value: Any) -> Any:
    """Remove only obsolete academic-review wording, not legal/technical review requirements."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key == "human_review_status" and item == "pending":
                cleaned[key] = "approved"
            else:
                cleaned[key] = clean_review_required_values(item)
        return cleaned
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, str) and item.strip().lower() in {
                "human excerpt approval",
                "human approval required for provision citation",
                "academic review required",
            }:
                continue
            result.append(clean_review_required_values(item))
        return result
    return value


def apply_to_record_items(data: Any) -> None:
    if not isinstance(data, dict):
        return
    for key, value in data.items():
        if key in RECORD_CONTAINER_KEYS and isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    item["human_review_status"] = "approved"
                    item["approval_record_id"] = REVIEW_ID
                    # Approval alone must never activate binding legal use.
                    if "binding_finding_eligible" in item:
                        item["binding_finding_eligible"] = False
        elif isinstance(value, dict):
            apply_to_record_items(value)


def migrate_document(path: Path) -> tuple[Any, bool]:
    original = load_document(path)
    if not isinstance(original, dict):
        raise ValueError(f"Expected object at document root: {path}")
    data = clean_review_required_values(copy.deepcopy(original))
    strict_schema_records = {"ethiopian_pdpa_verified_source_evidence"}
    if path.stem not in strict_schema_records:
        data.update(COMMON_APPROVAL)
        data.update(PER_FILE.get(path.stem, {}))
        apply_to_record_items(data)
    return data, data != original


def iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def replace_filename_references(root: Path, dry_run: bool, changed: list[str]) -> None:
    replacements = {old: new for old, new in RENAMES.items()}
    protected = {
        "migrate_academic_review_records.py",
        "tools/evidence/migrate_academic_review_records.py",
        "tools/evidence/generate_cybersecurity_policy_review_required_evidence.py",
        "tools/evidence/generate_esdp_vi_review_required_evidence.py",
        "tools/evidence/generate_unicef_review_required_evidence.py",
    }
    for path in iter_text_files(root):
        relative = path.relative_to(root).as_posix()
        if relative in protected:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            continue
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != text:
            changed.append(str(path.relative_to(root)))
            if not dry_run:
                path.write_text(updated, encoding="utf-8")


def validate(records_dir: Path) -> list[str]:
    errors: list[str] = []
    review_path = records_dir / "academic_review_record.json"
    if not review_path.exists():
        errors.append("academic_review_record.json is missing")
    else:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if review != REVIEW_RECORD:
            errors.append("academic_review_record.json does not match the required record")

    for old in RENAMES:
        if (records_dir / old).exists():
            errors.append(f"obsolete filename remains: {old}")
    for new in RENAMES.values():
        if not (records_dir / new).exists():
            errors.append(f"renamed file is missing: {new}")

    for name in sorted(TARGETS):
        path = records_dir / name
        if not path.exists():
            errors.append(f"expected evidence file is missing: {name}")
            continue
        data = load_document(path)
        if not isinstance(data, dict):
            errors.append(f"root is not an object: {name}")
            continue
        expected = {
            "human_review_status": "approved",
            "approval_record_id": REVIEW_ID,
            "approval_method": "active_shared_document_review",
            "review_record_status": "active",
            "binding_finding_eligible": False,
            "provision_citation_eligible": False,
        }
        strict_schema_records = {"ethiopian_pdpa_verified_source_evidence.json", "ethiopian_pdpa_verified_source_evidence.yaml"}
        if name not in strict_schema_records:
            for key, value in expected.items():
                if data.get(key) != value:
                    errors.append(f"{name}: {key} must be {value!r}")
        if data.get("aastu_institutional_approval") is True:
            errors.append(f"{name}: must not claim AASTU institutional approval")
        if data.get("formal_legal_opinion") is True:
            errors.append(f"{name}: must not claim a formal legal opinion")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="AMBA-GOV repository root")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write changes")
    mode.add_argument("--dry-run", action="store_true", help="show the migration without writing")
    args = parser.parse_args()
    dry_run = not args.apply
    root = args.root.resolve()
    records_dir = root / "kb" / "records"
    if not records_dir.is_dir():
        raise SystemExit(f"Not an AMBA-GOV root; missing: {records_dir}")

    missing_originals = [old for old, new in RENAMES.items()
                         if not (records_dir / old).exists() and not (records_dir / new).exists()]
    if missing_originals:
        raise SystemExit("Missing expected source files: " + ", ".join(missing_originals))

    changed: list[str] = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "migration_backups" / f"kb_records_before_academic_review_{timestamp}"
    if not dry_run:
        backup_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(records_dir, backup_dir)

    # Rename first. If already migrated, leave target in place.
    for old, new in RENAMES.items():
        src, dst = records_dir / old, records_dir / new
        if src.exists():
            if dst.exists():
                raise SystemExit(f"Refusing to overwrite existing target: {dst}")
            changed.append(f"{src.relative_to(root)} -> {dst.relative_to(root)}")
            if not dry_run:
                src.rename(dst)

    # In dry-run mode, process the old path as if it had the new name.
    for name in sorted(TARGETS):
        path = records_dir / name
        actual = path
        if dry_run and not actual.exists():
            old_match = next((old for old, new in RENAMES.items() if new == name), None)
            if old_match:
                actual = records_dir / old_match
        if not actual.exists():
            raise SystemExit(f"Expected evidence file not found: {path}")
        data, modified = migrate_document(actual)
        if modified or actual.name != name:
            changed.append(str(path.relative_to(root)))
            if not dry_run:
                path.write_text(dump_document(path, data), encoding="utf-8")

    review_path = records_dir / "academic_review_record.json"
    changed.append(str(review_path.relative_to(root)))
    if not dry_run:
        review_path.write_text(json.dumps(REVIEW_RECORD, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    replace_filename_references(root, dry_run, changed)

    report = {
        "migration": "academic_shared_document_review",
        "mode": "dry_run" if dry_run else "applied",
        "review_record_id": REVIEW_ID,
        "reviewer": REVIEWER_NAME,
        "record_owner": RECORD_OWNER,
        "changed_paths": sorted(set(changed)),
        "backup_directory": str(backup_dir.relative_to(root)) if not dry_run else None,
    }

    if not dry_run:
        errors = validate(records_dir)
        report["validation_errors"] = errors
        report_path = root / "academic_review_migration_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if errors:
            print(json.dumps(report, indent=2))
            print(f"Migration validation failed. Restore from: {backup_dir}", file=sys.stderr)
            return 1
        print(f"Migration applied successfully. Backup: {backup_dir}")
        print(f"Report: {report_path}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("Dry run only. Re-run with --apply to write changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
