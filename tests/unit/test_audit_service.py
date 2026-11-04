from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from amba_ai.db.audit_repository import AuditRepository
from amba_ai.db.governance_repository import GovernanceRepository
from amba_ai.governance.audit import AuditLedger
from amba_ai.governance.audit_verifier import AuditVerifier
from amba_ai.governance.principals import FixedClock
from amba_ai.services.audit_service import AuditService


@pytest.fixture
def audit_service() -> AuditService:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "audit_service.db"

        governance_repository = GovernanceRepository(
            db_path
        )
        governance_repository.apply_migration_file(
            "src/amba_ai/db/migrations/"
            "003_approval_execution_audit.sql"
        )

        ledger = AuditLedger(
            AuditRepository(db_path),
            FixedClock("2026-06-01T12:00:00Z"),
        )

        yield AuditService(
            ledger,
            AuditVerifier(ledger),
        )


@pytest.mark.parametrize(
    "ledger, verifier",
    (
        (None, object()),
        (object(), None),
        (object(), object()),
    ),
)
def test_constructor_rejects_invalid_dependencies(
    ledger: object,
    verifier: object,
) -> None:
    with pytest.raises(TypeError):
        AuditService(
            ledger,
            verifier,
        )  # type: ignore[arg-type]


def test_append_and_verify_run_scope(
    audit_service: AuditService,
) -> None:
    first = audit_service.append(
        run_id=" RUN-SYNTHETIC ",
        scenario_id=" SCENARIO-SYNTHETIC ",
        stage_id=" STAGE-A ",
        event_id=" EVENT-A ",
        operation_id=" synthetic-operation ",
        event_type=" POLICY_EVALUATED ",
        payload={
            "synthetic": True,
        },
    )

    second = audit_service.append(
        run_id="RUN-SYNTHETIC",
        scenario_id="SCENARIO-SYNTHETIC",
        stage_id="STAGE-B",
        event_id="EVENT-B",
        operation_id="synthetic-operation",
        event_type="EXECUTION_RECORDED",
        payload={
            "status": "succeeded",
        },
    )

    assert first.block_index == 1
    assert second.block_index == 2
    assert (
        second.audit_event.previous_hash
        == first.audit_event.block_hash
    )

    result = audit_service.verify(
        "RUN-SYNTHETIC"
    )

    assert result.valid is True
    assert result.verified_block_count == 2
    assert (
        result.message
        == "tamper-evident within verified scope"
    )


def test_append_redacts_prohibited_payload_fields(
    audit_service: AuditService,
) -> None:
    block = audit_service.append(
        run_id="RUN-REDACTION",
        scenario_id="SCENARIO-REDACTION",
        stage_id="STAGE-REDACTION",
        event_id="EVENT-REDACTION",
        operation_id="synthetic-operation",
        event_type="REDACTION_CHECK",
        payload={
            "visible": "retained",
            "credentials": "must-not-persist",
            "nested": {
                "raw_learner_content": (
                    "must-not-persist"
                ),
                "safe": True,
            },
        },
    )

    payload = block.audit_event.payload

    assert payload["visible"] == "retained"
    assert payload["credentials"] == "[REDACTED]"
    assert (
        payload["nested"]["raw_learner_content"]
        == "[REDACTED]"
    )
    assert payload["nested"]["safe"] is True


def test_verify_empty_scope_is_fail_closed_by_default(
    audit_service: AuditService,
) -> None:
    strict = audit_service.verify(
        "EMPTY-RUN"
    )
    allowed = audit_service.verify(
        "EMPTY-RUN",
        allow_empty=True,
    )

    assert strict.valid is False
    assert (
        strict.failure_code
        == "EMPTY_SCOPE_REJECTED"
    )

    assert allowed.valid is True
    assert allowed.verified_block_count == 0
    assert allowed.failure_code is None
    assert allowed.failure_block_index is None


def test_append_validates_all_identifiers_and_payload(
    audit_service: AuditService,
) -> None:
    valid = {
        "run_id": "RUN",
        "scenario_id": "SCENARIO",
        "stage_id": "STAGE",
        "event_id": "EVENT",
        "operation_id": "operation",
        "event_type": "EVENT_TYPE",
        "payload": {},
    }

    for field_name in (
        "run_id",
        "scenario_id",
        "stage_id",
        "event_id",
        "operation_id",
        "event_type",
    ):
        values = dict(valid)
        values[field_name] = " "

        with pytest.raises(
            ValueError,
            match=field_name,
        ):
            audit_service.append(**values)

    values = dict(valid)
    values["payload"] = []

    with pytest.raises(
        TypeError,
        match="payload must be a mapping",
    ):
        audit_service.append(
            **values
        )  # type: ignore[arg-type]


def test_append_rejects_non_string_identifiers(
    audit_service: AuditService,
) -> None:
    with pytest.raises(
        TypeError,
        match="run_id must be a string",
    ):
        audit_service.append(
            run_id=123,  # type: ignore[arg-type]
            scenario_id="SCENARIO",
            stage_id="STAGE",
            event_id="EVENT",
            operation_id="operation",
            event_type="EVENT_TYPE",
            payload={},
        )


def test_verify_validates_run_and_allow_empty(
    audit_service: AuditService,
) -> None:
    with pytest.raises(
        ValueError,
        match="run_id",
    ):
        audit_service.verify(" ")

    with pytest.raises(
        TypeError,
        match="run_id must be a string",
    ):
        audit_service.verify(
            123  # type: ignore[arg-type]
        )

    with pytest.raises(
        TypeError,
        match="strict Boolean",
    ):
        audit_service.verify(
            "RUN",
            allow_empty=1,  # type: ignore[arg-type]
        )