from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import html
import re
from typing import Any


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class TutorPersona(str, Enum):
    SOCRATIC = "Socratic Tutor"
    SIMPLE = "Simple & Intuitive"
    TECHNICAL = "Code & Technical Deep Dive"
    EXAM_PREP = "Exam & Retention Coach"
    ACADEMIC = "Academic Tutor"

    @classmethod
    def values(cls) -> list[str]:
        return [item.value for item in cls]

    @classmethod
    def coerce(cls, value: str | None) -> TutorPersona:
        if value is None:
            return cls.SIMPLE
        for item in cls:
            if str(value).strip().lower() == item.value.lower() or str(value).strip().upper() == item.name:
                return item
        return cls.SIMPLE


@dataclass(frozen=True)
class TutorRequest:
    question: str
    document_id: int | None = None
    top_k: int = 5
    max_tokens: int = 900
    active_tab: str = "Tutor"
    active_document_title: str | None = None
    due_flashcards: int | None = None
    session_id: str | None = None
    target_language: str = "English"
    simple_language: bool = True
    persona: TutorPersona = TutorPersona.SIMPLE
    preferred_model: str = "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["persona"] = self.persona.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TutorRequest:
        source = dict(data or {})

        raw_document_id = source.get("document_id")
        document_id = (
            int(raw_document_id)
            if raw_document_id not in {None, "", 0, "0"}
            else None
        )

        raw_due_flashcards = source.get("due_flashcards")
        due_flashcards = (
            int(raw_due_flashcards)
            if raw_due_flashcards not in {None, "", 0, "0"}
            else None
        )

        return cls(
            question=str(source.get("question") or "").strip(),
            document_id=document_id,
            top_k=int(source.get("top_k") or 5),
            max_tokens=int(source.get("max_tokens") or 900),
            active_tab=str(source.get("active_tab") or "Tutor"),
            active_document_title=(
                str(source.get("active_document_title"))
                if source.get("active_document_title") is not None
                else None
            ),
            due_flashcards=due_flashcards,
            session_id=(
                str(source.get("session_id"))
                if source.get("session_id") is not None
                else None
            ),
            target_language=str(source.get("target_language") or "English"),
            simple_language=_coerce_bool(source.get("simple_language"), True),
            persona=TutorPersona.coerce(source.get("persona")),
            preferred_model=str(source.get("preferred_model") or "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"),
        )


@dataclass(frozen=True)
class TutorSourceViewModel:
    index: int
    source: str
    relevance_score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TutorCodeSnippet:
    code: str
    language: str = "bash"
    title: str = "Command Example"


@dataclass(frozen=True)
class TutorAnswerViewModel:
    question: str
    answer_text: str
    model_name: str
    sources: list[TutorSourceViewModel] = field(default_factory=list)
    document_id: int | None = None
    fallback: bool = False
    low_confidence: bool = False
    key_points: list[str] = field(default_factory=list)
    code_snippets: list[TutorCodeSnippet] = field(default_factory=list)
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["sources"] = [source.to_dict() for source in self.sources]
        data["code_snippets"] = [asdict(s) for s in self.code_snippets]
        return data

    @classmethod
    def from_answer_result(
        cls,
        result: Any,
        *,
        question: str,
        document_id: int | None,
        persona: TutorPersona = TutorPersona.SIMPLE,
    ) -> TutorAnswerViewModel:
        metadata = dict(getattr(result, "metadata", {}) or {})
        raw_sources = list(getattr(result, "sources", []) or [])

        sources = [
            TutorSourceViewModel(
                index=idx,
                source=str(source),
                relevance_score=1.0 - (idx * 0.08),
            )
            for idx, source in enumerate(raw_sources, start=1)
        ]

        raw_answer = str(getattr(result, "answer_text", "") or "")
        clean_answer, key_points, code_snippets = cls._parse_and_enrich_answer(
            raw_answer, question, persona
        )

        return cls(
            question=question,
            answer_text=clean_answer,
            model_name=str(getattr(result, "model_name", "") or "amba-local-tutor"),
            sources=sources,
            document_id=document_id,
            fallback=bool(metadata.get("fallback") or False),
            low_confidence=bool(metadata.get("is_low_confidence") or False),
            key_points=key_points,
            code_snippets=code_snippets,
            metadata=metadata,
        )

    @classmethod
    def build_synthetic_grounded_answer(
        cls,
        question: str,
        document_id: int | None,
        doc_context: str = "",
        persona: TutorPersona = TutorPersona.SIMPLE,
    ) -> TutorAnswerViewModel:
        context_clean = str(doc_context or "").strip()
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", context_clean)
            if len(s.strip()) > 25
        ]

        if sentences:
            summary = (
                f"Based on the active curriculum material for question '{question}':\n\n"
                f"{sentences[0]}"
            )
            if len(sentences) > 1:
                summary += f" {sentences[1]}"

            key_points = [
                s[:150] for s in sentences[1:5]
            ]
        else:
            summary = (
                f"Regarding your inquiry '{question}', the local curriculum repository establishes "
                "core principles documented in the active source text. Review the corresponding sections "
                "or consult with your teacher for further detail."
            )
            key_points = [
                "Consult the primary course textbook.",
                "Review foundational definitions in the summary module.",
            ]

        snippets: list[TutorCodeSnippet] = []
        code_matches = re.finditer(r"```([a-zA-Z0-9_-]*)\n(.*?)```", context_clean, flags=re.DOTALL)
        for cm in code_matches:
            snippets.append(
                TutorCodeSnippet(
                    code=cm.group(2).strip(),
                    language=cm.group(1).strip() or "text",
                    title="Source Example",
                )
            )

        sources = [
            TutorSourceViewModel(
                index=1,
                source=f"Document #{document_id or 'Local'} :: Curriculum Repository",
                relevance_score=0.98,
            )
        ]

        return cls(
            question=question,
            answer_text=summary,
            model_name="amba-cognitive-offline",
            sources=sources,
            document_id=document_id,
            fallback=True,
            key_points=key_points,
            code_snippets=snippets,
            metadata={"resilient_fallback": True, "dynamic": True},
        )

    @classmethod
    def _parse_and_enrich_answer(
        cls,
        raw_text: str,
        question: str,
        persona: TutorPersona,
    ) -> tuple[str, list[str], list[TutorCodeSnippet]]:
        text = str(raw_text or "").strip()
        text = re.sub(r"\[Page\s*\d+\]\s*", "", text, flags=re.IGNORECASE)

        code_snippets: list[TutorCodeSnippet] = []
        code_matches = re.finditer(r"```([a-zA-Z0-9_-]*)\n(.*?)```", text, flags=re.DOTALL)
        for cm in code_matches:
            lang = cm.group(1).strip() or "text"
            code_body = cm.group(2).strip()
            code_snippets.append(
                TutorCodeSnippet(
                    code=code_body,
                    language=lang,
                    title="Code / Data Example",
                )
            )

        clean_text = re.sub(r"```[a-zA-Z0-9_-]*\n.*?```", "", text, flags=re.DOTALL).strip()
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
        if not clean_text:
            clean_text = "Here is the concise explanation based on your grounded curriculum material."

        key_points: list[str] = []
        bullet_matches = re.findall(r"(?:^|\n)[-•*✦]\s*(.+?)(?=\n[-•*✦]|\n\n|\Z)", clean_text)
        if bullet_matches:
            key_points = [b.strip() for b in bullet_matches[:4] if len(b.strip()) > 5]

        return clean_text, key_points, code_snippets