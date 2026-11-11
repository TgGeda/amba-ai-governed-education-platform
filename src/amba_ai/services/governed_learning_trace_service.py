from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from amba_ai.application.service_container import ApplicationServices
from amba_ai.governance.execution_context import GovernanceExecutionContext


CLAIM_BOUNDARIES = (
    "Synthetic demonstration only",
    "No legal effect",
    "Y.3172-oriented project mapping",
    "Not formal ITU conformance or certification",
)
REQUIRED_EVENT_TYPES = (
    "user_action",
    "operation_authorization",
    "source_digest_verified",
    "chunk_decisions_recorded",
    "index_revision_published",
    "retrieval_receipt_created",
    "generation_requested",
    "output_validated",
    "sink_receipt_created",
    "distribution_completed_or_prevented",
    "trace_completed",
    "audit_block_verified",
)
OPTIONAL_EVENT_TYPES = ("review_decision_published",)
SAFE_DETAIL_KEYS = frozenset(
    {
        "decision",
        "disposition",
        "source_sha256",
        "chunk_set_sha256",
        "chunk_ids",
        "approved_chunk_ids",
        "excluded_chunk_ids",
        "retrieved_chunk_ids",
        "revision_id",
        "retrieval_receipt",
        "generation_request_id",
        "output_id",
        "sanitized_sha256",
        "review_id",
        "receipt_id",
        "audit_receipt",
        "sink_name",
        "sink_receipts",
        "distribution_prevention_receipt",
        "status",
        "assertions",
    }
)


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class GovernanceTraceEvent:
    sequence: int
    event_type: str
    timestamp: str
    correlation_id: str
    session_id: str
    principal_id: str
    operation_id: str
    document_id: int | None
    runtime_request_id: str | None
    trace_id: str
    details: Mapping[str, Any]
    details_sha256: str
    previous_event_sha256: str | None
    event_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GovernedLearningEvidenceRecord:
    schema_version: str
    generated_at: str
    execution_context: GovernanceExecutionContext
    events: tuple[GovernanceTraceEvent, ...]
    required_event_types: tuple[str, ...]
    missing_required_events: tuple[str, ...]
    scenario_ids: tuple[str, ...]
    test_matrix: Mapping[str, str]
    source_inventory_sha256: str
    evidence_chain_sha256: str
    audit_verified: bool
    claim_boundaries: tuple[str, ...] = CLAIM_BOUNDARIES

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["execution_context"] = self.execution_context.to_dict()
        payload["events"] = [event.to_dict() for event in self.events]
        return payload


