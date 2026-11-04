from __future__ import annotations

import csv
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Sequence
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from amba_ai.config import STUDY_PACKS_DIR
from amba_ai.core.learning_pack import (
    build_learning_bundle,
    create_quiz_pdf,
    create_study_card_png,
    create_study_guide_pdf,
)
from amba_ai.exceptions import ExportError
from amba_ai.logger import logger
from amba_ai.models.schemas import ExportResult, Flashcard, MCQ

__all__ = [
    "export_markdown",
    "export_flashcards_csv",
    "export_pdf",
    "export_mcqs_csv",
    "build_learning_bundle",
    "create_quiz_pdf",
    "create_study_card_png",
    "create_study_guide_pdf",
]


def _context(
    *,
    operation: str,
    filename: str | None = None,
    path: Path | None = None,
    kind: str | None = None,
    item_count: int | None = None,
    text_length: int | None = None,
    title_length: int | None = None,
    body_length: int | None = None,
    paragraph_count: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    context: dict[str, Any] = {"operation": operation}

    if filename is not None:
        context["filename"] = filename
    if path is not None:
        context["path"] = str(path)
    if kind is not None:
        context["kind"] = kind
    if item_count is not None:
        context["item_count"] = item_count
    if text_length is not None:
        context["text_length"] = text_length
    if title_length is not None:
        context["title_length"] = title_length
    if body_length is not None:
        context["body_length"] = body_length
    if paragraph_count is not None:
        context["paragraph_count"] = paragraph_count

    context.update(extra)
    return context


def _ensure_export_dir() -> Path:
    try:
        STUDY_PACKS_DIR.mkdir(parents=True, exist_ok=True)
        return STUDY_PACKS_DIR
    except OSError as exc:
        context = _context(
            operation="ensure_export_dir",
            path=STUDY_PACKS_DIR,
            kind="directory",
            error_type="file_io_error",
        )
        logger.exception("Failed to create study packs directory", extra={"context": context})
        raise ExportError("Failed to create study packs directory.", context=context) from exc


def _resolve_export_path(filename: str, suffix: str) -> Path:
    if not isinstance(filename, str) or not filename.strip():
        raise ExportError(
            "Export filename must be a non-empty string.",
            context=_context(
                operation="resolve_export_path",
                filename=filename,
                kind=suffix.lstrip("."),
                error_type="validation_error",
            ),
        )

    if not suffix.startswith("."):
        suffix = f".{suffix}"

    export_dir = _ensure_export_dir()
    path = export_dir / filename.strip()

    if path.suffix.lower() != suffix.lower():
        path = path.with_suffix(suffix)

    return path


def _build_export_result(
    *,
    path: Path,
    kind: str,
    metadata: dict[str, Any],
) -> ExportResult:
    data = {
        "path": str(path),
        "kind": kind,
        "metadata": metadata,
    }

    if not is_dataclass(ExportResult):
        return ExportResult(**data)

    allowed = {field.name for field in fields(ExportResult)}
    filtered = {key: value for key, value in data.items() if key in allowed}

    return ExportResult(**filtered)


def _require_non_empty_text(
    value: str,
    *,
    field_name: str,
    context: dict[str, Any],
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExportError(
            f"{field_name} must be a non-empty string.",
            context={
                **context,
                "field": field_name,
                "error_type": "validation_error",
            },
        )

    return value.strip()


def _safe_card_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _validate_flashcards(
    cards: Sequence[Flashcard],
    *,
    context: dict[str, Any],
) -> list[Flashcard]:
    if not cards:
        raise ExportError(
            "At least one flashcard is required for CSV export.",
            context={
                **context,
                "error_type": "validation_error",
            },
        )

    valid: list[Flashcard] = []

    for index, card in enumerate(cards):
        question = getattr(card, "question", None)
        answer = getattr(card, "answer", None)

        if not isinstance(question, str) or not question.strip():
            logger.warning(
                "Flashcard export validation failed",
                extra={
                    "context": {
                        **context,
                        "index": index,
                        "reason": "empty_question",
                    }
                },
            )
            continue

        if not isinstance(answer, str) or not answer.strip():
            logger.warning(
                "Flashcard export validation failed",
                extra={
                    "context": {
                        **context,
                        "index": index,
                        "reason": "empty_answer",
                    }
                },
            )
            continue

        valid.append(card)

    if not valid:
        raise ExportError(
            "No valid flashcards were available for CSV export.",
            context={
                **context,
                "error_type": "validation_error",
                "valid_count": 0,
            },
        )

    return valid


def _split_pdf_paragraphs(body: str) -> list[str]:
    return [paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()]


def export_markdown(filename: str, markdown: str) -> ExportResult:
    path = _resolve_export_path(filename, ".md")

    context = _context(
        operation="export_markdown",
        filename=filename,
        path=path,
        kind="markdown",
        text_length=len(markdown) if isinstance(markdown, str) else None,
    )

    markdown = _require_non_empty_text(
        markdown,
        field_name="markdown",
        context=context,
    )

    metadata = {
        "text_length": len(markdown),
    }

    logger.info("Export started", extra={"context": context})

    try:
        with path.open("w", encoding="utf-8") as file:
            file.write(markdown)

    except UnicodeEncodeError as exc:
        error_context = {
            **context,
            "error_type": "encoding_error",
        }
        logger.exception("Markdown export failed due to encoding error", extra={"context": error_context})
        raise ExportError("Markdown export failed due to encoding error.", context=error_context) from exc

    except OSError as exc:
        error_context = {
            **context,
            "error_type": "file_io_error",
        }
        logger.exception("Markdown export failed due to file I/O error", extra={"context": error_context})
        raise ExportError("Markdown export failed due to file I/O error.", context=error_context) from exc

    result = _build_export_result(
        path=path,
        kind="markdown",
        metadata=metadata,
    )

    logger.info("Export succeeded", extra={"context": {**context, "metadata": metadata}})
    return result


def export_flashcards_csv(
    filename: str,
    cards: Sequence[Flashcard],
) -> ExportResult:
    path = _resolve_export_path(filename, ".csv")

    context = _context(
        operation="export_flashcards_csv",
        filename=filename,
        path=path,
        kind="flashcards_csv",
        item_count=len(cards),
    )

    valid_cards = _validate_flashcards(cards, context=context)

    metadata = {
        "number_of_cards": len(valid_cards),
    }

    logger.info("Export started", extra={"context": context})

    try:
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Front", "Back", "Source"])

            for card in valid_cards:
                writer.writerow(
                    [
                        _safe_card_value(card.question),
                        _safe_card_value(card.answer),
                        _safe_card_value(getattr(card, "source_ref", None)),
                    ]
                )

    except UnicodeEncodeError as exc:
        error_context = {
            **context,
            "error_type": "encoding_error",
        }
        logger.exception("Flashcards CSV export failed due to encoding error", extra={"context": error_context})
        raise ExportError("Flashcards CSV export failed due to encoding error.", context=error_context) from exc

    except csv.Error as exc:
        error_context = {
            **context,
            "error_type": "csv_library_error",
        }
        logger.exception("Flashcards CSV export failed due to CSV library error", extra={"context": error_context})
        raise ExportError("Flashcards CSV export failed due to CSV library error.", context=error_context) from exc

    except OSError as exc:
        error_context = {
            **context,
            "error_type": "file_io_error",
        }
        logger.exception("Flashcards CSV export failed due to file I/O error", extra={"context": error_context})
        raise ExportError("Flashcards CSV export failed due to file I/O error.", context=error_context) from exc

    result = _build_export_result(
        path=path,
        kind="flashcards_csv",
        metadata=metadata,
    )

    logger.info("Export succeeded", extra={"context": {**context, "metadata": metadata}})
    return result


def export_pdf(filename: str, title: str, body: str) -> ExportResult:
    path = _resolve_export_path(filename, ".pdf")

    initial_context = _context(
        operation="export_pdf",
        filename=filename,
        path=path,
        kind="pdf",
        title_length=len(title) if isinstance(title, str) else None,
        body_length=len(body) if isinstance(body, str) else None,
    )

    title = _require_non_empty_text(
        title,
        field_name="title",
        context=initial_context,
    )

    body = _require_non_empty_text(
        body,
        field_name="body",
        context=initial_context,
    )

    paragraphs = _split_pdf_paragraphs(body)

    context = {
        **initial_context,
        "title_length": len(title),
        "body_length": len(body),
        "paragraph_count": len(paragraphs),
    }

    metadata = {
        "title_length": len(title),
        "body_length": len(body),
        "paragraph_count": len(paragraphs),
    }

    logger.info("Export started", extra={"context": context})

    try:
        document = SimpleDocTemplate(str(path), pagesize=A4)
        styles = getSampleStyleSheet()

        story: list[Any] = [
            Paragraph(escape(title), styles["Title"]),
            Spacer(1, 12),
        ]

        for paragraph in paragraphs:
            safe_paragraph = escape(paragraph).replace("\n", "<br/>")
            story.append(Paragraph(safe_paragraph, styles["BodyText"]))
            story.append(Spacer(1, 8))

        document.build(story)

    except UnicodeEncodeError as exc:
        error_context = {
            **context,
            "error_type": "encoding_error",
        }
        logger.exception("PDF export failed due to encoding error", extra={"context": error_context})
        raise ExportError("PDF export failed due to encoding error.", context=error_context) from exc

    except OSError as exc:
        error_context = {
            **context,
            "error_type": "file_io_error",
        }
        logger.exception("PDF export failed due to file I/O error", extra={"context": error_context})
        raise ExportError("PDF export failed due to file I/O error.", context=error_context) from exc

    except Exception as exc:
        error_context = {
            **context,
            "error_type": "reportlab_library_error",
        }
        logger.exception("PDF export failed due to ReportLab/library error", extra={"context": error_context})
        raise ExportError("PDF export failed due to ReportLab/library error.", context=error_context) from exc

    result = _build_export_result(
        path=path,
        kind="pdf",
        metadata=metadata,
    )

    logger.info("Export succeeded", extra={"context": {**context, "metadata": metadata}})
    return result


def export_mcqs_csv(
    filename: str,
    mcqs: Sequence[MCQ],
) -> ExportResult:
    path = _resolve_export_path(filename, ".csv")

    context = _context(
        operation="export_mcqs_csv",
        filename=filename,
        path=path,
        kind="mcqs_csv",
        item_count=len(mcqs),
    )

    if not mcqs:
        raise ExportError(
            "At least one MCQ is required for CSV export.",
            context={
                **context,
                "error_type": "validation_error",
            },
        )

    metadata = {
        "number_of_mcqs": len(mcqs),
    }

    logger.info("Export started", extra={"context": context})

    try:
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "Question",
                    "Choice A",
                    "Choice B",
                    "Choice C",
                    "Choice D",
                    "Correct Answer",
                    "Explanation",
                    "Source",
                ]
            )

            for index, mcq in enumerate(mcqs):
                choices = getattr(mcq, "choices", [])

                if not isinstance(choices, list) or len(choices) != 4:
                    logger.warning(
                        "Skipping invalid MCQ during export",
                        extra={
                            "context": {
                                **context,
                                "index": index,
                                "reason": "choices_not_exactly_four",
                            }
                        },
                    )
                    continue

                writer.writerow(
                    [
                        _safe_card_value(mcq.question),
                        _safe_card_value(choices[0]),
                        _safe_card_value(choices[1]),
                        _safe_card_value(choices[2]),
                        _safe_card_value(choices[3]),
                        _safe_card_value(mcq.correct_answer),
                        _safe_card_value(mcq.explanation),
                        _safe_card_value(getattr(mcq, "source_ref", None)),
                    ]
                )

    except UnicodeEncodeError as exc:
        error_context = {
            **context,
            "error_type": "encoding_error",
        }
        logger.exception("MCQs CSV export failed due to encoding error", extra={"context": error_context})
        raise ExportError("MCQs CSV export failed due to encoding error.", context=error_context) from exc

    except csv.Error as exc:
        error_context = {
            **context,
            "error_type": "csv_library_error",
        }
        logger.exception("MCQs CSV export failed due to CSV library error", extra={"context": error_context})
        raise ExportError("MCQs CSV export failed due to CSV library error.", context=error_context) from exc

    except OSError as exc:
        error_context = {
            **context,
            "error_type": "file_io_error",
        }
        logger.exception("MCQs CSV export failed due to file I/O error", extra={"context": error_context})
        raise ExportError("MCQs CSV export failed due to file I/O error.", context=error_context) from exc

    result = _build_export_result(
        path=path,
        kind="mcqs_csv",
        metadata=metadata,
    )

    logger.info("Export succeeded", extra={"context": {**context, "metadata": metadata}})
    return result