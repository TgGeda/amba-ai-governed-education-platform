"""Feature-aware governed-learning result metadata contracts.

This module is the single source of truth for Summary, Notes, Study Assets,
and Tutor result metadata. Ingestion remains on its separate record/version
contract.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from amba_ai.governance.models import GovernanceConfigurationError

MAX_CITATIONS: Final = 100
MAX_SOURCE_DOCUMENT_IDS: Final = 100
MAX_CITATION_TEXT_LENGTH: Final = 500
MAX_CHUNK_IDS: Final = 1000

ALLOWED_CITATION_FIELDS: Final = frozenset({
    "record_id", "version_id", "source_id", "locator", "document_id",
    "chunk_id", "source_name", "source_type",
})


@dataclass(frozen=True, slots=True)
class ResultMetadataContract:
    output_type: str
    allowed_fields: frozenset[str]
    required_fields: frozenset[str]


_COMMON_FIELDS: Final = frozenset({
    "output_type", "document_id", "model_name", "tokens_used", "fallback",
    "citations", "source_document_ids",
})

RESULT_METADATA_CONTRACTS: Final = {
    "summary_result": ResultMetadataContract(
        "summary_result",
        _COMMON_FIELDS | {"markdown_length", "elapsed_time", "operation"},
        frozenset({"output_type", "document_id", "markdown_length"}),
    ),
    "notes_result": ResultMetadataContract(
        "notes_result",
        _COMMON_FIELDS | {"markdown_length", "elapsed_time", "operation"},
        frozenset({"output_type", "document_id", "markdown_length"}),
    ),
    "study_assets_result": ResultMetadataContract(
        "study_assets_result",
        _COMMON_FIELDS | {
            "flashcard_count", "mcq_count", "quality_score", "operation",
        },
        frozenset({"output_type", "document_id", "flashcard_count", "mcq_count"}),
    ),
    "answer_result": ResultMetadataContract(
        "answer_result",
        _COMMON_FIELDS | {
            "answer_length", "citation_count", "retrieved_chunk_ids",
            "excluded_chunk_ids", "confidence_score", "query_length",
            "query_sha256", "operation",
        },
        frozenset({"output_type", "answer_length", "citation_count"}),
    ),
}


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GovernanceConfigurationError(f"{field} must be a positive integer.")
    return value


def local_document_citation(document_id: int, source_name: str | None = None) -> dict[str, object]:
    document_id = _positive_int(document_id, "document_id")
    citation: dict[str, object] = {
        "source_id": f"local-document:{document_id}",
        "locator": f"document:{document_id}",
        "document_id": document_id,
        "source_type": "local_document",
    }
    name = str(source_name or "").strip()
    if name:
        citation["source_name"] = name[:MAX_CITATION_TEXT_LENGTH]
    return citation


def local_chunk_citation(
    document_id: int,
    chunk_id: int | str,
    source_name: str | None = None,
) -> dict[str, object]:
    citation = local_document_citation(document_id, source_name)
    if isinstance(chunk_id, bool):
        raise GovernanceConfigurationError("chunk_id must not be Boolean.")
    chunk = str(chunk_id).strip()
    if not chunk:
        raise GovernanceConfigurationError("chunk_id must not be empty.")
    if len(chunk) > MAX_CITATION_TEXT_LENGTH:
        raise GovernanceConfigurationError("chunk_id is too long.")
    citation["chunk_id"] = chunk
    citation["locator"] = f"chunk:{chunk}"
    return citation


def _safe_document_ids(value: object) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise GovernanceConfigurationError("source_document_ids must be a list or tuple.")
    if len(value) > MAX_SOURCE_DOCUMENT_IDS:
        raise GovernanceConfigurationError("source_document_ids exceeds its maximum size.")
    result: list[int] = []
    for item in value:
        item = _positive_int(item, "source_document_ids item")
        if item not in result:
            result.append(item)
    return tuple(result)


def _bounded_chunk_ids(value: object, field: str) -> tuple[int | str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise GovernanceConfigurationError(f"{field} must be a list or tuple.")
    if len(value) > MAX_CHUNK_IDS:
        raise GovernanceConfigurationError(f"{field} exceeds its maximum size.")
    result: list[int | str] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, str)):
            raise GovernanceConfigurationError(f"{field} contains an invalid identifier.")
        normalized: int | str = item if isinstance(item, int) else item.strip()
        if normalized == "" or (isinstance(normalized, int) and normalized < 0):
            raise GovernanceConfigurationError(f"{field} contains an invalid identifier.")
        if normalized not in result:
            result.append(normalized)
    return tuple(result)


def _canonicalize_citation(raw: Mapping[str, object]) -> dict[str, object]:
    unknown = set(raw) - ALLOWED_CITATION_FIELDS
    if unknown:
        raise GovernanceConfigurationError(
            f"citation contains non-permitted fields: {sorted(unknown)}"
        )
    item = dict(raw)
    document_id = item.get("document_id")
    # Upgrade the legacy document-level shape used by Summary/Notes/Study.
    if "source_id" not in item and document_id is not None:
        doc_id = _positive_int(document_id, "citation document_id")
        item["source_id"] = f"local-document:{doc_id}"
        chunk_id = item.get("chunk_id")
        item["locator"] = f"chunk:{chunk_id}" if chunk_id is not None else f"document:{doc_id}"
    for key, value in tuple(item.items()):
        if key == "document_id":
            item[key] = _positive_int(value, "citation document_id")
            continue
        if not isinstance(value, str):
            raise GovernanceConfigurationError(f"citation {key} must be a string.")
        text = value.strip()
        if not text:
            raise GovernanceConfigurationError(f"citation {key} must not be empty.")
        if len(text) > MAX_CITATION_TEXT_LENGTH:
            raise GovernanceConfigurationError(f"citation {key} is too long.")
        item[key] = text
    keys = set(item)
    if not (
        {"source_id", "locator"}.issubset(keys)
        or {"record_id", "version_id", "source_id"}.issubset(keys)
    ):
        raise GovernanceConfigurationError("citation must use a supported governance schema.")
    return item


def _safe_citations(value: object) -> tuple[dict[str, object], ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise GovernanceConfigurationError("citations must be a list or tuple.")
    if len(value) > MAX_CITATIONS:
        raise GovernanceConfigurationError("citations exceeds its maximum size.")
    result: list[dict[str, object]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise GovernanceConfigurationError(f"citation {index} must be a mapping.")
        result.append(_canonicalize_citation(raw))
    return tuple(result)


def learning_result_allowed_fields(metadata: Mapping[str, object]) -> frozenset[str]:
    output_type = metadata.get("output_type")
    if not isinstance(output_type, str):
        return frozenset()
    contract = RESULT_METADATA_CONTRACTS.get(output_type)
    return contract.allowed_fields if contract else frozenset()


def normalize_learning_result_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a known learning output; leave non-learning outputs unchanged."""
    result = dict(metadata)
    output_type = result.get("output_type")
    if not isinstance(output_type, str) or output_type not in RESULT_METADATA_CONTRACTS:
        return result
    contract = RESULT_METADATA_CONTRACTS[output_type]
    missing = contract.required_fields - set(result)
    if missing:
        raise GovernanceConfigurationError(
            f"result_metadata is missing required fields: {sorted(missing)}"
        )
    unknown = set(result) - contract.allowed_fields
    if unknown:
        raise GovernanceConfigurationError(
            f"{output_type} contains non-permitted fields: {sorted(unknown)}"
        )
    if "citations" in result:
        result["citations"] = _safe_citations(result["citations"])
    if "source_document_ids" in result:
        result["source_document_ids"] = _safe_document_ids(result["source_document_ids"])
    if "fallback" in result and type(result["fallback"]) is not bool:
        raise GovernanceConfigurationError("fallback must be a strict Boolean.")
    for field in ("retrieved_chunk_ids", "excluded_chunk_ids"):
        if field in result:
            result[field] = _bounded_chunk_ids(result[field], field)
    return result
