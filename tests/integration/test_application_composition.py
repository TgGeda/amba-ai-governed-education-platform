from __future__ import annotations

from types import SimpleNamespace

from amba_ai.application.bootstrap import build_application_services
from amba_ai.application.providers import ProviderRegistry
from amba_ai.application.service_container import ApplicationServices


def test_application_services_preserve_single_instance_graph() -> None:
    registry = ProviderRegistry()
    names = (
        "database", "model_service", "memory_service", "context_tracker",
        "runtime_governance", "job_governance_coordinator", "rag_engine",
        "governance_service", "approval_service", "execution_service",
        "distribution_service", "y3172_trace_coordinator", "audit_service",
    )
    values = {name: object() for name in names}
    corpus = SimpleNamespace(
        rag_engine=values["rag_engine"],
        runtime_governance=values["runtime_governance"],
    )
    job = SimpleNamespace(
        db=values["database"],
        runtime_governance=values["runtime_governance"],
        governance_coordinator=values["job_governance_coordinator"],
        rag=values["rag_engine"],
        memory=values["memory_service"],
        context_tracker=values["context_tracker"],
    )
    governed_ingestion = SimpleNamespace(
        db=values["database"],
        rag_engine=values["rag_engine"],
        runtime_governance=values["runtime_governance"],
    )
    governed_retrieval = SimpleNamespace(
        rag_engine=values["rag_engine"],
        runtime_governance=values["runtime_governance"],
    )
    grounded_answer = SimpleNamespace(
        model_service=values["model_service"],
    )
    governed_result_delivery = object()
    job.governed_ingestion = governed_ingestion
    job.governed_retrieval = governed_retrieval
    job.grounded_answer = grounded_answer
    job.result_delivery = governed_result_delivery
    values["governed_result_delivery"] = governed_result_delivery
    governance_review = SimpleNamespace(
        runtime_governance=values["runtime_governance"],
        rag_engine=values["rag_engine"],
        corpus_builder=corpus,
    )
    values["governance_review_service"] = governance_review
    document_lifecycle = SimpleNamespace(
        db=values["database"],
        runtime_governance=values["runtime_governance"],
        rag_engine=values["rag_engine"],
    )
    values["document_lifecycle_service"] = document_lifecycle
    job.document_lifecycle = document_lifecycle
    values["corpus_service"] = corpus
    values["governed_ingestion_service"] = governed_ingestion
    values["governed_retrieval_service"] = governed_retrieval
    values["grounded_answer_service"] = grounded_answer
    values["job_service"] = job
    for name,value in values.items(): registry.register_instance(name,value)
    services=build_application_services(registry)
    assert isinstance(services,ApplicationServices)
    assert services.job_service is job
    assert services.job_service.runtime_governance is services.runtime_governance
    assert services.job_service.governance_coordinator is services.governance_coordinator
    assert services.job_service.rag is services.rag_engine
    assert services.corpus_service.rag_engine is services.rag_engine


def test_main_window_uses_injected_application_services() -> None:
    from pathlib import Path
    source=Path("src/amba_ai/ui/main_window.py").read_text(encoding="utf-8")
    assert "self.services = services" in source
    assert "self.job_service = services.job_service" in source
    assert "self.db = Database()" not in source
    assert "JobService(self.db)" not in source
    assert "self.context_tracker = self.services.context_tracker" in source
    assert "self.memory_manager = self.services.memory_service" in source
