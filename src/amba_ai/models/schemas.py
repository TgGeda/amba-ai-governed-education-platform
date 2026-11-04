from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

DocumentKind = Literal[
    "pdf",
    "docx",
    "pptx",
    "text",
    "audio",
    "video",
    "youtube",
    "unknown",
]

ExportKind = Literal[
    "markdown",
    "flashcards_csv",
    "mcqs_csv",
    "anki_csv",
    "anki_apkg",
    "pdf",
    "audio",
]


@dataclass(frozen=True)
class IngestedDocument:
    title: str
    source_path: str
    kind: DocumentKind
    raw_text: str
    metadata: Mapping[str, Any] | None = field(default_factory=dict)
    id: int | None = None

    @property
    def document_id(self) -> int | None:
        return self.id

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("IngestedDocument.title must be non-empty.")
        if not self.source_path.strip():
            raise ValueError("IngestedDocument.source_path must be non-empty.")
        if not self.raw_text.strip():
            raise ValueError("IngestedDocument.raw_text must be non-empty.")
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})


@dataclass(frozen=True)
class IngestedDocumentResult:
    document: IngestedDocument
    document_id: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> int:
        return self.document_id


@dataclass(frozen=True)
class TextChunk:
    doc_id: int
    chunk_index: int
    text: str
    source_ref: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    heading_path: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: int | None = None

    @property
    def document_id(self) -> int:
        return self.doc_id

    @property
    def chunk_id(self) -> int | None:
        return self.id

    def __post_init__(self) -> None:
        if self.doc_id <= 0:
            raise ValueError("TextChunk.doc_id must be greater than zero.")
        if self.chunk_index < 0:
            raise ValueError("TextChunk.chunk_index must be greater than or equal to zero.")
        if not self.text.strip():
            raise ValueError("TextChunk.text must be non-empty.")


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int | None
    doc_id: int
    score: float
    text: str
    source_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def document_id(self) -> int:
        return self.doc_id

    def __post_init__(self) -> None:
        if self.doc_id <= 0:
            raise ValueError("RetrievedChunk.doc_id must be greater than zero.")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("RetrievedChunk.score must be normalized between 0.0 and 1.0.")
        if not self.text.strip():
            raise ValueError("RetrievedChunk.text must be non-empty.")


@dataclass(frozen=True)
class Summary:
    document_id: int
    summary_markdown: str
    model_name: str
    id: int | None = None
    created_at: str | None = None

    @property
    def doc_id(self) -> int:
        return self.document_id

    def __post_init__(self) -> None:
        if self.document_id <= 0:
            raise ValueError("Summary.document_id must be greater than zero.")
        if not self.summary_markdown.strip():
            raise ValueError("Summary.summary_markdown must be non-empty.")
        if not self.model_name.strip():
            raise ValueError("Summary.model_name must be non-empty.")


@dataclass(frozen=True)
class SummaryResult:
    markdown_notes: str
    model_name: str
    tokens_used: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.markdown_notes.strip():
            raise ValueError("SummaryResult.markdown_notes must be non-empty.")
        if not self.model_name.strip():
            raise ValueError("SummaryResult.model_name must be non-empty.")


@dataclass(frozen=True)
class Flashcard:
    question: str
    answer: str
    source_ref: str | None = None
    id: int | None = None
    document_id: int | None = None
    created_at: str | None = None

    @property
    def doc_id(self) -> int | None:
        return self.document_id

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("Flashcard.question must be non-empty.")
        if not self.answer.strip():
            raise ValueError("Flashcard.answer must be non-empty.")


@dataclass(frozen=True)
class MCQ:
    question: str
    choices: list[str]
    correct_answer: str
    explanation: str
    source_ref: str | None = None
    id: int | None = None
    document_id: int | None = None
    created_at: str | None = None

    @property
    def doc_id(self) -> int | None:
        return self.document_id

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("MCQ.question must be non-empty.")
        if len(self.choices) != 4:
            raise ValueError("MCQ.choices must contain exactly 4 choices.")

        normalized_choices = [choice.strip() for choice in self.choices]
        if any(not choice for choice in normalized_choices):
            raise ValueError("MCQ.choices cannot contain empty strings.")
        if len(set(normalized_choices)) != 4:
            raise ValueError("MCQ.choices must be unique.")
        if self.correct_answer.strip() not in normalized_choices:
            raise ValueError("MCQ.correct_answer must exactly match one choice.")
        if not self.explanation.strip():
            raise ValueError("MCQ.explanation must be non-empty.")

        object.__setattr__(self, "choices", normalized_choices)
        object.__setattr__(self, "correct_answer", self.correct_answer.strip())
        object.__setattr__(self, "question", self.question.strip())
        object.__setattr__(self, "explanation", self.explanation.strip())


@dataclass(frozen=True)
class StudyAssetsResult:
    flashcards: list[Flashcard] = field(default_factory=list)
    mcqs: list[MCQ] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def flashcard_count(self) -> int:
        return len(self.flashcards)

    @property
    def mcq_count(self) -> int:
        return len(self.mcqs)


@dataclass(frozen=True)
class AnswerResult:
    answer_text: str
    sources: list[str] = field(default_factory=list)
    model_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.answer_text.strip():
            raise ValueError("AnswerResult.answer_text must be non-empty.")


@dataclass(frozen=True)
class ExportResult:
    path: Path
    kind: ExportKind
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            object.__setattr__(self, "path", Path(self.path))
        if not str(self.path).strip():
            raise ValueError("ExportResult.path must be non-empty.")


@dataclass(frozen=True)
class ChatLog:
    role: str
    message: str
    context: list[dict[str, Any]] = field(default_factory=list)
    id: int | None = None
    created_at: str | None = None

    def __post_init__(self) -> None:
        if not self.role.strip():
            raise ValueError("ChatLog.role must be non-empty.")
        if not self.message.strip():
            raise ValueError("ChatLog.message must be non-empty.")


@dataclass(frozen=True)
class HITLFeedback:
    item_type: str
    item_id: int | None = None
    rating: int | None = None
    comment: str | None = None
    anonymized_payload: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    created_at: str | None = None

    def __post_init__(self) -> None:
        if not self.item_type.strip():
            raise ValueError("HITLFeedback.item_type must be non-empty.")
        if self.rating is not None and not 1 <= self.rating <= 5:
            raise ValueError("HITLFeedback.rating must be between 1 and 5.")