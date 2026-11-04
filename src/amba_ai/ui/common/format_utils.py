from __future__ import annotations

from typing import Any


def clean_text(value: str | None) -> str:
    """Normalize whitespace in text."""
    return " ".join(str(value or "").split())


def truncate_text(value: str | None, limit: int = 500, suffix: str = "...") -> str:
    """Truncate text to a given limit, appending a suffix if needed."""
    text = clean_text(value)
    if limit <= 0 or len(text) <= limit:
        return text
    if limit <= len(suffix):
        return suffix[:limit]
    return text[: limit - len(suffix)].rstrip() + suffix


def safe_filename_stem(value: str | None, default: str = "document") -> str:
    """Generate a safe filename stem with only alphanumeric, dash, and underscore."""
    raw = str(value or "").strip()
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in raw)
    cleaned = "_".join(part for part in cleaned.split("_") if part).strip("_")
    return cleaned or default


def format_markdown_notes_for_ui(markdown: str | None) -> str:
    """Format markdown notes for compact UI display."""
    text = str(markdown or "").strip()
    if not text:
        return ""

    lines = [line.rstrip() for line in text.splitlines()]
    compact: list[str] = []
    previous_blank = False

    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        compact.append(line)
        previous_blank = blank

    return "\n".join(compact).strip()


def _safe_str(value: Any, default: str = "") -> str:
    """Convert value to safe stripped string."""
    return str(value or default).strip()


def format_flashcards_for_ui(flashcards: list[Any] | None) -> str:
    """Format flashcards for UI display."""
    cards = list(flashcards or [])
    if not cards:
        return "No flashcards generated."

    output: list[str] = ["# Flashcards", ""]

    for index, card in enumerate(cards, start=1):
        question = getattr(card, "question", None)
        answer = getattr(card, "answer", None)
        source_ref = getattr(card, "source_ref", None)

        if isinstance(card, dict):
            question = card.get("question", question)
            answer = card.get("answer", answer)
            source_ref = card.get("source_ref", source_ref)

        output.extend(
            [
                f"## Flashcard {index}",
                "",
                f"Q: {_safe_str(question)}",
                "",
                f"A: {_safe_str(answer)}",
                "",
                f"Source: {_safe_str(source_ref, 'Local Study Material')}",
                "",
            ]
        )

    return "\n".join(output).strip()


def format_mcqs_for_ui(mcqs: list[Any] | None) -> str:
    """Format multiple-choice questions for UI display."""
    items = list(mcqs or [])
    if not items:
        return "No quiz questions generated."

    output: list[str] = ["# Quiz", ""]

    for index, mcq in enumerate(items, start=1):
        question = getattr(mcq, "question", None)
        choices = getattr(mcq, "choices", None)
        correct_answer = getattr(mcq, "correct_answer", None)
        explanation = getattr(mcq, "explanation", None)
        source_ref = getattr(mcq, "source_ref", None)

        if isinstance(mcq, dict):
            question = mcq.get("question", question)
            choices = mcq.get("choices", choices)
            correct_answer = mcq.get("correct_answer", correct_answer)
            explanation = mcq.get("explanation", explanation)
            source_ref = mcq.get("source_ref", source_ref)

        output.extend([f"## Question {index}", "", _safe_str(question), ""])

        for choice in list(choices or []):
            output.append(f"- {_safe_str(choice)}")

        output.extend(
            [
                "",
                f"Correct Answer: {_safe_str(correct_answer)}",
                "",
                f"Explanation: {_safe_str(explanation)}",
                "",
                f"Source: {_safe_str(source_ref, 'Local Study Material')}",
                "",
            ]
        )

    return "\n".join(output).strip()
