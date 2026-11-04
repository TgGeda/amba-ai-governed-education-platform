from __future__ import annotations

import threading
import time

import pytest

from amba_ai.application.providers import (
    ProviderDefinition,
    ProviderRegistry,
)


class Closable:
    def __init__(self, name: str, events: list[str]) -> None:
        self.name = name
        self.events = events

    def close(self) -> None:
        self.events.append(f"close:{self.name}")


def test_definition_validation() -> None:
    with pytest.raises(TypeError, match="name must be a string"):
        ProviderDefinition(1, lambda registry: object())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="factory must be callable"):
        ProviderDefinition("provider", object())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="strict Boolean"):
        ProviderDefinition("provider", lambda registry: object(), 1)  # type: ignore[arg-type]


def test_singletons_are_lazy_and_cached() -> None:
    registry = ProviderRegistry()
    calls = 0

    def factory(_registry: ProviderRegistry) -> object:
        nonlocal calls
        calls += 1
        return object()

    registry.register("value", factory)
    assert registry.is_resolved("value") is False

    first = registry.get("value")
    second = registry.get("value")

    assert first is second
    assert calls == 1
    assert registry.is_resolved("value") is True


def test_transient_provider_is_not_cached_or_closed() -> None:
    registry = ProviderRegistry()
    events: list[str] = []
    registry.register(
        "transient",
        lambda _registry: Closable("transient", events),
        singleton=False,
    )

    assert registry.get("transient") is not registry.get("transient")
    registry.close()
    assert events == []


def test_dependencies_resolve_and_cycles_fail() -> None:
    registry = ProviderRegistry()
    registry.register_instance("base", "value")
    registry.register(
        "derived",
        lambda values: f"{values.get('base')}-derived",
    )
    assert registry.get("derived") == "value-derived"

    cyclic = ProviderRegistry()
    cyclic.register("a", lambda values: values.get("b"))
    cyclic.register("b", lambda values: values.get("a"))
    with pytest.raises(RuntimeError, match="a -> b -> a"):
        cyclic.get("a")


def test_replacement_rules_are_fail_closed() -> None:
    registry = ProviderRegistry()
    registry.register_instance("value", "first")

    with pytest.raises(ValueError, match="already registered"):
        registry.register_instance("value", "second")

    registry.register_instance("value", "second", replace=True)
    assert registry.get("value") == "second"

    with pytest.raises(RuntimeError, match="resolved provider"):
        registry.register_instance("value", "third", replace=True)


def test_expected_type_is_validated() -> None:
    registry = ProviderRegistry()
    registry.register_instance("value", "text")

    assert registry.get("value", str) == "text"
    with pytest.raises(TypeError, match="is not a int"):
        registry.get("value", int)
    with pytest.raises(TypeError, match="expected_type"):
        registry.get("value", object())  # type: ignore[arg-type]


def test_singleton_factory_is_created_once_across_threads() -> None:
    registry = ProviderRegistry()
    calls = 0
    calls_lock = threading.Lock()

    def factory(_registry: ProviderRegistry) -> object:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return object()

    registry.register("value", factory)
    values: list[object] = []

    threads = [
        threading.Thread(target=lambda: values.append(registry.get("value")))
        for _ in range(6)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == 1
    assert len(values) == 6
    assert all(value is values[0] for value in values)


def test_cleanup_is_reverse_resolution_order_and_idempotent() -> None:
    events: list[str] = []
    registry = ProviderRegistry()
    registry.register(
        "first",
        lambda _registry: Closable("first", events),
    )
    registry.register(
        "second",
        lambda _registry: Closable("second", events),
    )

    registry.get("first")
    registry.get("second")
    registry.close()
    registry.close()

    assert events == ["close:second", "close:first"]
    assert registry.closed is True

    with pytest.raises(RuntimeError, match="closed"):
        registry.get("first")


def test_context_manager_preserves_body_exception() -> None:
    events: list[str] = []

    class FailingClose:
        def close(self) -> None:
            events.append("close")
            raise RuntimeError("cleanup failed")

    with pytest.raises(ValueError, match="body failed") as captured:
        with ProviderRegistry() as registry:
            registry.register_instance("resource", FailingClose())
            registry.get("resource")
            raise ValueError("body failed")

    assert events == ["close"]
    assert any("Provider cleanup also failed" in note for note in captured.value.__notes__)


def test_registry_introspection_is_deterministic() -> None:
    registry = ProviderRegistry()
    registry.register_instance("zeta", object())
    registry.register_instance("alpha", object())

    assert registry.names() == ("alpha", "zeta")
    assert registry.contains(" alpha ") is True
    assert registry.contains("missing") is False
