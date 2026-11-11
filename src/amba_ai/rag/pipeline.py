from __future__ import annotations

from .context import ContextAssembler
from .hybrid import HybridRetriever
from .models import RetrievalHit, RetrievalQuery
from .reranking import LexicalSemanticReranker


class ProductionRAGPipeline:
    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: LexicalSemanticReranker,
        assembler: ContextAssembler,
        minimum_confidence: float = 0.18,
    ) -> None:
        self.retriever = retriever
        self.reranker = reranker
        self.assembler = assembler
        self.minimum_confidence = minimum_confidence

    def retrieve(self, request: RetrievalQuery) -> tuple[list[RetrievalHit], float, bool]:
        """Retrieve and rerank only; generation belongs to GroundedAnswerService."""
        candidates = self.retriever.retrieve(request)
        hits = self.reranker.rerank(request.text, candidates, request.final_k)
        confidence = self._compute_epistemic_confidence(hits, request.text)
        return hits, confidence, bool(hits and confidence >= self.minimum_confidence)

    def _compute_epistemic_confidence(self, hits: list[RetrievalHit], query: str) -> float:
        if not hits:
            return 0.0

        top_score = max(0.0, min(1.0, hits[0].rerank_score or hits[0].score))
        mean_top_two = top_score
        if len(hits) > 1:
            second_score = max(0.0, min(1.0, hits[1].rerank_score or hits[1].score))
            mean_top_two = (top_score + second_score) / 2.0

        coverage = min(1.0, len(hits) / 3.0)
        q_words = set(query.lower().split())
        match_count = sum(1 for w in q_words if any(w in h.chunk.text.lower() for h in hits[:2]))
        lexical_coverage = match_count / max(1, len(q_words))

        raw_conf = 0.50 * mean_top_two + 0.30 * lexical_coverage + 0.20 * coverage
        return round(max(0.0, min(1.0, raw_conf)), 3)

    def _extract_available_breadcrumbs(self, hits: list[RetrievalHit]) -> list[str]:
        topics: list[str] = []
        for h in hits:
            if h.chunk.heading_path:
                topics.append(h.chunk.heading_path[-1])
            elif h.chunk.metadata.get("title"):
                topics.append(str(h.chunk.metadata.get("title")))
        return sorted(list(set(topics)))[:3]

    def _build_prompt(self, request: RetrievalQuery, context: str) -> str:
        instructions = (
            "You are AmbaAI, an offline educational tutor.\n"
            "Rules:\n"
            "1. Ground every statement entirely in the supplied SOURCES.\n"
            "2. Cite references precisely using [SOURCE n].\n"
            "3. If an answer cannot be completely derived from the sources, state what is missing.\n"
            "4. Explain concepts clearly, with step-by-step reasoning where applicable."
        )

        if request.pedagogical_mode == "socratic":
            instructions += (
                "\n5. Use Socratic questioning: explain the fundamental concept and ask the student "
                "a guiding question to verify their understanding."
            )

        return (
            f"{instructions}\n\n"
            f"SOURCES:\n{context}\n\n"
            f"STUDENT QUESTION:\n{request.text}\n\n"
            f"TUTOR ANSWER:\n"
        )

    def _generate_study_followups(self, hits: list[RetrievalHit]) -> list[str]:
        questions: list[str] = []
        for h in hits[:3]:
            for h_item in h.chunk.heading_path:
                if h_item and len(h_item) > 3:
                    questions.append(f"Would you like an explanation of {h_item}?")
        return list(dict.fromkeys(questions))[:2]