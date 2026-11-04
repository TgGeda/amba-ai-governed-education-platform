"""Typed models for Amba-Gov's interpreted ITU-T Y.3172 execution trace.

This module models one canonical application-level execution path:

    SRC -> C -> PP -> M -> P -> D -> SINK

It is not a general telecommunications topology model and does not establish
formal ITU-T Y.3172 conformance or ITU certification.

The models deliberately preserve these distinctions:

- policy recommendation is not execution;
- execution receipt is not distribution acknowledgment;
- review routing is not delivery;
- prevention is not failed delivery;
- a destination that was not reached cannot acknowledge delivery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from amba_ai.governance.models import deep_freeze, to_canonical_json


AMBA_GOV_Y3172_INTERPRETATION_ID = (
    "AMBA-GOV-Y3172-INTERPRETATION-V1"
)


class Y3172TraceError(ValueError):
    """Base error for invalid interpreted Y.3172 trace data."""


class Y3172ConfigurationError(Y3172TraceError):
    """Raised when the interpreted Y.3172 configuration is invalid."""


class Y3172Node(str, Enum):
    """Canonical functional nodes in the interpreted Y.3172 pipeline."""

    SRC = "SRC"
    C = "C"
    PP = "PP"
    M = "M"
    P = "P"
    D = "D"
    SINK = "SINK"


Y3172_NODE_ORDER: tuple[Y3172Node, ...] = (
    Y3172Node.SRC,
    Y3172Node.C,
    Y3172Node.PP,
    Y3172Node.M,
    Y3172Node.P,
    Y3172Node.D,
    Y3172Node.SINK,
)


class PipelineNodeStatus(str, Enum):
    """Runtime status of one interpreted pipeline node."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    HELD = "held"
    PREVENTED = "prevented"
    NOT_REACHED = "not_reached"
    FAILED_CLOSED = "failed_closed"


_TERMINAL_STATUSES = frozenset(
    {
        PipelineNodeStatus.COMPLETED,
        PipelineNodeStatus.HELD,
        PipelineNodeStatus.PREVENTED,
        PipelineNodeStatus.FAILED_CLOSED,
    }
)

_RATIONALE_REQUIRED_STATUSES = frozenset(
    {
        PipelineNodeStatus.HELD,
        PipelineNodeStatus.PREVENTED,
        PipelineNodeStatus.FAILED_CLOSED,
    }
)


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Y3172ConfigurationError(
            f"{field_name} must be a non-empty string"
        )
    return value.strip()


