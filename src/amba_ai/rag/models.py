from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class DocumentVersion:
    document_id: str
    version_id: str
    checksum: str
    title: str
    active: bool = True
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    document_id: str
    version_id: str
    text: str
    ordinal: int
    page_start: int | None = None
    page_end: int | None = None
    heading_path: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def token_estimate(self) -> int:
        return max(1, math.ceil(len(self.text) / 3.8))

    def citation_label(self) -> str:
        title = str(self.metadata.get("title") or f"Doc {self.document_id}")
        parts = [title]
        if self.heading_path:
            parts.append(self.heading_path[-1])
        if self.page_start is not None:
            if self.page_end is not None and self.page_end != self.page_start:
                parts.append(f"pp. {self.page_start}-{self.page_end}")
            else:
                parts.append(f"p. {self.page_start}")
        parts.append(f"[{self.version_id}]")
        return " - ".join(parts)


@dataclass(slots=True)
class RetrievalQuery:
    text: str
    filters: dict[str, Any] = field(default_factory=dict)
    vector_k: int = 20
    keyword_k: int = 20
    final_k: int = 6
    grade_level: str | None = None
    subject: str | None = None
    pedagogical_mode: str = "direct"


@dataclass(slots=True)
class RetrievalHit:
    chunk: Chunk
    score: float
    vector_score: float = 0.0
    keyword_score: float = 0.0
    rerank_score: float = 0.0
    rank_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GroundedAnswer:
    answer: str
    citations: list[dict[str, Any]]
    confidence: float
    evidence_sufficient: bool
    retrieved_hits: list[RetrievalHit] = field(default_factory=list)
    pedagogical_notes: str = ""
    suggested_followups: list[str] = field(default_factory=list)