from __future__ import annotations

from math import nan

import pytest

from amba_ai.standards.y3172_models import (
    AMBA_GOV_Y3172_INTERPRETATION_ID,
    PipelineNodeStatus,
    PipelineNodeTrace,
    Y3172ConfigurationError,
    Y3172Node,
    Y3172PipelineTrace,
    Y3172TraceError,
    Y3172_NODE_ORDER,
)


START = "2026-11-04T06:00:00+00:00"
END = "2026-11-04T06:00:01+00:00"


def _node(
    node: Y3172Node,
    status: PipelineNodeStatus,
    *,
    started_at: str | None = None,
    completed_at: str | None = None,
    artifact_ids: tuple[str, ...] = (),
    evidence_ids: tuple[str, ...] = (),
    rationale_codes: tuple[str, ...] = (),
    details: dict | None = None,
) -> PipelineNodeTrace:
    if status in {
        PipelineNodeStatus.COMPLETED,
        PipelineNodeStatus.HELD,
        PipelineNodeStatus.PREVENTED,
        PipelineNodeStatus.FAILED_CLOSED,
    }:
        started_at = started_at or START
        completed_at = completed_at or END

    if status is PipelineNodeStatus.RUNNING:
        started_at = started_at or START
        completed_at = None

    if status in {
        PipelineNodeStatus.PENDING,
        PipelineNodeStatus.NOT_REACHED,
    }:
        started_at = None
        completed_at = None

    if status is PipelineNodeStatus.COMPLETED:
        artifact_ids = artifact_ids or (
            f"ARTIFACT-{node.value}",
        )

    if status in {
        PipelineNodeStatus.HELD,
        PipelineNodeStatus.PREVENTED,
        PipelineNodeStatus.FAILED_CLOSED,
    }:
        rationale_codes = rationale_codes or (
            f"{status.value.upper()}-{node.value}",
        )

    return PipelineNodeTrace(
        node=node,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        artifact_ids=artifact_ids,
        evidence_ids=evidence_ids,
        rationale_codes=rationale_codes,
        details=details or {},
    )


def _nodes_for_outcome(
    distributor_status: PipelineNodeStatus,
    sink_status: PipelineNodeStatus,
) -> tuple[PipelineNodeTrace, ...]:
    traces: list[PipelineNodeTrace] = []

    for node in Y3172_NODE_ORDER:
        if node is Y3172Node.D:
            traces.append(
                _node(node, distributor_status)
            )
        elif node is Y3172Node.SINK:
            traces.append(
                _node(node, sink_status)
            )
        else:
            traces.append(
                _node(
                    node,
                    PipelineNodeStatus.COMPLETED,
                )
            )

    return tuple(traces)


def _delivered_trace(
    **overrides,
) -> Y3172PipelineTrace:
    values = {
        "trace_id": "TRACE-001",
        "run_id": "RUN-001",
        "created_at": START,
        "nodes": _nodes_for_outcome(
            PipelineNodeStatus.COMPLETED,
            PipelineNodeStatus.COMPLETED,
        ),
        "execution_receipt_id": "EXEC-001",
        "distribution_acknowledgment_id": "ACK-001",
    }
    values.update(overrides)
    return Y3172PipelineTrace(**values)


def test_node_order_is_canonical() -> None:
    assert Y3172_NODE_ORDER == (
        Y3172Node.SRC,
        Y3172Node.C,
        Y3172Node.PP,
        Y3172Node.M,
        Y3172Node.P,
        Y3172Node.D,
        Y3172Node.SINK,
    )


def test_completed_node_requires_trace_basis() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="requires at least one artifact",
    ):
        PipelineNodeTrace(
            node=Y3172Node.M,
            status=PipelineNodeStatus.COMPLETED,
            started_at=START,
            completed_at=END,
            artifact_ids=(),
            evidence_ids=(),
            rationale_codes=(),
        )

def test_pending_node_prohibits_timestamps() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="pending prohibits timestamps",
    ):
        PipelineNodeTrace(
            node=Y3172Node.M,
            status=PipelineNodeStatus.PENDING,
            started_at=START,
            completed_at=None,
        )


def test_running_node_requires_start_only() -> None:
    trace = _node(
        Y3172Node.M,
        PipelineNodeStatus.RUNNING,
    )

    assert trace.started_at == START
    assert trace.completed_at is None


def test_running_node_prohibits_completed_timestamp() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="RUNNING prohibits completed_at",
    ):
        PipelineNodeTrace(
            node=Y3172Node.M,
            status=PipelineNodeStatus.RUNNING,
            started_at=START,
            completed_at=END,
        )


def test_not_reached_prohibits_timestamps() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="not_reached prohibits timestamps",
    ):
        PipelineNodeTrace(
            node=Y3172Node.SINK,
            status=PipelineNodeStatus.NOT_REACHED,
            started_at=START,
            completed_at=END,
        )


