from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from amba_ai.governance.approvals import validate_sha256
from amba_ai.governance.models import (
    GovernanceConfigurationError,
    deep_freeze,
    to_canonical_json,
)
from amba_ai.governance.principals import (
    Clock,
    parse_timestamp,
)


PROHIBITED_AUDIT_KEYS = frozenset(
    {
        "hidden_reasoning",
        "chain_of_thought",
        "system_prompts",
        "raw_learner_content",
        "credentials",
        "credential_hashes",
        "authorization_secrets",
        "private_absolute_paths",
    }
)

REDACTED_VALUE = "[REDACTED]"


def _normalize_required_identifier(
    value: str,
    field_name: str,
) -> str:
    normalized = str(value).strip()

    if not normalized:
        raise ValueError(
            f"{field_name} must not be empty"
        )

    return normalized


def _sanitize_for_output(
    value: Any,
) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize_for_output(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [
            _sanitize_for_output(item)
            for item in value
        ]

    if isinstance(value, list):
        return [
            _sanitize_for_output(item)
            for item in value
        ]

    return value


def sanitize_audit_payload(
    value: Any,
) -> Any:
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}

        for raw_key, raw_value in value.items():
            key = str(raw_key)
            normalized_key = key.strip().lower()

            if normalized_key in PROHIBITED_AUDIT_KEYS:
                cleaned[key] = REDACTED_VALUE
            else:
                cleaned[key] = sanitize_audit_payload(
                    raw_value
                )

        return cleaned

    if isinstance(value, (list, tuple)):
        return [
            sanitize_audit_payload(item)
            for item in value
        ]

    if isinstance(value, (set, frozenset)):
        raise TypeError(
            "Set values are prohibited in audit payloads"
        )

    return value


