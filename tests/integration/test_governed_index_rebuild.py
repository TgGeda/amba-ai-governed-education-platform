from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from amba_ai.exceptions import RAGError
from amba_ai.governance.learning_operations import canonical_learning_operation
from amba_ai.rag.engine import FaissRAGEngine, _ChunkRecord
from amba_ai.rag.index_policy import IndexRebuildPolicy


class FakeIndex:
    def __init__(self) -> None:
        self.ntotal = 0
        self.identifiers: list[int] = []

    def add_with_ids(self, vectors, identifiers) -> None:
        self.identifiers.extend(int(value) for value in identifiers)
        self.ntotal += len(identifiers)


class TestEngine(FaissRAGEngine):
    __test__ = False

    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = sqlite_path
        self.embedding_dim = 2
        self._rw_lock = threading.RLock()
        self.index = FakeIndex()
        self.rebuild_policy_provider = None
        self.documents = {
            1: [
                _ChunkRecord(11, 1, "approved chunk"),
                _ChunkRecord(12, 1, "pending review chunk"),
                _ChunkRecord(13, 1, "unknown chunk"),
            ]
        }
        with sqlite3.connect(sqlite_path) as connection:
            connection.execute(
                """
                CREATE TABLE rag_chunks (
                    faiss_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id INTEGER,
                    document_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    source_ref TEXT,
                    text_hash TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )

    def _context(self, **values):
        return dict(values)

    def _get_connection(self):
        connection = sqlite3.connect(self.sqlite_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _list_document_ids(self):
        return sorted(self.documents)

    def _fetch_chunks_for_document(self, document_id):
        return list(self.documents[document_id])

    def _create_base_index(self):
        return FakeIndex()

    def embed(self, texts):
        return np.ones((len(texts), self.embedding_dim), dtype="float32")

    def save(self):
        return None


def policy() -> IndexRebuildPolicy:
    return IndexRebuildPolicy.from_allowlists(
        "tutor_answer",
        {1: {11}},
    )


def indexed_chunk_ids(engine: TestEngine) -> tuple[int, ...]:
    with engine._get_connection() as connection:
        rows = connection.execute(
            "SELECT chunk_id FROM rag_chunks ORDER BY chunk_id"
        ).fetchall()
    return tuple(int(row["chunk_id"]) for row in rows)


def test_governed_rebuild_indexes_only_approved_chunk(tmp_path) -> None:
    engine = TestEngine(tmp_path / "metadata.db")
    result = engine.rebuild_from_source_documents(policy=policy())
    assert result.indexed_chunk_ids == (11,)
    assert result.excluded_chunk_ids == (12, 13)
    assert indexed_chunk_ids(engine) == (11,)


def test_missing_document_allowlist_fails_before_mutation(tmp_path) -> None:
    engine = TestEngine(tmp_path / "metadata.db")
    engine.documents[2] = [_ChunkRecord(21, 2, "approved second document")]
    original_index = engine.index
    with engine._get_connection() as connection:
        before = connection.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
    with pytest.raises(RAGError, match="allowlists are incomplete"):
        engine.rebuild_from_source_documents(policy=policy())
    with engine._get_connection() as connection:
        after = connection.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
    assert engine.index is original_index
    assert before == after == 0


def test_recovery_uses_same_governed_allowlist(tmp_path) -> None:
    engine = TestEngine(tmp_path / "metadata.db")
    engine.rebuild_policy_provider = policy
    engine.rebuild_from_source_documents(policy=policy())
    assert indexed_chunk_ids(engine) == (11,)

    engine.index = FakeIndex()
    with engine._get_connection() as connection:
        connection.execute("DELETE FROM rag_chunks")
    result = engine._rebuild_after_recovery_failure()

    assert result.indexed_chunk_ids == (11,)
    assert result.excluded_chunk_ids == (12, 13)
    assert indexed_chunk_ids(engine) == (11,)


def test_stream_operations_are_normalized_centrally() -> None:
    assert canonical_learning_operation("tutor_answer_stream") == "learning.tutor.answer"
    assert canonical_learning_operation("tutor_chat_stream") == "learning.tutor.answer"
    assert canonical_learning_operation("generate_notes") == "learning.notes.generate"
