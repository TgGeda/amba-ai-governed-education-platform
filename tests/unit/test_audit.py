from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
import tempfile
from types import MappingProxyType
from typing import Any

import pytest

from amba_ai.db.audit_repository import AuditRepository
from amba_ai.db.governance_repository import GovernanceRepository
from amba_ai.governance.approvals import EMPTY_SHA256
from amba_ai.governance.audit import (
    REDACTED_VALUE,
    AuditBlock,
    AuditEvent,
    AuditLedger,
    sanitize_audit_payload,
)
from amba_ai.governance.audit_verifier import (
    AuditVerificationResult,
    AuditVerifier,
)
from amba_ai.governance.models import GovernanceConfigurationError
from amba_ai.governance.principals import FixedClock


MIGRATION_003 = Path(
    "src/amba_ai/db/migrations/003_approval_execution_audit.sql"
)
FIXED_TIME = "2026-06-01T12:00:00Z"
SCHEMA_VERSION = "1.0.0"


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class InMemoryLedger:
    SCHEMA_VERSION = SCHEMA_VERSION

    def __init__(
        self,
        scopes: dict[str, tuple[AuditBlock, ...]] | None = None,
        run_ids: tuple[str, ...] | None = None,
    ) -> None:
        self._scopes = scopes or {}
        self._run_ids = run_ids

    def list_scope(self, run_id: str) -> tuple[AuditBlock, ...]:
        return self._scopes.get(run_id, ())

    def list_run_ids(self) -> tuple[str, ...]:
        if self._run_ids is not None:
            return self._run_ids
        return tuple(sorted(self._scopes))


@pytest.fixture
def audit_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "audit.db"
        governance_repository = GovernanceRepository(db_path)
        governance_repository.apply_migration_file(MIGRATION_003)

        repository = AuditRepository(db_path)
        ledger = AuditLedger(repository, FixedClock(FIXED_TIME))
        verifier = AuditVerifier(ledger)

        yield {
            "db_path": db_path,
            "repository": repository,
            "ledger": ledger,
            "verifier": verifier,
        }


def append_event(
    ledger: AuditLedger,
    *,
    run_id: str = "RUN-001",
    stage_id: str = "STAGE-1",
    event_id: str = "EVT-001",
    operation_id: str = "classroom_exercise_telemetry",
    event_type: str = "POLICY_EVALUATED",
    payload: dict[str, Any] | None = None,
) -> AuditBlock:
    return ledger.append(
        run_id=run_id,
        scenario_id="SCENARIO-001",
        stage_id=stage_id,
        event_id=event_id,
        operation_id=operation_id,
        event_type=event_type,
        payload=payload or {"result": "allowed"},
    )


def verifier_for_blocks(
    run_id: str,
    blocks: tuple[AuditBlock, ...],
) -> AuditVerifier:
    return AuditVerifier(InMemoryLedger({run_id: blocks}))


def test_sanitize_audit_payload_redacts_nested_sensitive_keys():
    payload = {
        "credentials": "secret",
        "safe": "visible",
        "nested": {"CHAIN_OF_THOUGHT": "private", "value": 7},
        "items": [{"authorization_secrets": "token"}, "retained"],
    }
    sanitized = sanitize_audit_payload(payload)
    assert sanitized == {
        "credentials": REDACTED_VALUE,
        "safe": "visible",
        "nested": {"CHAIN_OF_THOUGHT": REDACTED_VALUE, "value": 7},
        "items": [{"authorization_secrets": REDACTED_VALUE}, "retained"],
    }


def test_sanitize_audit_payload_rejects_set_values():
    with pytest.raises(TypeError, match="Set values are prohibited"):
        sanitize_audit_payload({"invalid": {"a", "b"}})


