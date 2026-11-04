from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "on",
    "indexed",
    "complete",
    "completed",
}

_FALSE_VALUES = {
    "0",
    "false",
    "no",
    "off",
    "pending",
    "failed",
    "not_indexed",
    "",
}


def _coerce_bool(
    value: Any,
    default: bool = False,
) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value != 0

    if isinstance(value, float):
        return value != 0.0

    normalized = str(value).strip().lower()

    if normalized in _TRUE_VALUES:
        return True

    if normalized in _FALSE_VALUES:
        return False

    return default


@dataclass(frozen=True)
class IngestRequest:
    path: str

    @property
    def resolved_path(self) -> Path:
        return Path(self.path).expanduser().resolve()

    @property
    def exists(self) -> bool:
        return self.resolved_path.exists()

    @property
    def suffix(self) -> str:
        return self.resolved_path.suffix.lower()

    @property
    def filename(self) -> str:
        return self.resolved_path.name

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_path(cls, path: str | Path) -> IngestRequest:
        resolved = Path(path).expanduser().resolve()
        return cls(path=str(resolved))


@dataclass(frozen=True)
class IngestViewModel:
    document_id: int
    title: str
    kind: str
    source_path: str
    chunk_count: int | str
    text_length: int | str
    rag_indexed: bool
    metadata: dict[str, Any] | None = None

    @property
    def indexed_label(self) -> str:
        status = str(
            self.metadata.get("index_status", "") if self.metadata else ""
        ).strip().lower()

        if status == "failed":
            return "Failed"

        if status in {"pending", "processing", "indexing"}:
            return "Pending"

        return "Yes" if self.rag_indexed else "No"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_ingested_result(cls, result: Any) -> IngestViewModel:
        metadata = dict(getattr(result, "metadata", {}) or {})
        document = getattr(result, "document", None)

        document_id = int(
            getattr(result, "document_id", metadata.get("document_id") or 0) or 0
        )
        title = str(
            getattr(document, "title", metadata.get("title") or f"Document {document_id}")
            or f"Document {document_id}"
        )
        kind = str(
            getattr(document, "kind", metadata.get("kind") or "unknown") or "unknown"
        )
        source_path = str(
            getattr(document, "source_path", metadata.get("source_path") or "") or ""
        )

        chunk_value = metadata.get("chunk_count")
        if chunk_value is None:
            chunk_value = "Not calculated"

        text_length_value = metadata.get("text_length")
        if text_length_value is None:
            text_length_value = "Not calculated"

        return cls(
            document_id=document_id,
            title=title,
            kind=kind,
            source_path=source_path,
            chunk_count=chunk_value,
            text_length=text_length_value,
            rag_indexed=_coerce_bool(metadata.get("rag_indexed"), False),
            metadata=metadata,
        )