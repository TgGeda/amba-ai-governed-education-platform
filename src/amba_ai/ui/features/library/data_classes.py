from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

_TRUE_VALUES = {"1", "true", "yes", "on", "indexed", "complete", "completed"}
_FALSE_VALUES = {"0", "false", "no", "off", "pending", "failed", "not_indexed", ""}


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in _TRUE_VALUES


def _decode_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        res = json.loads(str(value))
        return res if isinstance(res, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


@dataclass(frozen=True)
class LibraryDocument:
    id: int
    title: str
    kind: str = "unknown"
    source_path: str = ""
    raw_text: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def document_id(self) -> int:
        return int(self.id)

    @property
    def safe_filename(self) -> str:
        """Sanitizes raw filesystem path to just the filename or friendly label."""
        if not self.source_path:
            return "Internal Document"
        # Extract base filename and strip internal directory structures
        base = os.path.basename(self.source_path.replace("\\", "/"))
        return base if base else "Uploaded File"

    @property
    def sanitized_metadata(self) -> dict[str, Any]:
        """Returns metadata with all system filesystem paths purged."""
        cleaned = {}
        path_keys = {"source_path", "path", "file_path", "filepath", "absolute_path", "abs_path"}
        for k, v in (self.metadata or {}).items():
            if str(k).lower() in path_keys:
                continue
            if isinstance(v, str) and ("\\" in v or "/" in v) and len(v) > 20:
                # Obfuscate potential nested path leaks
                cleaned[k] = os.path.basename(v.replace("\\", "/"))
            else:
                cleaned[k] = v
        return cleaned

    @property
    def chunk_count(self) -> int:
        meta = self.metadata or {}
        val = meta.get("chunk_count", meta.get("chunks", 0))
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

    @property
    def text_length(self) -> int:
        if self.raw_text:
            return len(self.raw_text)
        meta = self.metadata or {}
        val = meta.get("text_length", 0)
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

    @property
    def rag_indexed(self) -> bool:
        meta = self.metadata or {}
        return _coerce_bool(meta.get("rag_indexed", meta.get("indexed")), False)

    @property
    def index_status(self) -> str:
        meta = self.metadata or {}
        status = str(meta.get("index_status", "")).strip().lower()
        if status in {"indexed", "complete", "completed"} or self.rag_indexed:
            return "indexed"
        if status in {"pending", "processing", "indexing"}:
            return "pending"
        if status == "failed":
            return "failed"
        return "not_indexed"

    @property
    def estimated_read_time(self) -> str:
        words = self.text_length // 5 if self.text_length else 0
        minutes = max(1, round(words / 200))
        return f"~{minutes} min"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_any(cls, value: Any) -> LibraryDocument | None:
        if value is None:
            return None
        if is_dataclass(value):
            data = asdict(value)
        elif isinstance(value, dict):
            data = dict(value)
        else:
            try:
                data = dict(getattr(value, "__dict__", {}))
            except Exception:
                return None

        doc_id = data.get("id") or data.get("document_id") or data.get("doc_id")
        if doc_id is None:
            return None

        meta = _decode_metadata(
            data.get("metadata") or data.get("metadata_json") or data.get("metadata_dict") or {}
        )
        return cls(
            id=int(doc_id),
            title=str(data.get("title") or f"Document #{doc_id}"),
            kind=str(data.get("kind") or data.get("type") or "Document").upper(),
            source_path=str(data.get("source_path") or data.get("path") or ""),
            raw_text=str(data.get("raw_text") or ""),
            created_at=str(data.get("created_at") or ""),
            metadata=meta,
        )