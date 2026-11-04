from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Any, Mapping, Protocol

from amba_ai.governance.approvals import validate_sha256
from amba_ai.governance.models import to_canonical_json
from amba_ai.governance.principals import parse_timestamp


class AuditEventProtocol(Protocol):
    audit_event_id: str
    run_id: str
    timestamp: str
    schema_version: str
    payload: Mapping[str, Any]
    previous_hash: str
    payload_hash: str
    block_hash: str


class AuditBlockProtocol(Protocol):
    run_id: str
    block_index: int
    audit_event: AuditEventProtocol


class AuditLedgerProtocol(Protocol):
    SCHEMA_VERSION: str

    def list_scope(
        self,
        run_id: str,
    ) -> tuple[AuditBlockProtocol, ...]:
        ...

    def list_run_ids(self) -> tuple[str, ...]:
        ...


@dataclass(frozen=True, slots=True)
class AuditVerificationResult:
    valid: bool
    run_id: str
    verified_block_count: int
    failure_block_index: int | None
    failure_code: str | None
    message: str

    def __post_init__(self) -> None:
        run_id = str(self.run_id).strip()
        message = str(self.message).strip()
        failure_code = (
            str(self.failure_code).strip()
            if self.failure_code is not None
            else None
        )

        if type(self.valid) is not bool:
            raise TypeError("valid must be a strict Boolean")
        if self.verified_block_count < 0:
            raise ValueError("verified_block_count cannot be negative")
        if self.failure_block_index is not None and self.failure_block_index < 0:
            raise ValueError("failure_block_index cannot be negative")
        if not message:
            raise ValueError("message must not be empty")
        if self.valid:
            if self.failure_block_index is not None or failure_code is not None:
                raise ValueError("A valid result cannot contain failure details")
        elif not failure_code:
            raise ValueError("An invalid result requires a failure_code")

        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "failure_code", failure_code)
        object.__setattr__(self, "message", message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "run_id": self.run_id,
            "verified_block_count": self.verified_block_count,
            "failure_block_index": self.failure_block_index,
            "failure_code": self.failure_code,
            "message": self.message,
        }


