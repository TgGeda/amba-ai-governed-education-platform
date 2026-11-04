from __future__ import annotations

from pathlib import Path
from typing import Any

from amba_ai.application.health import (
    HealthRegistry,
)
from amba_ai.application.lifecycle import (
    ApplicationLifecycle,
)
from amba_ai.application.provider_installation import (
    install_application_providers,
)
from amba_ai.application.providers import (
    ProviderRegistry,
)
from amba_ai.application.settings import (
    ApplicationProfile,
    default_settings,
)
from amba_ai.governance.record_registry import (
    PolicyRecordRegistry,
)
from amba_ai.rag.policy_query import (
    PolicyQueryAdapter,
)
from amba_ai.services.policy_kb_service import (
    PolicyKBService,
)
from amba_ai.standards.ml_intent import (
    MLIntent,
)
from amba_ai.standards.y3172_registry import (
    Y3172Registry,
)
from amba_ai.standards.y3172_trace_coordinator import (
    Y3172TraceCoordinator,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

CONFIGURATION_ROOT = (
    PROJECT_ROOT
    / "config"
)

KNOWLEDGE_BASE_ROOT = (
    PROJECT_ROOT
    / "kb"
)

MIGRATIONS_ROOT = (
    PROJECT_ROOT
    / "src"
    / "amba_ai"
    / "db"
    / "migrations"
)


class RAGEngineStub:
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


def _providers(
    tmp_path: Path,
) -> ProviderRegistry:
    settings = default_settings(
        ApplicationProfile.TEST,
        project_root=tmp_path,
        overrides={
            "configuration_root": (
                CONFIGURATION_ROOT
            ),
            "knowledge_base_root": (
                KNOWLEDGE_BASE_ROOT
            ),
            "migrations_root": (
                MIGRATIONS_ROOT
            ),
            "verify_knowledge_base": False,
        },
    )

    providers = ProviderRegistry()

    providers.register_instance(
        "settings",
        settings,
    )
    providers.register_instance(
        "lifecycle",
        ApplicationLifecycle(),
    )
    providers.register_instance(
        "health_registry",
        HealthRegistry(),
    )

    install_application_providers(
        providers,
        settings,
    )

    return providers


def test_provider_graph_is_fully_lazy(
    tmp_path: Path,
) -> None:
    providers = _providers(
        tmp_path
    )

    try:
        for name in (
            "y3172_registry",
            "ml_intent",
            "y3172_trace_coordinator",
            "policy_query_adapter",
            "policy_kb_service",
        ):
            assert not providers.is_resolved(
                name
            )
    finally:
        providers.close()


def test_y3172_registry_and_intent_do_not_resolve_rag(
    tmp_path: Path,
) -> None:
    providers = _providers(
        tmp_path
    )

    try:
        registry = providers.get(
            "y3172_registry",
            Y3172Registry,
        )
        intent = providers.get(
            "ml_intent",
            MLIntent,
        )

        assert len(registry.list()) == 7
        assert intent.intent_id == (
            "AMBA-GOV-ML-INTENT-V1"
        )

        assert not providers.is_resolved(
            "rag_engine"
        )
        assert not providers.is_resolved(
            "policy_record_registry"
        )
    finally:
        providers.close()


def test_trace_coordinator_reuses_existing_singletons(
    tmp_path: Path,
) -> None:
    providers = _providers(
        tmp_path
    )

    try:
        coordinator = providers.get(
            "y3172_trace_coordinator",
            Y3172TraceCoordinator,
        )

        assert (
            coordinator.registry
            is providers.get(
                "y3172_registry",
                Y3172Registry,
            )
        )
        assert (
            coordinator.identifier_provider
            is providers.get(
                "identifier_provider"
            )
        )
        assert (
            coordinator.clock
            is providers.get(
                "clock"
            )
        )

        assert not providers.is_resolved(
            "rag_engine"
        )
    finally:
        providers.close()


def test_policy_query_adapter_reuses_existing_registry(
    tmp_path: Path,
) -> None:
    providers = _providers(
        tmp_path
    )

    try:
        adapter = providers.get(
            "policy_query_adapter",
            PolicyQueryAdapter,
        )
        policy_registry = providers.get(
            "policy_record_registry",
            PolicyRecordRegistry,
        )

        assert adapter.registry is policy_registry
        assert not providers.is_resolved(
            "rag_engine"
        )
    finally:
        providers.close()


def test_policy_kb_service_reuses_overridden_rag_engine(
    tmp_path: Path,
) -> None:
    providers = _providers(
        tmp_path
    )
    rag_engine = RAGEngineStub()

    try:
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

def test_policy_kb_service_accepts_search_protocol_override(
    tmp_path: Path,
) -> None:
    providers = _providers(
        tmp_path
    )
    rag_engine = RAGEngineStub()

    try:
        providers.register_instance(
            "rag_engine",
            rag_engine,
            replace=True,
        )

        service = providers.get(
            "policy_kb_service",
            PolicyKBService,
        )

        assert service.search_engine is rag_engine
        assert providers.get(
            "rag_engine"
        ) is rag_engine
    finally:
        providers.close()

def test_provider_singletons_are_cached(
    tmp_path: Path,
) -> None:
    providers = _providers(
        tmp_path
    )
    rag_engine = RAGEngineStub()

    try:
        providers.register_instance(
            "rag_engine",
            rag_engine,
            replace=True,
        )

        for name in (
            "y3172_registry",
            "ml_intent",
            "y3172_trace_coordinator",
            "policy_query_adapter",
            "policy_kb_service",
        ):
            first = providers.get(name)
            second = providers.get(name)

            assert first is second
    finally:
        providers.close()


def test_policy_kb_resolution_uses_one_dependency_chain(
    tmp_path: Path,
) -> None:
    providers = _providers(
        tmp_path
    )
    rag_engine = RAGEngineStub()

    try:
        providers.register_instance(
            "rag_engine",
            rag_engine,
            replace=True,
        )

        assert not providers.is_resolved(
            "policy_kb_service"
        )
        assert not providers.is_resolved(
            "policy_query_adapter"
        )

        service = providers.get(
            "policy_kb_service",
            PolicyKBService,
        )

        assert service is not None

        assert providers.is_resolved(
            "policy_kb_service"
        )
        assert providers.is_resolved(
            "policy_query_adapter"
        )
        assert providers.is_resolved(
            "policy_record_registry"
        )
        assert providers.is_resolved(
            "rag_engine"
        )

        assert not providers.is_resolved(
            "y3172_registry"
        )
        assert not providers.is_resolved(
            "ml_intent"
        )
        assert not providers.is_resolved(
            "y3172_trace_coordinator"
        )
    finally:
        providers.close()
