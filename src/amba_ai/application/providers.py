from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import threading
from typing import TypeVar, cast


T = TypeVar("T")
ProviderFactory = Callable[["ProviderRegistry"], object]


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    name: str
    factory: ProviderFactory
    singleton: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("provider name must be a string")

        normalized_name = self.name.strip()
        if not normalized_name:
            raise ValueError("provider name must not be empty")

        if not callable(self.factory):
            raise TypeError("provider factory must be callable")

        if type(self.singleton) is not bool:
            raise TypeError("provider singleton must be a strict Boolean")

        object.__setattr__(self, "name", normalized_name)


class ProviderRegistry(AbstractContextManager["ProviderRegistry"]):
    def __init__(self) -> None:
        self._definitions: dict[str, ProviderDefinition] = {}
        self._instances: dict[str, object] = {}
        self._resolution_order: list[str] = []
        self._resolving: dict[str, int] = {}
        self._local = threading.local()
        self._condition = threading.Condition(threading.RLock())
        self._closed = False
        self._closing = False

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    def register(
        self,
        name: str,
        factory: ProviderFactory,
        *,
        singleton: bool = True,
        replace: bool = False,
    ) -> None:
        definition = ProviderDefinition(name, factory, singleton)

        if type(replace) is not bool:
            raise TypeError("replace must be a strict Boolean")

        with self._condition:
            self._require_open()

            if definition.name in self._resolving:
                raise RuntimeError(
                    f"cannot replace resolving provider: {definition.name}"
                )

            if definition.name in self._instances:
                raise RuntimeError(
                    f"cannot replace resolved provider: {definition.name}"
                )

            if definition.name in self._definitions and not replace:
                raise ValueError(
                    f"provider already registered: {definition.name}"
                )

            self._definitions[definition.name] = definition

    def register_instance(
        self,
        name: str,
        instance: object,
        *,
        replace: bool = False,
    ) -> None:
        normalized = self._normalize_name(name)

        if instance is None:
            raise TypeError("provider instance must not be None")

        self.register(
            normalized,
            lambda _registry, value=instance: value,
            singleton=True,
            replace=replace,
        )

    def get(
        self,
        name: str,
        expected_type: type[T] | None = None,
    ) -> T:
        normalized = self._normalize_name(name)

        if expected_type is not None and not isinstance(expected_type, type):
            raise TypeError("expected_type must be a type or None")

        while True:
            with self._condition:
                self._require_open()

                existing = self._instances.get(normalized)
                if existing is not None:
                    return self._validate_type(
                        normalized,
                        existing,
                        expected_type,
                    )

                definition = self._definitions.get(normalized)
                if definition is None:
                    raise KeyError(
                        f"provider not registered: {normalized}"
                    )

                stack = self._resolution_stack()
                if normalized in stack:
                    start = stack.index(normalized)
                    chain = " -> ".join(
                        (*stack[start:], normalized)
                    )
                    raise RuntimeError(
                        f"circular provider dependency: {chain}"
                    )

                owner = self._resolving.get(normalized)
                current_thread = threading.get_ident()

                if owner is not None:
                    if owner == current_thread:
                        chain = " -> ".join((*stack, normalized))
                        raise RuntimeError(
                            f"circular provider dependency: {chain}"
                        )

                    self._condition.wait_for(
                        lambda: (
                            normalized not in self._resolving
                            or self._closed
                            or self._closing
                        )
                    )
                    continue

                self._resolving[normalized] = current_thread
                stack.append(normalized)

            try:
                value = definition.factory(self)
                if value is None:
                    raise RuntimeError(
                        f"provider returned None: {normalized}"
                    )
            except BaseException:
                with self._condition:
                    self._finish_resolution(normalized)
                raise

            with self._condition:
                self._finish_resolution(normalized)
                self._require_open()

                if definition.singleton:
                    prior = self._instances.get(normalized)
                    if prior is None:
                        self._instances[normalized] = value
                        self._resolution_order.append(normalized)
                    else:
                        value = prior

                return self._validate_type(
                    normalized,
                    value,
                    expected_type,
                )

    def contains(self, name: str) -> bool:
        normalized = self._normalize_name(name)
        with self._condition:
            return normalized in self._definitions

    def is_resolved(self, name: str) -> bool:
        normalized = self._normalize_name(name)
        with self._condition:
            return normalized in self._instances

    def names(self) -> tuple[str, ...]:
        with self._condition:
            return tuple(sorted(self._definitions))

    def close(self) -> None:
        if self._resolution_stack():
            raise RuntimeError(
                "provider registry cannot be closed while resolving a provider"
            )

        with self._condition:
            if self._closed:
                return

            if self._closing:
                self._condition.wait_for(lambda: self._closed)
                return

            self._closing = True
            self._condition.wait_for(lambda: not self._resolving)

            instances = tuple(
                (
                    name,
                    self._instances[name],
                )
                for name in reversed(self._resolution_order)
                if name in self._instances
            )

            self._instances.clear()
            self._resolution_order.clear()
            self._definitions.clear()

        errors: list[tuple[str, BaseException]] = []

        for name, instance in instances:
            close = getattr(instance, "close", None)
            if not callable(close):
                continue

            try:
                close()
            except BaseException as error:
                errors.append((name, error))

        with self._condition:
            self._closed = True
            self._closing = False
            self._condition.notify_all()

        if errors:
            names = ", ".join(name for name, _error in errors)
            failure = RuntimeError(
                f"{len(errors)} provider cleanup operation(s) failed: {names}"
            )
            for name, error in errors[1:]:
                failure.add_note(
                    f"Additional provider cleanup failure for {name}: "
                    f"{type(error).__name__}"
                )
            raise failure from errors[0][1]

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        try:
            self.close()
        except BaseException as cleanup_error:
            if exc is None:
                raise
            exc.add_note(
                "Provider cleanup also failed: "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
        return False

    def _finish_resolution(self, name: str) -> None:
        stack = self._resolution_stack()
        if stack and stack[-1] == name:
            stack.pop()
        elif name in stack:
            stack.remove(name)

        self._resolving.pop(name, None)
        self._condition.notify_all()

    def _resolution_stack(self) -> list[str]:
        stack = getattr(self._local, "resolution_stack", None)
        if stack is None:
            stack = []
            self._local.resolution_stack = stack
        return cast(list[str], stack)

    def _require_open(self) -> None:
        if self._closed or self._closing:
            raise RuntimeError("provider registry is closed")

    @staticmethod
    def _validate_type(
        name: str,
        value: object,
        expected_type: type[T] | None,
    ) -> T:
        if expected_type is not None and not isinstance(
            value,
            expected_type,
        ):
            raise TypeError(
                f"provider {name} is not a {expected_type.__name__}"
            )
        return cast(T, value)

    @staticmethod
    def _normalize_name(name: object) -> str:
        if not isinstance(name, str):
            raise TypeError("provider name must be a string")

        normalized = name.strip()
        if not normalized:
            raise ValueError("provider name must not be empty")

        return normalized
