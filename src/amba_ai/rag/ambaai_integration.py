from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from amba_ai.logger import logger
from amba_ai.models.schemas import AnswerResult
from amba_ai.rag.chunking import SemanticChunker
from amba_ai.rag.context import ContextAssembler
from amba_ai.rag.corpus_revision import GovernedCorpusBuilder
from amba_ai.rag.hybrid import HybridRetriever, InMemoryBM25
from amba_ai.rag.models import Chunk, RetrievalQuery
from amba_ai.rag.pipeline import ProductionRAGPipeline
from amba_ai.rag.reranking import LexicalSemanticReranker
from amba_ai.rag.chunk_adapter import ChunkAdapter
from amba_ai.rag.source_control import SourceControl


def _read_field(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value and value[name] is not None:
                return value[name]
    for name in names:
        candidate = getattr(value, name, None)
        if candidate is not None:
            return candidate
    return default


def _row_to_chunk(row: Any, document_id: int) -> Chunk:
    return ChunkAdapter.to_chunk(row, fallback_document_id=document_id)


class FaissVectorSearchAdapter:
    def __init__(self, rag_engine: Any, permitted_chunk_ids: frozenset[int]) -> None:
        self.rag_engine = rag_engine
        self.permitted_chunk_ids = permitted_chunk_ids

    def __call__(self, query: str, k: int, filters: dict[str, Any]) -> list[tuple[Chunk, float]]:
        wanted_doc_id = filters.get("document_id")
        results: list[tuple[Chunk, float]] = []

        raw_hits = self.rag_engine.search(query, top_k=max(k * 3, k))
        for rank, hit in enumerate(raw_hits, start=1):
            chunk = ChunkAdapter.to_chunk(hit)
            try:
                chunk_id = int(chunk.chunk_id)
            except (TypeError, ValueError):
                continue
            if chunk_id not in self.permitted_chunk_ids:
                continue
            if wanted_doc_id is not None and str(chunk.document_id) != str(wanted_doc_id):
                continue
            score = float(_read_field(hit, "score", "similarity", default=1.0 / rank))
            results.append((chunk, score))
            if len(results) >= k:
                break

        return results


def _build_answer_dto(grounded: Any, model_name: str) -> AnswerResult:
    citations = grounded.citations
    source_labels = [c["label"] for c in citations]
    payload = {
        "answer_text": grounded.answer,
        "raw_answer": grounded.answer,
        "model_name": model_name,
        "sources": source_labels,
        "metadata": {
            "confidence": grounded.confidence,
            "evidence_sufficient": grounded.evidence_sufficient,
            "citations": citations,
            "pedagogical_notes": grounded.pedagogical_notes,
            "suggested_followups": grounded.suggested_followups,
        },
    }

    if is_dataclass(AnswerResult):
        allowed = {f.name for f in fields(AnswerResult)}
        filtered = {k: v for k, v in payload.items() if k in allowed}
        return AnswerResult(**filtered)
    return AnswerResult(**payload)


def build_production_rag_pipeline(
    db: Any,
    rag_engine: Any,
    llm: Any,
    document_id: int | None = None,
    *,
    runtime_governance: Any | None = None,
    operation: str = "tutor_answer",
) -> ProductionRAGPipeline:
    if runtime_governance is None:
        raise RuntimeError(
            "Production hybrid retrieval requires runtime education governance."
        )
    builder = GovernedCorpusBuilder(
        db=db,
        rag_engine=rag_engine,
        runtime_governance=runtime_governance,
        cache=rag_engine.corpus_cache,
    )
    corpus = builder.build(operation=operation)
    filters = {"document_id": str(document_id)} if document_id is not None else {}
    pipeline = ProductionRAGPipeline(
        retriever=HybridRetriever(
            vector_search=FaissVectorSearchAdapter(
                rag_engine,
                corpus.eligible_chunk_ids,
            ),
            keyword_search=corpus.bm25.search,
        ),
        reranker=LexicalSemanticReranker(),
        assembler=ContextAssembler(max_chars=12000, max_tokens=3200),
        minimum_confidence=0.18,
    )
    pipeline.corpus_revision = corpus.revision
    pipeline.corpus_receipt_id = corpus.receipt_id
    pipeline.corpus_filters = filters
    return pipeline
