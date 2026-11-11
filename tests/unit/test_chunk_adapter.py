from __future__ import annotations

from amba_ai.models.schemas import RetrievedChunk
from amba_ai.rag.chunk_adapter import ChunkAdapter
from amba_ai.rag.engine import FaissRAGEngine
from amba_ai.rag.models import Chunk


def test_to_chunk_returns_existing_chunk_without_copy() -> None:
    chunk = Chunk(
        chunk_id="chunk-1",
        document_id="42",
        version_id="v3",
        text="Governed learning material",
        ordinal=2,
    )

    assert ChunkAdapter.to_chunk(chunk) is chunk


def test_to_chunk_converts_repository_aliases_and_json_fields() -> None:
    chunk = ChunkAdapter.to_chunk(
        {
            "id": 999,
            "doc_id": 42,
            "version_id": "v7",
            "chunk_index": 3,
            "chunk_text": "Approved evidence",
            "page_number": 5,
            "heading_path": '["Unit 1", "Safety"]',
            "metadata": '{"language": "en"}',
        }
    )

    assert chunk.chunk_id == "chk_42_3_v7"
    assert chunk.document_id == "42"
    assert chunk.version_id == "v7"
    assert chunk.text == "Approved evidence"
    assert chunk.ordinal == 3
    assert chunk.page_start == 5
    assert chunk.page_end == 5
    assert chunk.heading_path == ("Unit 1", "Safety")
    assert chunk.metadata == {"language": "en"}


def test_to_chunk_uses_fallback_document_id() -> None:
    chunk = ChunkAdapter.to_chunk(
        {"chunk_id": "chunk-2", "text": "Fallback document"},
        fallback_document_id=81,
    )

    assert chunk.document_id == "81"


def test_native_engine_dto_builder_preserves_retrieval_score() -> None:
    dto = FaissRAGEngine._build_dto(
        RetrievedChunk,
        {
            "chunk_id": 301,
            "document_id": 42,
            "doc_id": 42,
            "score": 0.875,
            "text": "Retrieved evidence",
            "source_ref": "lesson.pdf#page=2",
            "metadata": {"operation": "learning.tutor.retrieve"},
            "ignored": "not part of the DTO contract",
        },
    )

    assert dto == RetrievedChunk(
        chunk_id=301,
        doc_id=42,
        score=0.875,
        text="Retrieved evidence",
        source_ref="lesson.pdf#page=2",
        metadata={"operation": "learning.tutor.retrieve"},
    )


def test_importing_engine_does_not_mutate_engine_class() -> None:
    assert "_retrieved_chunk_compat_installed" not in FaissRAGEngine.__dict__
