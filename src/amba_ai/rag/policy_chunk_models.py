from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from typing import Any

from amba_ai.governance.models import (
    ActivationStatus,
    BindingLevel,
    LegalReviewStatus,
    LocatorVerificationStatus,
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@#/-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PolicyChunkError(ValueError):
    pass


def require_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise PolicyChunkError(f"{field_name} must not be empty")
    if _IDENTIFIER_RE.fullmatch(normalized) is None:
        raise PolicyChunkError(f"{field_name} contains invalid characters")
    return normalized


def require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = " ".join(value.split())
    if not normalized:
        raise PolicyChunkError(f"{field_name} must not be empty")
    return normalized


def require_sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip().lower()
    if _SHA256_RE.fullmatch(normalized) is None:
        raise PolicyChunkError(f"{field_name} must be a lowercase SHA-256 digest")
    return normalized


@dataclass(frozen=True, slots=True)
class ChunkingProfile:
    version: str = "amba-policy-v1"
    embedding_model: str = "intfloat/multilingual-e5-small"
    target_tokens: int = 320
    maximum_tokens: int = 420
    overlap_tokens: int = 48
    minimum_tokens: int = 30

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", require_identifier(self.version, "version"))
        object.__setattr__(self, "embedding_model", require_text(self.embedding_model, "embedding_model"))
        for field_name in ("target_tokens", "maximum_tokens", "overlap_tokens", "minimum_tokens"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
        if self.minimum_tokens <= 0:
            raise PolicyChunkError("minimum_tokens must be positive")
        if self.target_tokens < self.minimum_tokens:
            raise PolicyChunkError("target_tokens must be greater than or equal to minimum_tokens")
        if self.maximum_tokens < self.target_tokens:
            raise PolicyChunkError("maximum_tokens must be greater than or equal to target_tokens")
        if not 0 <= self.overlap_tokens < self.target_tokens:
            raise PolicyChunkError("overlap_tokens must be non-negative and less than target_tokens")


@dataclass(frozen=True, slots=True)
class PolicyChunkIdentity:
    chunk_id: str
    record_id: str
    version_id: str
    source_id: str
    chunk_index: int

    def __post_init__(self) -> None:
        for field_name in ("chunk_id", "record_id", "version_id", "source_id"):
            object.__setattr__(self, field_name, require_identifier(getattr(self, field_name), field_name))
        if isinstance(self.chunk_index, bool) or not isinstance(self.chunk_index, int):
            raise TypeError("chunk_index must be an integer")
        if self.chunk_index < 0:
            raise PolicyChunkError("chunk_index must be non-negative")


@dataclass(frozen=True, slots=True)
class PolicyChunk:
    identity: PolicyChunkIdentity
    artifact_sha256: str
    artifact_path: str
    page_start: int
    page_end: int
    official_locator: str
    section_title: str | None
    provision_numbers: tuple[str, ...]
    raw_text: str
    text_sha256: str
    token_count: int
    chunking_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, PolicyChunkIdentity):
            raise TypeError("identity must be a PolicyChunkIdentity")
        object.__setattr__(self, "artifact_sha256", require_sha256(self.artifact_sha256, "artifact_sha256"))
        object.__setattr__(self, "text_sha256", require_sha256(self.text_sha256, "text_sha256"))
        object.__setattr__(self, "artifact_path", require_text(self.artifact_path, "artifact_path"))
        object.__setattr__(self, "official_locator", require_text(self.official_locator, "official_locator"))
        object.__setattr__(self, "raw_text", require_text(self.raw_text, "raw_text"))
        object.__setattr__(self, "chunking_version", require_identifier(self.chunking_version, "chunking_version"))
        if self.section_title is not None:
            object.__setattr__(self, "section_title", require_text(self.section_title, "section_title"))
        if not isinstance(self.provision_numbers, tuple):
            raise TypeError("provision_numbers must be a tuple")
        provisions = tuple(require_text(value, "provision_number") for value in self.provision_numbers)
        if len(provisions) != len(set(provisions)):
            raise PolicyChunkError("provision_numbers must not contain duplicates")
        object.__setattr__(self, "provision_numbers", provisions)
        for field_name in ("page_start", "page_end", "token_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
        if self.page_start < 1 or self.page_end < self.page_start:
            raise PolicyChunkError("invalid page range")
        if self.token_count < 1:
            raise PolicyChunkError("token_count must be positive")
        actual = hashlib.sha256(self.raw_text.encode("utf-8")).hexdigest()
        if actual != self.text_sha256:
            raise PolicyChunkError("text_sha256 does not match raw_text")
        expected_prefix = (
            f"{self.identity.record_id}@{self.identity.version_id}:"
            f"p{self.page_start}-p{self.page_end}:c{self.identity.chunk_index:04d}:"
        )
        if not self.identity.chunk_id.startswith(expected_prefix):
            raise PolicyChunkError("chunk_id is not bound to identity, page range, and index")
        if not self.identity.chunk_id.endswith(self.text_sha256[:12]):
            raise PolicyChunkError("chunk_id is not bound to text_sha256")

    def to_embedding_payload(self, source_title: str) -> str:
        title = require_text(source_title, "source_title")
        section = self.section_title or "General"
        return (
            f"passage: {title}\n"
            f"section: {section}\n"
            f"locator: {self.official_locator}\n"
            f"text: {self.raw_text}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.identity.chunk_id,
            "record_id": self.identity.record_id,
            "version_id": self.identity.version_id,
            "source_id": self.identity.source_id,
            "chunk_index": self.identity.chunk_index,
            "artifact_sha256": self.artifact_sha256,
            "artifact_path": self.artifact_path,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "official_locator": self.official_locator,
            "section_title": self.section_title,
            "provision_numbers": list(self.provision_numbers),
            "raw_text": self.raw_text,
            "text_sha256": self.text_sha256,
            "token_count": self.token_count,
            "chunking_version": self.chunking_version,
        }


@dataclass(frozen=True, slots=True)
class GroundedChunkRetrievalResult:
    chunk: PolicyChunk
    binding_level: BindingLevel
    activation_status: ActivationStatus
    national_binding_status: bool
    legal_review_status: LegalReviewStatus
    locator_verification_status: LocatorVerificationStatus
    eligible_for_project_enforcement: bool
    eligible_for_national_legal_finding: bool
    eligible_for_citation: bool
    retrieval_score: float
    retrieval_rank: int

    def __post_init__(self) -> None:
        if not isinstance(self.chunk, PolicyChunk):
            raise TypeError("chunk must be a PolicyChunk")
        for field_name, enum_type in (
            ("binding_level", BindingLevel),
            ("activation_status", ActivationStatus),
            ("legal_review_status", LegalReviewStatus),
            ("locator_verification_status", LocatorVerificationStatus),
        ):
            if not isinstance(getattr(self, field_name), enum_type):
                raise TypeError(f"{field_name} must be a {enum_type.__name__}")
        for field_name in (
            "national_binding_status",
            "eligible_for_project_enforcement",
            "eligible_for_national_legal_finding",
            "eligible_for_citation",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a strict Boolean")
        if isinstance(self.retrieval_score, bool) or not isinstance(self.retrieval_score, float):
            raise TypeError("retrieval_score must be a float")
        if not math.isfinite(self.retrieval_score):
            raise PolicyChunkError("retrieval_score must be finite")
        if isinstance(self.retrieval_rank, bool) or not isinstance(self.retrieval_rank, int):
            raise TypeError("retrieval_rank must be an integer")
        if self.retrieval_rank < 1:
            raise PolicyChunkError("retrieval_rank must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk": self.chunk.to_dict(),
            "binding_level": self.binding_level.value,
            "activation_status": self.activation_status.value,
            "national_binding_status": self.national_binding_status,
            "legal_review_status": self.legal_review_status.value,
            "locator_verification_status": self.locator_verification_status.value,
            "eligible_for_project_enforcement": self.eligible_for_project_enforcement,
            "eligible_for_national_legal_finding": self.eligible_for_national_legal_finding,
            "eligible_for_citation": self.eligible_for_citation,
            "retrieval_score": self.retrieval_score,
            "retrieval_rank": self.retrieval_rank,
        }
