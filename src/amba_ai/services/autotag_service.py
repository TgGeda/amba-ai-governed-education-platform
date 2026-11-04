from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from amba_ai.compute.edge_slm import OllamaClient
from amba_ai.config import OLLAMA_STRUCTURED_MODEL
from amba_ai.logger import logger


class TagLLMProtocol(Protocol):
    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> Any:
        ...


@dataclass(frozen=True)
class AutoTagResult:
    tags: list[str]
    method: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


class AutoTagService:
    MAX_INPUT_CHARS = 12_000
    MAX_TAGS = 12
    MIN_TAG_LENGTH = 2
    MAX_TAG_LENGTH = 32

    DEFAULT_ALLOWED_TAGS = {
        "agriculture", "ai", "algebra", "biology", "business",
        "chemistry", "civics", "computer science", "economics",
        "education", "english", "environment", "exam", "geography",
        "health", "history", "ict", "language", "math", "physics",
        "science", "social studies", "technology", "verified",
    }

    STOPWORDS = {
        "a", "about", "above", "after", "again", "against", "all", "also", "am",
        "an", "and", "any", "are", "as", "at", "be", "because", "been", "before",
        "being", "below", "between", "both", "but", "by", "can", "did", "do",
        "does", "doing", "down", "during", "each", "few", "for", "from",
        "further", "had", "has", "have", "having", "he", "her", "here", "hers",
        "him", "his", "how", "i", "if", "in", "into", "is", "it", "its",
        "itself", "just", "me", "more", "most", "my", "no", "nor", "not", "now",
        "of", "off", "on", "once", "only", "or", "other", "our", "out", "over",
        "own", "same", "she", "should", "so", "some", "such", "than", "that",
        "the", "their", "them", "then", "there", "these", "they", "this",
        "those", "through", "to", "too", "under", "until", "up", "very", "was",
        "we", "were", "what", "when", "where", "which", "while", "who", "whom",
        "why", "with", "would", "you", "your",
    }

    SUBJECT_KEYWORDS = {
        "agriculture": {"soil", "crop", "crops", "farm", "farming", "irrigation", "fertilizer", "harvest", "livestock", "rotation"},
        "biology": {"cell", "cells", "photosynthesis", "organism", "organisms", "plant", "plants", "animal", "animals", "gene", "genes", "dna", "respiration", "enzyme"},
        "chemistry": {"atom", "atoms", "molecule", "molecules", "reaction", "acid", "base", "compound", "chemical", "bond", "periodic"},
        "physics": {"force", "motion", "energy", "velocity", "acceleration", "mass", "gravity", "electricity", "magnet", "wave"},
        "math": {"equation", "algebra", "geometry", "calculus", "fraction", "ratio", "variable", "function", "probability", "statistics"},
        "history": {"king", "empire", "war", "revolution", "ancient", "colonial", "civilization", "historical", "dynasty"},
        "geography": {"map", "climate", "river", "mountain", "population", "region", "landform", "weather", "ecosystem"},
        "computer science": {"algorithm", "programming", "python", "software", "data", "database", "network", "computer", "code"},
        "ai": {"artificial intelligence", "machine learning", "neural", "model", "llm", "embedding", "rag", "classification"},
        "health": {"disease", "nutrition", "medicine", "health", "virus", "bacteria", "infection", "hygiene", "diet"},
        "exam": {"exam", "test", "quiz", "review", "assessment", "practice", "question", "answer"},
    }

    def __init__(
        self,
        llm: TagLLMProtocol | None = None,
        *,
        allowed_tags: Iterable[str] | None = None,
        max_tags: int = MAX_TAGS,
        use_llm: bool = True,
    ) -> None:
        self.llm = llm or OllamaClient(model=OLLAMA_STRUCTURED_MODEL)
        self.allowed_tags = self._normalize_allowed_tags(allowed_tags or self.DEFAULT_ALLOWED_TAGS)
        self.max_tags = max(1, min(int(max_tags), self.MAX_TAGS))
        self.use_llm = use_llm

    def suggest_tags(self, text: str, *, title: str | None = None) -> list[str]:
        return self.suggest_tags_result(text=text, title=title).tags

    def suggest_tags_result(self, text: str, *, title: str | None = None) -> AutoTagResult:
        clean_text = self._clean_text(text)
        clean_title = self._clean_text(title or "")

        if not clean_text and not clean_title:
            return AutoTagResult(tags=[], method="empty", confidence=0.0, metadata={"reason": "empty_input"})

        llm_tags: list[str] =[]

        if self.use_llm:
            try:
                llm_tags = self._suggest_with_llm(clean_text, clean_title)
            except Exception as exc:
                logger.warning(
                    "LLM auto-tagging failed; falling back to deterministic tagging",
                    extra={"context": {"error": str(exc)}},
                    exc_info=True,
                )

        if llm_tags:
            return AutoTagResult(
                tags=llm_tags,
                method="llm",
                confidence=0.85,
                metadata={
                    "title_length": len(clean_title),
                    "text_length": len(clean_text),
                    "model": OLLAMA_STRUCTURED_MODEL,
                },
            )

        fallback_tags = self._suggest_with_rules(f"{clean_title}\n\n{clean_text}")

        return AutoTagResult(
            tags=fallback_tags,
            method="rules",
            confidence=0.55 if fallback_tags else 0.0,
            metadata={
                "title_length": len(clean_title),
                "text_length": len(clean_text),
            },
        )

    def _suggest_with_llm(self, text: str, title: str) -> list[str]:
        prompt = self._build_llm_prompt(text=text, title=title)

        result = self.llm.generate(
            prompt=prompt,
            system=(
                "You are AmbaAI's offline library auto-tagging engine. "
                "You classify educational documents using short, reusable tags. "
                "Return valid JSON only."
            ),
            temperature=0.0,
            max_tokens=300,
            model=OLLAMA_STRUCTURED_MODEL,
        )

        response_text = getattr(result, "response_text", str(result))
        raw_tags = self._parse_llm_tags(response_text)
        return self._sanitize_tags(raw_tags)

    def _build_llm_prompt(self, *, text: str, title: str) -> str:
        allowed = ", ".join(sorted(self.allowed_tags))
        sample = text[: self.MAX_INPUT_CHARS]

        return f"""
Suggest up to {self.max_tags} tags for this educational document.

Rules:
- Return JSON only.
- Use lowercase tags.
- Prefer tags from the allowed list when appropriate.
- Tags must be short and reusable.
- Do not include full sentences.
- Do not invent private information.
- If unsure, return fewer tags.

Allowed tags:
{allowed}

Document title:
{title or "Untitled"}

Document excerpt:
{sample}

Return schema:
{{"tags": ["tag1", "tag2"]}}
""".strip()

    def _parse_llm_tags(self, response_text: str) -> list[str]:
        text = response_text.strip()

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                return[]
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                return[]

        if isinstance(payload, dict):
            tags = payload.get("tags",[])
        elif isinstance(payload, list):
            tags = payload
        else:
            return []

        if not isinstance(tags, list):
            return[]

        return [str(tag) for tag in tags]

    def _suggest_with_rules(self, text: str) -> list[str]:
        lowered = text.lower()
        found: list[str] =[]

        for tag, keywords in self.SUBJECT_KEYWORDS.items():
            if self._contains_keyword(lowered, keywords):
                found.append(tag)

        keyword_tags = self._extract_keyword_tags(lowered)
        found.extend(keyword_tags)

        return self._sanitize_tags(found)

    def _extract_keyword_tags(self, text: str) -> list[str]:
        words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
        candidates =[word.replace("-", " ").strip() for word in words if word not in self.STOPWORDS]
        counts = Counter(candidates)

        frequent =[word for word, count in counts.most_common(20) if count >= 2 and self.MIN_TAG_LENGTH <= len(word) <= self.MAX_TAG_LENGTH]
        return[word for word in frequent if word in self.allowed_tags]

    def _sanitize_tags(self, tags: Iterable[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()

        for tag in tags:
            normalized = self._normalize_tag(tag)
            if not normalized:
                continue

            if normalized not in self.allowed_tags and not self._is_safe_custom_tag(normalized):
                continue

            if normalized in seen:
                continue

            seen.add(normalized)
            cleaned.append(normalized)

            if len(cleaned) >= self.max_tags:
                break

        return cleaned

    def _normalize_tag(self, tag: str) -> str:
        normalized = " ".join(str(tag).lower().strip().split())
        normalized = re.sub(r"[^a-z0-9\s\-]", "", normalized)
        normalized = normalized.replace("_", " ")
        normalized = " ".join(normalized.split())

        if len(normalized) < self.MIN_TAG_LENGTH or len(normalized) > self.MAX_TAG_LENGTH:
            return ""

        return normalized

    def _is_safe_custom_tag(self, tag: str) -> bool:
        return bool(re.fullmatch(r"[a-z0-9][a-z0-9\s\-]{1,31}", tag)) and tag not in self.STOPWORDS

    @staticmethod
    def _contains_keyword(text: str, keywords: Iterable[str]) -> bool:
        for keyword in keywords:
            clean = keyword.lower().strip()
            if not clean:
                continue
            if " " in clean:
                if clean in text:
                    return True
            else:
                if re.search(rf"\b{re.escape(clean)}\b", text):
                    return True
        return False

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", str(text)).strip() if text else ""

    @staticmethod
    def _normalize_allowed_tags(tags: Iterable[str]) -> set[str]:
        normalized: set[str] = set()
        for tag in tags:
            clean = " ".join(str(tag).lower().strip().split())
            clean = re.sub(r"[^a-z0-9\s\-]", "", clean)
            clean = " ".join(clean.split())
            if clean:
                normalized.add(clean)
        return normalized
