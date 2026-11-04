from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from typing import Any, Protocol

from .models import Chunk, RetrievalHit, RetrievalQuery


class VectorSearch(Protocol):
    def __call__(self, query: str, k: int, filters: dict[str, Any]) -> list[tuple[Chunk, float]]: ...


class KeywordSearch(Protocol):
    def __call__(self, query: str, k: int, filters: dict[str, Any]) -> list[tuple[Chunk, float]]: ...


_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "he", "in", "is", "it", "its", "of", "on", "that", "the",
    "to", "was", "were", "will", "with", "this", "these", "those",
}


def _tokenize(text: str) -> list[str]:
    raw_tokens = re.findall(r"[a-zA-Z0-9]+(?:'[a-zA-Z]+)?", text.lower())
    result: list[str] = []
    for t in raw_tokens:
        if t in _STOP_WORDS or len(t) <= 1:
            continue
        if len(t) > 4 and t.endswith("ies"):
            result.append(t[:-3] + "y")
        elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            result.append(t[:-1])
        elif len(t) > 4 and t.endswith("ing"):
            result.append(t[:-3])
        elif len(t) > 3 and t.endswith("ed"):
            result.append(t[:-2])
        else:
            result.append(t)
    return result


def _matches_filters(chunk: Chunk, filters: dict[str, Any]) -> bool:
    if not filters:
        return True
    data = {**chunk.metadata, "document_id": chunk.document_id, "version_id": chunk.version_id}
    for key, expected in filters.items():
        actual = data.get(key)
        if isinstance(expected, (set, list, tuple)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


class InMemoryBM25:
    def __init__(self, chunks: Iterable[Chunk]) -> None:
        self.chunks = list(chunks)
        self.doc_count = len(self.chunks)
        self.doc_tokens: list[list[str]] = [_tokenize(c.text) for c in self.chunks]
        self.doc_lengths = [len(tokens) for tokens in self.doc_tokens]
        self.avgdl = sum(self.doc_lengths) / max(1, self.doc_count)

        self.inverted_index: dict[str, list[tuple[int, int]]] = {}
        for idx, tokens in enumerate(self.doc_tokens):
            counts = Counter(tokens)
            for term, freq in counts.items():
                self.inverted_index.setdefault(term, []).append((idx, freq))

        self.doc_freqs = {term: len(postings) for term, postings in self.inverted_index.items()}

    def search(self, query: str, k: int, filters: dict[str, Any]) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []

        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        idfs: dict[str, float] = {}
        for term in set(q_tokens):
            n = self.doc_freqs.get(term, 0)
            idfs[term] = math.log(1.0 + (self.doc_count - n + 0.5) / (n + 0.5))

        k1 = 1.2
        b = 0.75
        scores: dict[int, float] = {}

        for term in q_tokens:
            postings = self.inverted_index.get(term, [])
            term_idf = idfs[term]
            for doc_idx, freq in postings:
                dl = self.doc_lengths[doc_idx]
                denom = freq + k1 * (1.0 - b + b * (dl / max(0.1, self.avgdl)))
                score = term_idf * ((freq * (k1 + 1.0)) / denom)
                scores[doc_idx] = scores.get(doc_idx, 0.0) + score

        ranked: list[tuple[Chunk, float]] = []
        for doc_idx, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
            chunk = self.chunks[doc_idx]
            if _matches_filters(chunk, filters):
                ranked.append((chunk, score))
            if len(ranked) >= k:
                break

        return ranked


def reciprocal_rank_fusion(
    result_sets: list[list[tuple[Chunk, float]]],
    weights: list[float] | None = None,
    rank_constant: int = 60,
) -> list[RetrievalHit]:
    weights = weights or [1.0] * len(result_sets)
    fused_scores: dict[str, float] = {}
    chunk_store: dict[str, Chunk] = {}
    dense_scores: dict[str, float] = {}
    sparse_scores: dict[str, float] = {}

    for set_idx, results in enumerate(result_sets):
        w = weights[set_idx]
        for rank, (chunk, raw_score) in enumerate(results, start=1):
            cid = chunk.chunk_id
            chunk_store[cid] = chunk
            rrf_point = w / (rank_constant + rank)
            fused_scores[cid] = fused_scores.get(cid, 0.0) + rrf_point

            if set_idx == 0:
                dense_scores[cid] = raw_score
            else:
                sparse_scores[cid] = raw_score

    ranked_keys = sorted(fused_scores.keys(), key=lambda k: fused_scores[k], reverse=True)
    return [
        RetrievalHit(
            chunk=chunk_store[cid],
            score=fused_scores[cid],
            vector_score=dense_scores.get(cid, 0.0),
            keyword_score=sparse_scores.get(cid, 0.0),
            rank_reasons=["rrf_fusion"],
        )
        for cid in ranked_keys
    ]


class HybridRetriever:
    def __init__(
        self,
        vector_search: VectorSearch,
        keyword_search: KeywordSearch,
        vector_weight: float = 1.0,
        keyword_weight: float = 1.0,
    ) -> None:
        self.vector_search = vector_search
        self.keyword_search = keyword_search
        self.weights = [vector_weight, keyword_weight]

    def retrieve(self, request: RetrievalQuery) -> list[RetrievalHit]:
        v_results = self.vector_search(request.text, request.vector_k, request.filters)
        k_results = self.keyword_search(request.text, request.keyword_k, request.filters)
        return reciprocal_rank_fusion([v_results, k_results], self.weights)[: max(request.final_k * 4, request.final_k)]