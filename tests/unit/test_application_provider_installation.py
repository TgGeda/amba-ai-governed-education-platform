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
from amba_ai.rag.policy_query import PolicyQueryAdapter
from amba_ai.services.policy_kb_service import PolicyKBService
from amba_ai.standards.ml_intent import MLIntent
from amba_ai.standards.y3172_registry import Y3172Registry
from amba_ai.standards.y3172_trace_coordinator import (
    Y3172TraceCoordinator,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_ROOT = (
    PROJECT_ROOT
    / "src"
    / "amba_ai"
    / "db"
    / "migrations"
)
CONFIGURATION_ROOT = PROJECT_ROOT / "config"
KNOWLEDGE_BASE_ROOT = PROJECT_ROOT / "kb"

Y3172_KB_PROVIDER_NAMES = (
    "y3172_registry",
    "ml_intent",
    "y3172_trace_coordinator",
    "policy_query_adapter",
    "policy_kb_service",
)

class PolicySearchEngineStub:
    def __init__(self) -> None:
        self.calls: list[
            tuple[str, int, float]
        ] = []

    def search(
        self,
        query: str,
        top_k: int = 10,
        min_similarity: float = 0.40,
    ) -> list:
        self.calls.append(
            (
                query,
                top_k,
                min_similarity,
            )
        )

        return []

def _registry(
    tmp_path: Path,
) -> tuple[
    ProviderRegistry,
    ApplicationSettings,
]:
    settings = default_settings(
        ApplicationProfile.TEST,
        project_root=tmp_path,
        overrides={
            "migrations_root": MIGRATIONS_ROOT,
            "configuration_root": CONFIGURATION_ROOT,
            "knowledge_base_root": KNOWLEDGE_BASE_ROOT,
            "verify_knowledge_base": False,
        },
    )

    providers = ProviderRegistry()

    providers.register_instance(
        "settings",
        settings,
    )

    from amba_ai.application.health import HealthRegistry
    from amba_ai.application.lifecycle import (
        ApplicationLifecycle,
    )

    providers.register_instance(
        "lifecycle",
        ApplicationLifecycle(),
    )

    providers.register_instance(
        "health_registry",
        HealthRegistry(),
    )

    return providers, settings


def test_installer_registers_complete_provider_graph(
    tmp_path: Path,
) -> None:
    providers, settings = _registry(tmp_path)

    try:
        install_application_providers(
            providers,
            settings,
        )

        assert set(
            REQUIRED_PROVIDER_NAMES
        ).issubset(
            providers.names()
        )
    finally:
        providers.close()


def test_expensive_application_providers_remain_lazy(
    tmp_path: Path,
) -> None:
    providers, settings = _registry(tmp_path)

    try:
        install_application_providers(
            providers,
            settings,
        )

        assert all(
            not providers.is_resolved(name)
            for name in LAZY_PROVIDER_NAMES
        )
    finally:
        providers.close()


def test_repositories_use_configured_database_path(
    tmp_path: Path,
) -> None:
    providers, settings = _registry(tmp_path)

    try:
        install_application_providers(
            providers,
            settings,
        )

        for name in (
            "governance_repository",
            "approval_repository",
            "execution_repository",
            "audit_repository",
            "policy_record_repository",
        ):
            repository = providers.get(name)

            assert (
                Path(
                    repository.db_path
                ).resolve()
                == settings.database_path.resolve()
            )
    finally:
        providers.close()


def test_schema_dependent_repository_triggers_migrations(
    tmp_path: Path,
) -> None:
    providers, settings = _registry(tmp_path)

    try:
        install_application_providers(
            providers,
            settings,
        )

        assert (
            not settings.database_path.exists()
        )

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
    providers, settings = _registry(
        tmp_path
    )

    second_providers: ProviderRegistry | None = None

    try:
        install_application_providers(
            providers,
            settings,
        )

        repository = providers.get(
            "policy_record_repository",
            PolicyRecordRepository,
        )

        assert repository.list_all() == ()

        second_providers, second_settings = (
            _registry(tmp_path)
        )

        install_application_providers(
            second_providers,
            second_settings,
        )

        runtime_registry = (
            second_providers.get(
                "policy_record_registry",
                PolicyRecordRegistry,
            )
        )

        assert (
            runtime_registry.list_all()
            == repository.list_all()
        )
    finally:
        if second_providers is not None:
            second_providers.close()

        providers.close()


def test_invalid_installer_arguments_are_rejected(
    tmp_path: Path,
) -> None:
    providers, settings = _registry(
        tmp_path
    )

    try:
        with pytest.raises(
            TypeError,
            match="providers",
        ):
            install_application_providers(
                object(),
                settings,
            )

        with pytest.raises(
            TypeError,
            match="settings",
        ):
            install_application_providers(
                providers,
                object(),
            )
    finally:
        providers.close()


def test_y3172_kb_providers_are_registered(
    tmp_path: Path,
) -> None:
    providers, settings = _registry(
        tmp_path
    )

    try:
        install_application_providers(
            providers,
            settings,
        )

        assert set(
            Y3172_KB_PROVIDER_NAMES
        ).issubset(
            providers.names()
        )

        assert set(
            Y3172_KB_PROVIDER_NAMES
        ).issubset(
            LAZY_PROVIDER_NAMES
        )
    finally:
        providers.close()


def test_y3172_registry_provider_resolves(
    tmp_path: Path,
) -> None:
    providers, settings = _registry(
        tmp_path
    )

    try:
        install_application_providers(
            providers,
            settings,
        )

        registry = providers.get(
            "y3172_registry",
            Y3172Registry,
        )

        assert isinstance(
            registry,
            Y3172Registry,
        )
    finally:
        providers.close()


def test_ml_intent_provider_resolves(
    tmp_path: Path,
) -> None:
    providers, settings = _registry(
        tmp_path
    )

    try:
        install_application_providers(
            providers,
            settings,
        )

        intent = providers.get(
            "ml_intent",
            MLIntent,
        )

        assert isinstance(
            intent,
            MLIntent,
        )
    finally:
        providers.close()


def test_policy_query_adapter_provider_resolves(
    tmp_path: Path,
) -> None:
    providers, settings = _registry(
        tmp_path
    )

    try:
        install_application_providers(
            providers,
            settings,
        )

        adapter = providers.get(
            "policy_query_adapter",
            PolicyQueryAdapter,
        )

        assert isinstance(
            adapter,
            PolicyQueryAdapter,
        )
    finally:
        providers.close()


def test_policy_kb_service_provider_resolves(
    tmp_path: Path,
) -> None:
    providers, settings = _registry(
        tmp_path
    )
    rag_engine = PolicySearchEngineStub()

    try:
        install_application_providers(
            providers,
            settings,
        )

        providers.register_instance(
            "rag_engine",
            rag_engine,
            replace=True,
        )

        service = providers.get(
            "policy_kb_service",
            PolicyKBService,
        )

        adapter = providers.get(
            "policy_query_adapter",
            PolicyQueryAdapter,
        )

        assert isinstance(
            service,
            PolicyKBService,
        )
        assert service.search_engine is rag_engine
        assert service.query_adapter is adapter

        response = service.query(
            "policy evidence"
        )

        assert response.results == ()
        assert rag_engine.calls == [
            (
                "policy evidence",
                10,
                0.40,
            )
        ]
    finally:
        providers.close()


def test_y3172_trace_coordinator_provider_resolves(
    tmp_path: Path,
) -> None:
    providers, settings = _registry(
        tmp_path
    )

    try:
        install_application_providers(
            providers,
            settings,
        )

        coordinator = providers.get(
            "y3172_trace_coordinator",
            Y3172TraceCoordinator,
        )

        assert isinstance(
            coordinator,
            Y3172TraceCoordinator,
        )
    finally:
        providers.close()
