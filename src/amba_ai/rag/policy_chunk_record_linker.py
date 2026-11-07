from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence

from amba_ai.governance.models import (
    LocatorVerificationStatus,
    PolicyRecord,
    PolicyRecordIdentity,
)
from amba_ai.governance.record_registry import PolicyRecordRegistry
from amba_ai.rag.policy_chunk_models import PolicyChunkError, require_identifier, require_raw_text, require_sha256


class ChunkRecordMatchStatus(str, Enum):
    STRUCTURAL_MATCH = "structural_match"
    PARTIAL_STRUCTURAL_MATCH = "partial_structural_match"
    LOCATOR_NOT_FOUND = "locator_not_found"
    ARTIFACT_MISMATCH = "artifact_mismatch"
    SOURCE_IDENTITY_MISMATCH = "source_identity_mismatch"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class ExcerptExactness(str, Enum):
    SOURCE_DERIVED = "source_derived"
    VERIFIED_EXACT = "verified_exact"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True, slots=True)
class SourcePolicyChunk:
    """A source-derived chunk before authority is attached.

    This model deliberately contains no PolicyRecord record_id. A source chunk
    can provide evidence for zero, one, or multiple structurally verified
    records without inheriting authority from retrieval rank.
    """

    chunk_id: str
    source_id: str
    version_id: str
    artifact_sha256: str
    page_start: int
    page_end: int
    raw_text: str
    text_sha256: str

    def __post_init__(self) -> None:
        for field_name in ("chunk_id", "source_id", "version_id"):
            object.__setattr__(
                self,
                field_name,
                require_identifier(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "artifact_sha256",
            require_sha256(self.artifact_sha256, "artifact_sha256"),
        )
        object.__setattr__(
            self,
            "text_sha256",
            require_sha256(self.text_sha256, "text_sha256"),
        )
        object.__setattr__(
            self,
            "raw_text",
            require_raw_text(self.raw_text, "raw_text"),
        )
        for field_name in ("page_start", "page_end"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
        if self.page_start < 1 or self.page_end < self.page_start:
            raise PolicyChunkError("source chunk has an invalid page range")
        actual = hashlib.sha256(self.raw_text.encode("utf-8")).hexdigest()
        if actual != self.text_sha256:
            raise PolicyChunkError("text_sha256 does not match raw_text")

    @classmethod
    def create(
        cls,
        *,
        source_id: str,
        version_id: str,
        artifact_sha256: str,
        page_start: int,
        page_end: int,
        raw_text: str,
        ordinal: int,
    ) -> SourcePolicyChunk:
        if isinstance(ordinal, bool) or not isinstance(ordinal, int):
            raise TypeError("ordinal must be an integer")
        if ordinal < 0:
            raise PolicyChunkError("ordinal must be non-negative")
        canonical_text = require_raw_text(raw_text, "raw_text")
        digest = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
        source = require_identifier(source_id, "source_id")
        version = require_identifier(version_id, "version_id")
        chunk_id = (
            f"{source}@{version}:source:p{page_start}-p{page_end}:"
            f"c{ordinal:04d}:{digest[:12]}"
        )
        return cls(
            chunk_id=chunk_id,
            source_id=source,
            version_id=version,
            artifact_sha256=artifact_sha256,
            page_start=page_start,
            page_end=page_end,
            raw_text=canonical_text,
            text_sha256=digest,
        )


@dataclass(frozen=True, slots=True)
class PolicyChunkRecordLink:
    chunk_id: str
    record_identity: PolicyRecordIdentity
    match_status: ChunkRecordMatchStatus
    matched_locators: tuple[str, ...]
    required_locators: tuple[str, ...]
    source_page_start: int
    source_page_end: int
    excerpt_exactness: ExcerptExactness
    registered_locator: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunk_id", require_identifier(self.chunk_id, "chunk_id"))
        if not isinstance(self.record_identity, PolicyRecordIdentity):
            raise TypeError("record_identity must be a PolicyRecordIdentity")
        if not isinstance(self.match_status, ChunkRecordMatchStatus):
            raise TypeError("match_status must be a ChunkRecordMatchStatus")
        if not isinstance(self.excerpt_exactness, ExcerptExactness):
            raise TypeError("excerpt_exactness must be an ExcerptExactness")
        if not isinstance(self.matched_locators, tuple) or not isinstance(self.required_locators, tuple):
            raise TypeError("locator collections must be tuples")
        if len(self.matched_locators) != len(set(self.matched_locators)):
            raise PolicyChunkError("matched_locators must be unique")
        if not set(self.matched_locators).issubset(set(self.required_locators)):
            raise PolicyChunkError("matched_locators must be a subset of required_locators")
        for field_name in ("source_page_start", "source_page_end"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
        if self.source_page_start < 1 or self.source_page_end < self.source_page_start:
            raise PolicyChunkError("link has an invalid page range")
        if self.excerpt_exactness is ExcerptExactness.VERIFIED_EXACT:
            raise PolicyChunkError("structural linker cannot produce verified_exact excerpts")
        if self.match_status is ChunkRecordMatchStatus.STRUCTURAL_MATCH:
            if set(self.matched_locators) != set(self.required_locators):
                raise PolicyChunkError("structural_match requires every required locator")
            if self.excerpt_exactness is not ExcerptExactness.SOURCE_DERIVED:
                raise PolicyChunkError("structural_match requires source_derived excerpt exactness")

    def to_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "record_identity": {
                "record_id": self.record_identity.record_id,
                "version_id": self.record_identity.version_id,
                "source_id": self.record_identity.source_id,
            },
            "match_status": self.match_status.value,
            "matched_locators": list(self.matched_locators),
            "required_locators": list(self.required_locators),
            "source_page_start": self.source_page_start,
            "source_page_end": self.source_page_end,
            "excerpt_exactness": self.excerpt_exactness.value,
            "registered_locator": self.registered_locator,
        }


@dataclass(frozen=True, slots=True)
class PolicyRecordLinkAssessment:
    record_identity: PolicyRecordIdentity
    registered_locator: str
    required_locators: tuple[str, ...]
    matched_locators: tuple[str, ...]
    match_status: ChunkRecordMatchStatus
    links: tuple[PolicyChunkRecordLink, ...]

    @property
    def is_complete(self) -> bool:
        return self.match_status is ChunkRecordMatchStatus.STRUCTURAL_MATCH

    def to_dict(self) -> dict[str, object]:
        return {
            "record_identity": {
                "record_id": self.record_identity.record_id,
                "version_id": self.record_identity.version_id,
                "source_id": self.record_identity.source_id,
            },
            "registered_locator": self.registered_locator,
            "required_locators": list(self.required_locators),
            "matched_locators": list(self.matched_locators),
            "match_status": self.match_status.value,
            "is_complete": self.is_complete,
            "links": [link.to_dict() for link in self.links],
        }


def _clause_pattern(clause: str) -> re.Pattern[str]:
    escaped = re.escape(clause)
    return re.compile(
        rf"(?im)^\s*(?:clause\s+)?{escaped}(?=\s|[.\-:–—])"
    )


_DEFAULT_LOCATOR_REQUIREMENTS: Mapping[str, tuple[str, ...]] = {
    "Clause 3.2.6": ("3.2.6",),
    "Clause 7.4": ("7.4",),
    "Clause 8.1": ("8.1",),
    "Clauses 8.1 and 8.2": ("8.1", "8.2"),
    "Clause 9": ("9",),
}


class PolicyChunkRecordLinker:
    """Deterministically links source chunks to structurally verified records."""

    def __init__(
        self,
        registry: PolicyRecordRegistry,
        *,
        locator_requirements: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        if not isinstance(registry, PolicyRecordRegistry):
            raise TypeError("registry must be a PolicyRecordRegistry")
        supplied = locator_requirements or _DEFAULT_LOCATOR_REQUIREMENTS
        normalized: dict[str, tuple[str, ...]] = {}
        for registered_locator, requirements in supplied.items():
            if not isinstance(registered_locator, str) or not registered_locator.strip():
                raise PolicyChunkError("registered locator must be a non-empty string")
            values = tuple(str(value).strip() for value in requirements)
            if not values or any(not value for value in values):
                raise PolicyChunkError("each registered locator requires at least one structural locator")
            if len(values) != len(set(values)):
                raise PolicyChunkError("required structural locators must be unique")
            normalized[registered_locator.strip()] = values
        self._registry = registry
        self._requirements = normalized
        self._patterns = {
            locator: _clause_pattern(locator)
            for requirements in normalized.values()
            for locator in requirements
        }

    def link_chunk(
        self,
        chunk: SourcePolicyChunk,
        record_identity: PolicyRecordIdentity,
        *,
        semantic_score: float | None = None,
    ) -> PolicyChunkRecordLink:
        if not isinstance(chunk, SourcePolicyChunk):
            raise TypeError("chunk must be a SourcePolicyChunk")
        if not isinstance(record_identity, PolicyRecordIdentity):
            raise TypeError("record_identity must be a PolicyRecordIdentity")
        if semantic_score is not None:
            if isinstance(semantic_score, bool) or not isinstance(semantic_score, (int, float)):
                raise TypeError("semantic_score must be numeric or None")
            # Deliberately unused. Semantic similarity cannot create authority.
        record = self._registry.require(record_identity)
        required = self._required_locators(record)
        if chunk.source_id != record.identity.source_id or chunk.version_id != record.identity.version_id:
            return self._link(
                chunk,
                record,
                ChunkRecordMatchStatus.SOURCE_IDENTITY_MISMATCH,
                (),
                required,
                ExcerptExactness.NOT_ASSESSED,
            )
        if chunk.artifact_sha256 != record.artifact_sha256:
            return self._link(
                chunk,
                record,
                ChunkRecordMatchStatus.ARTIFACT_MISMATCH,
                (),
                required,
                ExcerptExactness.NOT_ASSESSED,
            )
        if record.locator_verification_status is not LocatorVerificationStatus.VERIFIED_STRUCTURAL:
            return self._link(
                chunk,
                record,
                ChunkRecordMatchStatus.HUMAN_REVIEW_REQUIRED,
                (),
                required,
                ExcerptExactness.NOT_ASSESSED,
            )
        matched = tuple(
            locator
            for locator in required
            if self._patterns[locator].search(chunk.raw_text) is not None
        )
        if not matched:
            status = ChunkRecordMatchStatus.LOCATOR_NOT_FOUND
            exactness = ExcerptExactness.NOT_ASSESSED
        elif len(matched) < len(required):
            status = ChunkRecordMatchStatus.PARTIAL_STRUCTURAL_MATCH
            exactness = ExcerptExactness.SOURCE_DERIVED
        else:
            status = ChunkRecordMatchStatus.STRUCTURAL_MATCH
            exactness = ExcerptExactness.SOURCE_DERIVED
        return self._link(chunk, record, status, matched, required, exactness)

    def assess_record(
        self,
        chunks: Iterable[SourcePolicyChunk],
        record_identity: PolicyRecordIdentity,
    ) -> PolicyRecordLinkAssessment:
        if not isinstance(record_identity, PolicyRecordIdentity):
            raise TypeError("record_identity must be a PolicyRecordIdentity")
        record = self._registry.require(record_identity)
        required = self._required_locators(record)
        links = tuple(self.link_chunk(chunk, record_identity) for chunk in chunks)
        matched = tuple(
            locator
            for locator in required
            if any(
                locator in link.matched_locators
                and link.match_status
                in {
                    ChunkRecordMatchStatus.STRUCTURAL_MATCH,
                    ChunkRecordMatchStatus.PARTIAL_STRUCTURAL_MATCH,
                }
                for link in links
            )
        )
        if set(matched) == set(required):
            status = ChunkRecordMatchStatus.STRUCTURAL_MATCH
        elif matched:
            status = ChunkRecordMatchStatus.PARTIAL_STRUCTURAL_MATCH
        elif any(link.match_status is ChunkRecordMatchStatus.ARTIFACT_MISMATCH for link in links):
            status = ChunkRecordMatchStatus.ARTIFACT_MISMATCH
        elif any(link.match_status is ChunkRecordMatchStatus.SOURCE_IDENTITY_MISMATCH for link in links):
            status = ChunkRecordMatchStatus.SOURCE_IDENTITY_MISMATCH
        elif any(link.match_status is ChunkRecordMatchStatus.HUMAN_REVIEW_REQUIRED for link in links):
            status = ChunkRecordMatchStatus.HUMAN_REVIEW_REQUIRED
        else:
            status = ChunkRecordMatchStatus.LOCATOR_NOT_FOUND
        accepted_links = tuple(
            link
            for link in links
            if link.match_status
            in {
                ChunkRecordMatchStatus.STRUCTURAL_MATCH,
                ChunkRecordMatchStatus.PARTIAL_STRUCTURAL_MATCH,
            }
        )
        return PolicyRecordLinkAssessment(
            record_identity=record.identity,
            registered_locator=record.official_locator,
            required_locators=required,
            matched_locators=matched,
            match_status=status,
            links=accepted_links,
        )

    def assess_records(
        self,
        chunks: Iterable[SourcePolicyChunk],
        record_identities: Iterable[PolicyRecordIdentity],
    ) -> tuple[PolicyRecordLinkAssessment, ...]:
        materialized_chunks = tuple(chunks)
        assessments = tuple(
            self.assess_record(materialized_chunks, identity)
            for identity in record_identities
        )
        return tuple(
            sorted(
                assessments,
                key=lambda assessment: (
                    assessment.record_identity.source_id,
                    assessment.record_identity.version_id,
                    assessment.record_identity.record_id,
                ),
            )
        )

    def _required_locators(self, record: PolicyRecord) -> tuple[str, ...]:
        try:
            return self._requirements[record.official_locator]
        except KeyError as error:
            raise PolicyChunkError(
                f"no deterministic locator rule for registered locator: {record.official_locator}"
            ) from error

    @staticmethod
    def _link(
        chunk: SourcePolicyChunk,
        record: PolicyRecord,
        status: ChunkRecordMatchStatus,
        matched: tuple[str, ...],
        required: tuple[str, ...],
        exactness: ExcerptExactness,
    ) -> PolicyChunkRecordLink:
        return PolicyChunkRecordLink(
            chunk_id=chunk.chunk_id,
            record_identity=record.identity,
            match_status=status,
            matched_locators=matched,
            required_locators=required,
            source_page_start=chunk.page_start,
            source_page_end=chunk.page_end,
            excerpt_exactness=exactness,
            registered_locator=record.official_locator,
        )


def build_link_report(
    *,
    source_id: str,
    version_id: str,
    artifact_sha256: str,
    assessments: Sequence[PolicyRecordLinkAssessment],
) -> dict[str, object]:
    source = require_identifier(source_id, "source_id")
    version = require_identifier(version_id, "version_id")
    digest = require_sha256(artifact_sha256, "artifact_sha256")
    ordered = tuple(
        sorted(
            assessments,
            key=lambda value: value.record_identity.record_id,
        )
    )
    return {
        "schema_version": "1.0.0",
        "source_id": source,
        "version_id": version,
        "artifact_sha256": digest,
        "matching_method": "deterministic_structural_locator",
        "semantic_score_creates_links": False,
        "verified_exact_excerpt_claimed": False,
        "formal_y3172_conformance_claimed": False,
        "assessments": [assessment.to_dict() for assessment in ordered],
    }


def write_link_report(
    report_path: Path | str,
    report: Mapping[str, object],
) -> Path:
    path = Path(report_path)
    if path.is_absolute():
        raise PolicyChunkError("link report path must be repository-relative")
    if path.suffix.lower() != ".json":
        raise PolicyChunkError("link report path must end with .json")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(path)
    return path
