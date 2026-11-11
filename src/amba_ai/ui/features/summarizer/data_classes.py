from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from typing import Any

from amba_ai.learning.schemas import LearningConcept, SourceCitation


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class SummaryMode(str, Enum):
    SHORT = "Short Summary"
    DETAILED = "Detailed Summary"
    KEY_CONCEPTS = "Key Concepts"
    TEACHER_REVIEW = "Teacher Review Draft"
    LEARNER_FRIENDLY = "Learner-Friendly Summary"

    @classmethod
    def values(cls) -> list[str]:
        return [item.value for item in cls]

    @classmethod
    def coerce(cls, value: str | None) -> SummaryMode:
        if value is None:
            return cls.DETAILED
        for item in cls:
            if str(value).strip().lower() == item.value.lower():
                return item
        return cls.DETAILED


SummarizerMode = SummaryMode


@dataclass(frozen=True)
class SummarizerRequest:
    document_id: int
    mode: SummaryMode = SummaryMode.DETAILED
    force: bool = False
    target_language: str = "English"
    simple_language: bool = True
    teacher_review_required: bool = True
    max_context_tokens: int = 2048
    preferred_model: str = "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SummarizerRequest:
        source = dict(data or {})
        return cls(
            document_id=int(source.get("document_id") or 0),
            mode=SummaryMode.coerce(source.get("mode")),
            force=_coerce_bool(source.get("force"), False),
            target_language=str(source.get("target_language") or "English"),
            simple_language=_coerce_bool(source.get("simple_language"), True),
            teacher_review_required=_coerce_bool(source.get("teacher_review_required"), True),
            max_context_tokens=int(source.get("max_context_tokens") or 2048),
            preferred_model=str(source.get("preferred_model") or "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"),
        )


