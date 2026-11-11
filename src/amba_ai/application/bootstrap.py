from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from amba_ai.application.composition import ApplicationContainer, create_desktop
from amba_ai.application.provider_installation import install_application_providers
from amba_ai.application.providers import ProviderRegistry
from amba_ai.application.service_container import ApplicationServices


def build_application_services(providers: ProviderRegistry) -> ApplicationServices:
    if not isinstance(providers, ProviderRegistry):
        raise TypeError("providers must be a ProviderRegistry")
    services = ApplicationServices(
        providers=providers,
        database=providers.get("database"),
        model_service=providers.get("model_service"),
        memory_service=providers.get("memory_service"),
        context_tracker=providers.get("context_tracker"),
        runtime_governance=providers.get("runtime_governance"),
        governance_coordinator=providers.get("job_governance_coordinator"),
        rag_engine=providers.get("rag_engine"),
        corpus_service=providers.get("corpus_service"),
        governed_ingestion_service=providers.get("governed_ingestion_service"),
        governed_retrieval_service=providers.get("governed_retrieval_service"),
        grounded_answer_service=providers.get("grounded_answer_service"),
        governed_result_delivery=providers.get("governed_result_delivery"),
        governance_review_service=providers.get("governance_review_service"),
        document_lifecycle_service=providers.get("document_lifecycle_service"),
        job_service=providers.get("job_service"),
        governance_service=providers.get("governance_service"),
        approval_service=providers.get("approval_service"),
        execution_service=providers.get("execution_service"),
        distribution_service=providers.get("distribution_service"),
        trace_coordinator=providers.get("y3172_trace_coordinator"),
        audit_service=providers.get("audit_service"),
    )
    services.require_consistent_graph()
    return services


@dataclass(slots=True, weakref_slot=True)
class ApplicationBootstrap:
    application: ApplicationContainer
    services: ApplicationServices
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        self.application.stop()
        self._closed = True


def create_desktop_services(
    *, project_root: Path,
    settings_overrides: Mapping[str, Any] | None = None,
) -> ApplicationBootstrap:
    application = create_desktop(
        project_root=Path(project_root),
        settings_overrides=dict(settings_overrides or {}),
        configure=install_application_providers,
    )
    services = build_application_services(application.providers)
    return ApplicationBootstrap(application=application, services=services)