def test_audit_event_payload_is_deeply_immutable(audit_env):
    source_payload = {"outer": {"inner": [1, 2, 3]}}
    block = append_event(audit_env["ledger"], payload=source_payload)
    event = block.audit_event
    assert isinstance(event.payload, MappingProxyType)
    assert isinstance(event.payload["outer"], MappingProxyType)
    assert event.payload["outer"]["inner"] == (1, 2, 3)
    source_payload["outer"]["inner"].append(4)
    assert event.payload["outer"]["inner"] == (1, 2, 3)
    with pytest.raises(TypeError):
        event.payload["new"] = "value"


def test_audit_event_rejects_nonmapping_payload():
    with pytest.raises(TypeError, match="payload must be a mapping"):
        AuditEvent(
            audit_event_id="AUDIT-001", run_id="RUN-001",
            scenario_id="SCENARIO-001", stage_id="STAGE-1",
            event_id="EVT-001", operation_id="test_operation",
            event_type="TEST", timestamp=FIXED_TIME,
            payload=["not", "a", "mapping"],
            previous_hash=sha256(b"genesis"),
            payload_hash=sha256(b"payload"), block_hash=sha256(b"block"),
        )


def test_audit_event_rejects_empty_identifier():
    with pytest.raises(ValueError, match="event_id must not be empty"):
        AuditEvent(
            audit_event_id="AUDIT-001", run_id="RUN-001",
            scenario_id="SCENARIO-001", stage_id="STAGE-1", event_id=" ",
            operation_id="test_operation", event_type="TEST",
            timestamp=FIXED_TIME, payload={},
            previous_hash=sha256(b"genesis"),
            payload_hash=sha256(b"payload"), block_hash=sha256(b"block"),
        )


def test_audit_event_rejects_timezone_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        AuditEvent(
            audit_event_id="AUDIT-001", run_id="RUN-001",
            scenario_id="SCENARIO-001", stage_id="STAGE-1",
            event_id="EVT-001", operation_id="test_operation",
            event_type="TEST", timestamp="2026-06-01T12:00:00", payload={},
            previous_hash=sha256(b"genesis"),
            payload_hash=sha256(b"payload"), block_hash=sha256(b"block"),
        )


@pytest.mark.parametrize(
    "field_name, invalid_digest",
    [("previous_hash", "z" * 64), ("payload_hash", "0" * 64), ("block_hash", EMPTY_SHA256)],
)
def test_audit_event_rejects_invalid_digests(field_name: str, invalid_digest: str):
    values = {
        "previous_hash": sha256(b"genesis"),
        "payload_hash": sha256(b"payload"),
        "block_hash": sha256(b"block"),
    }
    values[field_name] = invalid_digest
    with pytest.raises(ValueError):
        AuditEvent(
            audit_event_id="AUDIT-001", run_id="RUN-001",
            scenario_id="SCENARIO-001", stage_id="STAGE-1",
            event_id="EVT-001", operation_id="test_operation",
            event_type="TEST", timestamp=FIXED_TIME, payload={},
            previous_hash=values["previous_hash"],
            payload_hash=values["payload_hash"], block_hash=values["block_hash"],
        )


def test_audit_event_serializes_without_mutable_internal_types(audit_env):
    event = append_event(audit_env["ledger"], payload={"nested": {"values": [1, 2]}}).audit_event
    serialized = event.to_dict()
    assert serialized["payload"] == {"nested": {"values": [1, 2]}}
    assert isinstance(serialized["payload"], dict)
    assert isinstance(serialized["payload"]["nested"], dict)
    assert isinstance(serialized["payload"]["nested"]["values"], list)
    assert event.to_canonical_json()


def test_audit_block_rejects_boolean_index(audit_env):
    event = append_event(audit_env["ledger"]).audit_event
    with pytest.raises(TypeError, match="block_index must be an integer"):
        AuditBlock(run_id=event.run_id, block_index=True, audit_event=event)


def test_audit_block_rejects_nonpositive_index(audit_env):
    event = append_event(audit_env["ledger"]).audit_event
    with pytest.raises(ValueError, match="strictly positive"):
        AuditBlock(run_id=event.run_id, block_index=0, audit_event=event)


