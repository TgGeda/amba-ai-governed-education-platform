from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPOSITORY_ROOT / "kb" / "schemas" / "pdpa_verified_source_evidence.schema.json"
INSTANCE_PATH = REPOSITORY_ROOT / "kb" / "records" / "ethiopian_pdpa_verified_source_evidence.json"


def test_pdpa_generated_evidence_matches_fail_closed_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    instance = json.loads(INSTANCE_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(instance)
