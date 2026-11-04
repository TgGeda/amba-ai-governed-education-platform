from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from amba_ai.governance.audit import (
    AuditBlock,
    PROHIBITED_AUDIT_KEYS,
    sanitize_audit_payload,
)
from amba_ai.governance.audit_verifier import AuditVerificationResult
from amba_ai.governance.models import (
    GovernanceConfigurationError,
    deep_freeze,
)


@runtime_checkable
class AuditLedgerProtocol(Protocol):
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
        ...


@runtime_checkable
class AuditVerifierProtocol(Protocol):
    def verify_scope(
        self,
        run_id: str,
        allow_empty: bool = False,
    ) -> AuditVerificationResult:
        ...


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")

    return normalized


class AuditService:
    """Application boundary for run-scoped audit append and verification.

    The service delegates chain construction and atomic persistence to the
    injected audit ledger, and run-scoped integrity verification to the
    injected verifier. Audit claims remain limited to tamper-evident behavior
    within the verified run scope.
    """

    def __init__(
        self,
        audit_ledger: AuditLedgerProtocol,
        audit_verifier: AuditVerifierProtocol,
    ) -> None:
        if audit_ledger is None:
            raise TypeError("audit_ledger is required")
        if audit_verifier is None:
            raise TypeError("audit_verifier is required")
        if not isinstance(audit_ledger, AuditLedgerProtocol):
            raise TypeError(
                "audit_ledger must provide a callable append method"
            )
        if not isinstance(audit_verifier, AuditVerifierProtocol):
            raise TypeError(
                "audit_verifier must provide a callable verify_scope method"
            )

        self._audit_ledger = audit_ledger
        self._audit_verifier = audit_verifier

    @property
    def audit_ledger(self) -> AuditLedgerProtocol:
        return self._audit_ledger

    @property
    def audit_verifier(self) -> AuditVerifierProtocol:
        return self._audit_verifier

    def append(
        self,
        *,
        run_id: str,
        scenario_id: str,
        stage_id: str,
        event_id: str,
        operation_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> AuditBlock:
        normalized = {
            "run_id": _require_text(run_id, "run_id"),
            "scenario_id": _require_text(scenario_id, "scenario_id"),
            "stage_id": _require_text(stage_id, "stage_id"),
            "event_id": _require_text(event_id, "event_id"),
            "operation_id": _require_text(operation_id, "operation_id"),
            "event_type": _require_text(event_type, "event_type"),
        }

        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")

        # Sanitize before delegation so secrets and learner content are never
        # passed across the application-service boundary in clear form.
        sanitized_payload = deep_freeze(
            sanitize_audit_payload(dict(payload))
        )

        block = self._audit_ledger.append(
            run_id=normalized["run_id"],
            scenario_id=normalized["scenario_id"],
            stage_id=normalized["stage_id"],
            event_id=normalized["event_id"],
            operation_id=normalized["operation_id"],
            event_type=normalized["event_type"],
            payload=sanitized_payload,
        )

        self._validate_block(block=block, expected=normalized)
        return block

    def verify(
        self,
        run_id: str,
        *,
        allow_empty: bool = False,
    ) -> AuditVerificationResult:
        normalized_run_id = _require_text(run_id, "run_id")

        if type(allow_empty) is not bool:
            raise TypeError("allow_empty must be a strict Boolean")

        result = self._audit_verifier.verify_scope(
            normalized_run_id,
            allow_empty=allow_empty,
        )

        if not isinstance(result, AuditVerificationResult):
            raise GovernanceConfigurationError(
                "audit_verifier returned an invalid verification result"
            )
        if result.run_id != normalized_run_id:
            raise GovernanceConfigurationError(
                "audit verification run identifier does not match request"
            )
        if type(result.valid) is not bool:
            raise GovernanceConfigurationError(
                "audit verification result contains an invalid validity flag"
            )
        if (
            isinstance(result.verified_block_count, bool)
            or not isinstance(result.verified_block_count, int)
            or result.verified_block_count < 0
        ):
            raise GovernanceConfigurationError(
                "audit verification result contains an invalid block count"
            )
        if result.valid:
            if result.failure_block_index is not None:
                raise GovernanceConfigurationError(
                    "valid audit verification cannot identify a failure block"
                )
            if result.failure_code is not None:
                raise GovernanceConfigurationError(
                    "valid audit verification cannot contain a failure code"
                )
        else:
            if not isinstance(result.failure_code, str) or not result.failure_code.strip():
                raise GovernanceConfigurationError(
                    "invalid audit verification requires a failure code"
                )

        return result

    @staticmethod
    def _validate_block(
        *,
        block: object,
        expected: Mapping[str, str],
    ) -> None:
        if not isinstance(block, AuditBlock):
            raise GovernanceConfigurationError(
                "audit_ledger returned an invalid audit block"
            )
        if block.run_id != expected["run_id"]:
            raise GovernanceConfigurationError(
                "audit block run identifier does not match append request"
            )
        if isinstance(block.block_index, bool) or block.block_index < 1:
            raise GovernanceConfigurationError(
                "audit block index must be strictly positive"
            )

        audit_event = block.audit_event
        relationships = {
            "run_id": audit_event.run_id,
            "scenario_id": audit_event.scenario_id,
            "stage_id": audit_event.stage_id,
            "event_id": audit_event.event_id,
            "operation_id": audit_event.operation_id,
            "event_type": audit_event.event_type,
        }
        for field_name, actual in relationships.items():
            if actual != expected[field_name]:
                raise GovernanceConfigurationError(
                    f"audit event {field_name} does not match append request"
                )

        for prohibited_key in PROHIBITED_AUDIT_KEYS:
            if prohibited_key in audit_event.payload:
                value = audit_event.payload[prohibited_key]
                if value != "[REDACTED]":
                    raise GovernanceConfigurationError(
                        "audit payload contains an unredacted prohibited field"
                    )