@dataclass
class LessonSectionModel:
    title: str
    summary_text: str = ""
    key_points: list[str] = field(default_factory=list)
    code_blocks: list[dict[str, str]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    bottom_line: str = ""


@dataclass
class ParsedLessonBundle:
    title: str
    source_badge: str
    executive_summary: str
    sections: list[LessonSectionModel]
    concepts: list[LearningConcept]
    raw_text: str

    @classmethod
    def from_raw(cls, markdown: str, metadata: dict[str, Any] | None = None) -> ParsedLessonBundle:
        meta = dict(metadata or {})
        raw = str(markdown or "").strip()

        source_badge = ""
        page_match = re.search(r"\[Page\s*(\d+)\]", raw, flags=re.IGNORECASE)
        if page_match:
            source_badge = f"Page {page_match.group(1)}"
            raw = re.sub(r"\[Page\s*\d+\]\s*", "", raw, flags=re.IGNORECASE).strip()

        title = str(meta.get("title") or "").strip()
        if not title:
            first_line = raw.split("\n")[0].strip() if raw else ""
            if first_line.startswith("#"):
                title = first_line.lstrip("#").strip()
            else:
                title = "Curriculum Study Material"

        cleaned_text = re.sub(r"^#+\s*.*?\n", "", raw).strip()

        bottom_line = ""
        bl_match = re.search(r"(?:💎|💡|Bottom line:?)\s*(.*?)(?=\n|$)", cleaned_text, flags=re.IGNORECASE)
        if bl_match:
            bottom_line = bl_match.group(1).strip()
            cleaned_text = cleaned_text[:bl_match.start()] + cleaned_text[bl_match.end():]

        intro_match = re.search(
            r"##\s*Executive\s*Summary\s*\n(.*?)(?=\n##|\Z)",
            cleaned_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if intro_match:
            exec_summary = intro_match.group(1).strip()
        else:
            first_paragraph = cleaned_text.split("\n\n")[0].strip()
            exec_summary = first_paragraph[:300] if first_paragraph else "Curriculum lesson summary."

        sections: list[LessonSectionModel] = []
        raw_sections = re.split(r"(?m)^##\s+", cleaned_text)

        for sec in raw_sections:
            lines = [l.strip() for l in sec.splitlines() if l.strip()]
            if not lines:
                continue

            sec_title = lines[0]
            if re.search(r"^(Executive Summary|Sources)\b", sec_title, re.IGNORECASE):
                continue

            content = "\n".join(lines[1:]).strip()

            code_snippets: list[dict[str, str]] = []
            code_matches = re.finditer(r"```([a-zA-Z0-9_-]*)\n(.*?)```", content, flags=re.DOTALL)
            for cm in code_matches:
                lang = cm.group(1).strip() or "text"
                code_text = cm.group(2).strip()
                code_snippets.append({
                    "language": lang,
                    "code": code_text,
                    "title": f"{sec_title} Code Example",
                })

            clean_content = re.sub(r"```[a-zA-Z0-9_-]*\n.*?```", "", content, flags=re.DOTALL).strip()

            key_points = [
                pt.strip()
                for pt in re.findall(r"(?:^|\n)[-•*✦]\s*(.+?)(?=\n[-•*✦]|\n\n|\Z)", clean_content)
                if len(pt.strip()) > 5
            ]

            words = re.findall(r"\b[A-Z][a-zA-Z0-9]{3,}\b", sec_title)
            tags = list(dict.fromkeys(words))[:3]

            sections.append(
                LessonSectionModel(
                    title=sec_title,
                    summary_text=clean_content[:1000],
                    key_points=key_points[:5],
                    code_blocks=code_snippets,
                    tags=tags,
                    bottom_line=bottom_line if not sections else "",
                )
            )

        if not sections:
            sections.append(
                LessonSectionModel(
                    title=title,
                    summary_text=cleaned_text[:1200],
                    key_points=[],
                    code_blocks=[],
                    bottom_line=bottom_line,
                )
            )

        citation = SourceCitation(source_name=source_badge or title)
        concepts: list[LearningConcept] = []

        concepts_match = re.search(
            r"##\s*Core\s*Concepts\s*\n(.*?)(?=\n##|\Z)",
            cleaned_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if concepts_match:
            concept_lines = [
                l.strip()
                for l in concepts_match.group(1).splitlines()
                if l.strip().startswith(("-", "*", "•"))
            ]
            for idx, line in enumerate(concept_lines[:5], start=1):
                clean_line = re.sub(r"^[-*•]\s*", "", line)
                parts = re.split(r"[:\-—]\s*", clean_line, maxsplit=1)
                name = parts[0].strip().replace("**", "")
                definition = parts[1].strip() if len(parts) > 1 else clean_line
                concepts.append(
                    LearningConcept(
                        concept_id=f"concept_{re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())[:30]}",
                        name=name,
                        category="Core Concept",
                        definition=definition,
                        why_it_matters="Foundational principle established in primary curriculum source.",
                        difficulty="intermediate",
                        citations=(citation,),
                    )
                )

        if not concepts:
            concepts.append(
                LearningConcept(
                    concept_id=f"concept_{re.sub(r'[^a-zA-Z0-9_]', '_', title.lower())[:30]}",
                    name=title,
                    category="Core Curriculum",
                    definition="Primary subject matter documented in current lesson.",
                    why_it_matters="Establishes essential domain competence.",
                    difficulty="beginner",
                    citations=(citation,),
                )
            )

        return cls(
            title=title,
            source_badge=source_badge,
            executive_summary=exec_summary,
            sections=sections,
            concepts=concepts,
            raw_text=raw,
        )


@dataclass(frozen=True)
class SummaryViewModel:
    document_id: int
    markdown: str
    model_name: str
    mode: str
    cached: bool = False
    fallback: bool = False
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_summary_result(cls, result: Any, *, mode: str) -> SummaryViewModel:
        metadata = dict(getattr(result, "metadata", {}) or {})
        return cls(
            document_id=int(metadata.get("document_id") or 0),
            markdown=str(getattr(result, "markdown_notes", "") or ""),
            model_name=str(getattr(result, "model_name", "") or "unknown"),
            mode=str(mode),
            cached=bool(metadata.get("cached") or False),
            fallback=bool(metadata.get("fallback") or False),
            metadata=metadata,
        )