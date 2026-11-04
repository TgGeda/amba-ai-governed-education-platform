# src/amba_ai/core/preprocessing.py
from __future__ import annotations

import re
from dataclasses import asdict, fields, is_dataclass
from typing import Any, Sequence

from amba_ai.config import DEFAULT_CHUNK_OVERLAP_CHARS, DEFAULT_CHUNK_SIZE_CHARS
from amba_ai.models.schemas import TextChunk


NOISE_PATTERNS: list[str] = [
    r"\r\n?",
    r"\n{3,}",
    r"[ \t]{2,}",
    r"(?i)\bconfidential\b",
]


def normalize_text(text: str) -> str:
    """
    Normalize extracted text before paragraph splitting and chunking.

    Rules:
    - Normalize CRLF/CR to LF.
    - Collapse excessive newlines to a single newline.
    - Collapse repeated spaces/tabs to a single space.
    - Remove confidential markers case-insensitively.
    - Trim each line and remove empty leading/trailing whitespace.
    """
    if not text:
        return ""

    cleaned = text

    # Normalize Windows/Mac newlines first.
    cleaned = re.sub(r"\r\n?", "\n", cleaned)

    # Remove confidential markers case-insensitively.
    cleaned = re.sub(r"(?i)\bconfidential\b", "", cleaned)

    # Collapse spaces and tabs, preserving newline boundaries.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)

    # Trim whitespace around each line.
    cleaned = "\n".join(line.strip() for line in cleaned.splitlines())

    # Collapse excessive blank lines/newlines to a single newline as required.
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)

    return cleaned.strip()


def split_paragraphs(text: str) -> list[str]:
    """
    Split text into paragraphs using blank lines.

    Note:
    normalize_text() collapses excessive blank lines. This function still supports
    callers that pass raw or lightly-normalized text containing blank lines.
    """
    if not text:
        return []

    paragraphs = re.split(r"\n\s*\n", text)
    return [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]


def _split_long_paragraph(paragraph: str, max_size: int) -> list[str]:
    """
    Split a paragraph that is longer than max_size without cutting mid-word
    when possible.
    """
    paragraph = paragraph.strip()

    if len(paragraph) <= max_size:
        return [paragraph]

    parts: list[str] = []
    remaining = paragraph

    while len(remaining) > max_size:
        split_at = remaining.rfind(" ", 0, max_size + 1)

        # If no reasonable whitespace split exists, hard split.
        if split_at <= 0:
            split_at = max_size

        part = remaining[:split_at].strip()
        if part:
            parts.append(part)

        remaining = remaining[split_at:].strip()

    if remaining:
        parts.append(remaining)

    return parts


def _word_safe_overlap(text: str, overlap_chars: int) -> str:
    """
    Return a suffix overlap that avoids starting mid-word when possible.
    """
    if overlap_chars <= 0 or not text:
        return ""

    if len(text) <= overlap_chars:
        return text.strip()

    overlap = text[-overlap_chars:].strip()

    # Avoid starting in the middle of a word if possible.
    first_space = overlap.find(" ")
    first_newline = overlap.find("\n")

    candidates = [
        idx
        for idx in (first_space, first_newline)
        if idx > 0
    ]

    if candidates:
        overlap = overlap[min(candidates) :].strip()

    return overlap


def _text_chunk_kwargs(
    *,
    document_id: int,
    chunk_index: int,
    text: str,
    source_ref: str,
) -> dict[str, Any]:
    """
    Build TextChunk constructor kwargs while tolerating either schema style:

    Preferred:
        TextChunk(document_id=...)

    Legacy:
        TextChunk(doc_id=...)

    This keeps preprocessing compatible with older AmbaAI schema versions.
    """
    base = {
        "document_id": document_id,
        "doc_id": document_id,
        "chunk_index": chunk_index,
        "text": text,
        "source_ref": source_ref,
    }

    if not is_dataclass(TextChunk):
        return base

    allowed = {field.name for field in fields(TextChunk)}
    return {key: value for key, value in base.items() if key in allowed}


def _make_chunk(
    *,
    document_id: int,
    chunk_index: int,
    text: str,
) -> TextChunk:
    source_ref = f"chunk:{chunk_index}"

    return TextChunk(
        **_text_chunk_kwargs(
            document_id=document_id,
            chunk_index=chunk_index,
            text=text,
            source_ref=source_ref,
        )
    )