@dataclass(frozen=True, slots=True)
class AuditEvent:
    audit_event_id: str
    run_id: str
    scenario_id: str
    stage_id: str
    event_id: str
    operation_id: str
    event_type: str
    timestamp: str
    payload: Mapping[str, Any]
    previous_hash: str
    payload_hash: str
    block_hash: str
    schema_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.payload, Mapping):
            raise TypeError(
                "payload must be a mapping"
            )

        audit_event_id = (
            _normalize_required_identifier(
                self.audit_event_id,
                "audit_event_id",
            )
        )
        run_id = _normalize_required_identifier(
            self.run_id,
            "run_id",
        )
        scenario_id = (
            _normalize_required_identifier(
                self.scenario_id,
                "scenario_id",
            )
        )
        stage_id = _normalize_required_identifier(
            self.stage_id,
            "stage_id",
        )
        event_id = _normalize_required_identifier(
            self.event_id,
            "event_id",
        )
        operation_id = (
            _normalize_required_identifier(
                self.operation_id,
                "operation_id",
            )
        )
        event_type = (
            _normalize_required_identifier(
                self.event_type,
                "event_type",
            )
        )
        schema_version = (
            _normalize_required_identifier(
                self.schema_version,
                "schema_version",
            )
        )

        timestamp = parse_timestamp(
            self.timestamp,
            "timestamp",
        ).isoformat()

        previous_hash = validate_sha256(
            self.previous_hash,
            "previous_hash",
        )
        payload_hash = validate_sha256(
            self.payload_hash,
            "payload_hash",
        )
        block_hash = validate_sha256(
            self.block_hash,
            "block_hash",
        )

        frozen_payload = deep_freeze(
            self.payload
        )

        try:
            to_canonical_json(frozen_payload)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "payload must be canonically serializable"
            ) from error

        object.__setattr__(
            self,
            "audit_event_id",
            audit_event_id,
        )
        object.__setattr__(
            self,
            "run_id",
            run_id,
        )
        object.__setattr__(
            self,
            "scenario_id",
            scenario_id,
        )
        object.__setattr__(
            self,
            "stage_id",
            stage_id,
        )
        object.__setattr__(
            self,
            "event_id",
            event_id,
        )
        object.__setattr__(
            self,
            "operation_id",
            operation_id,
        )
        object.__setattr__(
            self,
            "event_type",
            event_type,
        )
        object.__setattr__(
            self,
            "timestamp",
            timestamp,
        )
        object.__setattr__(
            self,
            "schema_version",
            schema_version,
        )
        object.__setattr__(
            self,
            "previous_hash",
            previous_hash,
        )
        object.__setattr__(
            self,
            "payload_hash",
            payload_hash,
        )
        object.__setattr__(
            self,
            "block_hash",
            block_hash,
        )
        object.__setattr__(
            self,
            "payload",
            frozen_payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_event_id": self.audit_event_id,
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "stage_id": self.stage_id,
            "event_id": self.event_id,
            "operation_id": self.operation_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "payload": _sanitize_for_output(
                self.payload
            ),
            "previous_hash": self.previous_hash,
            "payload_hash": self.payload_hash,
            "block_hash": self.block_hash,
            "schema_version": self.schema_version,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(
            self.to_dict()
        )


@dataclass(frozen=True, slots=True)
class AuditBlock:
    run_id: str
    block_index: int
    audit_event: AuditEvent

    def __post_init__(self) -> None:
        run_id = _normalize_required_identifier(
            self.run_id,
            "run_id",
        )

        if type(self.block_index) is not int:
            raise TypeError(
                "block_index must be an integer"
            )

        if self.block_index <= 0:
            raise ValueError(
                "block_index must be strictly positive"
            )

        if not isinstance(
            self.audit_event,
            AuditEvent,
        ):
            raise TypeError(
                "audit_event must be an AuditEvent"
            )

        if run_id != self.audit_event.run_id:
            raise ValueError(
                "AuditBlock run_id does not match "
                "AuditEvent run_id"
            )

        object.__setattr__(
            self,
            "run_id",
            run_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "block_index": self.block_index,
            "audit_event": (
                self.audit_event.to_dict()
            ),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(
            self.to_dict()
        )


class AuditRepositoryProtocol(Protocol):
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
        ...

    def get_block(
        self,
        run_id: str,
        block_index: int,
    ) -> AuditBlock | None:
        ...

    def list_scope(
        self,
        run_id: str,
    ) -> tuple[AuditBlock, ...]:
        ...

    def list_run_ids(
        self,
    ) -> tuple[str, ...]:
        ...

    def count_scope(
        self,
        run_id: str,
    ) -> int:
        ...


class AuditLedger:
    SCHEMA_VERSION = "1.0.0"

    def __init__(
        self,
        audit_repository: AuditRepositoryProtocol,
        clock: Clock,
    ) -> None:
        if audit_repository is None:
            raise TypeError(
                "audit_repository is required"
            )

        if clock is None:
            raise TypeError(
                "clock is required"
            )

        schema_version = str(
            self.SCHEMA_VERSION
        ).strip()

        if not schema_version:
            raise ValueError(
                "SCHEMA_VERSION must not be empty"
            )

        self.repository = audit_repository
        self.clock = clock

    def append(
        self,
        run_id: str,
        scenario_id: str,
        stage_id: str,
        event_id: str,
        operation_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> AuditBlock:
        normalized_run_id = (
            _normalize_required_identifier(
                run_id,
                "run_id",
            )
        )
        normalized_scenario_id = (
            _normalize_required_identifier(
                scenario_id,
                "scenario_id",
            )
        )
        normalized_stage_id = (
            _normalize_required_identifier(
                stage_id,
                "stage_id",
            )
        )
        normalized_event_id = (
            _normalize_required_identifier(
                event_id,
                "event_id",
            )
        )
        normalized_operation_id = (
            _normalize_required_identifier(
                operation_id,
                "operation_id",
            )
        )
        normalized_event_type = (
            _normalize_required_identifier(
                event_type,
                "event_type",
            )
        )

        if not isinstance(payload, Mapping):
            raise TypeError(
                "payload must be a mapping"
            )

        timestamp = parse_timestamp(
            self.clock.now_iso(),
            "clock timestamp",
        ).isoformat()

        try:
            sanitized_payload = (
                sanitize_audit_payload(payload)
            )
            frozen_payload = deep_freeze(
                sanitized_payload
            )
            to_canonical_json(frozen_payload)
        except (TypeError, ValueError) as error:
            raise GovernanceConfigurationError(
                "Audit payload cannot be "
                "canonically serialized"
            ) from error

        block = self.repository.append_atomic(
            run_id=normalized_run_id,
            scenario_id=normalized_scenario_id,
            stage_id=normalized_stage_id,
            event_id=normalized_event_id,
            operation_id=(
                normalized_operation_id
            ),
            event_type=normalized_event_type,
            timestamp=timestamp,
            payload=frozen_payload,
            schema_version=self.SCHEMA_VERSION,
        )

        if not isinstance(block, AuditBlock):
            raise GovernanceConfigurationError(
                "Audit repository returned an "
                "invalid block type"
            )

        if block.run_id != normalized_run_id:
            raise GovernanceConfigurationError(
                "Audit repository returned a block "
                "for a different run"
            )

        return block

    def get_block(
        self,
        run_id: str,
        block_index: int,
    ) -> AuditBlock | None:
        normalized_run_id = (
            _normalize_required_identifier(
                run_id,
                "run_id",
            )
        )

        if type(block_index) is not int:
            raise TypeError(
                "block_index must be an integer"
            )

        if block_index <= 0:
            raise ValueError(
                "block_index must be strictly positive"
            )

        block = self.repository.get_block(
            normalized_run_id,
            block_index,
        )

        if block is None:
            return None

        if not isinstance(block, AuditBlock):
            raise GovernanceConfigurationError(
                "Audit repository returned an "
                "invalid block type"
            )

        if (
            block.run_id != normalized_run_id
            or block.block_index != block_index
        ):
            raise GovernanceConfigurationError(
                "Audit repository returned an "
                "inconsistent block"
            )

        return block

    def list_scope(
        self,
        run_id: str,
    ) -> tuple[AuditBlock, ...]:
        normalized_run_id = (
            _normalize_required_identifier(
                run_id,
                "run_id",
            )
        )

        blocks = self.repository.list_scope(
            normalized_run_id
        )

        if not isinstance(blocks, tuple):
            raise GovernanceConfigurationError(
                "Audit repository returned an "
                "invalid scope collection"
            )

        for block in blocks:
            if not isinstance(block, AuditBlock):
                raise GovernanceConfigurationError(
                    "Audit scope contains an "
                    "invalid block type"
                )

            if block.run_id != normalized_run_id:
                raise GovernanceConfigurationError(
                    "Audit scope contains a block "
                    "from another run"
                )

        return blocks

    def list_run_ids(
        self,
    ) -> tuple[str, ...]:
        run_ids = self.repository.list_run_ids()

        if not isinstance(run_ids, tuple):
            raise GovernanceConfigurationError(
                "Audit repository returned an "
                "invalid run identifier collection"
            )

        normalized_run_ids = tuple(
            _normalize_required_identifier(
                run_id,
                "run_id",
            )
            for run_id in run_ids
        )

        if (
            len(normalized_run_ids)
            != len(set(normalized_run_ids))
        ):
            raise GovernanceConfigurationError(
                "Audit repository returned duplicate "
                "run identifiers"
            )

        return tuple(
            sorted(normalized_run_ids)
        )

    def count_scope(
        self,
        run_id: str,
    ) -> int:
        normalized_run_id = (
            _normalize_required_identifier(
                run_id,
                "run_id",
            )
        )

        count = self.repository.count_scope(
            normalized_run_id
        )

        if type(count) is not int:
            raise GovernanceConfigurationError(
                "Audit repository returned an "
                "invalid scope count"
            )

        if count < 0:
            raise GovernanceConfigurationError(
                "Audit repository returned a "
                "negative scope count"
            )

        return count