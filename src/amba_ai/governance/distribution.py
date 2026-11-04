from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from amba_ai.governance.models import (
    deep_freeze,
    to_canonical_json,
)


class DistributionDisposition(str, Enum):
    DELIVERED = "delivered"
    PREVENTED = "prevented"
    QUEUED_FOR_REVIEW = "queued_for_review"


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
        raise TypeError(f"{normalized_field_name} must be a string")

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{normalized_field_name} must not be empty")

    return normalized_value


def _to_mutable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _to_mutable_value(nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, tuple):
        return [_to_mutable_value(item) for item in value]

    if isinstance(value, list):
        return [_to_mutable_value(item) for item in value]

    if isinstance(value, Enum):
        return value.value

    return value


@dataclass(frozen=True, slots=True)
class DistributionEffect:
    executor_id: str
    destination_id: str
    disposition: DistributionDisposition
    effect_code: str
    details: Mapping[str, Any]

    def __post_init__(self) -> None:
        executor_id = _require_text(self.executor_id, "executor_id")
        destination_id = _require_text(self.destination_id, "destination_id")
        effect_code = _require_text(self.effect_code, "effect_code")

        if not isinstance(self.disposition, DistributionDisposition):
            raise TypeError(
                "disposition must be a DistributionDisposition"
            )

        if not isinstance(self.details, Mapping):
            raise TypeError("details must be a mapping")

        frozen_details = deep_freeze(self.details)
        if not isinstance(frozen_details, MappingProxyType):
            raise TypeError(
                "deep_freeze must return an immutable mapping for details"
            )

        object.__setattr__(self, "executor_id", executor_id)
        object.__setattr__(self, "destination_id", destination_id)
        object.__setattr__(self, "effect_code", effect_code)
        object.__setattr__(self, "details", frozen_details)

    @property
    def delivered(self) -> bool:
        return self.disposition is DistributionDisposition.DELIVERED

    @property
    def prevented(self) -> bool:
        return self.disposition is DistributionDisposition.PREVENTED

    @property
    def queued_for_review(self) -> bool:
        return (
            self.disposition
            is DistributionDisposition.QUEUED_FOR_REVIEW
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "executor_id": self.executor_id,
            "destination_id": self.destination_id,
            "disposition": self.disposition.value,
            "effect_code": self.effect_code,
            "details": _to_mutable_value(self.details),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


@runtime_checkable
class DistributionExecutor(Protocol):
    executor_id: str

    def execute(
        self,
        destination_id: str,
        payload: Mapping[str, Any],
    ) -> DistributionEffect:
        ...


class _BaseDistributionExecutor:
    executor_id: str

    def _validate_request(
        self,
        destination_id: object,
        payload: object,
    ) -> str:
        destination = _require_text(
            destination_id,
            "destination_id",
        )

        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")

        return destination


class DistributionPermitExecutor(_BaseDistributionExecutor):
    executor_id = "distribution-permit-executor"

    def execute(
        self,
        destination_id: str,
        payload: Mapping[str, Any],
    ) -> DistributionEffect:
        destination = self._validate_request(destination_id, payload)

        return DistributionEffect(
            executor_id=self.executor_id,
            destination_id=destination,
            disposition=DistributionDisposition.DELIVERED,
            effect_code="SIMULATED_DELIVERY_RECORDED",
            details={
                "simulated": True,
                "legal_effect": False,
                "delivery_recorded": True,
            },
        )


class DistributionBlockExecutor(_BaseDistributionExecutor):
    executor_id = "distribution-block-executor"

    def execute(
        self,
        destination_id: str,
        payload: Mapping[str, Any],
    ) -> DistributionEffect:
        destination = self._validate_request(destination_id, payload)

        return DistributionEffect(
            executor_id=self.executor_id,
            destination_id=destination,
            disposition=DistributionDisposition.PREVENTED,
            effect_code="SIMULATED_DISTRIBUTION_PREVENTED",
            details={
                "simulated": True,
                "legal_effect": False,
                "distribution_prevented": True,
            },
        )


class ReviewQueueExecutor(_BaseDistributionExecutor):
    executor_id = "review-queue-executor"

    def execute(
        self,
        destination_id: str,
        payload: Mapping[str, Any],
    ) -> DistributionEffect:
        destination = self._validate_request(destination_id, payload)

        return DistributionEffect(
            executor_id=self.executor_id,
            destination_id=destination,
            disposition=DistributionDisposition.QUEUED_FOR_REVIEW,
            effect_code="SIMULATED_REVIEW_QUEUE_ENQUEUED",
            details={
                "simulated": True,
                "legal_effect": False,
                "queued_for_review": True,
                "delivery_recorded": False,
            },
        )