def chunk_text(
    document_id: int,
    text: str,
    chunk_size_chars: int = DEFAULT_CHUNK_SIZE_CHARS,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> list[TextChunk]:
    """
    Normalize and chunk text into typed TextChunk DTOs.

    Behavior:
    - Normalizes text before chunking.
    - Prefers paragraph boundaries.
    - Splits very long paragraphs on word boundaries when possible.
    - Adds deterministic overlap between chunks.
    - Uses deterministic source_ref: chunk:{index}.
    """
    if chunk_size_chars <= 0:
        raise ValueError("chunk_size_chars must be greater than 0")

    if overlap_chars < 0:
        raise ValueError("overlap_chars must be greater than or equal to 0")

    if overlap_chars >= chunk_size_chars:
        raise ValueError("overlap_chars must be smaller than chunk_size_chars")

    normalized = normalize_text(text)

    if not normalized:
        return []

    # Since normalize_text collapses excessive newlines to single newlines,
    # use split_paragraphs first, then fall back to line-level paragraphs.
    paragraphs = split_paragraphs(normalized)
    if len(paragraphs) <= 1:
        paragraphs = [line.strip() for line in normalized.split("\n") if line.strip()]

    normalized_paragraphs: list[str] = []
    for paragraph in paragraphs:
        normalized_paragraphs.extend(_split_long_paragraph(paragraph, chunk_size_chars))

    chunks: list[TextChunk] = []
    current_parts: list[str] = []

    def current_text() -> str:
        return "\n\n".join(current_parts).strip()

    def flush_current() -> None:
        nonlocal current_parts

        text_to_flush = current_text()
        if not text_to_flush:
            current_parts = []
            return

        chunk_index = len(chunks)
        chunks.append(
            _make_chunk(
                document_id=document_id,
                chunk_index=chunk_index,
                text=text_to_flush,
            )
        )

        overlap = _word_safe_overlap(text_to_flush, overlap_chars)
        current_parts = [overlap] if overlap else []

    for paragraph in normalized_paragraphs:
        candidate_parts = [*current_parts, paragraph]
        candidate = "\n\n".join(part for part in candidate_parts if part).strip()

        if len(candidate) <= chunk_size_chars:
            current_parts = candidate_parts
            continue

        flush_current()

        candidate_parts = [*current_parts, paragraph]
        candidate = "\n\n".join(part for part in candidate_parts if part).strip()

        if len(candidate) <= chunk_size_chars:
            current_parts = candidate_parts
        else:
            # This can happen if overlap + paragraph exceeds chunk_size.
            # Drop overlap and keep the paragraph as its own chunk.
            current_parts = [paragraph]

            if len(paragraph) >= chunk_size_chars:
                flush_current()

    if current_text():
        flush_current()

    return chunks


def chunks_to_dicts(chunks: Sequence[TextChunk]) -> list[dict[str, Any]]:
    """
    Convert TextChunk DTOs to dictionaries.

    Guarantees each output dict includes:
    - document_id
    - chunk_index
    - text
    - source_ref
    """
    output: list[dict[str, Any]] = []

    for chunk in chunks:
        item = asdict(chunk) if is_dataclass(chunk) else dict(chunk)  # type: ignore[arg-type]

        if "document_id" not in item and "doc_id" in item:
            item["document_id"] = item["doc_id"]

        if "doc_id" not in item and "document_id" in item:
            item["doc_id"] = item["document_id"]

        output.append(
            {
                "document_id": item["document_id"],
                "chunk_index": item["chunk_index"],
                "text": item["text"],
                "source_ref": item["source_ref"],
            }
        )

    return output


def chunk_text_dicts(
    document_id: int,
    text: str,
    chunk_size_chars: int = DEFAULT_CHUNK_SIZE_CHARS,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> list[dict[str, Any]]:
    """
    Backward-compatible helper for legacy callers that still expect dict chunks.
    New code should call chunk_text() and work with TextChunk DTOs directly.
    """
    return chunks_to_dicts(
        chunk_text(
            document_id=document_id,
            text=text,
            chunk_size_chars=chunk_size_chars,
            overlap_chars=overlap_chars,
        )
    )