from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
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


class NoteStyle(str, Enum):
    STUDENT = "Student Study Notes"
    TEACHER = "Teacher Review Notes"
    EXAM = "Exam Revision Notes"
    CORNELL = "Cornell Active Recall Notes"
    CHEATSHEET = "Command & Syntax Cheatsheet"

    @classmethod
    def values(cls) -> list[str]:
        return [item.value for item in cls]

    @classmethod
    def coerce(cls, value: str | None) -> NoteStyle:
        if value is None:
            return cls.STUDENT
        for item in cls:
            if str(value).strip().lower() == item.value.lower():
                return item
        return cls.STUDENT


@dataclass(frozen=True)
class NotesGenerationRequest:
    document_id: int
    force: bool = False
    target_language: str = "English"
    simple_language: bool = True
    teacher_review_required: bool = True
    preferred_model: str = "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"
    note_style: str = "Student Study Notes"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> NotesGenerationRequest:
        source = dict(data or {})
        return cls(
            document_id=int(source.get("document_id") or 0),
            force=_coerce_bool(source.get("force"), False),
            target_language=str(source.get("target_language") or "English"),
            simple_language=_coerce_bool(source.get("simple_language"), True),
            teacher_review_required=_coerce_bool(source.get("teacher_review_required"), True),
            preferred_model=str(source.get("preferred_model") or "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"),
            note_style=str(source.get("note_style") or "Student Study Notes"),
        )


@dataclass
class InteractiveCodeBlockModel:
    code: str
    language: str = "text"
    title: str = "Example / Code"
    description: str = ""


@dataclass
class StudyNoteCardModel:
    section_id: str
    title: str
    cue_question: str = ""
    summary_text: str = ""
    key_points: list[str] = field(default_factory=list)
    code_blocks: list[InteractiveCodeBlockModel] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    bottom_line: str = ""
    personal_note: str = ""
    is_mastered: bool = False


@dataclass
class ParsedStudyNotesBundle:
    title: str
    source_badge: str
    overview: str
    cards: list[StudyNoteCardModel]
    key_takeaway: str
    raw_markdown: str

    @classmethod
    def from_raw(cls, markdown: str, metadata: dict[str, Any] | None = None) -> ParsedStudyNotesBundle:
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
                title = "Study Notes & Reference"

        title = re.sub(r"^(?:Executive Summary|Structured Study Notes)\s*[:\-—]?\s*", "", title, flags=re.IGNORECASE).strip()
        if not title:
            title = "Study Notes & Reference"

        content = re.sub(r"^#+\s*.*?\n", "", raw).strip()

        sections_split = re.split(r"##\s+(?:Executive Summary|Structured Study Notes|Sources)", content, flags=re.IGNORECASE)
        working_content = ""
        for s in sections_split:
            clean_s = s.strip()
            if len(clean_s) > len(working_content):
                working_content = clean_s

        if not working_content:
            working_content = content

        key_takeaway = ""
        bl_match = re.search(r"(?:💎|💡|Bottom line:?)\s*(.*?)(?=\n|$)", working_content, flags=re.IGNORECASE)
        if bl_match:
            key_takeaway = bl_match.group(1).strip()
            working_content = working_content[:bl_match.start()] + working_content[bl_match.end():]

        overview_match = re.search(
            r"##\s*Executive\s*Summary\s*\n(.*?)(?=\n##|\Z)",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if overview_match:
            overview = overview_match.group(1).strip()
        else:
            first_p = working_content.split("\n\n")[0].strip() if working_content else ""
            overview = first_p[:200] if first_p else "Core structured curriculum study notes."

        cards: list[StudyNoteCardModel] = []
        raw_sections = re.split(r"(?m)^###?\s+", working_content)

        for i, sec in enumerate(raw_sections, 1):
            lines = [l.strip() for l in sec.splitlines() if l.strip()]
            if not lines:
                continue

            sec_title = lines[0]
            if re.search(r"^(Executive Summary|Sources)\b", sec_title, re.IGNORECASE):
                continue

            sec_body = "\n".join(lines[1:]).strip()

            code_snippets: list[InteractiveCodeBlockModel] = []
            code_matches = re.finditer(r"```([a-zA-Z0-9_-]*)\n(.*?)```", sec_body, flags=re.DOTALL)
            for cm in code_matches:
                lang = cm.group(1).strip() or "text"
                code_snippets.append(
                    InteractiveCodeBlockModel(
                        code=cm.group(2).strip(),
                        language=lang,
                        title=f"{sec_title} Code / Formula",
                    )
                )

            clean_text = re.sub(r"```[a-zA-Z0-9_-]*\n.*?```", "", sec_body, flags=re.DOTALL).strip()

            key_points = [
                pt.strip()
                for pt in re.findall(r"(?:^|\n)[-•*✦]\s*(.+?)(?=\n[-•*✦]|\n\n|\Z)", clean_text)
                if len(pt.strip()) > 5
            ]

            words = re.findall(r"\b[A-Z][a-zA-Z0-9]{3,}\b", sec_title)
            tags = list(dict.fromkeys(words))[:3]

            cue = f"What key principle is established in '{sec_title}'?"

            cards.append(
                StudyNoteCardModel(
                    section_id=f"note_sec_{i}",
                    title=sec_title,
                    cue_question=cue,
                    summary_text=clean_text[:1000],
                    key_points=key_points[:5],
                    code_blocks=code_snippets,
                    tags=tags,
                    bottom_line=key_takeaway if not cards else "",
                )
            )

        if not cards:
            cards.append(
                StudyNoteCardModel(
                    section_id="note_sec_1",
                    title=title,
                    cue_question=f"What are the core concepts covered in {title}?",
                    summary_text=working_content[:1200],
                    key_points=[],
                    code_blocks=[],
                    bottom_line=key_takeaway,
                )
            )

        return cls(
            title=title,
            source_badge=source_badge,
            overview=overview,
            cards=cards,
            key_takeaway=key_takeaway,
            raw_markdown=markdown,
        )


@dataclass(frozen=True)
class NotesViewModel:
    document_id: int
    markdown: str
    model_name: str
    note_style: str = "Student Study Notes"
    cached: bool = False
    fallback: bool = False
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_result(cls, result: Any, *, note_style: str) -> NotesViewModel:
        metadata = dict(getattr(result, "metadata", {}) or {})
        return cls(
            document_id=int(metadata.get("document_id") or 0),
            markdown=str(getattr(result, "markdown_notes", "") or ""),
            model_name=str(getattr(result, "model_name", "") or "unknown"),
            note_style=str(note_style or "Student Study Notes"),
            cached=bool(metadata.get("cached") or False),
            fallback=bool(metadata.get("fallback") or False),
            metadata=metadata,
        )