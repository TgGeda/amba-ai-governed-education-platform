from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any, Mapping

_GENERIC = frozenset({
    "",
    "uploaded learning material",
    "local study material",
    "document",
    "unknown",
    "learning material",
    "material",
    "untitled",
    "untitled document",
    "file",
    "source",
})

_INTERNAL = re.compile(r"^(?:document\s*)?\d+$|^.+_\d+$|^[0-9a-f]{8,32}$", re.IGNORECASE)

_PRIORITY_FIELDS = (
    "original_filename",
    "original_name",
    "filename",
    "file_name",
    "source_path",
    "stored_path",
    "file_path",
    "path",
    "source_name",
    "source",
    "document_title",
    "title",
)


def _read_field(obj: Any, name: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def _sanitize_filename(name: str) -> str:
    cleaned = name.replace("\\", "/").strip()
    posix_name = PurePosixPath(cleaned).name.strip()
    if posix_name:
        return posix_name
    return PureWindowsPath(cleaned).name.strip()


def resolve_source_name(*objects: Any, fallback: str = "Learning Material") -> str:
    strong_candidates: list[str] = []
    secondary_candidates: list[str] = []

    for obj in objects:
        if obj is None:
            continue
        for field in _PRIORITY_FIELDS:
            raw = str(_read_field(obj, field) or "").strip()
            if not raw:
                continue

            name = _sanitize_filename(raw)
            if not name:
                continue

            folded = name.casefold()
            if folded in _GENERIC or _INTERNAL.match(name):
                continue

            if "." in name and not name.startswith("."):
                return name

            if field in {"original_filename", "filename", "file_name"}:
                strong_candidates.append(name)
            else:
                secondary_candidates.append(name)

    if strong_candidates:
        return strong_candidates[0]
    if secondary_candidates:
        return secondary_candidates[0]
    return fallback