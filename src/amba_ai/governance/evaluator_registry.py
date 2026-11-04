from __future__ import annotations

import threading
from typing import Iterator, Protocol, runtime_checkable

from amba_ai.governance.models import (
    DuplicateEvaluatorError,
    MissingEvaluatorsError,
    PipelineEvent,
    PolicyFinding,
    ResolvedOperation,
)
from amba_ai.governance.operation_registry import OperationRegistry
from amba_ai.governance.record_registry import PolicyRecordRegistry


def _require_identifier(
    value: str,
    field_name: str,
) -> str:
    normalized = str(value).strip()

    if not normalized:
        raise ValueError(
            f"{field_name} must not be empty"
        )

    return normalized


@runtime_checkable
class PolicyEvaluatorProtocol(Protocol):
    evaluator_id: str
    evaluator_version: str

    def evaluate(
        self,
        event: PipelineEvent,
        operation: ResolvedOperation,
        record_registry: PolicyRecordRegistry,
    ) -> PolicyFinding:
        ...


class EvaluatorRegistry:
    def __init__(self) -> None:
        self._evaluators: dict[
            str,
            PolicyEvaluatorProtocol,
        ] = {}
        self._lock = threading.RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._evaluators)

    def __iter__(
        self,
    ) -> Iterator[PolicyEvaluatorProtocol]:
        return iter(self.list_evaluators())

    def __contains__(
        self,
        evaluator_id: object,
    ) -> bool:
        if not isinstance(evaluator_id, str):
            return False

        normalized_id = evaluator_id.strip()

        if not normalized_id:
            return False

        with self._lock:
            return normalized_id in self._evaluators

    @staticmethod
    def _validate_evaluator(
        evaluator: PolicyEvaluatorProtocol,
    ) -> tuple[str, str]:
        if evaluator is None:
            raise TypeError(
                "evaluator is required"
            )

        if not isinstance(
            evaluator,
            PolicyEvaluatorProtocol,
        ):
            raise TypeError(
                "evaluator must satisfy "
                "PolicyEvaluatorProtocol"
            )

        evaluator_id = _require_identifier(
            evaluator.evaluator_id,
            "evaluator_id",
        )
        evaluator_version = _require_identifier(
            evaluator.evaluator_version,
            "evaluator_version",
        )

        if not callable(
            getattr(evaluator, "evaluate", None)
        ):
            raise TypeError(
                "evaluator.evaluate must be callable"
            )

        return evaluator_id, evaluator_version

    def register(
        self,
        evaluator: PolicyEvaluatorProtocol,
    ) -> None:
        evaluator_id, evaluator_version = (
            self._validate_evaluator(evaluator)
        )

        with self._lock:
            existing = self._evaluators.get(
                evaluator_id
            )

            if existing is None:
                self._evaluators[evaluator_id] = evaluator
                return

            if existing is evaluator:
                return

            existing_version = _require_identifier(
                existing.evaluator_version,
                "existing evaluator_version",
            )

            if existing_version == evaluator_version:
                raise DuplicateEvaluatorError(
                    f"Evaluator '{evaluator_id}' is already "
                    f"registered at version '{existing_version}' "
                    "with a different instance"
                )

            raise DuplicateEvaluatorError(
                f"Evaluator '{evaluator_id}' is already "
                f"registered at version '{existing_version}'; "
                f"version '{evaluator_version}' cannot be "
                "registered under the same identifier"
            )

    def get(
        self,
        evaluator_id: str,
    ) -> PolicyEvaluatorProtocol | None:
        normalized_id = _require_identifier(
            evaluator_id,
            "evaluator_id",
        )

        with self._lock:
            return self._evaluators.get(
                normalized_id
            )

    def require(
        self,
        evaluator_id: str,
    ) -> PolicyEvaluatorProtocol:
        normalized_id = _require_identifier(
            evaluator_id,
            "evaluator_id",
        )

        with self._lock:
            evaluator = self._evaluators.get(
                normalized_id
            )

        if evaluator is None:
            raise MissingEvaluatorsError(
                f"Required evaluator '{normalized_id}' "
                "is not registered"
            )

        return evaluator

    def contains(
        self,
        evaluator_id: str,
    ) -> bool:
        normalized_id = _require_identifier(
            evaluator_id,
            "evaluator_id",
        )

        with self._lock:
            return normalized_id in self._evaluators

    def list_evaluator_ids(
        self,
    ) -> tuple[str, ...]:
        with self._lock:
            return tuple(
                sorted(self._evaluators)
            )

    def list_evaluators(
        self,
    ) -> tuple[PolicyEvaluatorProtocol, ...]:
        with self._lock:
            return tuple(
                self._evaluators[evaluator_id]
                for evaluator_id in sorted(
                    self._evaluators
                )
            )

    def validate_operations(
        self,
        operation_registry: OperationRegistry,
    ) -> None:
        if not isinstance(
            operation_registry,
            OperationRegistry,
        ):
            raise TypeError(
                "operation_registry must be an "
                "OperationRegistry"
            )

        operations = operation_registry.list_operations()

        if not isinstance(operations, tuple):
            raise TypeError(
                "OperationRegistry.list_operations() "
                "must return a tuple"
            )

        with self._lock:
            registered_ids = frozenset(
                self._evaluators
            )

        missing: set[str] = set()

        for operation in operations:
            required_ids = getattr(
                operation,
                "required_evaluator_ids",
                None,
            )

            if not isinstance(required_ids, tuple):
                raise TypeError(
                    "Operation required_evaluator_ids "
                    "must be a tuple"
                )

            normalized_required_ids = tuple(
                _require_identifier(
                    required_id,
                    "required_evaluator_id",
                )
                for required_id in required_ids
            )

            if len(normalized_required_ids) != len(
                set(normalized_required_ids)
            ):
                raise ValueError(
                    "Operation required_evaluator_ids "
                    "cannot contain duplicates"
                )

            missing.update(
                required_id
                for required_id in normalized_required_ids
                if required_id not in registered_ids
            )

        if missing:
            raise MissingEvaluatorsError(
                "Operation registry requires unregistered "
                f"evaluators: {', '.join(sorted(missing))}"
            )
