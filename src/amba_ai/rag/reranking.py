from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable

from .models import RetrievalHit


class LexicalSemanticReranker:
    def __init__(
        self,
        external_reranker: Callable[[str, list[str]], list[float]] | None = None,
    ) -> None:
        self.external_reranker = external_reranker

    def rerank(self, query: str, hits: list[RetrievalHit], top_k: int) -> list[RetrievalHit]:
        if not hits:
            return []

        q_tokens = self._tokenize(query)
        q_counter = Counter(q_tokens)

        if self.external_reranker is not None:
            raw_scores = self.external_reranker(query, [h.chunk.text for h in hits])
        else:
            raw_scores = [self._compute_lexical_alignment(q_tokens, q_counter, h) for h in hits]

        max_raw = max(raw_scores) if raw_scores else 1.0
        min_raw = min(raw_scores) if raw_scores else 0.0
        spread = (max_raw - min_raw) or 1.0

        for hit, raw_score in zip(hits, raw_scores):
            norm_rerank = (raw_score - min_raw) / spread
            hit.rerank_score = float(norm_rerank)
            hit.score = float(0.40 * hit.score + 0.60 * norm_rerank)
            hit.rank_reasons.append("lexical_reranked")

        return sorted(hits, key=lambda h: h.score, reverse=True)[:top_k]

    def _compute_lexical_alignment(
        self,
        q_tokens: list[str],
        q_counter: Counter[str],
        hit: RetrievalHit,
    ) -> float:
        chunk = hit.chunk
        doc_tokens = self._tokenize(chunk.text)
        if not doc_tokens:
            return 0.0

        doc_counter = Counter(doc_tokens)
        cosine = self._cosine_similarity(q_counter, doc_counter)

        heading_text = " ".join(chunk.heading_path).lower()
        title_text = str(chunk.metadata.get("title", "")).lower()
        heading_boost = 0.0
        for token in q_tokens:
            if token in heading_text:
                heading_boost += 0.15
            if token in title_text:
                heading_boost += 0.10

        phrase_boost = 0.0
        clean_chunk = chunk.text.lower()
        clean_query = " ".join(q_tokens).strip()
        if len(q_tokens) >= 2 and clean_query in clean_chunk:
            phrase_boost = 0.30

        return cosine + heading_boost + phrase_boost

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [t for t in re.findall(r"[a-zA-Z0-9]+", text.lower()) if len(t) > 1]

    @staticmethod
    def _cosine_similarity(a: Counter[str], b: Counter[str]) -> float:
        intersection = a.keys() & b.keys()
        if not intersection:
            return 0.0
        dot = sum(a[k] * b[k] for k in intersection)
        na = sum(v * v for v in a.values()) ** 0.5
        nb = sum(v * v for v in b.values()) ** 0.5
        return (dot / (na * nb)) if (na and nb) else 0.0