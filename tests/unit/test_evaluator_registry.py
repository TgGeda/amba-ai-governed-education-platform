from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import threading
from typing import Any

import pytest

from amba_ai.governance.evaluator_registry import (
    EvaluatorRegistry,
    PolicyEvaluatorProtocol,
)
from amba_ai.governance.models import (
    DuplicateEvaluatorError,
    MissingEvaluatorsError,
)
from amba_ai.governance.operation_registry import OperationRegistry


@dataclass
class StubEvaluator:
    evaluator_id: str
    evaluator_version: str = "1.0.0"
    result: Any = None

    def evaluate(
        self,
        event: Any,
        operation: Any,
        record_registry: Any,
    ) -> Any:
        return self.result


class MissingEvaluate:
    evaluator_id = "missing-evaluate"
    evaluator_version = "1.0.0"


class NonCallableEvaluate:
    evaluator_id = "non-callable"
    evaluator_version = "1.0.0"
    evaluate = "not-callable"


class MissingEvaluatorId:
    evaluator_version = "1.0.0"

    def evaluate(
        self,
        event: Any,
        operation: Any,
        record_registry: Any,
    ) -> Any:
        return None


class MissingEvaluatorVersion:
    evaluator_id = "missing-version"

    def evaluate(
        self,
        event: Any,
        operation: Any,
        record_registry: Any,
    ) -> Any:
        return None


def make_operation_registry(
    monkeypatch: pytest.MonkeyPatch,
    required_ids_by_operation: tuple[tuple[str, ...], ...],
) -> OperationRegistry:
    operations = tuple(
        SimpleNamespace(required_evaluator_ids=required_ids)
        for required_ids in required_ids_by_operation
    )
    monkeypatch.setattr(
        OperationRegistry,
        "list_operations",
        lambda self: operations,
    )
    return object.__new__(OperationRegistry)


def test_protocol_accepts_structurally_valid_evaluator() -> None:
    evaluator = StubEvaluator("evaluator-a")

    assert isinstance(evaluator, PolicyEvaluatorProtocol)


def test_registry_starts_empty() -> None:
    registry = EvaluatorRegistry()

    assert len(registry) == 0
    assert registry.list_evaluator_ids() == ()
    assert registry.list_evaluators() == ()
    assert tuple(registry) == ()
    assert "unknown" not in registry
    assert 123 not in registry
    assert " " not in registry


def test_register_get_require_contains_and_membership() -> None:
    registry = EvaluatorRegistry()
    evaluator = StubEvaluator(" evaluator-a ", " 1.0.0 ")

    registry.register(evaluator)

    assert len(registry) == 1
    assert registry.get("evaluator-a") is evaluator
    assert registry.get(" evaluator-a ") is evaluator
    assert registry.require("evaluator-a") is evaluator
    assert registry.contains("evaluator-a") is True
    assert "evaluator-a" in registry
    assert " evaluator-a " in registry


def test_register_same_instance_is_idempotent() -> None:
    registry = EvaluatorRegistry()
    evaluator = StubEvaluator("evaluator-a")

    registry.register(evaluator)
    registry.register(evaluator)

    assert len(registry) == 1
    assert registry.require("evaluator-a") is evaluator


def test_register_different_instance_same_version_is_rejected() -> None:
    registry = EvaluatorRegistry()
    registry.register(StubEvaluator("evaluator-a", "1.0.0"))

    with pytest.raises(
        DuplicateEvaluatorError,
        match=(
            "Evaluator 'evaluator-a' is already registered at version "
            "'1.0.0' with a different instance"
        ),
    ):
        registry.register(StubEvaluator("evaluator-a", "1.0.0"))


