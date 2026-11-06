from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import faiss
import numpy as np

from amba_ai.governance.models import PolicyRecordIdentity
from amba_ai.governance.record_registry import PolicyRecordRegistry
from amba_ai.rag.policy_chunk_models import (
    GroundedChunkRetrievalResult,
    PolicyChunk,
    PolicyChunkError,
)


class EmbeddingEncoder(Protocol):
    @property
    def dimension(self) -> int: ...
    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


class SentenceTransformerE5Encoder:
    def __init__(self, model_name: str = "intfloat/multilingual-e5-small") -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)
        dimension = self._model.get_sentence_embedding_dimension()
        if not isinstance(dimension, int) or dimension < 1:
            raise PolicyChunkError("embedding model returned an invalid dimension")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode(tuple(texts), normalize_embeddings=True)
        return np.ascontiguousarray(vectors, dtype=np.float32)


class PolicyChunkIndex:
    def __init__(self, record_registry: PolicyRecordRegistry, encoder: EmbeddingEncoder) -> None:
        if not isinstance(record_registry, PolicyRecordRegistry):
            raise TypeError("record_registry must be a PolicyRecordRegistry")
        if not hasattr(encoder, "encode") or not hasattr(encoder, "dimension"):
            raise TypeError("encoder must implement dimension and encode(texts)")
        if isinstance(encoder.dimension, bool) or not isinstance(encoder.dimension, int) or encoder.dimension < 1:
            raise PolicyChunkError("encoder dimension must be a positive integer")
        self._record_registry = record_registry
        self._encoder = encoder
        self._index = faiss.IndexFlatIP(encoder.dimension)
        self._chunks: tuple[PolicyChunk, ...] = ()

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def rebuild(self, chunks: Sequence[PolicyChunk]) -> int:
        by_id: dict[str, PolicyChunk] = {}
        eligible: list[PolicyChunk] = []
        passages: list[str] = []
        for chunk in chunks:
            if not isinstance(chunk, PolicyChunk):
                raise TypeError("chunks must contain only PolicyChunk values")
            existing = by_id.get(chunk.identity.chunk_id)
            if existing is not None:
                if existing != chunk:
                    raise PolicyChunkError(f"conflicting chunk identity: {chunk.identity.chunk_id}")
                continue
            by_id[chunk.identity.chunk_id] = chunk
            identity = PolicyRecordIdentity(
                record_id=chunk.identity.record_id,
                version_id=chunk.identity.version_id,
                source_id=chunk.identity.source_id,
            )
            record = self._record_registry.require(identity)
            if chunk.artifact_sha256 != record.artifact_sha256:
                raise PolicyChunkError("chunk artifact digest conflicts with PolicyRecord")
            if not self._record_registry.eligible_for_citation(identity):
                continue
            eligible.append(chunk)
            passages.append(chunk.to_embedding_payload(record.document_title))
        new_index = faiss.IndexFlatIP(self._encoder.dimension)
        if passages:
            vectors = self._validated_vectors(self._encoder.encode(passages), len(passages))
            new_index.add(vectors)
        self._index = new_index
        self._chunks = tuple(eligible)
        return len(self._chunks)

    def search(
        self,
        query_text: str,
        *,
        k: int = 5,
        min_score: float = 0.30,
    ) -> tuple[GroundedChunkRetrievalResult, ...]:
        if not isinstance(query_text, str):
            raise TypeError("query_text must be a string")
        query = " ".join(query_text.split())
        if not query:
            raise PolicyChunkError("query_text must not be empty")
        if isinstance(k, bool) or not isinstance(k, int):
            raise TypeError("k must be an integer")
        if k < 1:
            raise PolicyChunkError("k must be positive")
        if isinstance(min_score, bool) or not isinstance(min_score, (int, float)):
            raise TypeError("min_score must be numeric")
        threshold = float(min_score)
        if not 0.0 <= threshold <= 1.0:
            raise PolicyChunkError("min_score must be between 0 and 1")
        if not self._chunks:
            return ()
        query_vectors = self._validated_vectors(self._encoder.encode((f"query: {query}",)), 1)
        scores, indices = self._index.search(query_vectors, min(k, len(self._chunks)))
        results: list[GroundedChunkRetrievalResult] = []
        for score, position in zip(scores[0], indices[0]):
            if position < 0 or float(score) < threshold:
                continue
            chunk = self._chunks[int(position)]
            identity = PolicyRecordIdentity(
                record_id=chunk.identity.record_id,
                version_id=chunk.identity.version_id,
                source_id=chunk.identity.source_id,
            )
            record = self._record_registry.require(identity)
            if not self._record_registry.eligible_for_citation(identity):
                continue
            results.append(
                GroundedChunkRetrievalResult(
                    chunk=chunk,
                    binding_level=record.binding_level,
                    activation_status=record.activation_status,
                    national_binding_status=record.national_binding_status,
                    legal_review_status=record.legal_review_status,
                    locator_verification_status=record.locator_verification_status,
                    eligible_for_project_enforcement=record.eligible_for_project_enforcement,
                    eligible_for_national_legal_finding=record.eligible_for_national_legal_finding,
                    eligible_for_citation=record.eligible_for_citation,
                    retrieval_score=float(score),
                    retrieval_rank=len(results) + 1,
                )
            )
        return tuple(results)

    def _validated_vectors(self, vectors: np.ndarray, expected_rows: int) -> np.ndarray:
        array = np.ascontiguousarray(vectors, dtype=np.float32)
        if array.ndim != 2:
            raise PolicyChunkError("encoder output must be a two-dimensional array")
        if array.shape != (expected_rows, self._encoder.dimension):
            raise PolicyChunkError("encoder output shape is invalid")
        if not np.isfinite(array).all():
            raise PolicyChunkError("encoder output contains non-finite values")
        norms = np.linalg.norm(array, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise PolicyChunkError("encoder output contains a zero vector")
        return np.ascontiguousarray(array / norms, dtype=np.float32)
