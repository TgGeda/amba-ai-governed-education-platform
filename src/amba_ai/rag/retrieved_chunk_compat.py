from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from typing import Any, Mapping

from .models import Chunk


class ChunkAdapter:
    @staticmethod
    def to_chunk(data: Any, fallback_document_id: int | str = 0) -> Chunk:
        if isinstance(data, Chunk):
            return data

        d = dict(data) if isinstance(data, Mapping) else dict(getattr(data, "__dict__", {}))

        doc_id = str(d.get("document_id") or d.get("doc_id") or fallback_document_id)
        version_id = str(d.get("version_id") or "v1")
        ordinal = int(d.get("ordinal", d.get("chunk_index", 0)))

        text = str(d.get("text") or d.get("content") or d.get("chunk_text") or "")
        p_start = d.get("page_start", d.get("page", d.get("page_number")))
        p_end = d.get("page_end", p_start)

        headings = d.get("heading_path", ())
        if isinstance(headings, str):
            try:
                headings = json.loads(headings)
            except Exception:
                headings = (headings,)
        if not isinstance(headings, tuple):
            headings = tuple(headings or ())

        meta = d.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        meta = dict(meta or {})

        chunk_id = str(d.get("chunk_id") or f"chk_{doc_id}_{ordinal}_{version_id}")

        return Chunk(
            chunk_id=chunk_id,
            document_id=doc_id,
            version_id=version_id,
            text=text,
            ordinal=ordinal,
            page_start=int(p_start) if p_start is not None else None,
            page_end=int(p_end) if p_end is not None else None,
            heading_path=headings,
            metadata=meta,
        )

    @staticmethod
    def to_dto(dto_cls: type, chunk: Chunk) -> Any:
        allowed = {f.name for f in fields(dto_cls)} if is_dataclass(dto_cls) else set()
        data = {
            "chunk_id": chunk.chunk_id,
            "document_id": int(chunk.document_id) if chunk.document_id.isdigit() else chunk.document_id,
            "doc_id": int(chunk.document_id) if chunk.document_id.isdigit() else chunk.document_id,
            "version_id": chunk.version_id,
            "text": chunk.text,
            "content": chunk.text,
            "chunk_text": chunk.text,
            "ordinal": chunk.ordinal,
            "chunk_index": chunk.ordinal - 1,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "heading_path": list(chunk.heading_path),
            "metadata": chunk.metadata,
            "source_ref": chunk.citation_label(),
        }

        if not allowed:
            return dto_cls(**data)

        filtered = {k: v for k, v in data.items() if k in allowed}
        return dto_cls(**filtered)


def install_retrieved_chunk_compat(rag_engine_cls: type) -> None:
    if getattr(rag_engine_cls, "_retrieved_chunk_compat_installed", False):
        return

    original_build_dto = getattr(rag_engine_cls, "_build_dto", None)

    def compatible_build_dto(dto_cls: type, data: dict[str, Any]) -> Any:
        chunk = ChunkAdapter.to_chunk(data)
        if dto_cls is Chunk:
            return chunk
        return ChunkAdapter.to_dto(dto_cls, chunk)

    rag_engine_cls._build_dto = staticmethod(compatible_build_dto)
    rag_engine_cls._retrieved_chunk_compat_installed = True