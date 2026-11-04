from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

import pytest

from amba_ai.governance.execution import (
    ExecutionRequest,
    ExecutionResult,
    ReviewQueueReceipt,
)
from amba_ai.governance.models import (
    EnforcementAction,
    GovernanceConfigurationError,
    PipelineEvent,
    PolicyRecommendation,
)
from amba_ai.services.execution_service import ExecutionService


def make_event(
    *,
    event_id: str = "SYNTHETIC-EVENT",
    operation_id: str = "commercial_purchase_request",
) -> PipelineEvent:
    return PipelineEvent(
        event_id=event_id,
        timestamp="2026-06-01T12:00:00Z",
        operation_id=operation_id,
        source_node="SYNTHETIC-SOURCE",
        destination_id="SYNTHETIC-REVIEW-QUEUE",
        payload_type="synthetic_payload",
        payload={"synthetic": True},
        authorization_basis=None,
        synthetic_flag=True,
    )


def make_recommendation(
    *,
    event_id: str = "SYNTHETIC-EVENT",
) -> PolicyRecommendation:
    return PolicyRecommendation(
        recommendation_id="SYNTHETIC-RECOMMENDATION",
        event_id=event_id,
        recommended_action=EnforcementAction.HOLD_FOR_REVIEW,
        mitigation_steps=(),
        requires_approval=False,
        escalation_role=None,
    )


def make_result(
    *,
    event_id: str = "SYNTHETIC-EVENT",
    operation_id: str = "commercial_purchase_request",
    idempotency_key: str = "SYNTHETIC-EXECUTION-IDEMPOTENCY",
) -> ExecutionResult:
    request = ExecutionRequest.create(
        request_id="SYNTHETIC-EXECUTION-REQUEST",
        event_id=event_id,
        operation_id=operation_id,
        recommended_action=EnforcementAction.HOLD_FOR_REVIEW,
        destination_id="SYNTHETIC-REVIEW-QUEUE",
        precondition_digest=hashlib.sha256(b"precondition").hexdigest(),
        recommendation_digest=hashlib.sha256(b"recommendation").hexdigest(),
        approval_decision_id=None,
        idempotency_key=idempotency_key,
        created_at="2026-06-01T12:00:00Z",
    )
    receipt = ReviewQueueReceipt(
        receipt_id="SYNTHETIC-REVIEW-RECEIPT",
        request_id=request.request_id,
        event_id=event_id,
        queue_destination_id="SYNTHETIC-REVIEW-QUEUE",
        enqueued_at="2026-06-01T12:00:00Z",
        receipt_digest=hashlib.sha256(b"receipt").hexdigest(),
        reason_code="POLICY_HOLD",
        details={"synthetic": True},
    )
    return ExecutionResult(
        request=request,
        execution_receipt=None,
        review_queue_receipt=receipt,
        distribution_acknowledgment=None,
        duplicate=False,
    )


@dataclass
class StaticExecutionGateway:
    result: object
    call_count: int = 0
    received: dict[str, Any] | None = None

    def execute(
        self,
        event: PipelineEvent,
        recommendation: PolicyRecommendation,
        approval_decision: object | None,
        idempotency_key: str,
        execution_details: Mapping[str, Any] | None = None,
    ) -> Any:
        self.call_count += 1
        self.received = {
            "event": event,
            "recommendation": recommendation,
            "approval_decision": approval_decision,
            "idempotency_key": idempotency_key,
            "execution_details": execution_details,
        }
        return self.result


@pytest.mark.parametrize("value", [None, object()])
def test_constructor_rejects_invalid_gateway(value: object) -> None:
    with pytest.raises(TypeError, match="execution_gateway"):
        ExecutionService(value)  # type: ignore[arg-type]


def test_execute_delegates_once_and_freezes_details() -> None:
    event = make_event()
    recommendation = make_recommendation()
    expected = make_result(idempotency_key="synthetic-idempotency")
    gateway = StaticExecutionGateway(expected)
    service = ExecutionService(gateway)
    source_details = {"nested": {"items": [1, 2]}}

    result = service.execute(
        event=event,
        recommendation=recommendation,
        approval_decision=None,
        idempotency_key=" synthetic-idempotency ",
        execution_details=source_details,
    )

    source_details["nested"]["items"].append(3)
    assert result is expected
    assert gateway.call_count == 1
    assert gateway.received is not None
    assert gateway.received["idempotency_key"] == "synthetic-idempotency"
    assert gateway.received["execution_details"]["nested"]["items"] == (1, 2)


def test_execute_rejects_mismatched_recommendation() -> None:
    service = ExecutionService(StaticExecutionGateway(make_result()))

    with pytest.raises(
        GovernanceConfigurationError,
        match="recommendation event identifier",
    ):
        service.execute(
            event=make_event(event_id="EVENT-A"),
            recommendation=make_recommendation(event_id="EVENT-B"),
            approval_decision=None,
            idempotency_key="idempotency",
        )


def test_execute_rejects_invalid_inputs_before_delegation() -> None:
    gateway = StaticExecutionGateway(make_result())
    service = ExecutionService(gateway)
    event = make_event()
    recommendation = make_recommendation()

    with pytest.raises(TypeError, match="PipelineEvent"):
        service.execute(  # type: ignore[arg-type]
            event=object(),
            recommendation=recommendation,
            approval_decision=None,
            idempotency_key="idempotency",
        )
    with pytest.raises(ValueError, match="idempotency_key"):
        service.execute(
            event=event,
            recommendation=recommendation,
            approval_decision=None,
            idempotency_key=" ",
        )
    with pytest.raises(TypeError, match="execution_details"):
        service.execute(  # type: ignore[arg-type]
            event=event,
            recommendation=recommendation,
            approval_decision=None,
            idempotency_key="idempotency",
            execution_details=[],
        )

    assert gateway.call_count == 0


def test_execute_rejects_invalid_gateway_result() -> None:
    service = ExecutionService(StaticExecutionGateway(object()))

    with pytest.raises(
        GovernanceConfigurationError,
        match="invalid result",
    ):
        service.execute(
            event=make_event(),
            recommendation=make_recommendation(),
            approval_decision=None,
            idempotency_key="idempotency",
        )


def test_execute_rejects_result_for_different_event_or_operation() -> None:
    service = ExecutionService(
        StaticExecutionGateway(
            make_result(
                event_id="OTHER-EVENT",
                idempotency_key="idempotency",
            )
        )
    )
    with pytest.raises(
        GovernanceConfigurationError,
        match="result event identifier",
    ):
        service.execute(
            event=make_event(),
            recommendation=make_recommendation(),
            approval_decision=None,
            idempotency_key="idempotency",
        )

    service = ExecutionService(
        StaticExecutionGateway(
            make_result(
                operation_id="other-operation",
                idempotency_key="idempotency",
            )
        )
    )
    with pytest.raises(
        GovernanceConfigurationError,
        match="result operation identifier",
    ):
        service.execute(
            event=make_event(),
            recommendation=make_recommendation(),
            approval_decision=None,
            idempotency_key="idempotency",
        )
