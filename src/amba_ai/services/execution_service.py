from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from amba_ai.governance.approvals import ApprovalDecision
from amba_ai.governance.execution import ExecutionResult
from amba_ai.governance.models import (
    GovernanceConfigurationError,
    PipelineEvent,
    PolicyRecommendation,
    deep_freeze,
)


@runtime_checkable
class ExecutionGatewayProtocol(Protocol):
    def execute(
        self,
        event: PipelineEvent,
        recommendation: PolicyRecommendation,
        approval_decision: ApprovalDecision | None,
        idempotency_key: str,
        execution_details: Mapping[str, Any] | None = None,
    ) -> ExecutionResult:
        ...


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")

    return normalized


class ExecutionService:
    """Application boundary for typed, idempotent execution.

    The service delegates to the single injected execution gateway. It does
    not reinterpret recommendations, authenticate approvals, select a
    different action, or construct execution receipts independently.
    """

    def __init__(self, execution_gateway: ExecutionGatewayProtocol) -> None:
        if execution_gateway is None:
            raise TypeError("execution_gateway is required")
        if not isinstance(execution_gateway, ExecutionGatewayProtocol):
            raise TypeError(
                "execution_gateway must provide a callable execute method"
            )

        self._execution_gateway = execution_gateway

    @property
    def execution_gateway(self) -> ExecutionGatewayProtocol:
        return self._execution_gateway

    def execute(
        self,
        *,
        event: PipelineEvent,
        recommendation: PolicyRecommendation,
        approval_decision: ApprovalDecision | None,
        idempotency_key: str,
        execution_details: Mapping[str, Any] | None = None,
    ) -> ExecutionResult:
        if not isinstance(event, PipelineEvent):
            raise TypeError("event must be a PipelineEvent")
        if not isinstance(recommendation, PolicyRecommendation):
            raise TypeError("recommendation must be a PolicyRecommendation")
        if recommendation.event_id != event.event_id:
            raise GovernanceConfigurationError(
                "recommendation event identifier does not match pipeline event"
            )
        if approval_decision is not None and not isinstance(
            approval_decision,
            ApprovalDecision,
        ):
            raise TypeError(
                "approval_decision must be an ApprovalDecision or None"
            )

        normalized_idempotency_key = _require_text(
            idempotency_key,
            "idempotency_key",
        )

        if execution_details is not None and not isinstance(
            execution_details,
            Mapping,
        ):
            raise TypeError("execution_details must be a mapping or None")

        frozen_details = (
            None
            if execution_details is None
            else deep_freeze(dict(execution_details))
        )

        result = self._execution_gateway.execute(
            event=event,
            recommendation=recommendation,
            approval_decision=approval_decision,
            idempotency_key=normalized_idempotency_key,
            execution_details=frozen_details,
        )

        self._validate_result(
            event=event,
            recommendation=recommendation,
            approval_decision=approval_decision,
            idempotency_key=normalized_idempotency_key,
            result=result,
        )
        return result

    @staticmethod
    def _validate_result(
        *,
        event: PipelineEvent,
        recommendation: PolicyRecommendation,
        approval_decision: ApprovalDecision | None,
        idempotency_key: str,
        result: object,
    ) -> None:
        if not isinstance(result, ExecutionResult):
            raise GovernanceConfigurationError(
                "execution_gateway returned an invalid result"
            )

        request = result.request
        if request.event_id != event.event_id:
            raise GovernanceConfigurationError(
                "execution result event identifier does not match pipeline event"
            )
        if request.operation_id != event.operation_id:
            raise GovernanceConfigurationError(
                "execution result operation identifier does not match pipeline event"
            )
        if request.destination_id != event.destination_id:
            raise GovernanceConfigurationError(
                "execution result destination identifier does not match pipeline event"
            )
        if request.recommended_action is not recommendation.recommended_action:
            raise GovernanceConfigurationError(
                "execution request action does not match policy recommendation"
            )
        if request.idempotency_key != idempotency_key:
            raise GovernanceConfigurationError(
                "execution result idempotency key does not match execution request"
            )

        expected_decision_id = (
            None
            if approval_decision is None
            else approval_decision.decision_id
        )
        if request.approval_decision_id != expected_decision_id:
            raise GovernanceConfigurationError(
                "execution request approval decision does not match supplied approval"
            )

        if result.execution_receipt is not None:
            if result.execution_receipt.request_id != request.request_id:
                raise GovernanceConfigurationError(
                    "execution receipt does not belong to the execution request"
                )
            if result.execution_receipt.event_id != event.event_id:
                raise GovernanceConfigurationError(
                    "execution receipt event identifier does not match pipeline event"
                )

        if result.review_queue_receipt is not None:
            if result.review_queue_receipt.request_id != request.request_id:
                raise GovernanceConfigurationError(
                    "review queue receipt does not belong to the execution request"
                )
            if result.review_queue_receipt.event_id != event.event_id:
                raise GovernanceConfigurationError(
                    "review queue receipt event identifier does not match pipeline event"
                )

        acknowledgment = result.distribution_acknowledgment
        if acknowledgment is not None:
            receipt = result.execution_receipt
            if receipt is None:
                raise GovernanceConfigurationError(
                    "distribution acknowledgment requires an execution receipt"
                )
            if acknowledgment.execution_receipt_id != receipt.receipt_id:
                raise GovernanceConfigurationError(
                    "distribution acknowledgment does not belong to the execution receipt"
                )
            if acknowledgment.destination_id != event.destination_id:
                raise GovernanceConfigurationError(
                    "distribution acknowledgment destination does not match pipeline event"
                )
