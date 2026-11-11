from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from amba_ai.exceptions import RAGError
from amba_ai.governance.learning_operations import canonical_learning_operation, runtime_learning_operation

@dataclass(frozen=True, slots=True)
class GovernedRetrieval:
    document_id: int
    operation: str
    hits: tuple[Any, ...]
    retrieved_chunk_ids: tuple[int, ...]
    excluded_chunk_ids: tuple[int, ...]
    receipt_id: str
    corpus_revision_id: str | None = None

class GovernedRetrievalService:
    def __init__(self, *, rag_engine: Any, runtime_governance: Any, corpus_builder: Any) -> None:
        self.rag_engine=rag_engine; self.runtime_governance=runtime_governance; self.corpus_builder=corpus_builder
    @staticmethod
    def _chunk_id(hit: Any) -> int | None:
        value=hit.get("chunk_id") if isinstance(hit,dict) else getattr(hit,"chunk_id",None)
        return int(value) if value is not None else None
    def retrieve(self, question: str, *, document_id: int, operation: str="learning.tutor.retrieve", top_k: int=5) -> GovernedRetrieval:
        clean=str(question).strip()
        if not clean: raise ValueError("Retrieval question must be non-empty.")
        if not isinstance(document_id,int) or document_id<=0: raise ValueError("Governed retrieval requires a positive document_id.")
        canonical=canonical_learning_operation(operation)
        if canonical not in {"learning.tutor.retrieve","learning.tutor.answer"}: raise ValueError(f"Unsupported retrieval operation: {canonical}")
        runtime=runtime_learning_operation(canonical)
        self.runtime_governance.authorize_generation(document_id,runtime)
        corpus=self.corpus_builder.build(operation=canonical)
        corpus.require_aligned()
        raw=list(self.rag_engine.search(clean,top_k=max(top_k*3,top_k)))
        scoped=[h for h in raw if int(getattr(h,"document_id",getattr(h,"doc_id",document_id)))==document_id]
        governed=self.runtime_governance.filter_retrieval(document_id,runtime,scoped)
        hits=tuple(governed.hits[:top_k])
        returned=tuple(x for x in (self._chunk_id(h) for h in hits) if x is not None)
        if not set(returned).issubset(corpus.eligible_chunk_ids): raise RAGError("Governed retrieval returned a chunk outside the corpus allowlist.")
        excluded=tuple(sorted(set(corpus.excluded_chunk_ids).union(governed.excluded_chunk_ids)))
        receipt=self.runtime_governance.repository.receipt("governed_retrieval_completed",{"document_id":document_id,"operation":canonical,"retrieved_chunk_ids":list(returned),"excluded_chunk_ids":list(excluded),"corpus_revision_id":corpus.revision.revision_id},document_id,canonical)
        if not receipt: raise RAGError("Governed retrieval receipt was not produced.")
        return GovernedRetrieval(document_id,canonical,hits,returned,excluded,receipt,corpus.revision.revision_id)