class GovernedLearningTraceService:
    """Build a privacy-safe, digest-linked learning evidence record."""

    def __init__(self, services: ApplicationServices) -> None:
        if not isinstance(services, ApplicationServices):
            raise TypeError("services must be ApplicationServices")
        services.require_consistent_graph()
        self.services = services

    @staticmethod
    def _sanitize_details(details: Mapping[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in details.items():
            normalized_key = str(key)
            if normalized_key not in SAFE_DETAIL_KEYS:
                continue
            if normalized_key.endswith("_sha256"):
                digest = str(value)
                if digest and (len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest)):
                    raise ValueError(f"{normalized_key} must be a SHA-256 hex digest")
            safe[normalized_key] = value
        serialized = json.dumps(safe, ensure_ascii=False, default=str)
        forbidden = (
            "learner@example.com",
            "Student ID: ABC-123",
            r"F:\Private\student_record.txt",
        )
        if any(value in serialized for value in forbidden):
            raise ValueError("Evidence details contain raw sensitive fixture material")
        return safe

    def event(
        self,
        *,
        sequence: int,
        event_type: str,
        context: GovernanceExecutionContext,
        details: Mapping[str, Any],
        previous_event_sha256: str | None,
        timestamp: str | None = None,
    ) -> GovernanceTraceEvent:
        if event_type not in set(REQUIRED_EVENT_TYPES).union(OPTIONAL_EVENT_TYPES):
            raise ValueError(f"Unsupported evidence event: {event_type}")
        safe_details = self._sanitize_details(details)
        details_sha256 = _digest(safe_details)
        event_payload = {
            "sequence": int(sequence),
            "event_type": event_type,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            **context.to_dict(),
            "details_sha256": details_sha256,
            "previous_event_sha256": previous_event_sha256,
        }
        event_sha256 = _digest(event_payload)
        return GovernanceTraceEvent(
            sequence=int(sequence),
            event_type=event_type,
            timestamp=str(event_payload["timestamp"]),
            correlation_id=context.correlation_id,
            session_id=context.session_id,
            principal_id=context.principal_id,
            operation_id=context.operation_id,
            document_id=context.document_id,
            runtime_request_id=context.runtime_request_id,
            trace_id=context.trace_id,
            details=safe_details,
            details_sha256=details_sha256,
            previous_event_sha256=previous_event_sha256,
            event_sha256=event_sha256,
        )

    def build_record(
        self,
        *,
        context: GovernanceExecutionContext,
        event_details: Iterable[tuple[str, Mapping[str, Any]]],
        scenario_ids: Iterable[str],
        test_matrix: Mapping[str, str],
        source_inventory_sha256: str,
        audit_verified: bool,
    ) -> GovernedLearningEvidenceRecord:
        events: list[GovernanceTraceEvent] = []
        previous: str | None = None
        for sequence, (event_type, details) in enumerate(event_details, start=1):
            event = self.event(
                sequence=sequence,
                event_type=event_type,
                context=context,
                details=details,
                previous_event_sha256=previous,
            )
            events.append(event)
            previous = event.event_sha256
        present = {event.event_type for event in events}
        missing = tuple(
            event_type
            for event_type in REQUIRED_EVENT_TYPES
            if event_type not in present
        )
        chain_payload = [event.to_dict() for event in events]
        return GovernedLearningEvidenceRecord(
            schema_version="1.0",
            generated_at=datetime.now(timezone.utc).isoformat(),
            execution_context=context,
            events=tuple(events),
            required_event_types=REQUIRED_EVENT_TYPES,
            missing_required_events=missing,
            scenario_ids=tuple(str(value) for value in scenario_ids),
            test_matrix=dict(test_matrix),
            source_inventory_sha256=str(source_inventory_sha256),
            evidence_chain_sha256=_digest(chain_payload),
            audit_verified=bool(audit_verified),
        )

    @staticmethod
    def verify_record(record: GovernedLearningEvidenceRecord) -> None:
        if record.missing_required_events:
            raise ValueError(
                "Evidence chain is incomplete: "
                + ", ".join(record.missing_required_events)
            )
        previous: str | None = None
        for expected_sequence, event in enumerate(record.events, start=1):
            if event.sequence != expected_sequence:
                raise ValueError("Evidence event sequence is not contiguous")
            if event.previous_event_sha256 != previous:
                raise ValueError("Evidence event chain linkage is invalid")
            if _digest(dict(event.details)) != event.details_sha256:
                raise ValueError("Evidence detail digest mismatch")
            event_payload = {
                "sequence": event.sequence,
                "event_type": event.event_type,
                "timestamp": event.timestamp,
                "correlation_id": event.correlation_id,
                "session_id": event.session_id,
                "principal_id": event.principal_id,
                "operation_id": event.operation_id,
                "document_id": event.document_id,
                "runtime_request_id": event.runtime_request_id,
                "trace_id": event.trace_id,
                "details_sha256": event.details_sha256,
                "previous_event_sha256": event.previous_event_sha256,
            }
            if _digest(event_payload) != event.event_sha256:
                raise ValueError("Evidence event digest mismatch")
            previous = event.event_sha256
        if _digest([event.to_dict() for event in record.events]) != record.evidence_chain_sha256:
            raise ValueError("Evidence chain digest mismatch")
        if not record.audit_verified:
            raise ValueError("Evidence chain has no verified audit block")

    def write_artifacts(
        self,
        *,
        record: GovernedLearningEvidenceRecord,
        json_path: Path,
        markdown_path: Path,
    ) -> str:
        self.verify_record(record)
        payload = record.to_dict()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        json_text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        json_path.write_text(json_text, encoding="utf-8", newline="\n")
        lines = [
            "# Governed Learning Evidence Chain",
            "",
            *[f"- {boundary}" for boundary in record.claim_boundaries],
            "",
            "## Correlation context",
            "",
            f"- Correlation ID: `{record.execution_context.correlation_id}`",
            f"- Session ID: `{record.execution_context.session_id}`",
            f"- Principal ID: `{record.execution_context.principal_id}`",
            f"- Operation ID: `{record.execution_context.operation_id}`",
            f"- Document ID: `{record.execution_context.document_id}`",
            f"- Runtime request ID: `{record.execution_context.runtime_request_id}`",
            f"- Trace ID: `{record.execution_context.trace_id}`",
            "",
            "## Verified chain",
            "",
        ]
        for event in record.events:
            lines.append(
                f"{event.sequence}. `{event.event_type}`: "
                f"details `{event.details_sha256}`, event `{event.event_sha256}`"
            )
        lines.extend(
            [
                "",
                "## Evidence status",
                "",
                f"- Audit verified: `{record.audit_verified}`",
                f"- Missing required events: `{list(record.missing_required_events)}`",
                f"- Evidence-chain SHA-256: `{record.evidence_chain_sha256}`",
                f"- Source-inventory SHA-256: `{record.source_inventory_sha256}`",
                "",
                "## Test matrix",
                "",
            ]
        )
        lines.extend(
            f"- `{test_name}`: {purpose}"
            for test_name, purpose in record.test_matrix.items()
        )
        markdown_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        return hashlib.sha256(json_text.encode("utf-8")).hexdigest()
