from __future__ import annotations

import numpy as np
from typing import Callable, Dict, Iterable, List, Tuple


class SemanticSearchIndex:
    """
    Lightweight in-memory semantic search index.

    Responsibilities:
    - Embed text using a provided embedding function
    - Store normalized vectors by document_id
    - Perform cosine-similarity search
    - Support upsert, delete, and batch indexing

    This index is intentionally simple and offline-first.
    For large corpora, FAISS should wrap or replace this class.
    """

    def __init__(self, embed_fn: Callable[[str], np.ndarray]) -> None:
        if not callable(embed_fn):
            raise ValueError("embed_fn must be callable")

        self.embed_fn = embed_fn
        self._vectors: Dict[int, np.ndarray] = {}

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index(self, doc_id: int, text: str) -> None:
        """
        Index or update a single document.
        """
        if not isinstance(doc_id, int):
            raise ValueError("doc_id must be an integer")

        if not isinstance(text, str) or not text.strip():
            return

        vector = self._embed(text)
        self._vectors[doc_id] = vector

    def index_many(self, items: Iterable[Tuple[int, str]]) -> None:
        """
        Index multiple (doc_id, text) pairs.
        """
        for doc_id, text in items:
            self.index(doc_id, text)

    def remove(self, doc_id: int) -> None:
        """
        Remove a document from the index.
        """
        self._vectors.pop(doc_id, None)

    def clear(self) -> None:
        """
        Remove all indexed vectors.
        """
        self._vectors.clear()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, k: int = 5) -> List[Tuple[int, float]]:
        """
        Search for the top-k most similar documents.

        Returns:
            List of (doc_id, similarity_score), sorted descending.
        """
        if not isinstance(query, str) or not query.strip():
            return []

        if not self._vectors:
            return []

        query_vec = self._embed(query)

        scores: list[tuple[int, float]] = []
        for doc_id, vec in self._vectors.items():
            score = float(np.dot(vec, query_vec))
            scores.append((doc_id, score))

        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[: max(0, int(k))]

    # ------------------------------------------------------------------
    # Stats / Introspection
    # ------------------------------------------------------------------

    def size(self) -> int:
        """
        Number of indexed documents.
        """
        return len(self._vectors)

    def contains(self, doc_id: int) -> bool:
        """
        Check whether a document is indexed.
        """
        return doc_id in self._vectors

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> np.ndarray:
        """
        Embed and normalize text safely.
        """
        vec = self.embed_fn(text)

        if not isinstance(vec, np.ndarray):
            vec = np.asarray(vec, dtype=np.float32)

        if vec.ndim != 1:
            raise ValueError("Embedding vector must be 1‑dimensional")

        norm = np.linalg.norm(vec)
        if norm == 0.0:
            return vec.astype(np.float32)

        return (vec / norm).astype(np.float32)
