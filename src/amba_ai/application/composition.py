from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from amba_ai.application.health import (
    ApplicationHealth,
    HealthCheckResult,
    HealthRegistry,
    HealthStatus,
)
from amba_ai.application.lifecycle import (
    ApplicationLifecycle,
    LifecycleState,
)
from amba_ai.application.providers import (
    ProviderFactory,
    ProviderRegistry,
)
from amba_ai.application.settings import (
    ApplicationProfile,
    ApplicationSettings,
    default_settings,
)


ProviderOverrides = Mapping[str, ProviderFactory | object]
ProviderConfigurer = Callable[[ProviderRegistry, ApplicationSettings], None]


@dataclass(slots=True)
class ApplicationContainer:
    settings: ApplicationSettings
    providers: ProviderRegistry
    lifecycle: ApplicationLifecycle
    health: HealthRegistry

    def __post_init__(self) -> None:
        if not isinstance(self.settings, ApplicationSettings):
            raise TypeError("settings must be an ApplicationSettings")
        if not isinstance(self.providers, ProviderRegistry):
            raise TypeError("providers must be a ProviderRegistry")
        if not isinstance(self.lifecycle, ApplicationLifecycle):
            raise TypeError("lifecycle must be an ApplicationLifecycle")
        if not isinstance(self.health, HealthRegistry):
            raise TypeError("health must be a HealthRegistry")

    @property
    def started(self) -> bool:
        return self.lifecycle.state is LifecycleState.RUNNING

    def start(self) -> ApplicationContainer:
        if self.started:
            return self

        try:
            self.lifecycle.start()

            if self.settings.strict_governance:
                self.check_health().require_healthy()

        except BaseException as startup_error:
            cleanup_errors: list[BaseException] = []

            if self.lifecycle.state in {
                LifecycleState.RUNNING,
                LifecycleState.FAILED,
            }:
                try:
                    self.lifecycle.stop()
                except BaseException as error:
                    cleanup_errors.append(error)

            try:
                self.providers.close()
            except BaseException as error:
                cleanup_errors.append(error)

            for cleanup_error in cleanup_errors:
                startup_error.add_note(
                    "Application startup cleanup also failed: "
                    f"{type(cleanup_error).__name__}: "
                    f"{cleanup_error}"
                )

            raise

        return self

    def stop(self) -> None:
        lifecycle_error: BaseException | None = None
        provider_error: BaseException | None = None

        try:
            self.lifecycle.stop()
        except BaseException as error:
            lifecycle_error = error

        try:
            self.providers.close()
        except BaseException as error:
            provider_error = error

        if lifecycle_error is not None:
            if provider_error is not None:
                lifecycle_error.add_note(
                    "Provider cleanup also failed: "
                    f"{type(provider_error).__name__}: {provider_error}"
                )
            raise lifecycle_error

        if provider_error is not None:
            raise provider_error

    def get(
        self,
        name: str,
        expected_type: type[Any] | None = None,
    ) -> Any:
        if not isinstance(name, str):
            raise TypeError("name must be a string")

        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("name must not be empty")

        if expected_type is not None and not isinstance(expected_type, type):
            raise TypeError("expected_type must be a type or None")

        return self.providers.get(normalized_name, expected_type)

    def check_health(self) -> ApplicationHealth:
        result = self.health.evaluate()
        if not isinstance(result, ApplicationHealth):
            raise TypeError(
                "Health registry returned an invalid application-health result"
            )
        return result

    def __enter__(self) -> ApplicationContainer:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        try:
            self.stop()
        except BaseException as shutdown_error:
            if exc is None:
                raise
            exc.add_note(
                "Application shutdown also failed: "
                f"{type(shutdown_error).__name__}: {shutdown_error}"
            )
        return False


def _prepare_runtime_directories(settings: ApplicationSettings) -> None:
    database_parent = settings.database_path.parent

    try:
        database_parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise RuntimeError(
            "Application database directory could not be prepared"
        ) from error

    if not database_parent.is_dir():
        raise RuntimeError(
            "Application database parent is not a directory"
        )


def _register_foundation(
    providers: ProviderRegistry,
    lifecycle: ApplicationLifecycle,
    health: HealthRegistry,
    settings: ApplicationSettings,
) -> None:
    providers.register_instance("settings", settings)
    providers.register_instance("lifecycle", lifecycle)
    providers.register_instance("health_registry", health)


def _apply_provider_overrides(
    providers: ProviderRegistry,
    overrides: ProviderOverrides | None,
) -> None:
    if overrides is None:
        return
    if not isinstance(overrides, Mapping):
        raise TypeError("provider_overrides must be a mapping or None")

    for raw_name, value in overrides.items():
        if not isinstance(raw_name, str):
            raise TypeError("Provider override names must be strings")

        name = raw_name.strip()
        if not name:
            raise ValueError("Provider override names must not be empty")

        if callable(value):
            providers.register(name, value, replace=True)
        else:
            providers.register_instance(name, value, replace=True)


