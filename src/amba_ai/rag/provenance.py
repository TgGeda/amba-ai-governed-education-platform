from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amba_ai.governance.models import to_canonical_json


def _require_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(field_name, str):
        raise TypeError("field_name must be a string")

    normalized_field_name = field_name.strip()
    if not normalized_field_name:
        raise ValueError("field_name must not be empty")

    if not isinstance(value, str):
        raise TypeError(f"{normalized_field_name} must be a string")

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{normalized_field_name} must not be empty")

    return normalized_value


def _normalize_page(
    value: int | None,
    field_name: str,
) -> int | None:
    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer or None")

    if value < 1:
        raise ValueError(f"{field_name} must be strictly positive")

    return value


@dataclass(frozen=True, slots=True)
class RetrievalProvenance:
    source_id: str
    document_version_id: str
    policy_record_id: str
    chunk_id: str
    locator: str
    page_start: int | None = None
    page_end: int | None = None

    def __post_init__(self) -> None:
        source_id = _require_text(
            self.source_id,
            "source_id",
        )
        document_version_id = _require_text(
            self.document_version_id,
            "document_version_id",
        )
        policy_record_id = _require_text(
            self.policy_record_id,
            "policy_record_id",
        )
        chunk_id = _require_text(
            self.chunk_id,
            "chunk_id",
        )
        locator = _require_text(
            self.locator,
            "locator",
        )
        page_start = _normalize_page(
            self.page_start,
            "page_start",
        )
        page_end = _normalize_page(
            self.page_end,
            "page_end",
        )

        if (page_start is None) != (page_end is None):
            raise ValueError(
                "page_start and page_end must either both be set or both be None"
            )

        if (
            page_start is not None
            and page_end is not None
            and page_end < page_start
        ):
            raise ValueError("page_end cannot precede page_start")

        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(
            self,
            "document_version_id",
            document_version_id,
        )
        object.__setattr__(
            self,
            "policy_record_id",
            policy_record_id,
        )
        object.__setattr__(self, "chunk_id", chunk_id)
        object.__setattr__(self, "locator", locator)
        object.__setattr__(self, "page_start", page_start)
        object.__setattr__(self, "page_end", page_end)

    @property
    def has_page_range(self) -> bool:
        return self.page_start is not None

    @property
    def page_count(self) -> int | None:
        if self.page_start is None or self.page_end is None:
            return None
        return self.page_end - self.page_start + 1

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (
            self.source_id,
            self.document_version_id,
            self.policy_record_id,
            self.chunk_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "document_version_id": self.document_version_id,
            "policy_record_id": self.policy_record_id,
            "chunk_id": self.chunk_id,
            "locator": self.locator,
            "page_start": self.page_start,
            "page_end": self.page_end,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())