def test_terminal_node_requires_both_timestamps() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="requires both started_at and completed_at",
    ):
        PipelineNodeTrace(
            node=Y3172Node.D,
            status=PipelineNodeStatus.PREVENTED,
            started_at=START,
            completed_at=None,
            rationale_codes=("DISTRIBUTION-PREVENTED",),
        )


def test_timestamp_must_be_timezone_aware() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="must include a timezone",
    ):
        PipelineNodeTrace(
            node=Y3172Node.M,
            status=PipelineNodeStatus.COMPLETED,
            started_at="2026-11-04T06:00:00",
            completed_at="2026-11-04T06:00:01",
            artifact_ids=("MODEL-OUTPUT-001",),
        )


def test_timestamps_are_normalized_to_utc() -> None:
    trace = PipelineNodeTrace(
        node=Y3172Node.M,
        status=PipelineNodeStatus.COMPLETED,
        started_at="2026-11-04T09:00:00+03:00",
        completed_at="2026-11-04T09:00:01+03:00",
        artifact_ids=("MODEL-OUTPUT-001",),
    )

    assert trace.started_at == "2026-11-04T06:00:00+00:00"
    assert trace.completed_at == "2026-11-04T06:00:01+00:00"


def test_completed_at_cannot_precede_started_at() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="cannot precede",
    ):
        PipelineNodeTrace(
            node=Y3172Node.P,
            status=PipelineNodeStatus.COMPLETED,
            started_at=END,
            completed_at=START,
            artifact_ids=("RECOMMENDATION-001",),
        )


def test_details_are_deeply_immutable() -> None:
    trace = _node(
        Y3172Node.PP,
        PipelineNodeStatus.COMPLETED,
        details={
            "nested": {
                "status": "verified",
            },
        },
    )

    with pytest.raises(TypeError):
        trace.details["other"] = "value"

    with pytest.raises(TypeError):
        trace.details["nested"]["status"] = "modified"


def test_details_reject_sets() -> None:
    with pytest.raises((TypeError, ValueError)):
        _node(
            Y3172Node.PP,
            PipelineNodeStatus.COMPLETED,
            details={
                "unsafe": {"set-value"},
            },
        )


def test_details_reject_nan() -> None:
    with pytest.raises((TypeError, ValueError)):
        _node(
            Y3172Node.M,
            PipelineNodeStatus.COMPLETED,
            details={
                "score": nan,
            },
        )


@pytest.mark.parametrize(
    "field_name, invalid_value",
    [
        ("formal_conformance_claimed", 0),
        ("formal_conformance_claimed", "false"),
        ("certification_claimed", 0),
        ("certification_claimed", ""),
    ],
)
def test_claim_flags_require_strict_booleans(
    field_name: str,
    invalid_value: object,
) -> None:
    values = {
        "trace_id": "TRACE-BOOL",
        "run_id": "RUN-BOOL",
        "created_at": START,
        "nodes": _nodes_for_outcome(
            PipelineNodeStatus.COMPLETED,
            PipelineNodeStatus.COMPLETED,
        ),
        "execution_receipt_id": "EXEC-BOOL",
        "distribution_acknowledgment_id": "ACK-BOOL",
        field_name: invalid_value,
    }

    with pytest.raises(TypeError):
        Y3172PipelineTrace(**values)


def test_formal_conformance_claim_is_rejected() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="formal ITU-T Y.3172 conformance",
    ):
        _delivered_trace(
            formal_conformance_claimed=True,
        )


def test_certification_claim_is_rejected() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="ITU certification",
    ):
        _delivered_trace(
            certification_claimed=True,
        )


def test_delivered_outcome_requires_execution_receipt() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="requires execution_receipt_id",
    ):
        _delivered_trace(
            execution_receipt_id=None,
        )


def test_delivered_outcome_requires_acknowledgment() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="requires distribution_acknowledgment_id",
    ):
        _delivered_trace(
            distribution_acknowledgment_id=None,
        )


def test_delivered_outcome_prohibits_review_receipt() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="prohibits review_queue_receipt_id",
    ):
        _delivered_trace(
            review_queue_receipt_id="REVIEW-001",
        )


def test_held_outcome_requires_review_receipt() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="requires review_queue_receipt_id",
    ):
        Y3172PipelineTrace(
            trace_id="TRACE-HOLD",
            run_id="RUN-HOLD",
            created_at=START,
            nodes=_nodes_for_outcome(
                PipelineNodeStatus.HELD,
                PipelineNodeStatus.NOT_REACHED,
            ),
        )


def test_held_outcome_prohibits_delivery_artifacts() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="prohibits execution_receipt_id",
    ):
        Y3172PipelineTrace(
            trace_id="TRACE-HOLD",
            run_id="RUN-HOLD",
            created_at=START,
            nodes=_nodes_for_outcome(
                PipelineNodeStatus.HELD,
                PipelineNodeStatus.NOT_REACHED,
            ),
            execution_receipt_id="EXEC-HOLD",
            review_queue_receipt_id="REVIEW-HOLD",
        )


