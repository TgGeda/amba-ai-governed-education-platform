from __future__ import annotations

import pytest

from amba_ai.application.lifecycle import (
    ApplicationLifecycle,
    LifecycleRegistration,
    LifecycleState,
)


def test_registration_validates_and_preserves_order() -> None:
    lifecycle = ApplicationLifecycle()
    lifecycle.register(" first ")
    lifecycle.register("second")

    assert lifecycle.names() == ("first", "second")

    with pytest.raises(ValueError, match="already exists"):
        lifecycle.register("first")


def test_startup_and_shutdown_order() -> None:
    events: list[str] = []
    lifecycle = ApplicationLifecycle()
    lifecycle.register(
        "first",
        startup=lambda: events.append("start:first"),
        shutdown=lambda: events.append("stop:first"),
    )
    lifecycle.register(
        "second",
        startup=lambda: events.append("start:second"),
        shutdown=lambda: events.append("stop:second"),
    )

    lifecycle.start()
    assert lifecycle.state is LifecycleState.RUNNING
    assert lifecycle.running is True

    lifecycle.stop()
    assert lifecycle.state is LifecycleState.STOPPED
    assert lifecycle.running is False
    assert events == [
        "start:first",
        "start:second",
        "stop:second",
        "stop:first",
    ]


def test_start_and_stop_are_idempotent_in_terminal_states() -> None:
    lifecycle = ApplicationLifecycle()
    lifecycle.start()
    lifecycle.start()
    lifecycle.stop()
    lifecycle.stop()
    assert lifecycle.state is LifecycleState.STOPPED


def test_stop_before_start_is_supported() -> None:
    lifecycle = ApplicationLifecycle()
    lifecycle.stop()
    assert lifecycle.state is LifecycleState.STOPPED

    with pytest.raises(RuntimeError, match="cannot start"):
        lifecycle.start()


def test_startup_failure_rolls_back_started_hooks() -> None:
    events: list[str] = []
    lifecycle = ApplicationLifecycle()
    lifecycle.register(
        "first",
        startup=lambda: events.append("start:first"),
        shutdown=lambda: events.append("stop:first"),
    )

    def fail() -> None:
        raise RuntimeError("startup failed")

    lifecycle.register("second", startup=fail)

    with pytest.raises(RuntimeError, match="startup failed"):
        lifecycle.start()

    assert lifecycle.state is LifecycleState.FAILED
    assert events == ["start:first", "stop:first"]

    lifecycle.stop()
    assert lifecycle.state is LifecycleState.STOPPED


def test_shutdown_runs_all_hooks_and_reports_failures() -> None:
    events: list[str] = []
    lifecycle = ApplicationLifecycle()

    def fail_second() -> None:
        events.append("stop:second")
        raise RuntimeError("second failed")

    lifecycle.register(
        "first",
        shutdown=lambda: events.append("stop:first"),
    )
    lifecycle.register("second", shutdown=fail_second)
    lifecycle.start()

    with pytest.raises(RuntimeError, match="1 lifecycle shutdown"):
        lifecycle.stop()

    assert lifecycle.state is LifecycleState.FAILED
    assert events == ["stop:second", "stop:first"]


def test_registration_is_closed_after_startup() -> None:
    lifecycle = ApplicationLifecycle()
    lifecycle.start()

    with pytest.raises(RuntimeError, match="before startup"):
        lifecycle.register("late")


def test_registration_model_rejects_invalid_hooks() -> None:
    with pytest.raises(TypeError, match="name must be a string"):
        LifecycleRegistration(1)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="startup hook"):
        LifecycleRegistration("test", startup=object())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="shutdown hook"):
        LifecycleRegistration("test", shutdown=object())  # type: ignore[arg-type]
