from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Collection, Mapping


@dataclass(frozen=True, slots=True)
class IndexRebuildPolicy:
    operation: str
    permitted_chunk_ids_by_document: Mapping[int, frozenset[int]]
    require_complete_allowlists: bool = True
    effective_text_by_chunk_id: Mapping[int, str] | None = None

    def __post_init__(self) -> None:
        operation = str(self.operation).strip()
        if not operation:
            raise ValueError("Index rebuild operation must be non-empty.")
        normalized = {
            int(document_id): frozenset(int(chunk_id) for chunk_id in chunk_ids)
            for document_id, chunk_ids in self.permitted_chunk_ids_by_document.items()
        }
        object.__setattr__(self, "operation", operation)
        object.__setattr__(
            self,
            "permitted_chunk_ids_by_document",
            MappingProxyType(normalized),
        )
        effective_text = {
            int(chunk_id): str(text)
            for chunk_id, text in (self.effective_text_by_chunk_id or {}).items()
        }
        object.__setattr__(
            self,
            "effective_text_by_chunk_id",
            MappingProxyType(effective_text),
        )

    @classmethod
    def from_allowlists(
        cls,
        operation: str,
        allowlists: Mapping[int, Collection[int]],
        *,
        require_complete_allowlists: bool = True,
        effective_text_by_chunk_id: Mapping[int, str] | None = None,
    ) -> "IndexRebuildPolicy":
        return cls(
            operation=operation,
            permitted_chunk_ids_by_document={
                int(document_id): frozenset(int(chunk_id) for chunk_id in chunk_ids)
                for document_id, chunk_ids in allowlists.items()
            },
            require_complete_allowlists=require_complete_allowlists,
            effective_text_by_chunk_id=effective_text_by_chunk_id,
        )

    def effective_text_for(self, chunk_id: int, original_text: str) -> str:
        return (self.effective_text_by_chunk_id or {}).get(int(chunk_id), original_text)

    def permitted_for(self, document_id: int) -> frozenset[int] | None:
        return self.permitted_chunk_ids_by_document.get(int(document_id))

    def missing_documents(self, document_ids: Collection[int]) -> tuple[int, ...]:
        return tuple(
            sorted(
                int(document_id)
                for document_id in document_ids
                if int(document_id) not in self.permitted_chunk_ids_by_document
            )
        )


@dataclass(frozen=True, slots=True)
class IndexRebuildResult:
    operation: str
    document_ids: tuple[int, ...]
    indexed_chunk_ids: tuple[int, ...]
    excluded_chunk_ids: tuple[int, ...]
    missing_document_ids: tuple[int, ...]

    @property
    def indexed_count(self) -> int:
        return len(self.indexed_chunk_ids)

    @property
    def excluded_count(self) -> int:
        return len(self.excluded_chunk_ids)