def test_register_different_version_is_rejected() -> None:
    registry = EvaluatorRegistry()
    registry.register(StubEvaluator("evaluator-a", "1.0.0"))

    with pytest.raises(
        DuplicateEvaluatorError,
        match=(
            "Evaluator 'evaluator-a' is already registered at version "
            "'1.0.0'; version '2.0.0' cannot be registered"
        ),
    ):
        registry.register(StubEvaluator("evaluator-a", "2.0.0"))


@pytest.mark.parametrize(
    "evaluator, exception, message",
    [
        (None, TypeError, "evaluator is required"),
        (
            object(),
            TypeError,
            "evaluator must satisfy PolicyEvaluatorProtocol",
        ),
        (
            MissingEvaluate(),
            TypeError,
            "evaluator must satisfy PolicyEvaluatorProtocol",
        ),
        (
            NonCallableEvaluate(),
            TypeError,
            "evaluator.evaluate must be callable",
        ),
        (
            MissingEvaluatorId(),
            TypeError,
            "evaluator must satisfy PolicyEvaluatorProtocol",
        ),
        (
            MissingEvaluatorVersion(),
            TypeError,
            "evaluator must satisfy PolicyEvaluatorProtocol",
        ),
        (
            StubEvaluator(" ", "1.0.0"),
            ValueError,
            "evaluator_id must not be empty",
        ),
        (
            StubEvaluator("evaluator-a", " "),
            ValueError,
            "evaluator_version must not be empty",
        ),
    ],
)
def test_register_rejects_invalid_evaluators(
    evaluator: Any,
    exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception, match=message):
        EvaluatorRegistry().register(evaluator)


@pytest.mark.parametrize(
    "method_name",
    ["get", "require", "contains"],
)
def test_lookup_methods_reject_empty_identifier(
    method_name: str,
) -> None:
    registry = EvaluatorRegistry()
    method = getattr(registry, method_name)

    with pytest.raises(
        ValueError,
        match="evaluator_id must not be empty",
    ):
        method(" ")


def test_get_and_contains_return_missing_values() -> None:
    registry = EvaluatorRegistry()

    assert registry.get("missing") is None
    assert registry.contains("missing") is False
    assert "missing" not in registry


def test_require_rejects_missing_evaluator() -> None:
    with pytest.raises(
        MissingEvaluatorsError,
        match="Required evaluator 'missing' is not registered",
    ):
        EvaluatorRegistry().require("missing")


def test_listing_and_iteration_are_deterministic() -> None:
    registry = EvaluatorRegistry()
    evaluator_c = StubEvaluator("evaluator-c")
    evaluator_a = StubEvaluator("evaluator-a")
    evaluator_b = StubEvaluator("evaluator-b")

    for evaluator in (evaluator_c, evaluator_a, evaluator_b):
        registry.register(evaluator)

    assert registry.list_evaluator_ids() == (
        "evaluator-a",
        "evaluator-b",
        "evaluator-c",
    )
    assert registry.list_evaluators() == (
        evaluator_a,
        evaluator_b,
        evaluator_c,
    )
    assert tuple(registry) == (
        evaluator_a,
        evaluator_b,
        evaluator_c,
    )


def test_iteration_uses_snapshot() -> None:
    registry = EvaluatorRegistry()
    first = StubEvaluator("evaluator-a")
    second = StubEvaluator("evaluator-b")
    registry.register(first)

    iterator = iter(registry)
    registry.register(second)

    assert tuple(iterator) == (first,)
    assert tuple(registry) == (first, second)


def test_validate_operations_accepts_registered_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = EvaluatorRegistry()
    registry.register(StubEvaluator("evaluator-a"))
    registry.register(StubEvaluator("evaluator-b"))
    operation_registry = make_operation_registry(
        monkeypatch,
        (
            ("evaluator-a",),
            ("evaluator-a", "evaluator-b"),
            (),
        ),
    )

    registry.validate_operations(operation_registry)


