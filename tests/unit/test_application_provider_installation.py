from __future__ import annotations

from pathlib import Path

import pytest

from amba_ai.application.provider_installation import (
    LAZY_PROVIDER_NAMES,
    REQUIRED_PROVIDER_NAMES,
    install_application_providers,
)
from amba_ai.application.providers import ProviderRegistry
from amba_ai.application.settings import (
    ApplicationProfile,
    ApplicationSettings,
    default_settings,
)
from amba_ai.db.policy_record_repository import PolicyRecordRepository
from amba_ai.governance.record_registry import PolicyRecordRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_ROOT = PROJECT_ROOT / "src" / "amba_ai" / "db" / "migrations"
CONFIGURATION_ROOT = PROJECT_ROOT / "config"


def _registry(tmp_path: Path) -> tuple[ProviderRegistry, ApplicationSettings]:
    settings = default_settings(
        ApplicationProfile.TEST,
        project_root=tmp_path,
        overrides={
            "migrations_root": MIGRATIONS_ROOT,
            "configuration_root": CONFIGURATION_ROOT,
            "verify_knowledge_base": False,
        },
    )
    providers = ProviderRegistry()
    providers.register_instance("settings", settings)
    from amba_ai.application.health import HealthRegistry
    from amba_ai.application.lifecycle import ApplicationLifecycle
    providers.register_instance("lifecycle", ApplicationLifecycle())
    providers.register_instance("health_registry", HealthRegistry())
    return providers, settings


def test_installer_registers_complete_provider_graph(tmp_path: Path) -> None:
    providers, settings = _registry(tmp_path)
    try:
        install_application_providers(providers, settings)
        assert set(REQUIRED_PROVIDER_NAMES).issubset(providers.names())
    finally:
        providers.close()


def test_expensive_application_providers_remain_lazy(tmp_path: Path) -> None:
    providers, settings = _registry(tmp_path)
    try:
        install_application_providers(providers, settings)
        assert all(not providers.is_resolved(name) for name in LAZY_PROVIDER_NAMES)
    finally:
        providers.close()


def test_repositories_use_configured_database_path(tmp_path: Path) -> None:
    providers, settings = _registry(tmp_path)
    try:
        install_application_providers(providers, settings)
        for name in (
            "governance_repository",
            "approval_repository",
            "execution_repository",
            "audit_repository",
            "policy_record_repository",
        ):
            repository = providers.get(name)
            assert Path(repository.db_path).resolve() == settings.database_path.resolve()
    finally:
        providers.close()


def test_schema_dependent_repository_triggers_migrations(tmp_path: Path) -> None:
    providers, settings = _registry(tmp_path)
    try:
        install_application_providers(providers, settings)
        assert not settings.database_path.exists()
        repository = providers.get(
            "policy_record_repository",
            PolicyRecordRepository,
        )
        assert repository is not None
        assert settings.database_path.is_file()
    finally:
        providers.close()


def test_policy_registry_is_hydrated_from_authoritative_repository(
    tmp_path: Path,
) -> None:
    providers, settings = _registry(tmp_path)
    second_providers: ProviderRegistry | None = None
    try:
        install_application_providers(providers, settings)
        repository = providers.get(
            "policy_record_repository",
            PolicyRecordRepository,
        )
        assert repository.list_all() == ()

        second_providers, second_settings = _registry(tmp_path)
        install_application_providers(second_providers, second_settings)
        runtime_registry = second_providers.get(
            "policy_record_registry",
            PolicyRecordRegistry,
        )
        assert runtime_registry.list_all() == repository.list_all()
    finally:
        if second_providers is not None:
            second_providers.close()
        providers.close()


def test_invalid_installer_arguments_are_rejected(tmp_path: Path) -> None:
    providers, settings = _registry(tmp_path)
    try:
        with pytest.raises(TypeError, match="providers"):
            install_application_providers(object(), settings)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="settings"):
            install_application_providers(providers, object())  # type: ignore[arg-type]
    finally:
        providers.close()