def test_held_outcome_is_valid_with_review_receipt() -> None:
    trace = Y3172PipelineTrace(
        trace_id="TRACE-HOLD",
        run_id="RUN-HOLD",
        created_at=START,
        nodes=_nodes_for_outcome(
            PipelineNodeStatus.HELD,
            PipelineNodeStatus.NOT_REACHED,
        ),
        review_queue_receipt_id="REVIEW-HOLD",
    )

    assert trace.review_queue_receipt_id == "REVIEW-HOLD"
    assert trace.distribution_acknowledgment_id is None


def test_prevented_outcome_requires_execution_receipt() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="requires execution_receipt_id",
    ):
        Y3172PipelineTrace(
            trace_id="TRACE-BLOCK",
            run_id="RUN-BLOCK",
            created_at=START,
            nodes=_nodes_for_outcome(
                PipelineNodeStatus.PREVENTED,
                PipelineNodeStatus.NOT_REACHED,
            ),
        )


def test_prevented_outcome_is_valid_without_ack() -> None:
    trace = Y3172PipelineTrace(
        trace_id="TRACE-BLOCK",
        run_id="RUN-BLOCK",
        created_at=START,
        nodes=_nodes_for_outcome(
            PipelineNodeStatus.PREVENTED,
            PipelineNodeStatus.NOT_REACHED,
        ),
        execution_receipt_id="EXEC-BLOCK",
    )

    assert trace.execution_receipt_id == "EXEC-BLOCK"
    assert trace.distribution_acknowledgment_id is None


def test_prevented_outcome_prohibits_ack() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="prohibits distribution_acknowledgment_id",
    ):
        Y3172PipelineTrace(
            trace_id="TRACE-BLOCK",
            run_id="RUN-BLOCK",
            created_at=START,
            nodes=_nodes_for_outcome(
                PipelineNodeStatus.PREVENTED,
                PipelineNodeStatus.NOT_REACHED,
            ),
            execution_receipt_id="EXEC-BLOCK",
            distribution_acknowledgment_id="ACK-BLOCK",
        )


def test_not_attempted_outcome_prohibits_receipts() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="prohibits receipts and acknowledgments",
    ):
        Y3172PipelineTrace(
            trace_id="TRACE-NOT-ATTEMPTED",
            run_id="RUN-NOT-ATTEMPTED",
            created_at=START,
            nodes=_nodes_for_outcome(
                PipelineNodeStatus.NOT_REACHED,
                PipelineNodeStatus.NOT_REACHED,
            ),
            execution_receipt_id="EXEC-INVALID",
        )


def test_failed_closed_prohibits_acknowledgment() -> None:
    with pytest.raises(
        Y3172TraceError,
        match="prohibits distribution acknowledgment",
    ):
        Y3172PipelineTrace(
            trace_id="TRACE-FAILED",
            run_id="RUN-FAILED",
            created_at=START,
            nodes=_nodes_for_outcome(
                PipelineNodeStatus.FAILED_CLOSED,
                PipelineNodeStatus.NOT_REACHED,
            ),
            distribution_acknowledgment_id="ACK-INVALID",
        )


def test_invalid_node_order_is_rejected() -> None:
    nodes = list(
        _nodes_for_outcome(
            PipelineNodeStatus.COMPLETED,
            PipelineNodeStatus.COMPLETED,
        )
    )
    nodes[0], nodes[1] = nodes[1], nodes[0]

    with pytest.raises(
        Y3172TraceError,
        match="canonical order",
    ):
        Y3172PipelineTrace(
            trace_id="TRACE-ORDER",
            run_id="RUN-ORDER",
            created_at=START,
            nodes=tuple(nodes),
            execution_receipt_id="EXEC-ORDER",
            distribution_acknowledgment_id="ACK-ORDER",
        )


def test_interpretation_id_is_fixed() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="interpretation_id must be",
    ):
        _delivered_trace(
            interpretation_id="UNREGISTERED-INTERPRETATION",
        )


def test_receipt_identifiers_cannot_be_blank() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="execution_receipt_id",
    ):
        _delivered_trace(
            execution_receipt_id="   ",
        )


def test_canonical_json_is_deterministic() -> None:
    first = _delivered_trace(
        project_extensions=(
            "deterministic_policy_gate",
            "tamper_evident_audit",
        ),
    )
    second = _delivered_trace(
        project_extensions=(
            "deterministic_policy_gate",
            "tamper_evident_audit",
        ),
    )

    assert first.to_canonical_json() == second.to_canonical_json()


def test_claim_boundary_is_serialized_explicitly() -> None:
    trace = _delivered_trace()
    payload = trace.to_dict()

    assert payload["formal_conformance_claimed"] is False
    assert payload["certification_claimed"] is False
    assert (
        payload["interpretation_id"]
        == AMBA_GOV_Y3172_INTERPRETATION_ID
    )