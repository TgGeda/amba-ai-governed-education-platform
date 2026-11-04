from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional


# ---------------------------------------------------------------------
# Domain Model
# ---------------------------------------------------------------------

@dataclass
class LibraryDocument:
    """
    In-memory representation of a library document.

    This object is mutable by design and intended to be managed
    exclusively by DocumentStore.
    """

    document_id: int
    title: str
    kind: str
    created_at: str
    size: int | None

    tags: list[str] = field(default_factory=list)

    # Usage analytics
    usage_count: int = 0
    usage_timestamps: list[float] = field(default_factory=list)

    # Soft-delete lifecycle
    deleted: bool = False
    deleted_at: float | None = None


# ---------------------------------------------------------------------
# Document Store
# ---------------------------------------------------------------------

class DocumentStore:
    """
    Lightweight in-memory document registry.

    Responsibilities:
    - Track active vs deleted documents
    - Track usage counts & timestamps (heat-map support)
    - Support soft-delete, restore, and hard purge
    - Provide basic statistics

    This store is intentionally offline-only and fast.
    Persistence (DB / sync) should wrap this class, not replace it.
    """

    def __init__(self) -> None:
        self._docs: Dict[int, LibraryDocument] = {}

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def upsert(self, doc: LibraryDocument) -> None:
        """
        Insert or update a document by document_id.
        """
        if not isinstance(doc.document_id, int):
            raise ValueError("document_id must be an integer")

        self._docs[doc.document_id] = doc

    def get(self, doc_id: int) -> Optional[LibraryDocument]:
        """
        Retrieve a document by ID (active or deleted).
        """
        return self._docs.get(doc_id)

    def list_active(self) -> list[LibraryDocument]:
        """
        Return all non-deleted documents.
        """
        return [doc for doc in self._docs.values() if not doc.deleted]

    def list_deleted(self) -> list[LibraryDocument]:
        """
        Return all soft-deleted documents.
        """
        return [doc for doc in self._docs.values() if doc.deleted]

    def list_all(self) -> list[LibraryDocument]:
        """
        Return all documents (active + deleted).
        """
        return list(self._docs.values())

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

    def mark_used(self, doc_id: int) -> None:
        """
        Record a document usage event.
        """
        doc = self._docs.get(doc_id)
        if doc is None:
            return

        now = time.time()
        doc.usage_count += 1
        doc.usage_timestamps.append(now)

    # ------------------------------------------------------------------
    # Deletion lifecycle
    # ------------------------------------------------------------------

    def soft_delete(self, doc_id: int) -> None:
        """
        Soft-delete a document (reversible).
        """
        doc = self._docs.get(doc_id)
        if doc is None or doc.deleted:
            return

        doc.deleted = True
        doc.deleted_at = time.time()

    def restore(self, doc_id: int) -> None:
        """
        Restore a soft-deleted document.
        """
        doc = self._docs.get(doc_id)
        if doc is None:
            return

        doc.deleted = False
        doc.deleted_at = None

    def purge(self, doc_id: int) -> None:
        """
        Permanently remove a document from the store.
        """
        self._docs.pop(doc_id, None)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        """
        Return aggregate statistics.

        Returns:
            {
                "total": int,
                "deleted": int,
                "size_bytes": int
            }
        """
        total = len(self._docs)
        deleted = sum(1 for doc in self._docs.values() if doc.deleted)
        size_bytes = sum(doc.size or 0 for doc in self._docs.values())

        return {
            "total": total,
            "deleted": deleted,
            "size_bytes": size_bytes,
        }