class AuditVerifier:
    SUCCESS_MESSAGE = "tamper-evident within verified scope"

    def __init__(
        self,
        audit_ledger: AuditLedgerProtocol,
    ) -> None:
        if audit_ledger is None:
            raise TypeError("audit_ledger is required")

        schema_version = str(audit_ledger.SCHEMA_VERSION).strip()
        if not schema_version:
            raise ValueError("Audit ledger schema version must not be empty")

        self.ledger = audit_ledger
        self._schema_version = schema_version

    @staticmethod
    def _failure(
        run_id: str,
        verified_count: int,
        block_index: int | None,
        code: str,
        message: str,
    ) -> AuditVerificationResult:
        return AuditVerificationResult(
            valid=False,
            run_id=run_id,
            verified_block_count=verified_count,
            failure_block_index=block_index,
            failure_code=code,
            message=message,
        )

    def verify_scope(
        self,
        run_id: str,
        allow_empty: bool = False,
    ) -> AuditVerificationResult:
        normalized_run_id = str(run_id).strip()

        if type(allow_empty) is not bool:
            raise TypeError("allow_empty must be a strict Boolean")

        if not normalized_run_id:
            return self._failure(
                run_id="",
                verified_count=0,
                block_index=None,
                code="RUN_ID_EMPTY",
                message="Audit run identifier is empty",
            )

        blocks = self.ledger.list_scope(normalized_run_id)

        if not isinstance(blocks, tuple):
            return self._failure(
                run_id=normalized_run_id,
                verified_count=0,
                block_index=None,
                code="SCOPE_TYPE_INVALID",
                message="Audit ledger returned an invalid scope collection",
            )

        if not blocks:
            if allow_empty:
                return AuditVerificationResult(
                    valid=True,
                    run_id=normalized_run_id,
                    verified_block_count=0,
                    failure_block_index=None,
                    failure_code=None,
                    message=self.SUCCESS_MESSAGE,
                )

            return self._failure(
                run_id=normalized_run_id,
                verified_count=0,
                block_index=0,
                code="EMPTY_SCOPE_REJECTED",
                message="Expected audit run has no recorded blocks",
            )

        expected_previous_hash = hashlib.sha256(
            f"GENESIS:{normalized_run_id}".encode("utf-8")
        ).hexdigest()
        verified_count = 0
        observed_event_ids: set[str] = set()

        for expected_index, block in enumerate(blocks, start=1):
            try:
                block_run_id = str(block.run_id).strip()
                block_index = block.block_index
                event = block.audit_event
            except (AttributeError, TypeError, ValueError):
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=expected_index,
                    code="BLOCK_STRUCTURE_INVALID",
                    message="Audit block structure is invalid",
                )

            if type(block_index) is not int or block_index <= 0:
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=expected_index,
                    code="BLOCK_INDEX_INVALID",
                    message="Audit block index is invalid",
                )

            if block_run_id != normalized_run_id:
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=block_index,
                    code="BLOCK_RUN_ID_MISMATCH",
                    message="Audit block run identifier does not match the verified scope",
                )

            if block_index != expected_index:
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=block_index,
                    code="INDEX_SEQUENCE_BROKEN",
                    message="Audit block index sequence is broken",
                )

            try:
                event_run_id = str(event.run_id).strip()
                event_id = str(event.audit_event_id).strip()
                schema_version = str(event.schema_version).strip()
                timestamp = str(event.timestamp).strip()
                previous_hash = validate_sha256(
                    event.previous_hash,
                    "previous_hash",
                )
                payload_hash = validate_sha256(
                    event.payload_hash,
                    "payload_hash",
                )
                block_hash = validate_sha256(
                    event.block_hash,
                    "block_hash",
                )
            except (AttributeError, TypeError, ValueError):
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=expected_index,
                    code="EVENT_STRUCTURE_INVALID",
                    message="Audit event structure or digest format is invalid",
                )

            if event_run_id != normalized_run_id:
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=expected_index,
                    code="EVENT_RUN_ID_MISMATCH",
                    message="Audit event run identifier does not match the verified scope",
                )

            if schema_version != self._schema_version:
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=expected_index,
                    code="SCHEMA_VERSION_MISMATCH",
                    message="Audit event schema version is not supported",
                )

            try:
                parse_timestamp(timestamp, "audit timestamp")
            except (TypeError, ValueError):
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=expected_index,
                    code="TIMESTAMP_INVALID",
                    message="Audit event timestamp is invalid",
                )

            if not event_id:
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=expected_index,
                    code="AUDIT_EVENT_ID_EMPTY",
                    message="Audit event identifier is empty",
                )

            if event_id in observed_event_ids:
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=expected_index,
                    code="AUDIT_EVENT_ID_DUPLICATE",
                    message="Audit event identifier is duplicated within the run",
                )
            observed_event_ids.add(event_id)

            if not hmac.compare_digest(previous_hash, expected_previous_hash):
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=expected_index,
                    code="PREVIOUS_HASH_MISMATCH",
                    message="Audit hash continuity is broken",
                )

            try:
                canonical_payload = to_canonical_json(event.payload)
            except (AttributeError, TypeError, ValueError):
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=expected_index,
                    code="PAYLOAD_CANONICALIZATION_FAILED",
                    message="Audit payload cannot be canonically serialized",
                )

            computed_payload_hash = hashlib.sha256(
                canonical_payload.encode("utf-8")
            ).hexdigest()

            if not hmac.compare_digest(computed_payload_hash, payload_hash):
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=expected_index,
                    code="PAYLOAD_HASH_MISMATCH",
                    message="Audit payload hash verification failed",
                )

            block_material = {
                "run_id": normalized_run_id,
                "block_index": expected_index,
                "timestamp": timestamp,
                "schema_version": schema_version,
                "previous_hash": previous_hash,
                "payload_hash": payload_hash,
            }

            computed_block_hash = hashlib.sha256(
                to_canonical_json(block_material).encode("utf-8")
            ).hexdigest()

            if not hmac.compare_digest(computed_block_hash, block_hash):
                return self._failure(
                    run_id=normalized_run_id,
                    verified_count=verified_count,
                    block_index=expected_index,
                    code="BLOCK_HASH_MISMATCH",
                    message="Audit block hash verification failed",
                )

            expected_previous_hash = block_hash
            verified_count += 1

        return AuditVerificationResult(
            valid=True,
            run_id=normalized_run_id,
            verified_block_count=verified_count,
            failure_block_index=None,
            failure_code=None,
            message=self.SUCCESS_MESSAGE,
        )

    def verify_all_scopes(self) -> tuple[AuditVerificationResult, ...]:
        run_ids = self.ledger.list_run_ids()

        if not isinstance(run_ids, tuple):
            raise TypeError("Audit ledger returned an invalid run identifier collection")

        normalized_run_ids = tuple(str(run_id).strip() for run_id in run_ids)

        if any(not run_id for run_id in normalized_run_ids):
            raise ValueError("Audit ledger returned an empty run identifier")

        if len(normalized_run_ids) != len(set(normalized_run_ids)):
            raise ValueError("Audit ledger returned duplicate run identifiers")

        return tuple(
            self.verify_scope(run_id)
            for run_id in sorted(normalized_run_ids)
        )
