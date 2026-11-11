from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from amba_ai.governance.learning_operations import canonical_learning_operation
from amba_ai.rag.chunk_adapter import ChunkAdapter
from amba_ai.rag.hybrid import InMemoryBM25
from amba_ai.rag.index_policy import IndexRebuildPolicy
from amba_ai.rag.models import Chunk


def _sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _field(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value and value[name] is not None:
                return value[name]
    for name in names:
        candidate = getattr(value, name, None)
        if candidate is not None:
            return candidate
    return default


@dataclass(frozen=True, slots=True)
class RetrievalCorpusRevision:
    document_digest: str
    chunk_set_digest: str
    governance_allowlist_digest: str

    @property
    def revision_id(self) -> str:
        return _sha256(
            {
                "document_digest": self.document_digest,
                "chunk_set_digest": self.chunk_set_digest,
                "governance_allowlist_digest": self.governance_allowlist_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class GovernedCorpusBuildResult:
    operation: str
    revision: RetrievalCorpusRevision
    eligible_chunk_ids: frozenset[int]
    excluded_chunk_ids: frozenset[int]
    faiss_chunk_ids: frozenset[int]
    bm25_chunk_ids: frozenset[int]
    bm25: InMemoryBM25
    receipt_id: str

    def require_aligned(self) -> None:
        if not (
            self.faiss_chunk_ids
            == self.bm25_chunk_ids
            == self.eligible_chunk_ids
        ):
            raise RuntimeError(
                "Governed retrieval corpus is not aligned across FAISS, BM25, and governance."
            )


class RetrievalCorpusCache:
    def __init__(self) -> None:
        self._revision_id: str | None = None
        self._result: GovernedCorpusBuildResult | None = None

    def get(self, revision: RetrievalCorpusRevision) -> GovernedCorpusBuildResult | None:
        if self._revision_id == revision.revision_id:
            return self._result
        return None

    def store(self, result: GovernedCorpusBuildResult) -> None:
        self._revision_id = result.revision.revision_id
        self._result = result

    def invalidate(self) -> None:
        self._revision_id = None
        self._result = None


class GovernedCorpusBuilder:
    def __init__(self, *, db: Any, rag_engine: Any, runtime_governance: Any, cache: RetrievalCorpusCache) -> None:
        self.db = db
        self.rag_engine = rag_engine
        self.runtime_governance = runtime_governance
        self.cache = cache

    def _documents(self) -> list[Any]:
        if hasattr(self.db, "list_documents"):
            return list(self.db.list_documents(limit=100_000, offset=0))
        return list(self.db.list_documents_typed(limit=100_000, offset=0))

    def _chunks(self, document_id: int) -> list[Any]:
        return list(self.db.get_chunks(document_id))

    def _snapshot(self, operation: str) -> tuple[RetrievalCorpusRevision, dict[int, frozenset[int]], list[Chunk], frozenset[int]]:
        documents = self._documents()
        document_payload: list[dict[str, Any]] = []
        chunk_payload: list[dict[str, Any]] = []
        governance_payload: list[dict[str, Any]] = []
        allowlists: dict[int, frozenset[int]] = {}
        eligible_chunks: list[Chunk] = []
        all_chunk_ids: set[int] = set()

        for document in sorted(documents, key=lambda item: int(_field(item, "id", "document_id"))):
            document_id = int(_field(document, "id", "document_id"))
            governance_document = self.runtime_governance.repository.get_document(document_id)
            if not governance_document:
                raise RuntimeError(f"Document {document_id} has no runtime governance record.")
            metadata = dict(_field(document, "metadata", default={}) or {})
            document_payload.append(
                {
                    "document_id": document_id,
                    "source_sha256": governance_document["source_sha256"],
                    "version_id": metadata.get("version_id") or metadata.get("version") or "v1",
                    "created_at": _field(document, "created_at", default=""),
                }
            )
            decisions = self.runtime_governance.repository.get_chunk_decisions(document_id)
            if not decisions:
                raise RuntimeError(f"Document {document_id} has no chunk governance decisions.")
            allowed = self.runtime_governance.permitted_chunk_ids(document_id, operation)
            allowlists[document_id] = frozenset(int(value) for value in allowed)
            decision_by_id = {int(item["chunk_id"]): item for item in decisions}

            for row in self._chunks(document_id):
                chunk = ChunkAdapter.to_chunk(row, fallback_document_id=document_id)
                effective_text_resolver = getattr(
                    self.runtime_governance.repository,
                    "effective_chunk_text",
                    None,
                )
                if callable(effective_text_resolver):
                    chunk.text = effective_text_resolver(
                        chunk_id=int(_field(row, "id", "chunk_id")),
                        original_text=chunk.text,
                    )
                chunk_id = int(_field(row, "id", "chunk_id"))
                all_chunk_ids.add(chunk_id)
                decision = decision_by_id.get(chunk_id)
                chunk_sha = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
                chunk_payload.append(
                    {
                        "document_id": document_id,
                        "chunk_id": chunk_id,
                        "chunk_sha256": chunk_sha,
                        "version_id": chunk.version_id,
                    }
                )
                governance_payload.append(
                    {
                        "document_id": document_id,
                        "chunk_id": chunk_id,
                        "operation": operation,
                        "allowed": chunk_id in allowed,
                        "decision": decision.get("decision") if decision else "unknown",
                        "review_status": decision.get("review_status") if decision else "unknown",
                        "indexing_permitted": bool(decision and decision.get("indexing_permitted")),
                        "generation_eligible": bool(decision and decision.get("generation_eligible")),
                        "operations_permitted": sorted(decision.get("operations_permitted", ())) if decision else [],
                        "governance_chunk_sha256": decision.get("chunk_sha256") if decision else None,
                        "effective_review_id": decision.get("effective_review_id") if decision else None,
                    }
                )
                if chunk_id in allowed:
                    chunk.chunk_id = str(chunk_id)
                    eligible_chunks.append(chunk)

        revision = RetrievalCorpusRevision(
            document_digest=_sha256(document_payload),
            chunk_set_digest=_sha256(chunk_payload),
            governance_allowlist_digest=_sha256(governance_payload),
        )
        eligible_ids = frozenset(value for values in allowlists.values() for value in values)
        return revision, allowlists, eligible_chunks, frozenset(all_chunk_ids - set(eligible_ids))

    def build(self, *, operation: str) -> GovernedCorpusBuildResult:
        canonical_operation = canonical_learning_operation(operation)
        revision, allowlists, eligible_chunks, excluded_ids = self._snapshot(canonical_operation)
        cached = self.cache.get(revision)
        if cached is not None:
            cached.require_aligned()
            return cached

        eligible_ids = frozenset(int(chunk.chunk_id) for chunk in eligible_chunks)
        current_faiss_ids = self.rag_engine.indexed_chunk_ids()
        if current_faiss_ids != eligible_ids:
            policy = IndexRebuildPolicy.from_allowlists(
                canonical_operation,
                allowlists,
                require_complete_allowlists=True,
                effective_text_by_chunk_id={
                    int(chunk.chunk_id): chunk.text
                    for chunk in eligible_chunks
                },
            )
            self.rag_engine.rebuild_from_source_documents(policy=policy)
            current_faiss_ids = self.rag_engine.indexed_chunk_ids()

        bm25 = InMemoryBM25(eligible_chunks, revision_id=revision.revision_id)
        bm25_ids = frozenset(int(value) for value in bm25.chunk_ids)
        receipt_id = self.runtime_governance.repository.receipt(
            "retrieval_corpus_built",
            {
                "operation": canonical_operation,
                "revision_id": revision.revision_id,
                "document_digest": revision.document_digest,
                "chunk_set_digest": revision.chunk_set_digest,
                "governance_allowlist_digest": revision.governance_allowlist_digest,
                "eligible_chunk_ids": sorted(eligible_ids),
                "excluded_chunk_ids": sorted(excluded_ids),
            },
            operation=canonical_operation,
        )
        result = GovernedCorpusBuildResult(
            operation=canonical_operation,
            revision=revision,
            eligible_chunk_ids=eligible_ids,
            excluded_chunk_ids=excluded_ids,
            faiss_chunk_ids=current_faiss_ids,
            bm25_chunk_ids=bm25_ids,
            bm25=bm25,
            receipt_id=receipt_id,
        )
        result.require_aligned()
        self.cache.store(result)
        return result