def test_audit_block_rejects_run_mismatch(audit_env):
    event = append_event(audit_env["ledger"]).audit_event
    with pytest.raises(ValueError, match="does not match"):
        AuditBlock(run_id="RUN-DIFFERENT", block_index=1, audit_event=event)


def test_audit_ledger_validates_constructor_dependencies(audit_env):
    with pytest.raises(TypeError, match="audit_repository is required"):
        AuditLedger(None, FixedClock(FIXED_TIME))
    with pytest.raises(TypeError, match="clock is required"):
        AuditLedger(audit_env["repository"], None)


def test_audit_ledger_rejects_empty_identifiers(audit_env):
    with pytest.raises(ValueError, match="run_id must not be empty"):
        append_event(audit_env["ledger"], run_id=" ")


def test_audit_ledger_rejects_nonmapping_payload(audit_env):
    with pytest.raises(TypeError, match="payload must be a mapping"):
        audit_env["ledger"].append(
            run_id="RUN-001", scenario_id="SCENARIO-001", stage_id="STAGE-1",
            event_id="EVT-001", operation_id="test_operation",
            event_type="TEST", payload=["invalid"],
        )


def test_audit_ledger_redacts_sensitive_fields_before_persistence(audit_env):
    block = append_event(
        audit_env["ledger"],
        payload={"credentials": "secret", "normal": "retained", "nested": {"system_prompts": "hidden"}},
    )
    assert block.audit_event.payload["credentials"] == REDACTED_VALUE
    assert block.audit_event.payload["normal"] == "retained"
    assert block.audit_event.payload["nested"]["system_prompts"] == REDACTED_VALUE
    assert audit_env["ledger"].get_block("RUN-001", 1) == block


def test_audit_ledger_get_block_validates_index(audit_env):
    with pytest.raises(TypeError, match="block_index must be an integer"):
        audit_env["ledger"].get_block("RUN-001", True)
    with pytest.raises(ValueError, match="strictly positive"):
        audit_env["ledger"].get_block("RUN-001", 0)


def test_audit_chain_verifies_successfully(audit_env):
    first = append_event(audit_env["ledger"])
    second = append_event(audit_env["ledger"], stage_id="STAGE-2", event_id="EVT-002", payload={"result": "held"})
    assert first.block_index == 1
    assert second.block_index == 2
    assert second.audit_event.previous_hash == first.audit_event.block_hash
    result = audit_env["verifier"].verify_scope("RUN-001")
    assert result.valid is True
    assert result.verified_block_count == 2
    assert result.failure_code is None
    assert result.message == "tamper-evident within verified scope"


def test_empty_scope_is_rejected_by_default_and_optional_when_explicit(audit_env):
    rejected = audit_env["verifier"].verify_scope("RUN-EMPTY")
    allowed = audit_env["verifier"].verify_scope("RUN-EMPTY", allow_empty=True)
    assert rejected.valid is False
    assert rejected.failure_code == "EMPTY_SCOPE_REJECTED"
    assert allowed.valid is True
    assert allowed.verified_block_count == 0


def test_verifier_detects_payload_tampering(audit_env):
    block = append_event(audit_env["ledger"])
    tampered_event = replace(block.audit_event, payload={"result": "tampered"})
    result = verifier_for_blocks(
        block.run_id,
        (AuditBlock(run_id=block.run_id, block_index=block.block_index, audit_event=tampered_event),),
    ).verify_scope(block.run_id)
    assert result.valid is False
    assert result.failure_code == "PAYLOAD_HASH_MISMATCH"


def test_verifier_detects_previous_hash_tampering(audit_env):
    block = append_event(audit_env["ledger"])
    tampered_event = replace(block.audit_event, previous_hash=sha256(b"different-previous-hash"))
    result = verifier_for_blocks(block.run_id, (AuditBlock(block.run_id, 1, tampered_event),)).verify_scope(block.run_id)
    assert result.valid is False
    assert result.failure_code == "PREVIOUS_HASH_MISMATCH"


