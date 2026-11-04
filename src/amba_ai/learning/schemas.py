from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "ambaai.learning-content.v2"


@dataclass(frozen=True, slots=True)
class SourceCitation:
    source_name: str
    page: int | None = None
    page_end: int | None = None
    chunk_id: str | None = None
    version: str | None = None
    quote: str | None = None
    section_ref: str | None = None
    confidence: float = 1.0

    @property
    def display(self) -> str:
        if self.page is not None and self.page_end is not None and self.page_end != self.page:
            loc = f"Pages {self.page}–{self.page_end}"
        elif self.page is not None:
            loc = f"Page {self.page}"
        elif self.section_ref:
            loc = self.section_ref
        else:
            loc = ""

        if loc:
            return f"{self.source_name} · {loc}"
        return self.source_name

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LearningConcept:
    concept_id: str
    name: str
    category: str
    definition: str
    why_it_matters: str = ""
    related_concepts: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    bloom_level: str = "understand"
    difficulty: str = "intermediate"
    examples: tuple[str, ...] = ()
    common_misconceptions: tuple[str, ...] = ()
    citations: tuple[SourceCitation, ...] = ()
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TechnicalBlock:
    block_id: str
    block_type: str
    label: str
    content: str
    explanation: str = ""
    language: str = "text"
    citations: tuple[SourceCitation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LearningSection:
    section_id: str
    heading: str
    explanation: str
    level: int = 2
    parent_id: str | None = None
    key_points: tuple[str, ...] = ()
    concepts: tuple[LearningConcept, ...] = ()
    technical_blocks: tuple[TechnicalBlock, ...] = ()
    examples: tuple[str, ...] = ()
    misconceptions: tuple[str, ...] = ()
    citations: tuple[SourceCitation, ...] = ()
    word_count: int = 0
    reading_time_minutes: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LearningDocument:
    document_id: int
    title: str
    source_name: str
    executive_summary: str
    learning_objectives: tuple[str, ...]
    concepts: tuple[LearningConcept, ...]
    sections: tuple[LearningSection, ...]
    citations: tuple[SourceCitation, ...]
    domain: str = "general"
    language: str = "en"
    target_grade_level: str = "all"
    estimated_study_time_minutes: int = 0
    bloom_distribution: dict[str, int] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "warning"
    location: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    valid: bool
    issues: tuple[ValidationIssue, ...] = ()
    quality_score: float = 1.0

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "info")

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "quality_score": self.quality_score,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }