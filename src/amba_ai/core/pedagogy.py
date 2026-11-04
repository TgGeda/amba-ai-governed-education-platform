from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from amba_ai.logger import logger


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PedagogicalResponse:
    """
    Final pedagogically formatted response returned to the UI.
    """
    raw_answer: str
    formatted_answer: str
    citations: list[str]
    is_low_confidence: bool


# ---------------------------------------------------------------------------
# Pedagogical Formatter
# ---------------------------------------------------------------------------

class PedagogicalFormatter:
    """
    Pedagogical guardrail for AmbaAI responses.

    Responsibilities:
    - Detect low‑confidence / uncertain answers
    - Extract curriculum citations from retrieved context
    - Produce a student‑friendly, structured Markdown layout

    This class is intentionally stateless and side‑effect free.
    """

    UNCERTAINTY_PATTERNS = [
        r"\bi am not sure\b",
        r"\bi'm not sure\b",
        r"\bit is possible that\b",
        r"\bmight be\b",
        r"\bcould be\b",
        r"\bi do not know\b",
        r"\bi don't know\b",
        r"\blimited information\b",
        r"\bcannot verify\b",
        r"\buncertain\b",
    ]

    MIN_CONFIDENT_WORD_COUNT = 10

    def __init__(self) -> None:
        self._uncertainty_regex = re.compile(
            "|".join(self.UNCERTAINTY_PATTERNS),
            flags=re.IGNORECASE,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format_response(
        self,
        raw_llm_answer: str,
        retrieved_context: Sequence[Any] | None = None,
    ) -> PedagogicalResponse:
        """
        Convert raw LLM output into a pedagogically safe, student‑ready response.

        Args:
            raw_llm_answer:
                The direct text output from the LLM.
            retrieved_context:
                Iterable of retrieved knowledge objects (RAG chunks).
                Items may be LangChain Documents or plain dicts.

        Returns:
            PedagogicalResponse
        """
        text = self._normalize_text(raw_llm_answer)

        is_low_confidence = self._detect_low_confidence(text)
        if is_low_confidence:
            logger.warning(
                "Low confidence detected in AI response",
                extra={"context": {"length": len(text)}},
            )

        citations = self._extract_citations(retrieved_context or [])
        formatted = self._build_layout(
            answer=text,
            citations=citations,
            flagged=is_low_confidence,
        )

        return PedagogicalResponse(
            raw_answer=raw_llm_answer,
            formatted_answer=formatted,
            citations=citations,
            is_low_confidence=is_low_confidence,
        )

    # ------------------------------------------------------------------
    # Confidence Detection
    # ------------------------------------------------------------------

    def _detect_low_confidence(self, text: str) -> bool:
        """
        Heuristically detect uncertain or weak answers.

        Rules:
        - Explicit uncertainty language
        - Extremely short responses
        """
        if not text:
            return True

        if self._uncertainty_regex.search(text):
            return True

        if len(text.split()) < self.MIN_CONFIDENT_WORD_COUNT:
            return True

        return False

    # ------------------------------------------------------------------
    # Citation Handling
    # ------------------------------------------------------------------

    def _extract_citations(self, context_items: Iterable[Any]) -> list[str]:
        """
        Extract unique, human‑readable citations from retrieved context.

        Supports:
        - LangChain Document‑like objects (metadata attr)
        - Plain dict objects
        """
        citations: set[str] = set()

        for item in context_items:
            metadata = self._get_metadata(item)

            source = metadata.get("source") or metadata.get("title") or "Curriculum Source"
            page = metadata.get("page")

            if page not in (None, "", "N/A"):
                citations.add(f"{source} (Page {page})")
            else:
                citations.add(str(source))

        return sorted(citations)

    @staticmethod
    def _get_metadata(item: Any) -> Mapping[str, Any]:
        """
        Safely extract metadata from different document representations.
        """
        if hasattr(item, "metadata") and isinstance(item.metadata, Mapping):
            return item.metadata

        if isinstance(item, Mapping):
            return item.get("metadata", {}) if isinstance(item.get("metadata"), Mapping) else {}

        return {}

    # ------------------------------------------------------------------
    # Layout Construction
    # ------------------------------------------------------------------

    def _build_layout(
        self,
        *,
        answer: str,
        citations: Sequence[str],
        flagged: bool,
    ) -> str:
        """
        Build final Markdown layout for UI rendering.
        """
        sections: list[str] = []

        if flagged:
            sections.append(
                "> ⚠️ **Note:** *AmbaAI is uncertain about this answer and recommends teacher verification.*\n"
            )

        sections.append(answer.strip())

        if citations:
            sections.append("\n---\n**📚 Curriculum Sources:**")
            for idx, citation in enumerate(citations, start=1):
                sections.append(f"{idx}. *{citation}*")

        return "\n".join(sections).strip()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize LLM output:
        - Strip excess whitespace
        - Collapse repeated newlines
        """
        if not text:
            return ""

        cleaned = re.sub(r"\n{3,}", "\n\n", text.strip())
        return cleaned