def _register_health_checks(
    health: HealthRegistry,
    lifecycle: ApplicationLifecycle,
    settings: ApplicationSettings,
) -> None:
    health.register(
        "lifecycle",
        lambda: HealthCheckResult(
            name="lifecycle",
            status=(
                HealthStatus.HEALTHY
                if lifecycle.state is LifecycleState.RUNNING
                else HealthStatus.UNHEALTHY
            ),
            message=f"lifecycle={lifecycle.state.value}",
        ),
    )

    def check_knowledge_base() -> HealthCheckResult:
        if settings.knowledge_base_root.is_dir():
            return HealthCheckResult(
                name="knowledge-base-root",
                status=HealthStatus.HEALTHY,
                message="knowledge base root is available",
            )

        return HealthCheckResult(
            name="knowledge-base-root",
            status=(
                HealthStatus.UNHEALTHY
                if settings.verify_knowledge_base
                else HealthStatus.DEGRADED
            ),
            message="knowledge base root is unavailable",
        )

    health.register("knowledge-base-root", check_knowledge_base)

    def check_database_parent() -> HealthCheckResult:
        database_parent = settings.database_path.parent

        if not database_parent.exists():
            return HealthCheckResult(
                name="database-parent",
                status=HealthStatus.UNHEALTHY,
                message="database parent directory does not exist",
            )

        if not database_parent.is_dir():
            return HealthCheckResult(
                name="database-parent",
                status=HealthStatus.UNHEALTHY,
                message="database parent path is not a directory",
            )

        return HealthCheckResult(
            name="database-parent",
            status=HealthStatus.HEALTHY,
            message="database parent directory is available",
        )

    health.register("database-parent", check_database_parent)


def _create_application(
    profile: ApplicationProfile,
    *,
    project_root: Path | str = Path("."),
    settings_overrides: Mapping[str, object] | None = None,
    provider_overrides: ProviderOverrides | None = None,
    configure: ProviderConfigurer | None = None,
) -> ApplicationContainer:
    if not isinstance(profile, ApplicationProfile):
        raise TypeError("profile must be an ApplicationProfile")
    if configure is not None and not callable(configure):
        raise TypeError("configure must be callable or None")

    settings = default_settings(
        profile,
        project_root=project_root,
        overrides=settings_overrides,
    )
    providers = ProviderRegistry()
    lifecycle = ApplicationLifecycle()
    health = HealthRegistry()

    try:
        _register_foundation(providers, lifecycle, health, settings)

        if configure is not None:
            configure(providers, settings)

        _apply_provider_overrides(providers, provider_overrides)

        lifecycle.register(
            "runtime-directories",
            startup=lambda: _prepare_runtime_directories(settings),
        )

        _register_health_checks(health, lifecycle, settings)

        return ApplicationContainer(
            settings=settings,
            providers=providers,
            lifecycle=lifecycle,
            health=health,
        )
    except BaseException:
        providers.close()
        raise


def create_desktop(
    *,
    project_root: Path | str = Path("."),
    settings_overrides: Mapping[str, object] | None = None,
    provider_overrides: ProviderOverrides | None = None,
    configure: ProviderConfigurer | None = None,
) -> ApplicationContainer:
    return _create_application(
        ApplicationProfile.DESKTOP,
        project_root=project_root,
        settings_overrides=settings_overrides,
        provider_overrides=provider_overrides,
        configure=configure,
    )


def create_headless(
    *,
    project_root: Path | str = Path("."),
    settings_overrides: Mapping[str, object] | None = None,
    provider_overrides: ProviderOverrides | None = None,
    configure: ProviderConfigurer | None = None,
) -> ApplicationContainer:
    return _create_application(
        ApplicationProfile.HEADLESS,
        project_root=project_root,
        settings_overrides=settings_overrides,
        provider_overrides=provider_overrides,
        configure=configure,
    )


def create_demo(
    *,
    project_root: Path | str = Path("."),
    settings_overrides: Mapping[str, object] | None = None,
    provider_overrides: ProviderOverrides | None = None,
    configure: ProviderConfigurer | None = None,
) -> ApplicationContainer:
    return _create_application(
        ApplicationProfile.DEMO,
        project_root=project_root,
        settings_overrides=settings_overrides,
        provider_overrides=provider_overrides,
        configure=configure,
    )


def create_test(
    *,
    project_root: Path | str = Path("."),
    settings_overrides: Mapping[str, object] | None = None,
    provider_overrides: ProviderOverrides | None = None,
    configure: ProviderConfigurer | None = None,
) -> ApplicationContainer:
    return _create_application(
        ApplicationProfile.TEST,
        project_root=project_root,
        settings_overrides=settings_overrides,
        provider_overrides=provider_overrides,
        configure=configure,
    )
