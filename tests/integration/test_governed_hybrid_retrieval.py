from __future__ import annotations

import hashlib
from types import SimpleNamespace

from amba_ai.rag.corpus_revision import GovernedCorpusBuilder, RetrievalCorpusCache


class GovernanceRepository:
    def __init__(self) -> None:
        self.allowed = {1: {11}}
        self.decisions = {
            1: [
                {"chunk_id": 11, "chunk_sha256": hashlib.sha256(b"approved algebra").hexdigest(), "decision": "accepted_with_restrictions", "review_status": "approved", "indexing_permitted": True, "generation_eligible": True, "operations_permitted": ["tutor_answer"]},
                {"chunk_id": 12, "chunk_sha256": hashlib.sha256(b"revoked answer key").hexdigest(), "decision": "rejected", "review_status": "revoked", "indexing_permitted": False, "generation_eligible": False, "operations_permitted": []},
            ]
        }
        self.receipts = []
    def get_document(self, document_id): return {"source_sha256": "source-v1"}
    def get_chunk_decisions(self, document_id): return list(self.decisions[document_id])
    def receipt(self, event_type, payload, document_id=None, operation=None):
        self.receipts.append((event_type, payload))
        return "EDU-GOV-CORPUS"


class Governance:
    def __init__(self, repository): self.repository = repository
    def permitted_chunk_ids(self, document_id, operation):
        return frozenset(self.repository.allowed[document_id])


class Database:
    def list_documents(self, limit=100000, offset=0):
        return [{"id": 1, "metadata": {"version_id": "v1"}, "created_at": "now"}]
    def get_chunks(self, document_id):
        return [
            {"id": 11, "document_id": 1, "text": "approved algebra", "chunk_index": 0},
            {"id": 12, "document_id": 1, "text": "revoked answer key", "chunk_index": 1},
        ]


class Engine:
    def __init__(self):
        self.ids = frozenset()
        self.rebuilds = 0
    def indexed_chunk_ids(self): return self.ids
    def rebuild_from_source_documents(self, *, policy):
        self.ids = frozenset(value for values in policy.permitted_chunk_ids_by_document.values() for value in values)
        self.rebuilds += 1


def build(repository, engine, cache):
    return GovernedCorpusBuilder(
        db=Database(),
        rag_engine=engine,
        runtime_governance=Governance(repository),
        cache=cache,
    ).build(operation="tutor_answer_stream")


def test_faiss_bm25_and_governance_share_identical_chunk_ids() -> None:
    repository = GovernanceRepository()
    engine = Engine()
    result = build(repository, engine, RetrievalCorpusCache())
    assert result.operation == "learning.tutor.answer"
    assert result.eligible_chunk_ids == frozenset({11})
    assert result.faiss_chunk_ids == frozenset({11})
    assert result.bm25_chunk_ids == frozenset({11})
    assert result.excluded_chunk_ids == frozenset({12})
    result.require_aligned()


def test_same_document_count_but_changed_governance_invalidates_cache() -> None:
    repository = GovernanceRepository()
    engine = Engine()
    cache = RetrievalCorpusCache()
    first = build(repository, engine, cache)
    repository.allowed[1] = {12}
    repository.decisions[1][0]["review_status"] = "revoked"
    repository.decisions[1][0]["indexing_permitted"] = False
    repository.decisions[1][1]["review_status"] = "approved"
    repository.decisions[1][1]["indexing_permitted"] = True
    repository.decisions[1][1]["generation_eligible"] = True
    repository.decisions[1][1]["operations_permitted"] = ["tutor_answer"]
    second = build(repository, engine, cache)
    assert first.revision.revision_id != second.revision.revision_id
    assert second.eligible_chunk_ids == frozenset({12})
    assert second.faiss_chunk_ids == second.bm25_chunk_ids == frozenset({12})
    assert engine.rebuilds == 2