def test_validate_operations_reports_sorted_unique_missing_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = EvaluatorRegistry()
    registry.register(StubEvaluator("registered"))
    operation_registry = make_operation_registry(
        monkeypatch,
        (
            ("missing-z", "registered"),
            ("missing-a", "missing-z"),
        ),
    )

    with pytest.raises(
        MissingEvaluatorsError,
        match=(
            "Operation registry requires unregistered evaluators: "
            "missing-a, missing-z"
        ),
    ):
        registry.validate_operations(operation_registry)


def test_validate_operations_normalizes_required_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = EvaluatorRegistry()
    registry.register(StubEvaluator("evaluator-a"))
    operation_registry = make_operation_registry(
        monkeypatch,
        ((" evaluator-a ",),),
    )

    registry.validate_operations(operation_registry)


def test_validate_operations_rejects_wrong_registry_type() -> None:
    with pytest.raises(
        TypeError,
        match="operation_registry must be an OperationRegistry",
    ):
        EvaluatorRegistry().validate_operations(
            object()  # type: ignore[arg-type]
        )


def test_validate_operations_requires_tuple_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        OperationRegistry,
        "list_operations",
        lambda self: [],
    )
    operation_registry = object.__new__(OperationRegistry)

    with pytest.raises(
        TypeError,
        match=r"list_operations\(\) must return a tuple",
    ):
        EvaluatorRegistry().validate_operations(operation_registry)


def test_validate_operations_requires_tuple_evaluator_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        OperationRegistry,
        "list_operations",
        lambda self: (
            SimpleNamespace(
                required_evaluator_ids=["evaluator-a"]
            ),
        ),
    )
    operation_registry = object.__new__(OperationRegistry)

    with pytest.raises(
        TypeError,
        match="required_evaluator_ids must be a tuple",
    ):
        EvaluatorRegistry().validate_operations(operation_registry)


def test_validate_operations_rejects_missing_required_ids_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        OperationRegistry,
        "list_operations",
        lambda self: (SimpleNamespace(),),
    )
    operation_registry = object.__new__(OperationRegistry)

    with pytest.raises(
        TypeError,
        match="required_evaluator_ids must be a tuple",
    ):
        EvaluatorRegistry().validate_operations(operation_registry)


def test_validate_operations_rejects_empty_required_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_registry = make_operation_registry(
        monkeypatch,
        ((" ",),),
    )

    with pytest.raises(
        ValueError,
        match="required_evaluator_id must not be empty",
    ):
        EvaluatorRegistry().validate_operations(operation_registry)


def test_validate_operations_rejects_duplicate_required_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_registry = make_operation_registry(
        monkeypatch,
        (("evaluator-a", "evaluator-a"),),
    )

    with pytest.raises(
        ValueError,
        match="required_evaluator_ids cannot contain duplicates",
    ):
        EvaluatorRegistry().validate_operations(operation_registry)


def test_concurrent_identical_registration_is_safe() -> None:
    registry = EvaluatorRegistry()
    evaluator = StubEvaluator("evaluator-a")
    failures: list[Exception] = []

    def register() -> None:
        try:
            registry.register(evaluator)
        except Exception as error:
            failures.append(error)

    threads = [
        threading.Thread(target=register)
        for _ in range(20)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert len(registry) == 1
    assert registry.require("evaluator-a") is evaluator


def test_concurrent_distinct_registration_is_safe() -> None:
    registry = EvaluatorRegistry()
    evaluators = tuple(
        StubEvaluator(f"evaluator-{index:02d}")
        for index in range(20)
    )
    failures: list[Exception] = []

    def register(evaluator: StubEvaluator) -> None:
        try:
            registry.register(evaluator)
        except Exception as error:
            failures.append(error)

    threads = [
        threading.Thread(target=register, args=(evaluator,))
        for evaluator in evaluators
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert len(registry) == len(evaluators)
    assert registry.list_evaluator_ids() == tuple(
        sorted(
            evaluator.evaluator_id
            for evaluator in evaluators
        )
    )
