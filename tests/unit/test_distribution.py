from __future__ import annotations

from types import MappingProxyType
import pytest

from amba_ai.governance.distribution import (
    DistributionBlockExecutor, DistributionDisposition, DistributionEffect,
    DistributionPermitExecutor, ReviewQueueExecutor,
)


def test_permit_delivers_and_only_delivery_is_acknowledgeable() -> None:
    effect = DistributionPermitExecutor().execute("destination", {"id": "request"})
    assert effect.disposition is DistributionDisposition.DELIVERED
    assert effect.delivered is True
    assert effect.prevented is False
    assert effect.queued_for_review is False


def test_block_has_observable_prevention_effect() -> None:
    effect = DistributionBlockExecutor().execute("destination", {"id": "request"})
    assert effect.disposition is DistributionDisposition.PREVENTED
    assert effect.prevented is True
    assert effect.delivered is False
    assert effect.details["distribution_prevented"] is True


def test_review_queue_is_distinct_from_delivery_and_block() -> None:
    effect = ReviewQueueExecutor().execute("review", {"id": "request"})
    assert effect.disposition is DistributionDisposition.QUEUED_FOR_REVIEW
    assert effect.queued_for_review is True
    assert effect.delivered is False
    assert effect.prevented is False
    assert effect.details["delivery_recorded"] is False


def test_details_are_deeply_immutable_and_serializable() -> None:
    source = {"nested": {"values": [1, 2]}}
    effect = DistributionEffect(
        executor_id="executor", destination_id="destination",
        disposition=DistributionDisposition.PREVENTED,
        effect_code="TEST", details=source,
    )
    source["nested"]["values"].append(3)
    assert isinstance(effect.details, MappingProxyType)
    assert effect.details["nested"]["values"] == (1, 2)
    assert effect.to_dict()["details"] == {"nested": {"values": [1, 2]}}
    assert effect.to_canonical_json() == effect.to_canonical_json()


@pytest.mark.parametrize("executor", [DistributionPermitExecutor(), DistributionBlockExecutor(), ReviewQueueExecutor()])
def test_executors_validate_requests(executor: object) -> None:
    with pytest.raises(TypeError):
        executor.execute(123, {})  # type: ignore[attr-defined,arg-type]
    with pytest.raises(ValueError):
        executor.execute(" ", {})  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        executor.execute("destination", [])  # type: ignore[attr-defined,arg-type]
