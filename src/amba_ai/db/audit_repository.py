from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Iterator, Mapping

from amba_ai.db.governance_repository import create_sqlite_connection
from amba_ai.governance.audit import (
    AuditBlock,
    AuditEvent,
    AuditRepositoryProtocol,
)
from amba_ai.governance.models import (
    GovernanceConfigurationError,
    to_canonical_json,
)
from amba_ai.governance.principals import parse_timestamp


MAX_AUDIT_PAYLOAD_BYTES = 5_000_000
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _require_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(field_name, str):
        raise TypeError("field_name must be a string")

    normalized_field_name = field_name.strip()
    if not normalized_field_name:
        raise ValueError("field_name must not be empty")

    if not isinstance(value, str):
        raise TypeError(
            f"{normalized_field_name} must be a string"
        )

    normalized_value = value.strip()
    if not normalized_value:
        raise GovernanceConfigurationError(
            f"{normalized_field_name} must not be empty"
        )

    return normalized_value


def _rollback_if_active(
    connection: sqlite3.Connection,
) -> None:
    if connection.in_transaction:
        connection.rollback()


def _strict_positive_integer(
    value: object,
    field_name: str,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GovernanceConfigurationError(
            f"Persisted {field_name} must be an integer"
        )

    if value <= 0:
        raise GovernanceConfigurationError(
            f"Persisted {field_name} must be positive"
        )

    return value


def _require_sha256(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise GovernanceConfigurationError(
            f"Persisted {field_name} must be a string"
        )

    normalized = value.strip()
    if _SHA256_PATTERN.fullmatch(normalized) is None:
        raise GovernanceConfigurationError(
            f"Persisted {field_name} must be a lowercase SHA-256 digest"
        )

    return normalized


class AuditRepository(AuditRepositoryProtocol):
    def __init__(
        self,
        db_path: Path | str,
    ) -> None:
        if not isinstance(db_path, (str, Path)):
            raise TypeError("db_path must be a path")

        raw_path = str(db_path).strip()
        if not raw_path:
            raise ValueError("db_path must not be empty")

        self.db_path = Path(raw_path)
        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._lock = threading.RLock()

    @contextmanager
    def _conn(
        self,
    ) -> Iterator[sqlite3.Connection]:
        connection = create_sqlite_connection(
            self.db_path
        )

        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def append_atomic(
        self,
        run_id: str,
        scenario_id: str,
        stage_id: str,
        event_id: str,
        operation_id: str,
        event_type: str,
        timestamp: str,
        payload: Mapping[str, Any],
        schema_version: str,
    ) -> AuditBlock:
        normalized_run_id = _require_text(
            run_id,
            "run_id",
        )
        normalized_scenario_id = _require_text(
            scenario_id,
            "scenario_id",
        )
        normalized_stage_id = _require_text(
            stage_id,
            "stage_id",
        )
        normalized_event_id = _require_text(
            event_id,
            "event_id",
        )
        normalized_operation_id = _require_text(
            operation_id,
            "operation_id",
        )
        normalized_event_type = _require_text(
            event_type,
            "event_type",
        )
        normalized_schema_version = _require_text(
            schema_version,
            "schema_version",
        )
        normalized_timestamp = parse_timestamp(
            timestamp,
            "timestamp",
        ).isoformat()

        if not isinstance(payload, Mapping):
            raise GovernanceConfigurationError(
                "Audit payload must be a mapping"
            )

        try:
            payload_json = to_canonical_json(
                dict(payload)
            )
            canonical_payload = json.loads(
                payload_json
            )
        except (TypeError, ValueError) as error:
            raise GovernanceConfigurationError(
                "Audit event payload cannot be canonically serialized"
            ) from error

        if not isinstance(canonical_payload, dict):
            raise GovernanceConfigurationError(
                "Canonical audit payload must be a mapping"
            )

        payload_bytes = payload_json.encode("utf-8")
        if len(payload_bytes) > MAX_AUDIT_PAYLOAD_BYTES:
            raise GovernanceConfigurationError(
                "Audit payload exceeds maximum size"
            )

        payload_hash = hashlib.sha256(
            payload_bytes
        ).hexdigest()

        with self._lock, self._conn() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE;")

                previous_row = connection.execute(
                    """
                    SELECT block_index, block_hash
                    FROM governance_audit_blocks
                    WHERE run_id = ?
                    ORDER BY block_index DESC
                    LIMIT 1;
                    """,
                    (normalized_run_id,),
                ).fetchone()

                if previous_row is None:
                    block_index = 1
                    previous_hash = hashlib.sha256(
                        f"GENESIS:{normalized_run_id}".encode(
                            "utf-8"
                        )
                    ).hexdigest()
                else:
                    previous_index = _strict_positive_integer(
                        previous_row["block_index"],
                        "block_index",
                    )
                    previous_hash = _require_sha256(
                        previous_row["block_hash"],
                        "block_hash",
                    )
                    block_index = previous_index + 1

                block_material = {
                    "run_id": normalized_run_id,
                    "block_index": block_index,
                    "timestamp": normalized_timestamp,
                    "schema_version": normalized_schema_version,
                    "previous_hash": previous_hash,
                    "payload_hash": payload_hash,
                }
                block_hash = hashlib.sha256(
                    to_canonical_json(
                        block_material
                    ).encode("utf-8")
                ).hexdigest()
                audit_event_id = (
                    f"audit_{normalized_run_id}_{block_index}"
                )

                connection.execute(
                    """
                    INSERT INTO governance_audit_blocks (
                        run_id,
                        block_index,
                        audit_event_id,
                        scenario_id,
                        stage_id,
                        event_id,
                        operation_id,
                        event_type,
                        timestamp,
                        schema_version,
                        payload_json,
                        previous_hash,
                        payload_hash,
                        block_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        normalized_run_id,
                        block_index,
                        audit_event_id,
                        normalized_scenario_id,
                        normalized_stage_id,
                        normalized_event_id,
                        normalized_operation_id,
                        normalized_event_type,
                        normalized_timestamp,
                        normalized_schema_version,
                        payload_json,
                        previous_hash,
                        payload_hash,
                        block_hash,
                    ),
                )

                audit_event = AuditEvent(
                    audit_event_id=audit_event_id,
                    run_id=normalized_run_id,
                    scenario_id=normalized_scenario_id,
                    stage_id=normalized_stage_id,
                    event_id=normalized_event_id,
                    operation_id=normalized_operation_id,
                    event_type=normalized_event_type,
                    timestamp=normalized_timestamp,
                    payload=canonical_payload,
                    previous_hash=previous_hash,
                    payload_hash=payload_hash,
                    block_hash=block_hash,
                    schema_version=normalized_schema_version,
                )
                audit_block = AuditBlock(
                    run_id=normalized_run_id,
                    block_index=block_index,
                    audit_event=audit_event,
                )

                connection.commit()
                return audit_block

            except GovernanceConfigurationError:
                _rollback_if_active(connection)
                raise
            except sqlite3.IntegrityError as error:
                _rollback_if_active(connection)
                raise GovernanceConfigurationError(
                    "Audit block sequence or identifier collision"
                ) from error
            except sqlite3.Error as error:
                _rollback_if_active(connection)
                raise GovernanceConfigurationError(
                    "Atomic audit append transaction failed"
                ) from error
            except Exception:
                _rollback_if_active(connection)
                raise

    def get_block(
        self,
        run_id: str,
        block_index: int,
    ) -> AuditBlock | None:
        normalized_run_id = _require_text(
            run_id,
            "run_id",
        )

        if isinstance(block_index, bool) or not isinstance(
            block_index,
            int,
        ):
            raise GovernanceConfigurationError(
                "block_index must be a positive integer"
            )
        if block_index <= 0:
            raise GovernanceConfigurationError(
                "block_index must be a positive integer"
            )

        with self._lock, self._conn() as connection:
            try:
                row = connection.execute(
                    """
                    SELECT *
                    FROM governance_audit_blocks
                    WHERE run_id = ? AND block_index = ?;
                    """,
                    (
                        normalized_run_id,
                        block_index,
                    ),
                ).fetchone()
            except sqlite3.Error as error:
                raise GovernanceConfigurationError(
                    "Audit block query failed"
                ) from error

        return None if row is None else self._row_to_block(row)

    def get_last_block(
        self,
        run_id: str,
    ) -> AuditBlock | None:
        normalized_run_id = _require_text(
            run_id,
            "run_id",
        )

        with self._lock, self._conn() as connection:
            try:
                row = connection.execute(
                    """
                    SELECT *
                    FROM governance_audit_blocks
                    WHERE run_id = ?
                    ORDER BY block_index DESC
                    LIMIT 1;
                    """,
                    (normalized_run_id,),
                ).fetchone()
            except sqlite3.Error as error:
                raise GovernanceConfigurationError(
                    "Last audit block query failed"
                ) from error

        return None if row is None else self._row_to_block(row)

    def list_scope(
        self,
        run_id: str,
    ) -> tuple[AuditBlock, ...]:
        normalized_run_id = _require_text(
            run_id,
            "run_id",
        )

        with self._lock, self._conn() as connection:
            try:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM governance_audit_blocks
                    WHERE run_id = ?
                    ORDER BY block_index ASC;
                    """,
                    (normalized_run_id,),
                ).fetchall()
            except sqlite3.Error as error:
                raise GovernanceConfigurationError(
                    "Audit scope query failed"
                ) from error

        return tuple(
            self._row_to_block(row)
            for row in rows
        )

    def list_run_ids(self) -> tuple[str, ...]:
        with self._lock, self._conn() as connection:
            try:
                rows = connection.execute(
                    """
                    SELECT DISTINCT run_id
                    FROM governance_audit_blocks
                    ORDER BY run_id ASC;
                    """
                ).fetchall()
            except sqlite3.Error as error:
                raise GovernanceConfigurationError(
                    "Audit run identifier query failed"
                ) from error

        run_ids: list[str] = []
        for row in rows:
            run_ids.append(
                _require_text(
                    row["run_id"],
                    "persisted run_id",
                )
            )

        return tuple(run_ids)

    def count_scope(
        self,
        run_id: str,
    ) -> int:
        normalized_run_id = _require_text(
            run_id,
            "run_id",
        )

        with self._lock, self._conn() as connection:
            try:
                row = connection.execute(
                    """
                    SELECT COUNT(*) AS block_count
                    FROM governance_audit_blocks
                    WHERE run_id = ?;
                    """,
                    (normalized_run_id,),
                ).fetchone()
            except sqlite3.Error as error:
                raise GovernanceConfigurationError(
                    "Audit scope count query failed"
                ) from error

        if row is None:
            return 0

        block_count = row["block_count"]
        if isinstance(block_count, bool) or not isinstance(
            block_count,
            int,
        ):
            raise GovernanceConfigurationError(
                "Persisted audit scope count is invalid"
            )
        if block_count < 0:
            raise GovernanceConfigurationError(
                "Persisted audit scope count is invalid"
            )

        return block_count

    @staticmethod
    def _row_to_block(
        row: sqlite3.Row,
    ) -> AuditBlock:
        try:
            record = {
                key: row[key]
                for key in row.keys()
            }
        except (AttributeError, IndexError, KeyError, TypeError) as error:
            raise GovernanceConfigurationError(
                "Persisted audit row is invalid"
            ) from error

        try:
            payload_json = record["payload_json"]
            if not isinstance(payload_json, str):
                raise TypeError(
                    "payload_json must be a string"
                )
            decoded_payload = json.loads(payload_json)
        except (KeyError, TypeError, ValueError) as error:
            raise GovernanceConfigurationError(
                "Persisted audit payload is not valid JSON"
            ) from error

        if not isinstance(decoded_payload, dict):
            raise GovernanceConfigurationError(
                "Persisted audit payload must decode to a mapping"
            )

        block_index = _strict_positive_integer(
            record.get("block_index"),
            "block_index",
        )
        previous_hash = _require_sha256(
            record.get("previous_hash"),
            "previous_hash",
        )
        payload_hash = _require_sha256(
            record.get("payload_hash"),
            "payload_hash",
        )
        block_hash = _require_sha256(
            record.get("block_hash"),
            "block_hash",
        )

        try:
            audit_event = AuditEvent(
                audit_event_id=record["audit_event_id"],
                run_id=record["run_id"],
                scenario_id=record["scenario_id"],
                stage_id=record["stage_id"],
                event_id=record["event_id"],
                operation_id=record["operation_id"],
                event_type=record["event_type"],
                timestamp=record["timestamp"],
                payload=decoded_payload,
                previous_hash=previous_hash,
                payload_hash=payload_hash,
                block_hash=block_hash,
                schema_version=record["schema_version"],
            )
            return AuditBlock(
                run_id=record["run_id"],
                block_index=block_index,
                audit_event=audit_event,
            )
        except GovernanceConfigurationError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise GovernanceConfigurationError(
                "Persisted audit block is invalid"
            ) from error