def _optional_text(
    value: object | None,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _require_text_tuple(
    value: object,
    field_name: str,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")

    normalized = tuple(
        _require_text(item, f"{field_name} item")
        for item in value
    )

    if len(normalized) != len(set(normalized)):
        raise Y3172ConfigurationError(
            f"{field_name} must not contain duplicates"
        )

    return normalized


def _normalize_timestamp(
    value: object | None,
    field_name: str,
) -> str | None:
    """Validate and normalize a timezone-aware ISO-8601 timestamp to UTC."""

    if value is None:
        return None

    text = _require_text(value, field_name)

    normalized_input = (
        f"{text[:-1]}+00:00"
        if text.endswith(("Z", "z"))
        else text
    )

    try:
        parsed = datetime.fromisoformat(normalized_input)
    except ValueError as exc:
        raise Y3172ConfigurationError(
            f"{field_name} must be a valid ISO-8601 timestamp"
        ) from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Y3172ConfigurationError(
            f"{field_name} must include a timezone offset"
        )

    return parsed.astimezone(timezone.utc).isoformat()


def _parse_normalized_timestamp(
    value: str,
) -> datetime:
    """Parse an already normalized timestamp for chronological comparison."""

    return datetime.fromisoformat(value)


@dataclass(frozen=True, slots=True)
class PipelineNodeTrace:
    """Trace record for one canonical interpreted pipeline node.

    This model records execution evidence. It does not execute the node and
    does not make governance decisions.
    """

    node: Y3172Node
    status: PipelineNodeStatus
    started_at: str | None
    completed_at: str | None
    artifact_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    rationale_codes: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.node, Y3172Node):
            raise TypeError("node must be a Y3172Node")

        if not isinstance(self.status, PipelineNodeStatus):
            raise TypeError(
                "status must be a PipelineNodeStatus"
            )

        started_at = _normalize_timestamp(
            self.started_at,
            "started_at",
        )
        completed_at = _normalize_timestamp(
            self.completed_at,
            "completed_at",
        )

        artifact_ids = _require_text_tuple(
            self.artifact_ids,
            "artifact_ids",
        )
        evidence_ids = _require_text_tuple(
            self.evidence_ids,
            "evidence_ids",
        )
        rationale_codes = _require_text_tuple(
            self.rationale_codes,
            "rationale_codes",
        )

        if not isinstance(self.details, Mapping):
            raise TypeError("details must be a mapping")

        frozen_details = deep_freeze(self.details)

        if self.status in {
            PipelineNodeStatus.PENDING,
            PipelineNodeStatus.NOT_REACHED,
        }:
            if started_at is not None or completed_at is not None:
                raise Y3172TraceError(
                    f"{self.status.value} prohibits timestamps"
                )

        elif self.status is PipelineNodeStatus.RUNNING:
            if started_at is None:
                raise Y3172TraceError(
                    "RUNNING requires started_at"
                )
            if completed_at is not None:
                raise Y3172TraceError(
                    "RUNNING prohibits completed_at"
                )

        elif self.status in _TERMINAL_STATUSES:
            if started_at is None or completed_at is None:
                raise Y3172TraceError(
                    f"{self.status.value} requires both "
                    "started_at and completed_at"
                )

        if started_at is not None and completed_at is not None:
            if (
                _parse_normalized_timestamp(completed_at)
                < _parse_normalized_timestamp(started_at)
            ):
                raise Y3172TraceError(
                    "completed_at cannot precede started_at"
                )

        if self.status is PipelineNodeStatus.COMPLETED:
            if not (
                artifact_ids
                or evidence_ids
                or rationale_codes
            ):
                raise Y3172TraceError(
                    "COMPLETED requires at least one artifact, "
                    "evidence identifier, or rationale code"
                )

        if self.status in _RATIONALE_REQUIRED_STATUSES:
            if not rationale_codes:
                raise Y3172TraceError(
                    f"{self.status.value} requires at least one "
                    "rationale code"
                )

        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "completed_at", completed_at)
        object.__setattr__(self, "artifact_ids", artifact_ids)
        object.__setattr__(self, "evidence_ids", evidence_ids)
        object.__setattr__(
            self,
            "rationale_codes",
            rationale_codes,
        )
        object.__setattr__(self, "details", frozen_details)

        # Validate canonical serializability during construction.
        to_canonical_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node.value,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "artifact_ids": list(self.artifact_ids),
            "evidence_ids": list(self.evidence_ids),
            "rationale_codes": list(self.rationale_codes),
            "details": self.details,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class Y3172PipelineTrace:
    """Canonical interpreted Y.3172 trace for one Amba-Gov run.

    Receipt semantics:

    - ``execution_receipt_id`` records an execution, prevention, or mitigation
      attempt. It is not proof that a destination received content.
    - ``distribution_acknowledgment_id`` exists only when a destination was
      reached and acknowledged delivery.
    - ``review_queue_receipt_id`` exists only for held-for-review routing.
    """

    trace_id: str
    run_id: str
    created_at: str
    nodes: tuple[PipelineNodeTrace, ...]

    interpretation_id: str = (
        AMBA_GOV_Y3172_INTERPRETATION_ID
    )
    project_extensions: tuple[str, ...] = ()

    execution_receipt_id: str | None = None
    distribution_acknowledgment_id: str | None = None
    review_queue_receipt_id: str | None = None

    formal_conformance_claimed: bool = False
    certification_claimed: bool = False

    def __post_init__(self) -> None:
        trace_id = _require_text(
            self.trace_id,
            "trace_id",
        )
        run_id = _require_text(
            self.run_id,
            "run_id",
        )
        created_at = _normalize_timestamp(
            self.created_at,
            "created_at",
        )

        interpretation_id = _require_text(
            self.interpretation_id,
            "interpretation_id",
        )

        if (
            interpretation_id
            != AMBA_GOV_Y3172_INTERPRETATION_ID
        ):
            raise Y3172ConfigurationError(
                "interpretation_id must be "
                f"{AMBA_GOV_Y3172_INTERPRETATION_ID}"
            )

        if type(self.formal_conformance_claimed) is not bool:
            raise TypeError(
                "formal_conformance_claimed must be a strict Boolean"
            )

        if type(self.certification_claimed) is not bool:
            raise TypeError(
                "certification_claimed must be a strict Boolean"
            )

        if self.formal_conformance_claimed:
            raise Y3172ConfigurationError(
                "formal ITU-T Y.3172 conformance must not be claimed"
            )

        if self.certification_claimed:
            raise Y3172ConfigurationError(
                "ITU certification must not be claimed"
            )

        if not isinstance(self.nodes, tuple):
            raise TypeError("nodes must be a tuple")

        actual_order = tuple(
            node_trace.node
            for node_trace in self.nodes
        )

        if actual_order != Y3172_NODE_ORDER:
            raise Y3172TraceError(
                "nodes must contain exactly "
                "SRC, C, PP, M, P, D, SINK in canonical order"
            )

        project_extensions = _require_text_tuple(
            self.project_extensions,
            "project_extensions",
        )

        execution_receipt_id = _optional_text(
            self.execution_receipt_id,
            "execution_receipt_id",
        )
        distribution_acknowledgment_id = _optional_text(
            self.distribution_acknowledgment_id,
            "distribution_acknowledgment_id",
        )
        review_queue_receipt_id = _optional_text(
            self.review_queue_receipt_id,
            "review_queue_receipt_id",
        )

        distributor = self.nodes[-2]
        sink = self.nodes[-1]

        self._validate_distribution_outcome(
            distributor=distributor,
            sink=sink,
            execution_receipt_id=execution_receipt_id,
            distribution_acknowledgment_id=(
                distribution_acknowledgment_id
            ),
            review_queue_receipt_id=(
                review_queue_receipt_id
            ),
        )

        object.__setattr__(self, "trace_id", trace_id)
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(
            self,
            "interpretation_id",
            interpretation_id,
        )
        object.__setattr__(
            self,
            "project_extensions",
            project_extensions,
        )
        object.__setattr__(
            self,
            "execution_receipt_id",
            execution_receipt_id,
        )
        object.__setattr__(
            self,
            "distribution_acknowledgment_id",
            distribution_acknowledgment_id,
        )
        object.__setattr__(
            self,
            "review_queue_receipt_id",
            review_queue_receipt_id,
        )

        # Validate complete trace serialization during construction.
        to_canonical_json(self.to_dict())

    @staticmethod
    def _validate_distribution_outcome(
        *,
        distributor: PipelineNodeTrace,
        sink: PipelineNodeTrace,
        execution_receipt_id: str | None,
        distribution_acknowledgment_id: str | None,
        review_queue_receipt_id: str | None,
    ) -> None:
        d_status = distributor.status
        sink_status = sink.status

        if d_status is PipelineNodeStatus.COMPLETED:
            if sink_status is not PipelineNodeStatus.COMPLETED:
                raise Y3172TraceError(
                    "D=COMPLETED requires SINK=COMPLETED"
                )
            if execution_receipt_id is None:
                raise Y3172TraceError(
                    "delivered outcome requires execution_receipt_id"
                )
            if distribution_acknowledgment_id is None:
                raise Y3172TraceError(
                    "delivered outcome requires "
                    "distribution_acknowledgment_id"
                )
            if review_queue_receipt_id is not None:
                raise Y3172TraceError(
                    "delivered outcome prohibits "
                    "review_queue_receipt_id"
                )
            return

        if d_status is PipelineNodeStatus.HELD:
            if sink_status is not PipelineNodeStatus.NOT_REACHED:
                raise Y3172TraceError(
                    "D=HELD requires SINK=NOT_REACHED"
                )
            if review_queue_receipt_id is None:
                raise Y3172TraceError(
                    "held outcome requires review_queue_receipt_id"
                )
            if execution_receipt_id is not None:
                raise Y3172TraceError(
                    "held outcome prohibits execution_receipt_id"
                )
            if distribution_acknowledgment_id is not None:
                raise Y3172TraceError(
                    "held outcome prohibits "
                    "distribution_acknowledgment_id"
                )
            return

        if d_status is PipelineNodeStatus.PREVENTED:
            if sink_status is not PipelineNodeStatus.NOT_REACHED:
                raise Y3172TraceError(
                    "D=PREVENTED requires SINK=NOT_REACHED"
                )
            if execution_receipt_id is None:
                raise Y3172TraceError(
                    "prevented outcome requires execution_receipt_id"
                )
            if distribution_acknowledgment_id is not None:
                raise Y3172TraceError(
                    "prevented outcome prohibits "
                    "distribution_acknowledgment_id"
                )
            if review_queue_receipt_id is not None:
                raise Y3172TraceError(
                    "prevented outcome prohibits "
                    "review_queue_receipt_id"
                )
            return

        if d_status is PipelineNodeStatus.NOT_REACHED:
            if sink_status is not PipelineNodeStatus.NOT_REACHED:
                raise Y3172TraceError(
                    "D=NOT_REACHED requires SINK=NOT_REACHED"
                )
            if any(
                value is not None
                for value in (
                    execution_receipt_id,
                    distribution_acknowledgment_id,
                    review_queue_receipt_id,
                )
            ):
                raise Y3172TraceError(
                    "not-attempted outcome prohibits receipts "
                    "and acknowledgments"
                )
            return

        if d_status is PipelineNodeStatus.FAILED_CLOSED:
            if sink_status is not PipelineNodeStatus.NOT_REACHED:
                raise Y3172TraceError(
                    "D=FAILED_CLOSED requires SINK=NOT_REACHED"
                )
            if distribution_acknowledgment_id is not None:
                raise Y3172TraceError(
                    "failed-closed outcome prohibits "
                    "distribution acknowledgment"
                )
            if review_queue_receipt_id is not None:
                raise Y3172TraceError(
                    "failed-closed outcome prohibits "
                    "review queue receipt"
                )
            return

        raise Y3172TraceError(
            "D must be COMPLETED, HELD, PREVENTED, "
            "NOT_REACHED, or FAILED_CLOSED in a finalized trace"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "interpretation_id": self.interpretation_id,
            "formal_conformance_claimed": False,
            "certification_claimed": False,
            "project_extensions": list(
                self.project_extensions
            ),
            "execution_receipt_id": (
                self.execution_receipt_id
            ),
            "distribution_acknowledgment_id": (
                self.distribution_acknowledgment_id
            ),
            "review_queue_receipt_id": (
                self.review_queue_receipt_id
            ),
            "nodes": [
                node_trace.to_dict()
                for node_trace in self.nodes
            ],
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())