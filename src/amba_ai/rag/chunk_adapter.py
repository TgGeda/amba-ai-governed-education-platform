from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from amba_ai.rag.models import Chunk


class ChunkAdapter:
    @staticmethod
    def to_chunk(
        data: Any,
        fallback_document_id: int | str = 0,
    ) -> Chunk:
        if isinstance(data, Chunk):
            return data

        values: dict[str, Any]
        use_repository_id = False

        if isinstance(data, Mapping):
            values = dict(data)
        elif callable(getattr(data, "keys", None)):
            try:
                values = {str(key): data[key] for key in data.keys()}
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise TypeError(
                    "Row-like chunk data could not be converted to a mapping."
                ) from error
            use_repository_id = True
        elif is_dataclass(data):
            values = asdict(data)
        else:
            values = dict(getattr(data, "__dict__", {}))
            for attribute in (
                "chunk_id",
                "document_id",
                "doc_id",
                "version_id",
                "ordinal",
                "chunk_index",
                "text",
                "content",
                "chunk_text",
                "page_start",
                "page",
                "page_number",
                "page_end",
                "heading_path",
                "metadata",
                "score",
                "source_ref",
            ):
                if attribute not in values and hasattr(data, attribute):
                    values[attribute] = getattr(data, attribute)

        raw_document_id = values.get("document_id")
        if raw_document_id is None:
            raw_document_id = values.get("doc_id")
        if raw_document_id is None:
            raw_document_id = fallback_document_id

        document_id = str(raw_document_id)
        version_id = str(values.get("version_id") or "v1")

        raw_ordinal = values.get("ordinal")
        if raw_ordinal is None:
            raw_ordinal = values.get("chunk_index", 0)
        ordinal = int(raw_ordinal)

        text = str(
            values.get("text")
            or values.get("content")
            or values.get("chunk_text")
            or ""
        )

        raw_page_start = values.get("page_start")
        if raw_page_start is None:
            raw_page_start = values.get("page")
        if raw_page_start is None:
            raw_page_start = values.get("page_number")

        raw_page_end = values.get("page_end")
        if raw_page_end is None:
            raw_page_end = raw_page_start

        page_start = (
            int(raw_page_start)
            if raw_page_start is not None
            else None
        )
        page_end = (
            int(raw_page_end)
            if raw_page_end is not None
            else None
        )

        heading_path = ChunkAdapter._parse_heading_path(
            values.get("heading_path", ())
        )
        raw_metadata = values.get("metadata")
        if raw_metadata is None:
            raw_metadata = values.get("metadata_json", {})
        metadata = ChunkAdapter._parse_metadata(raw_metadata)

        score = values.get("score")
        if score is not None and "score" not in metadata:
            metadata["score"] = score

        source_ref = values.get("source_ref")
        if source_ref is not None and "source_ref" not in metadata:
            metadata["source_ref"] = source_ref

        raw_chunk_id = values.get("chunk_id")
        if raw_chunk_id is None and use_repository_id:
            raw_chunk_id = values.get("id")

        chunk_id = (
            str(raw_chunk_id)
            if raw_chunk_id is not None
            else f"chk_{document_id}_{ordinal}_{version_id}"
        )

        return Chunk(
            chunk_id=chunk_id,
            document_id=document_id,
            version_id=version_id,
            text=text,
            ordinal=ordinal,
            page_start=page_start,
            page_end=page_end,
            heading_path=heading_path,
            metadata=metadata,
        )

    @staticmethod
    def _parse_heading_path(value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                return (value,)

        if isinstance(value, (list, tuple)):
            return tuple(str(item) for item in value)

        return ()

    @staticmethod
    def _parse_metadata(value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                return {}

        if isinstance(value, Mapping):
            return dict(value)

        return {}