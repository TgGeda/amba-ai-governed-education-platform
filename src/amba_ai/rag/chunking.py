from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from typing import Any

from .models import Chunk

_HEADING_PATTERNS = [
    re.compile(r"^(?:unit|chapter|lesson|module|part|section|topic)\s+\d+(?:[\.:\s]+.*)?$", re.I),
    re.compile(r"^(?:\d+\.){1,4}\d*\s+.+$"),
    re.compile(r"^[A-Z][A-Z0-9\s,:;()/'\"-]{3,90}$"),
    re.compile(r"^(?:definition|theorem|proof|lemma|corollary|example|exercise|activity|summary|review)\s*(?:\d+[\.:])?.*$", re.I),
]

_ABBREVIATIONS = {
    "e.g.", "i.e.", "etc.", "vs.", "al.", "fig.", "figs.", "eq.", "eqs.",
    "dr.", "prof.", "mr.", "mrs.", "ms.", "vol.", "no.", "ch.", "sec.",
    "p.", "pp.", "approx.", "def.", "dept.", "ref.",
}

_NUMERIC_SECTION = re.compile(r"^(\d+(?:\.\d+)*)")


class SemanticChunker:
    def __init__(
        self,
        target_chars: int = 1400,
        max_chars: int = 1900,
        overlap_sentences: int = 2,
    ) -> None:
        if target_chars < 200 or max_chars <= target_chars:
            raise ValueError("Require target_chars >= 200 and max_chars > target_chars")
        self.target_chars = target_chars
        self.max_chars = max_chars
        self.overlap_sentences = max(0, overlap_sentences)

    def chunk(
        self,
        *,
        document_id: str,
        version_id: str,
        pages: Iterable[tuple[int, str]],
        base_metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        metadata = dict(base_metadata or {})
        sections: list[tuple[tuple[str, ...], int, list[str]]] = []
        heading_stack: list[str] = []

        for page_no, raw in pages:
            lines = (raw or "").splitlines()
            paragraphs: list[str] = []
            para_buffer: list[str] = []

            for line in lines:
                s = line.strip()
                if not s:
                    if para_buffer:
                        paragraphs.append("\n".join(para_buffer))
                        para_buffer = []
                else:
                    para_buffer.append(s)
            if para_buffer:
                paragraphs.append("\n".join(para_buffer))

            current_body: list[str] = []
            for paragraph in paragraphs:
                if self._is_heading(paragraph):
                    if current_body:
                        sections.append((tuple(heading_stack), page_no, current_body))
                        current_body = []
                    heading_stack = self._resolve_heading_hierarchy(heading_stack, paragraph)
                else:
                    current_body.append(paragraph)

            if current_body:
                sections.append((tuple(heading_stack), page_no, current_body))

        chunks: list[Chunk] = []
        ordinal = 0
        carry_sentences: list[str] = []

        for headings, page_no, paragraphs in sections:
            full_text = "\n\n".join(paragraphs).strip()
            if not full_text:
                continue

            extracted = self._split_sentences(full_text)
            sentences = carry_sentences + extracted
            carry_sentences = []
            buffer: list[str] = []

            for sentence in sentences:
                candidate = " ".join(buffer + [sentence]).strip()
                if buffer and len(candidate) > self.target_chars:
                    ordinal += 1
                    chunks.append(
                        self._create_chunk(
                            document_id=document_id,
                            version_id=version_id,
                            ordinal=ordinal,
                            sentences=buffer,
                            page_start=page_no,
                            page_end=page_no,
                            headings=headings,
                            metadata=metadata,
                        )
                    )
                    buffer = buffer[-self.overlap_sentences:] if self.overlap_sentences else []

                if len(sentence) > self.max_chars:
                    slices = self._safe_break_long_text(sentence, self.max_chars)
                    for piece in slices:
                        if buffer and len(" ".join(buffer + [piece])) > self.target_chars:
                            ordinal += 1
                            chunks.append(
                                self._create_chunk(
                                    document_id=document_id,
                                    version_id=version_id,
                                    ordinal=ordinal,
                                    sentences=buffer,
                                    page_start=page_no,
                                    page_end=page_no,
                                    headings=headings,
                                    metadata=metadata,
                                )
                            )
                            buffer = buffer[-self.overlap_sentences:] if self.overlap_sentences else []
                        buffer.append(piece)
                else:
                    buffer.append(sentence)

            carry_sentences = buffer

        if carry_sentences:
            ordinal += 1
            chunks.append(
                self._create_chunk(
                    document_id=document_id,
                    version_id=version_id,
                    ordinal=ordinal,
                    sentences=carry_sentences,
                    page_start=sections[-1][1] if sections else 1,
                    page_end=sections[-1][1] if sections else 1,
                    headings=sections[-1][0] if sections else (),
                    metadata=metadata,
                )
            )

        return chunks

    def _is_heading(self, text: str) -> bool:
        clean = text.strip()
        if not clean or len(clean) > 120 or "\n" in clean:
            return False
        return any(pattern.match(clean) is not None for pattern in _HEADING_PATTERNS)

    def _resolve_heading_hierarchy(self, current_stack: list[str], new_heading: str) -> list[str]:
        match = _NUMERIC_SECTION.match(new_heading)
        if match:
            level = match.group(1).count(".") + 1
            return current_stack[: level - 1] + [new_heading]
        if not current_stack:
            return [new_heading]
        if len(current_stack) >= 3:
            return current_stack[:2] + [new_heading]
        return current_stack + [new_heading]

    def _split_sentences(self, text: str) -> list[str]:
        raw_parts = re.split(r"(?<=[.!?])\s+", text)
        sentences: list[str] = []
        merge_buffer = ""

        for part in raw_parts:
            segment = f"{merge_buffer} {part}".strip() if merge_buffer else part.strip()
            if not segment:
                continue

            last_word = segment.split()[-1].lower() if segment.split() else ""
            if last_word in _ABBREVIATIONS or re.search(r"\b\d+\.$", segment):
                merge_buffer = segment
            else:
                sentences.append(segment)
                merge_buffer = ""

        if merge_buffer:
            sentences.append(merge_buffer)
        return sentences

    def _safe_break_long_text(self, text: str, max_size: int) -> list[str]:
        words = text.split()
        pieces: list[str] = []
        current: list[str] = []
        current_len = 0

        for word in words:
            if current and (current_len + len(word) + 1) > max_size:
                pieces.append(" ".join(current))
                current = [word]
                current_len = len(word)
            else:
                current.append(word)
                current_len += len(word) + 1

        if current:
            pieces.append(" ".join(current))
        return pieces

    def _create_chunk(
        self,
        *,
        document_id: str,
        version_id: str,
        ordinal: int,
        sentences: list[str],
        page_start: int,
        page_end: int,
        headings: tuple[str, ...],
        metadata: dict[str, Any],
    ) -> Chunk:
        text = " ".join(sentences).strip()
        hash_seed = f"{document_id}|{version_id}|{' > '.join(headings)}|{text}"
        digest = hashlib.sha256(hash_seed.encode("utf-8")).hexdigest()[:24]

        meta = dict(metadata)
        meta["heading_path"] = list(headings)
        meta["page_start"] = page_start
        meta["page_end"] = page_end

        return Chunk(
            chunk_id=f"chk_{digest}",
            document_id=str(document_id),
            version_id=str(version_id),
            text=text,
            ordinal=ordinal,
            page_start=page_start,
            page_end=page_end,
            heading_path=headings,
            metadata=meta,
        )