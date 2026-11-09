from __future__ import annotations

from pathlib import Path
from amba_ai.db.database import Database
from amba_ai.models.schemas import IngestedDocument
from amba_ai.ui.features.library.data_classes import LibraryDocument
from amba_ai.ui.features.ingest.data_classes import IngestViewModel, _coerce_bool


def test_coerce_bool_rules():
    assert _coerce_bool("true") is True
    assert _coerce_bool("True") is True
    assert _coerce_bool("1") is True
    assert _coerce_bool("indexed") is True
    assert _coerce_bool(True) is True
    assert _coerce_bool(1) is True

    # "false" string must not evaluate to True
    assert _coerce_bool("false") is False
    assert _coerce_bool("False") is False
    assert _coerce_bool("0") is False
    assert _coerce_bool("not_indexed") is False
    assert _coerce_bool("failed") is False
    assert _coerce_bool(False) is False
    assert _coerce_bool(0) is False
    assert _coerce_bool(None, default=False) is False


def test_database_update_document_metadata_merge(tmp_path: Path):
    db_file = tmp_path / "test.db"
    db = Database(path=db_file)

    doc_id = db.insert_document(
        IngestedDocument(
            title="Physics Notes",
            source_path="/path/notes.pdf",
            kind="pdf",
            raw_text="Hello physics world",
            metadata={"page_count": 5, "author": "Newton"},
        )
    )

    # Initial fetch
    initial_meta = db.get_document_metadata(doc_id)
    assert initial_meta["page_count"] == 5
    assert initial_meta["author"] == "Newton"

    # Merge updates
    updated = db.update_document_metadata(
        doc_id,
        {
            "chunk_count": 0,
            "text_length": 19,
            "rag_indexed": False,
            "index_status": "not_indexed",
        },
    )

    assert updated["page_count"] == 5
    assert updated["author"] == "Newton"
    assert updated["chunk_count"] == 0
    assert updated["text_length"] == 19
    assert updated["rag_indexed"] is False
    assert updated["index_status"] == "not_indexed"

    re_fetched = db.get_document_metadata(doc_id)
    assert re_fetched == updated


def test_library_document_zero_chunks_and_boolean_handling():
    lib_doc = LibraryDocument.from_any(
        {
            "id": 10,
            "title": "Empty Document",
            "metadata_json": '{"chunk_count": 0, "text_length": 0, "rag_indexed": "false", "index_status": "not_indexed"}',
        }
    )

    assert lib_doc is not None
    assert lib_doc.chunk_count == 0
    assert lib_doc.text_length == 0
    assert lib_doc.rag_indexed is False
    assert lib_doc.index_status == "not_indexed"


def test_ingest_view_model_failure_status():
    vm = IngestViewModel.from_ingested_result(
        type(
            "Result",
            (),
            {
                "document_id": 4,
                "document": type("Doc", (), {"title": "Doc 4", "kind": "pdf", "source_path": "x.pdf"}),
                "metadata": {
                    "chunk_count": 1,
                    "text_length": 744,
                    "rag_indexed": False,
                    "index_status": "failed",
                    "index_error": "FAISS allocation error",
                },
            },
        )
    )

    assert vm.chunk_count == 1
    assert vm.text_length == 744
    assert vm.rag_indexed is False
    assert vm.indexed_label == "Failed"