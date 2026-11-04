from __future__ import annotations

from pathlib import Path

import pytest

from amba_ai.application import (
    create_demo,
    create_desktop,
    create_headless,
    create_test,
)
from amba_ai.application.health import HealthStatus
from amba_ai.application.lifecycle import LifecycleState
from amba_ai.application.settings import ApplicationProfile


def _prepare_project_root(root: Path) -> None:
    (root / "kb").mkdir(parents=True, exist_ok=True)


def test_required_profiles_are_distinct(tmp_path: Path) -> None:
    _prepare_project_root(tmp_path)

    desktop = create_desktop(project_root=tmp_path)
    headless = create_headless(project_root=tmp_path)
    demo = create_demo(project_root=tmp_path)
    test_app = create_test(project_root=tmp_path)

    assert desktop.settings.profile is ApplicationProfile.DESKTOP
    assert desktop.settings.enable_ui is True
    assert desktop.settings.synthetic_only is False

    assert headless.settings.profile is ApplicationProfile.HEADLESS
    assert headless.settings.enable_ui is False
    assert headless.settings.synthetic_only is False

    assert demo.settings.profile is ApplicationProfile.DEMO
    assert demo.settings.enable_ui is False
    assert demo.settings.synthetic_only is True

    assert test_app.settings.profile is ApplicationProfile.TEST
    assert test_app.settings.enable_ui is False
    assert test_app.settings.synthetic_only is True


def test_foundation_providers_are_registered(tmp_path: Path) -> None:
    _prepare_project_root(tmp_path)
    container = create_test(project_root=tmp_path)

    assert container.get("settings") is container.settings
    assert container.get("lifecycle") is container.lifecycle
    assert container.get("health_registry") is container.health


def test_configure_and_overrides_have_deterministic_precedence(
    tmp_path: Path,
) -> None:
    _prepare_project_root(tmp_path)

    def configure(providers, settings) -> None:
        providers.register_instance("value", "configured")
        providers.register(
            "derived",
            lambda registry: f"{registry.get('value')}-derived",
        )

    container = create_test(
        project_root=tmp_path,
        configure=configure,
        provider_overrides={"value": "overridden"},
    )

    assert container.get("value") == "overridden"
    assert container.get("derived") == "overridden-derived"


def test_lifecycle_is_idempotent(tmp_path: Path) -> None:
    _prepare_project_root(tmp_path)
    container = create_test(project_root=tmp_path)

    container.start()
    container.start()

    assert container.lifecycle.state is LifecycleState.RUNNING
    assert container.check_health().status is HealthStatus.HEALTHY

    container.stop()
    container.stop()

    assert container.lifecycle.state is LifecycleState.STOPPED

def test_lifecycle_startup_failure_closes_providers(
    tmp_path: Path,
) -> None:
    (tmp_path / "kb").mkdir()

    application = create_test(
        project_root=tmp_path,
    )

    def fail_startup() -> None:
        raise RuntimeError(
            "synthetic startup failure"
        )

    application.lifecycle.register(
        "synthetic-failure",
        startup=fail_startup,
    )

    with pytest.raises(
        RuntimeError,
        match="synthetic startup failure",
    ):
        application.start()

    assert application.started is False
    assert (
        application.lifecycle.state
        is LifecycleState.STOPPED
    )
    assert application.providers.closed is True

def test_start_prepares_database_parent(tmp_path: Path) -> None:
    _prepare_project_root(tmp_path)
    container = create_test(project_root=tmp_path)
    database_parent = container.settings.database_path.parent

    assert database_parent.exists() is False

    container.start()

    try:
        assert database_parent.is_dir()

        database_check = next(
            check
            for check in container.check_health().checks
            if check.name == "database-parent"
        )
        assert database_check.status is HealthStatus.HEALTHY
    finally:
        container.stop()


def test_context_manager_starts_and_stops(tmp_path: Path) -> None:
    _prepare_project_root(tmp_path)
    container = create_test(project_root=tmp_path)

    with container as running:
        assert running is container
        assert container.lifecycle.state is LifecycleState.RUNNING

    assert container.lifecycle.state is LifecycleState.STOPPED


def test_strict_health_failure_rolls_back_startup(tmp_path: Path) -> None:
    container = create_test(project_root=tmp_path)

    with pytest.raises(RuntimeError, match="application health is unhealthy"):
        container.start()

    assert container.lifecycle.state is LifecycleState.STOPPED


def test_invalid_configuration_inputs_are_rejected(tmp_path: Path) -> None:
    _prepare_project_root(tmp_path)

    with pytest.raises(TypeError, match="configure must be callable"):
        create_test(
            project_root=tmp_path,
            configure=object(),  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="provider_overrides must be a mapping"):
        create_test(
            project_root=tmp_path,
            provider_overrides=[],  # type: ignore[arg-type]
        )


def test_get_validates_provider_name(tmp_path: Path) -> None:
    _prepare_project_root(tmp_path)
    container = create_test(project_root=tmp_path)

    with pytest.raises(TypeError, match="name must be a string"):
        container.get(1)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="name must not be empty"):
        container.get(" ")