def test_verifier_detects_block_hash_tampering(audit_env):
    block = append_event(audit_env["ledger"])
    tampered_event = replace(block.audit_event, block_hash=sha256(b"different-block-hash"))
    result = verifier_for_blocks(block.run_id, (AuditBlock(block.run_id, 1, tampered_event),)).verify_scope(block.run_id)
    assert result.valid is False
    assert result.failure_code == "BLOCK_HASH_MISMATCH"


def test_verifier_detects_schema_version_tampering(audit_env):
    block = append_event(audit_env["ledger"])
    tampered_event = replace(block.audit_event, schema_version="9.9.9")
    result = verifier_for_blocks(block.run_id, (AuditBlock(block.run_id, 1, tampered_event),)).verify_scope(block.run_id)
    assert result.valid is False
    assert result.failure_code == "SCHEMA_VERSION_MISMATCH"


def test_verifier_detects_index_gap(audit_env):
    first = append_event(audit_env["ledger"])
    second = append_event(audit_env["ledger"], event_id="EVT-002")
    result = verifier_for_blocks("RUN-001", (first, replace(second, block_index=3))).verify_scope("RUN-001")
    assert result.valid is False
    assert result.failure_code == "INDEX_SEQUENCE_BROKEN"


def test_verifier_detects_duplicate_event_identifier(audit_env):
    first = append_event(audit_env["ledger"])
    second = append_event(audit_env["ledger"], event_id="EVT-002")
    duplicate_event = replace(second.audit_event, audit_event_id=first.audit_event.audit_event_id)
    duplicate_block = AuditBlock(run_id=second.run_id, block_index=second.block_index, audit_event=duplicate_event)
    result = verifier_for_blocks("RUN-001", (first, duplicate_block)).verify_scope("RUN-001")
    assert result.valid is False
    assert result.failure_code == "AUDIT_EVENT_ID_DUPLICATE"


def test_verify_all_scopes_returns_deterministic_run_order(audit_env):
    append_event(audit_env["ledger"], run_id="RUN-Z")
    append_event(audit_env["ledger"], run_id="RUN-A")
    results = audit_env["verifier"].verify_all_scopes()
    assert tuple(result.run_id for result in results) == ("RUN-A", "RUN-Z")
    assert all(result.valid for result in results)


def test_audit_verification_result_enforces_invariants():
    with pytest.raises(ValueError, match="valid result cannot contain failure details"):
        AuditVerificationResult(
            valid=True, run_id="RUN-001", verified_block_count=1,
            failure_block_index=1, failure_code="UNEXPECTED",
            message="invalid combination",
        )
    with pytest.raises(ValueError, match="invalid result requires a failure_code"):
        AuditVerificationResult(
            valid=False, run_id="RUN-001", verified_block_count=0,
            failure_block_index=1, failure_code=None, message="missing code",
        )


def test_repository_recreation_preserves_verifiable_chain(audit_env):
    append_event(audit_env["ledger"])
    append_event(audit_env["ledger"], event_id="EVT-002", stage_id="STAGE-2")
    reopened_repository = AuditRepository(audit_env["db_path"])
    reopened_ledger = AuditLedger(reopened_repository, FixedClock(FIXED_TIME))
    result = AuditVerifier(reopened_ledger).verify_scope("RUN-001")
    assert result.valid is True
    assert result.verified_block_count == 2
    assert reopened_ledger.count_scope("RUN-001") == 2
    assert reopened_ledger.list_run_ids() == ("RUN-001",)


def test_repository_foreign_database_tampering_is_detected(audit_env):
    block = append_event(audit_env["ledger"])

    connection = sqlite3.connect(str(audit_env["db_path"]))
    try:
        connection.execute(
            """
            UPDATE governance_audit_blocks
            SET payload_json = ?
            WHERE run_id = ? AND block_index = ?;
            """,
            ('{"result":"tampered"}', block.run_id, block.block_index),
        )
        connection.commit()
    finally:
        connection.close()

    result = audit_env["verifier"].verify_scope(block.run_id)
    assert result.valid is False
    assert result.failure_code == "PAYLOAD_HASH_MISMATCH"
