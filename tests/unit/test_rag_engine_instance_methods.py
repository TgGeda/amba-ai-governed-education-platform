from __future__ import annotations

from pathlib import Path

from amba_ai.rag.engine import FaissRAGEngine


def test_ensure_kb_dir_is_an_instance_method(tmp_path: Path) -> None:
    engine = object.__new__(FaissRAGEngine)
    engine.kb_dir = tmp_path / "nested" / "kb"
    engine.index_path = engine.kb_dir / FaissRAGEngine.INDEX_FILENAME
    engine.sqlite_path = engine.kb_dir / FaissRAGEngine.DB_FILENAME
    engine.embedding_model_name = "synthetic-test-model"
    engine.embedding_dim = 1
    engine.similarity_metric = "cosine"
    engine.index = None

    engine._ensure_kb_dir()

    assert engine.kb_dir.is_dir()
