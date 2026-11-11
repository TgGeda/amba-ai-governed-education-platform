from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amba_ai.application.providers import ProviderRegistry


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    providers: ProviderRegistry
    database: Any
    model_service: Any
    memory_service: Any
    context_tracker: Any
    runtime_governance: Any
    governance_coordinator: Any
    rag_engine: Any
    corpus_service: Any
    governed_ingestion_service: Any
    governed_retrieval_service: Any
    grounded_answer_service: Any
    governed_result_delivery: Any
    governance_review_service: Any
    document_lifecycle_service: Any
    job_service: Any
    governance_service: Any
    approval_service: Any
    execution_service: Any
    distribution_service: Any
    trace_coordinator: Any
    audit_service: Any

    def require_consistent_graph(self) -> None:
        if self.job_service.db is not self.database:
            raise RuntimeError("JobService does not share the application database.")
        if self.job_service.runtime_governance is not self.runtime_governance:
            raise RuntimeError("JobService does not share runtime governance.")
        if self.job_service.governance_coordinator is not self.governance_coordinator:
            raise RuntimeError("JobService does not share the governance coordinator.")
        if self.job_service.rag is not self.rag_engine:
            raise RuntimeError("JobService does not share the RAG engine.")
        if self.job_service.memory is not self.memory_service:
            raise RuntimeError("JobService does not share learning memory.")
        if self.job_service.context_tracker is not self.context_tracker:
            raise RuntimeError("JobService does not share the context tracker.")
        if self.governed_ingestion_service.db is not self.database:
            raise RuntimeError("Governed ingestion does not share the database.")
        if self.governed_ingestion_service.rag_engine is not self.rag_engine:
            raise RuntimeError("Governed ingestion does not share the RAG engine.")
        if self.governed_ingestion_service.runtime_governance is not self.runtime_governance:
            raise RuntimeError("Governed ingestion does not share runtime governance.")
        if self.job_service.governed_ingestion is not self.governed_ingestion_service:
            raise RuntimeError("JobService does not share governed ingestion.")
        if self.governed_retrieval_service.rag_engine is not self.rag_engine:
            raise RuntimeError("Governed retrieval does not share the RAG engine.")
        if self.governed_retrieval_service.runtime_governance is not self.runtime_governance:
            raise RuntimeError("Governed retrieval does not share runtime governance.")
        if self.grounded_answer_service.model_service is not self.model_service:
            raise RuntimeError("Grounded answer does not share ModelService.")
        if self.job_service.governed_retrieval is not self.governed_retrieval_service:
            raise RuntimeError("JobService does not share governed retrieval.")
        if self.job_service.grounded_answer is not self.grounded_answer_service:
            raise RuntimeError("JobService does not share grounded answer generation.")
        if self.governance_review_service.runtime_governance is not self.runtime_governance:
            raise RuntimeError("Review service does not share runtime governance.")
        if self.governance_review_service.rag_engine is not self.rag_engine:
            raise RuntimeError("Review service does not share the RAG engine.")
        if self.document_lifecycle_service.db is not self.database:
            raise RuntimeError("Document lifecycle does not share the database.")
        if self.document_lifecycle_service.runtime_governance is not self.runtime_governance:
            raise RuntimeError("Document lifecycle does not share runtime governance.")
        if self.document_lifecycle_service.rag_engine is not self.rag_engine:
            raise RuntimeError("Document lifecycle does not share the RAG engine.")
        if self.job_service.document_lifecycle is not self.document_lifecycle_service:
            raise RuntimeError("JobService does not share document lifecycle.")
        if self.job_service.result_delivery is not self.governed_result_delivery:
            raise RuntimeError("JobService does not share governed result delivery.")
        if self.corpus_service.rag_engine is not self.rag_engine:
            raise RuntimeError("Corpus service does not share the RAG engine.")
        if self.corpus_service.runtime_governance is not self.runtime_governance:
            raise RuntimeError("Corpus service does not share runtime governance.")
