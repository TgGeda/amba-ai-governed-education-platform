from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import faiss
import numpy as np

from amba_ai.governance.models import PolicyRecordIdentity
from amba_ai.governance.record_registry import PolicyRecordRegistry
from amba_ai.rag.policy_chunk_models import PolicyChunk, PolicyChunkError
from amba_ai.rag.policy_query import (
    PolicyQueryAdapter,
    PolicyQueryResult,
    build_policy_source_reference,
)
from amba_ai.rag.provenance import RetrievalProvenance


class EmbeddingEncoder(Protocol):
    @property
    def dimension(self) -> int: ...

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


class SentenceTransformerE5Encoder:
    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        dimension = self._model.get_sentence_embedding_dimension()
        if not isinstance(dimension, int) or dimension < 1:
            raise PolicyChunkError(
                "embedding model returned an invalid dimension"
            )
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode(
            tuple(texts),
            normalize_embeddings=True,
        )
        return np.ascontiguousarray(vectors, dtype=np.float32)


@dataclass(frozen=True, slots=True)
class PolicyChunkRetrievalHit:
    chunk_id: str
    document_id: str
    text: str
    source_ref: str
    score: float
    page_start: int
    page_end: int
    chunk_locator: str
    text_sha256: str

    def __post_init__(self) -> None:
        for field_name in (
            "chunk_id",
            "document_id",
            "text",
            "source_ref",
            "chunk_locator",
            "text_sha256",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise PolicyChunkError(
                    f"{field_name} must be a non-empty string"
                )
        if isinstance(self.score, bool) or not isinstance(
            self.score,
            float,
        ):
            raise TypeError("score must be a float")
        if not 0.0 <= self.score <= 1.0:
            raise PolicyChunkError("score must be between 0 and 1")
        for field_name in ("page_start", "page_end"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
        if self.page_start < 1 or self.page_end < self.page_start:
            raise PolicyChunkError("retrieval hit has an invalid page range")


class PolicyChunkIndex:
    def __init__(
        self,
        record_registry: PolicyRecordRegistry,
        encoder: EmbeddingEncoder,
        query_adapter: PolicyQueryAdapter | None = None,
    ) -> None:
        if not isinstance(record_registry, PolicyRecordRegistry):
            raise TypeError(
                "record_registry must be a PolicyRecordRegistry"
            )
        if not hasattr(encoder, "encode") or not hasattr(
            encoder,
            "dimension",
        ):
            raise TypeError(
                "encoder must implement dimension and encode(texts)"
            )
        if (
            isinstance(encoder.dimension, bool)
            or not isinstance(encoder.dimension, int)
            or encoder.dimension < 1
        ):
            raise PolicyChunkError(
                "encoder dimension must be a positive integer"
            )
        if query_adapter is not None:
            if not isinstance(query_adapter, PolicyQueryAdapter):
                raise TypeError(
                    "query_adapter must be a PolicyQueryAdapter or None"
                )
            if query_adapter.registry is not record_registry:
                raise PolicyChunkError(
                    "query_adapter and index must share one registry"
                )
        self._record_registry = record_registry
        self._query_adapter = query_adapter or PolicyQueryAdapter(
            record_registry
        )
        self._encoder = encoder
        self._index = faiss.IndexFlatIP(encoder.dimension)
        self._chunks: tuple[PolicyChunk, ...] = ()

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def query_adapter(self) -> PolicyQueryAdapter:
        return self._query_adapter

    def rebuild(self, chunks: Sequence[PolicyChunk]) -> int:
        by_id: dict[str, PolicyChunk] = {}
        eligible: list[PolicyChunk] = []
        passages: list[str] = []
        for chunk in chunks:
            if not isinstance(chunk, PolicyChunk):
                raise TypeError(
                    "chunks must contain only PolicyChunk values"
                )
            existing = by_id.get(chunk.identity.chunk_id)
            if existing is not None:
                if existing != chunk:
                    raise PolicyChunkError(
                        "conflicting chunk identity: "
                        f"{chunk.identity.chunk_id}"
                    )
                continue
            by_id[chunk.identity.chunk_id] = chunk
            identity = self._identity(chunk)
            record = self._record_registry.require(identity)
            if chunk.artifact_sha256 != record.artifact_sha256:
                raise PolicyChunkError(
                    "chunk artifact digest conflicts with PolicyRecord"
                )
            if not self._record_registry.eligible_for_citation(identity):
                continue
            eligible.append(chunk)
            passages.append(
                chunk.to_embedding_payload(record.document_title)
            )
        new_index = faiss.IndexFlatIP(self._encoder.dimension)
        if passages:
            vectors = self._validated_vectors(
                self._encoder.encode(passages),
                len(passages),
            )
            new_index.add(vectors)
        self._index = new_index
        self._chunks = tuple(eligible)
        return len(self._chunks)

    def search_hits(
        self,
        query_text: str,
        *,
        k: int = 5,
        min_score: float = 0.30,
    ) -> tuple[PolicyChunkRetrievalHit, ...]:
        query, limit, threshold = self._validate_search(
            query_text,
            k,
            min_score,
        )
        if not self._chunks:
            return ()
        query_vectors = self._validated_vectors(
            self._encoder.encode((f"query: {query}",)),
            1,
        )
        scores, indices = self._index.search(
            query_vectors,
            min(limit, len(self._chunks)),
        )
        hits: list[PolicyChunkRetrievalHit] = []
        for raw_score, position in zip(scores[0], indices[0]):
            if position < 0:
                continue
            score = max(0.0, min(1.0, float(raw_score)))
            if score < threshold:
                continue
            chunk = self._chunks[int(position)]
            identity = self._identity(chunk)
            record = self._record_registry.require(identity)
            provenance = RetrievalProvenance(
                source_id=identity.source_id,
                document_version_id=identity.version_id,
                policy_record_id=identity.record_id,
                chunk_id=chunk.identity.chunk_id,
                locator=record.official_locator,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
            )
            hits.append(
                PolicyChunkRetrievalHit(
                    chunk_id=chunk.identity.chunk_id,
                    document_id=str(identity),
                    text=chunk.raw_text,
                    source_ref=build_policy_source_reference(
                        provenance=provenance
                    ),
                    score=score,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chunk_locator=chunk.official_locator,
                    text_sha256=chunk.text_sha256,
                )
            )
        return tuple(hits)

    def search(
        self,
        query_text: str,
        *,
        k: int = 5,
        min_score: float = 0.30,
    ) -> tuple[PolicyQueryResult, ...]:
        hits = self.search_hits(
            query_text,
            k=k,
            min_score=min_score,
        )
        return self._query_adapter.adapt(hits, limit=k)

    @staticmethod
    def _identity(chunk: PolicyChunk) -> PolicyRecordIdentity:
        return PolicyRecordIdentity(
            record_id=chunk.identity.record_id,
            version_id=chunk.identity.version_id,
            source_id=chunk.identity.source_id,
        )

    @staticmethod
    def _validate_search(
        query_text: str,
        k: int,
        min_score: float,
    ) -> tuple[str, int, float]:
        if not isinstance(query_text, str):
            raise TypeError("query_text must be a string")
        query = " ".join(query_text.split())
        if not query:
            raise PolicyChunkError("query_text must not be empty")
        if isinstance(k, bool) or not isinstance(k, int):
            raise TypeError("k must be an integer")
        if k < 1:
            raise PolicyChunkError("k must be positive")
        if isinstance(min_score, bool) or not isinstance(
            min_score,
            (int, float),
        ):
            raise TypeError("min_score must be numeric")
        threshold = float(min_score)
        if not 0.0 <= threshold <= 1.0:
            raise PolicyChunkError(
                "min_score must be between 0 and 1"
            )
        return query, k, threshold

    def _validated_vectors(
        self,
        vectors: np.ndarray,
        expected_rows: int,
    ) -> np.ndarray:
        array = np.ascontiguousarray(vectors, dtype=np.float32)
        if array.ndim != 2:
            raise PolicyChunkError(
                "encoder output must be a two-dimensional array"
            )
        if array.shape != (
            expected_rows,
            self._encoder.dimension,
        ):
            raise PolicyChunkError("encoder output shape is invalid")
        if not np.isfinite(array).all():
            raise PolicyChunkError(
                "encoder output contains non-finite values"
            )
        norms = np.linalg.norm(array, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise PolicyChunkError(
                "encoder output contains a zero vector"
            )
        return np.ascontiguousarray(
            array / norms,
            dtype=np.float32,
        )
