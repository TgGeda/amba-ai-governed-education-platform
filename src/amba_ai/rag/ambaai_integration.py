from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from amba_ai.logger import logger
from amba_ai.models.schemas import AnswerResult
from amba_ai.rag.chunking import SemanticChunker
from amba_ai.rag.context import ContextAssembler
from amba_ai.rag.hybrid import HybridRetriever, InMemoryBM25
from amba_ai.rag.models import Chunk, RetrievalQuery
from amba_ai.rag.pipeline import ProductionRAGPipeline
from amba_ai.rag.reranking import LexicalSemanticReranker
from amba_ai.rag.retrieved_chunk_compat import ChunkAdapter, install_retrieved_chunk_compat
from amba_ai.rag.source_control import SourceControl


class _GlobalRetrieverCache:
    _bm25_instance: InMemoryBM25 | None = None
    _indexed_doc_count: int = -1


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


def _load_all_chunks(db: Any, document_id: int | None = None) -> list[Chunk]:
    if document_id is not None:
        doc_ids = [int(document_id)]
    else:
        doc_ids = [int(_read_field(d, "id", "document_id")) for d in db.list_documents()]

    results: list[Chunk] = []
    for d_id in doc_ids:
        rows = db.get_chunks(d_id)
        for r in rows:
            c = _row_to_chunk(r, d_id)
            if c.text.strip():
                results.append(c)
    return results


def _get_or_build_bm25(db: Any, document_id: int | None = None) -> InMemoryBM25:
    if document_id is not None:
        chunks = _load_all_chunks(db, document_id)
        return InMemoryBM25(chunks)

    all_docs = db.list_documents()
    current_count = len(all_docs)

    if _GlobalRetrieverCache._bm25_instance is not None and _GlobalRetrieverCache._indexed_doc_count == current_count:
        return _GlobalRetrieverCache._bm25_instance

    all_chunks = _load_all_chunks(db, None)
    bm25 = InMemoryBM25(all_chunks)
    _GlobalRetrieverCache._bm25_instance = bm25
    _GlobalRetrieverCache._indexed_doc_count = current_count
    return bm25


class FaissVectorSearchAdapter:
    def __init__(self, rag_engine: Any) -> None:
        self.rag_engine = rag_engine

    def __call__(self, query: str, k: int, filters: dict[str, Any]) -> list[tuple[Chunk, float]]:
        wanted_doc_id = filters.get("document_id")
        results: list[tuple[Chunk, float]] = []

        raw_hits = self.rag_engine.search(query, top_k=max(k * 3, k))
        for rank, hit in enumerate(raw_hits, start=1):
            chunk = ChunkAdapter.to_chunk(hit)
            if wanted_doc_id is not None and str(chunk.document_id) != str(wanted_doc_id):
                continue
            score = float(_read_field(hit, "score", "similarity", default=1.0 / rank))
            results.append((chunk, score))
            if len(results) >= k:
                break

        return results


def _create_generator_closure(llm: Any) -> Any:
    def run(prompt: str) -> str:
        res = llm.generate(
            prompt=prompt,
            system="You are AmbaAI, an offline curriculum tutor. Base answers strictly on the supplied sources.",
            temperature=0.1,
            max_tokens=1200,
        )
        return str(_read_field(res, "response_text", "text", "content", default=res))
    return run


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
) -> ProductionRAGPipeline:
    bm25 = _get_or_build_bm25(db, document_id)
    return ProductionRAGPipeline(
        retriever=HybridRetriever(
            vector_search=FaissVectorSearchAdapter(rag_engine),
            keyword_search=bm25.search,
        ),
        reranker=LexicalSemanticReranker(),
        assembler=ContextAssembler(max_chars=12000, max_tokens=3200),
        generator=_create_generator_closure(llm),
        minimum_confidence=0.18,
    )