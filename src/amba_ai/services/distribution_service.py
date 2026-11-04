from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from amba_ai.governance.distribution import (
    DistributionBlockExecutor,
    DistributionDisposition,
    DistributionEffect,
    DistributionPermitExecutor,
    ReviewQueueExecutor,
)
from amba_ai.governance.execution import ExecutionResult, ExecutionStatus
from amba_ai.governance.models import (
    EnforcementAction,
    GovernanceConfigurationError,
    PipelineEvent,
    deep_freeze,
)


@runtime_checkable
class DistributionExecutorProtocol(Protocol):
    def execute(
        self,
        destination_id: str,
        payload: Mapping[str, Any],
    ) -> DistributionEffect:
        ...


class DistributionService:
    def __init__(
        self,
        *,
        permit_executor: DistributionExecutorProtocol,
        block_executor: DistributionExecutorProtocol,
        review_executor: DistributionExecutorProtocol,
    ) -> None:
        for name, value in (
            ("permit_executor", permit_executor),
            ("block_executor", block_executor),
            ("review_executor", review_executor),
        ):
            if not isinstance(value, DistributionExecutorProtocol):
                raise TypeError(f"{name} must implement DistributionExecutorProtocol")
        self._permit_executor = permit_executor
        self._block_executor = block_executor
        self._review_executor = review_executor

    @property
    def permit_executor(self) -> DistributionExecutorProtocol:
        return self._permit_executor

    @property
    def block_executor(self) -> DistributionExecutorProtocol:
        return self._block_executor

    @property
    def review_executor(self) -> DistributionExecutorProtocol:
        return self._review_executor

    def distribute(
        self,
        *,
        event: PipelineEvent,
        execution_result: ExecutionResult,
        payload: Mapping[str, Any],
    ) -> DistributionEffect | None:
        if not isinstance(event, PipelineEvent):
            raise TypeError("event must be a PipelineEvent")
        if not isinstance(execution_result, ExecutionResult):
            raise TypeError("execution_result must be an ExecutionResult")
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        request = execution_result.request
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
        frozen_payload = deep_freeze(dict(payload))
        review = execution_result.review_queue_receipt
        receipt = execution_result.execution_receipt
        acknowledgment = execution_result.distribution_acknowledgment
        if review is not None:
            if review.request_id != request.request_id:
                raise GovernanceConfigurationError(
                    "review receipt does not belong to the execution request"
                )
            if review.event_id != event.event_id:
                raise GovernanceConfigurationError(
                    "review receipt event identifier does not match pipeline event"
                )
            if receipt is not None or acknowledgment is not None:
                raise GovernanceConfigurationError(
                    "review routing must not contain execution delivery artifacts"
                )
            effect = self._review_executor.execute(
                review.queue_destination_id,
                frozen_payload,
            )
            return self._validate_effect(
                effect,
                DistributionDisposition.QUEUED_FOR_REVIEW,
                review.queue_destination_id,
            )
        if receipt is None:
            raise GovernanceConfigurationError(
                "execution result does not contain a receipt"
            )
        if receipt.request_id != request.request_id:
            raise GovernanceConfigurationError(
                "execution receipt does not belong to the execution request"
            )
        if receipt.event_id != event.event_id:
            raise GovernanceConfigurationError(
                "execution receipt event identifier does not match pipeline event"
            )
        if receipt.operation_id != event.operation_id:
            raise GovernanceConfigurationError(
                "execution receipt operation identifier does not match pipeline event"
            )
        if receipt.action_executed is not request.recommended_action:
            raise GovernanceConfigurationError(
                "execution receipt action does not match execution request"
            )
        if receipt.status in {
            ExecutionStatus.FAILED,
            ExecutionStatus.NOT_ATTEMPTED,
            ExecutionStatus.CANCELLED,
        }:
            if acknowledgment is not None:
                raise GovernanceConfigurationError(
                    "non-successful execution cannot contain an acknowledgment"
                )
            return None
        if receipt.status is not ExecutionStatus.SUCCEEDED:
            raise GovernanceConfigurationError(
                "unsupported execution status for distribution"
            )
        action = receipt.action_executed
        if action is EnforcementAction.PROCEED:
            if acknowledgment is None:
                raise GovernanceConfigurationError(
                    "successful delivery requires an acknowledgment"
                )
            if acknowledgment.execution_receipt_id != receipt.receipt_id:
                raise GovernanceConfigurationError(
                    "distribution acknowledgment does not reference execution receipt"
                )
            if acknowledgment.destination_id != event.destination_id:
                raise GovernanceConfigurationError(
                    "distribution acknowledgment destination does not match pipeline event"
                )
            effect = self._permit_executor.execute(
                event.destination_id,
                frozen_payload,
            )
            return self._validate_effect(
                effect,
                DistributionDisposition.DELIVERED,
                event.destination_id,
            )
        if action in {EnforcementAction.BLOCK, EnforcementAction.ABSTAIN}:
            if acknowledgment is not None:
                raise GovernanceConfigurationError(
                    "prevented distribution cannot contain an acknowledgment"
                )
            effect = self._block_executor.execute(
                event.destination_id,
                frozen_payload,
            )
            return self._validate_effect(
                effect,
                DistributionDisposition.PREVENTED,
                event.destination_id,
            )
        raise GovernanceConfigurationError(
            "execution result cannot be routed to a distribution executor"
        )

    @staticmethod
    def _validate_effect(
        effect: object,
        disposition: DistributionDisposition,
        destination_id: str,
    ) -> DistributionEffect:
        if not isinstance(effect, DistributionEffect):
            raise GovernanceConfigurationError(
                "distribution executor returned an invalid effect"
            )
        if effect.disposition is not disposition:
            raise GovernanceConfigurationError(
                "distribution effect disposition does not match routed outcome"
            )
        if effect.destination_id != destination_id:
            raise GovernanceConfigurationError(
                "distribution effect destination does not match routed destination"
            )
        return effect


def build_default_distribution_service() -> DistributionService:
    return DistributionService(
        permit_executor=DistributionPermitExecutor(),
        block_executor=DistributionBlockExecutor(),
        review_executor=ReviewQueueExecutor(),
    )
