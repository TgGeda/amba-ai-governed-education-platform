from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from amba_ai.config import WHISPER_MODEL
from amba_ai.core.ingest import ingest_path
from amba_ai.core.preprocessing import chunk_text
from amba_ai.exceptions import IngestionError
from amba_ai.governance.runtime import RuntimeEducationGovernanceService
from amba_ai.governance.runtime.guardrails import sha256_file
from amba_ai.models.schemas import IngestedDocumentResult


@dataclass(frozen=True, slots=True)
class GovernedIngestionReceipt:
    receipt_id: str
    document_id: int
    source_sha256: str
    chunk_ids: tuple[int, ...]
    approved_chunk_ids: tuple[int, ...]
    excluded_chunk_ids: tuple[int, ...]
    indexed_chunk_ids: tuple[int, ...]


class GovernedIngestionService:
    """Fail-closed orchestration for document persistence, governance, and indexing."""

    def __init__(
        self,
        *,
        db: Any,
        rag_engine: Any,
        runtime_governance: RuntimeEducationGovernanceService,
        extractor: Callable[..., Any] = ingest_path,
        chunker: Callable[..., Any] = chunk_text,
    ) -> None:
        self.db = db
        self.rag_engine = rag_engine
        self.runtime_governance = runtime_governance
        self.extractor = extractor
        self.chunker = chunker

    def ingest(self, path: str | Path) -> IngestedDocumentResult:
        source = Path(path).expanduser().resolve()
        document_id: int | None = None
        stage = "preflight"
        try:
            preflight_digest, _findings = self.runtime_governance.preflight_file(source)
            stage = "extract"
            document = self.extractor(source, whisper_model=WHISPER_MODEL)
            raw_text = str(document.raw_text or "").strip()
            if not raw_text:
                raise IngestionError("Extraction is incomplete: no text was produced.", context={"stage": stage})
            stored_path = Path(document.source_path)
            if not stored_path.is_file() or sha256_file(stored_path) != preflight_digest:
                raise IngestionError("Source digest changed during extraction.", context={"stage": stage})

            stage = "assess_document"
            decision = self.runtime_governance.assess_ingestion(stored_path, raw_text)
            if decision.source_sha256 != preflight_digest:
                raise IngestionError("Document governance digest does not match source digest.", context={"stage": stage})
            if not decision.permits_persistence or not decision.permits_indexing:
                raise IngestionError("Document governance refused governed indexing.", context={"stage": stage, "decision": decision.decision.value})

            stage = "persist_primary"
            document_id, chunk_ids = self.db.insert_governed_document_with_chunker(
                document,
                text=raw_text,
                chunker=self.chunker,
            )
            if not chunk_ids:
                raise IngestionError(
                    "Extraction is incomplete: no chunks were produced.",
                    context={"stage": "chunk", "document_id": document_id},
                )
            persisted = list(self.db.get_chunks(document_id))
            if tuple(int(row["id"]) for row in persisted) != chunk_ids:
                raise IngestionError("Persisted chunk set is incomplete.", context={"stage": stage, "document_id": document_id})

            stage = "record_document_governance"
            self.runtime_governance.record_document(document_id, decision)
            record = self.runtime_governance.repository.get_document(document_id)
            if not record or record.get("source_sha256") != preflight_digest:
                raise IngestionError("Document governance record is missing or invalid.", context={"stage": stage, "document_id": document_id})

            stage = "assess_chunks"
            chunk_decisions = self.runtime_governance.assess_chunks(document_id, persisted)
            decision_ids = {int(item.chunk_id) for item in chunk_decisions}
            if decision_ids != set(chunk_ids):
                raise IngestionError("A chunk has no governance decision.", context={"stage": stage, "document_id": document_id})
            approved = frozenset(int(item.chunk_id) for item in chunk_decisions if item.indexing_permitted and item.generation_eligible and item.review_status == "approved")
            if not approved:
                raise IngestionError("A governed indexing allowlist cannot be produced.", context={"stage": stage, "document_id": document_id})

            stage = "index"
            self.rag_engine.index_document(document_id, permitted_chunk_ids=approved)
            indexed = frozenset(int(value) for value in self.rag_engine.indexed_chunk_ids())
            if not approved.issubset(indexed) or self.rag_engine.has_document(document_id) is False:
                raise IngestionError("Index and governance did not complete consistently.", context={"stage": stage, "document_id": document_id})

            stage = "receipt"
            excluded = frozenset(chunk_ids) - approved
            receipt_id = self.runtime_governance.repository.receipt(
                "governed_ingestion_completed",
                {
                    "document_id": document_id,
                    "source_sha256": preflight_digest,
                    "chunk_ids": list(chunk_ids),
                    "approved_chunk_ids": sorted(approved),
                    "excluded_chunk_ids": sorted(excluded),
                    "indexed_chunk_ids": sorted(approved),
                },
                document_id,
                "learning.document.ingest",
            )
            if not receipt_id:
                raise IngestionError("Ingestion receipt could not be produced.", context={"stage": stage, "document_id": document_id})
            metadata = self.db.update_document_metadata(document_id, {
                "source_sha256": preflight_digest,
                "chunk_count": len(chunk_ids),
                "approved_chunk_count": len(approved),
                "excluded_chunk_count": len(excluded),
                "rag_indexed": True,
                "index_status": "indexed",
                "ingestion_status": "complete",
                "ingestion_receipt_id": receipt_id,
            })
            return IngestedDocumentResult(document=document, document_id=document_id, metadata={**dict(document.metadata or {}), **metadata})
        except Exception as error:
            self._compensate(document_id)
            if isinstance(error, IngestionError):
                raise
            raise IngestionError("Governed ingestion failed closed.", context={"stage": stage, "document_id": document_id, "error_type": type(error).__name__, "error_message": str(error)}) from error

    def _compensate(self, document_id: int | None) -> None:
        if document_id is None:
            return
        try:
            self.rag_engine.remove_document(document_id)
        except Exception:
            pass
        try:
            self.runtime_governance.repository.delete_document_records(document_id)
        except Exception:
            pass
        try:
            self.db.delete_document(document_id)
        except Exception:
            pass
        cache = getattr(self.rag_engine, "corpus_cache", None)
        if cache is not None:
            cache.invalidate()
