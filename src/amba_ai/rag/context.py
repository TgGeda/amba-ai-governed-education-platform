from __future__ import annotations

import math
from .models import RetrievalHit


class ContextAssembler:
    def __init__(self, max_chars: int = 12000, max_tokens: int = 3200) -> None:
        self.max_chars = max_chars
        self.max_tokens = max_tokens

    def assemble(self, hits: list[RetrievalHit]) -> tuple[str, list[dict[str, any]]]:
        if not hits:
            return "", []

        ordered_hits = sorted(
            hits,
            key=lambda h: (
                str(h.chunk.document_id),
                h.chunk.page_start or 0,
                h.chunk.ordinal,
            ),
        )

        parts: list[str] = []
        citations: list[dict[str, any]] = []
        used_chars = 0
        used_tokens = 0
        seen_texts: set[str] = set()

        for index, hit in enumerate(ordered_hits, start=1):
            chunk = hit.chunk
            clean_text = chunk.text.strip()
            text_fingerprint = " ".join(clean_text.split()[:15])

            if text_fingerprint in seen_texts:
                continue
            seen_texts.add(text_fingerprint)

            heading = " > ".join(chunk.heading_path) if chunk.heading_path else "Curriculum Section"
            doc_title = str(chunk.metadata.get("title") or f"Doc {chunk.document_id}")
            page_info = f"p. {chunk.page_start}" if chunk.page_start else "Section Reference"

            block = (
                f"[SOURCE {index}]\n"
                f"Curriculum: {doc_title} | Version: {chunk.version_id}\n"
                f"Location: {page_info} | Section: {heading}\n"
                f"Content:\n{clean_text}\n"
            )

            est_tokens = max(1, math.ceil(len(block) / 3.8))
            if (used_chars + len(block) > self.max_chars) or (used_tokens + est_tokens > self.max_tokens):
                break

            parts.append(block)
            used_chars += len(block)
            used_tokens += est_tokens

            citations.append(
                {
                    "source_index": index,
                    "label": chunk.citation_label(),
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "version_id": chunk.version_id,
                    "title": doc_title,
                    "heading_path": list(chunk.heading_path),
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                }
            )

        return "\n\n".join(parts), citations