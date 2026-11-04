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

        title = str(meta.get("title") or "")
        if not title:
            first_line = raw.split("\n")[0].strip()
            if first_line.startswith("#"):
                title = first_line.lstrip("#").strip()
            else:
                title_match = re.search(r"^(.*?)(?:The\s+jq\s+utility|is\s+not\s+just|\.|\n|$)", raw, flags=re.IGNORECASE)
                if title_match:
                    title = title_match.group(1).strip()
        if not title:
            title = "Command-Line Safety & Parsing"

        cleaned_text = re.sub(r"^#+\s*.*?\n", "", raw).strip()

        bottom_line = ""
        bl_match = re.search(r"(?:💎|💡|Bottom line:?)\s*(.*?)(?=\n|$)", cleaned_text, flags=re.IGNORECASE)
        if bl_match:
            bottom_line = bl_match.group(1).strip()
            cleaned_text = cleaned_text[:bl_match.start()] + cleaned_text[bl_match.end():]

        intro_match = re.search(r"^(.*?)(?=(?:🎯|🔍|🛡|⚡|📌|\b\d+\.|\n##|\n###))", cleaned_text, flags=re.DOTALL)
        if intro_match:
            exec_summary = intro_match.group(1).strip()
            rest = cleaned_text[intro_match.end():].strip()
        else:
            exec_summary = cleaned_text[:200].strip()
            rest = cleaned_text[200:].strip()

        sections: list[LessonSectionModel] = []

        step_pattern = re.compile(
            r"(?:🎯|🔍|🛡|⚡|📌|\b)\s*(\d+)\.\s*([^:\n]+)[:\.\-]?\s*(.*?)(?=(?:🎯|🔍|🛡|⚡|📌|\b)\s*\d+\.|\Z)",
            flags=re.DOTALL,
        )
        matches = list(step_pattern.finditer(rest))

        if matches:
            for m in matches:
                sec_title = m.group(2).strip()
                content = m.group(3).strip()

                code_snippets: list[dict[str, str]] = []
                codes = re.findall(r"(curl\s+-[^\n]+|cat\s+[^\n]+|diff\s+<[^\n]+|jq\s+[^\n]+)", content)
                for c in codes:
                    code_clean = c.strip().rstrip("'\"")
                    code_snippets.append({
                        "language": "bash",
                        "code": code_clean,
                        "title": "Terminal Execution",
                    })

                clean_content = content
                for c in codes:
                    clean_content = clean_content.replace(c, "").strip()
                clean_content = re.sub(r"['\"]{2,}", "", clean_content).strip()

                tags = []
                if "api" in sec_title.lower():
                    tags.extend(["API", "JSON"])
                if "secret" in sec_title.lower() or "token" in sec_title.lower():
                    tags.extend(["Security", "Regex"])
                if "config" in sec_title.lower() or "diff" in sec_title.lower():
                    tags.extend(["Diff", "DevOps"])

                sections.append(
                    LessonSectionModel(
                        title=sec_title,
                        summary_text=clean_content,
                        code_blocks=code_snippets,
                        tags=tags,
                        bottom_line=bottom_line if not sections else "",
                    )
                )
        else:
            code_snippets: list[dict[str, str]] = []
            codes = re.findall(r"(curl\s+-[^\n]+|cat\s+[^\n]+|diff\s+<[^\n]+|jq\s+[^\n]+)", rest)
            for c in codes:
                code_snippets.append({
                    "language": "bash",
                    "code": c.strip(),
                    "title": "Terminal Command",
                })

            sections.append(
                LessonSectionModel(
                    title=title,
                    summary_text=rest,
                    code_blocks=code_snippets,
                    bottom_line=bottom_line,
                )
            )

        citation = SourceCitation(source_name=source_badge or title)
        concepts = [
            LearningConcept(
                concept_id="concept_jq_filtering",
                name="jq filtering",
                category="CLI",
                definition="A lightweight and flexible command-line JSON processor.",
                why_it_matters="Enables reliable extraction without fragile regular expression parsing.",
                difficulty="beginner",
                citations=(citation,),
            ),
            LearningConcept(
                concept_id="concept_api_intelligence",
                name="API intelligence",
                category="API",
                definition="Extracting focused keys (id, email, roles) from response payloads.",
                why_it_matters="Reduces context tokens and filters out noisy metadata.",
                difficulty="intermediate",
                citations=(citation,),
            ),
            LearningConcept(
                concept_id="concept_regex_log_scanning",
                name="Regex log scanning",
                category="Security",
                definition="Traversing nested JSON hierarchies to identify leaked tokens.",
                why_it_matters="Allows security analysts to audit massive logs for high-entropy secrets.",
                difficulty="advanced",
                citations=(citation,),
            ),
        ]

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