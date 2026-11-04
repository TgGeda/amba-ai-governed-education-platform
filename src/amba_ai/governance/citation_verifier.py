from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from amba_ai.governance.errors import GovernanceCitationError
from amba_ai.governance.models import (
    BindingLevel,
    PolicyRecord,
    PolicyRecordIdentity,
    to_canonical_json,
)

class CitationFailureCode(str, Enum):
    EMPTY_COLLECTION = "EMPTY_COLLECTION"
    INVALID_STRUCTURE = "INVALID_STRUCTURE"
    DUPLICATE_CITATION = "DUPLICATE_CITATION"
    RECORD_NOT_FOUND = "RECORD_NOT_FOUND"
    RECORD_INACTIVE = "RECORD_INACTIVE"
    CITATION_INELIGIBLE = "CITATION_INELIGIBLE"
    BINDING_EVIDENCE_INELIGIBLE = "BINDING_EVIDENCE_INELIGIBLE"
    BINDING_LEVEL_INELIGIBLE = "BINDING_LEVEL_INELIGIBLE"
    LOCATOR_ONLY_UNVERIFIED = "LOCATOR_ONLY_UNVERIFIED"


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


class PolicyRecordRegistryProtocol(Protocol):
    def get(self, identity: PolicyRecordIdentity) -> PolicyRecord | None:
        ...

    def get_active_by_record_id(self, record_id: str) -> PolicyRecord | None:
        ...

    def require_active_by_record_id(self, record_id: str) -> PolicyRecord:
        ...

    def eligible_for_citation(self, identity: PolicyRecordIdentity) -> bool:
        ...


@dataclass(frozen=True, slots=True)
class CitationReference:
    record_id: str
    version_id: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _require_text(self.record_id, "record_id"))
        object.__setattr__(self, "version_id", _require_text(self.version_id, "version_id"))
        object.__setattr__(self, "source_id", _require_text(self.source_id, "source_id"))

    @property
    def identity(self) -> PolicyRecordIdentity:
        return PolicyRecordIdentity(
            record_id=self.record_id,
            version_id=self.version_id,
            source_id=self.source_id,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "record_id": self.record_id,
            "version_id": self.version_id,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class CitationFailure:
    code: CitationFailureCode
    message: str
    record_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, CitationFailureCode):
            raise TypeError("code must be a CitationFailureCode")
        object.__setattr__(self, "message", _require_text(self.message, "message"))
        if self.record_id is not None:
            object.__setattr__(self, "record_id", _require_text(self.record_id, "record_id"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "record_id": self.record_id,
        }


@dataclass(frozen=True, slots=True)
class CitationVerificationResult:
    valid: bool
    verified_record_ids: tuple[str, ...]
    failures: tuple[CitationFailure, ...]

    def __post_init__(self) -> None:
        if type(self.valid) is not bool:
            raise TypeError("valid must be a strict Boolean")
        if not isinstance(self.verified_record_ids, tuple):
            raise TypeError("verified_record_ids must be a tuple")
        if not isinstance(self.failures, tuple):
            raise TypeError("failures must be a tuple")

        record_ids = tuple(
            _require_text(value, "verified_record_id")
            for value in self.verified_record_ids
        )
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("verified_record_ids cannot contain duplicates")
        if any(not isinstance(value, CitationFailure) for value in self.failures):
            raise TypeError("failures must contain only CitationFailure values")
        if self.valid and self.failures:
            raise ValueError("valid result cannot contain failures")
        if not self.valid and not self.failures:
            raise ValueError("invalid result requires at least one failure")

        object.__setattr__(self, "verified_record_ids", tuple(sorted(record_ids)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "verified_record_ids": list(self.verified_record_ids),
            "failures": [failure.to_dict() for failure in self.failures],
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())

    def require_valid(self) -> None:
        if not self.valid:
            codes = ", ".join(failure.code.value for failure in self.failures)
            raise GovernanceCitationError(f"Citation verification failed: {codes}")


class CitationVerifier:
    def __init__(self, record_registry: PolicyRecordRegistryProtocol) -> None:
        if record_registry is None:
            raise TypeError("record_registry is required")
        for method_name in (
            "get",
            "get_active_by_record_id",
            "require_active_by_record_id",
            "eligible_for_citation",
        ):
            if not callable(getattr(record_registry, method_name, None)):
                raise TypeError(
                    "record_registry must provide callable "
                    f"{method_name}"
                )
        self._record_registry = record_registry

    @property
    def record_registry(self) -> PolicyRecordRegistryProtocol:
        return self._record_registry

    def verify(
        self,
        citations: tuple[Mapping[str, Any] | CitationReference, ...],
        *,
        binding_use: bool,
        require_citations: bool = True,
    ) -> CitationVerificationResult:
        if not isinstance(citations, tuple):
            raise TypeError("citations must be a tuple")
        if type(binding_use) is not bool:
            raise TypeError("binding_use must be a strict Boolean")
        if type(require_citations) is not bool:
            raise TypeError("require_citations must be a strict Boolean")

        if not citations:
            if require_citations:
                return CitationVerificationResult(
                    valid=False,
                    verified_record_ids=(),
                    failures=(
                        CitationFailure(
                            code=CitationFailureCode.EMPTY_COLLECTION,
                            message="At least one structured citation is required",
                        ),
                    ),
                )
            return CitationVerificationResult(
                valid=True,
                verified_record_ids=(),
                failures=(),
            )

        verified: list[str] = []
        failures: list[CitationFailure] = []
        seen: set[PolicyRecordIdentity] = set()

        for raw_citation in citations:
            citation = self._parse_reference(raw_citation)
            if isinstance(citation, CitationFailure):
                failures.append(citation)
                continue

            identity = citation.identity
            if identity in seen:
                failures.append(
                    CitationFailure(
                        code=CitationFailureCode.DUPLICATE_CITATION,
                        record_id=citation.record_id,
                        message="Duplicate policy-record citation",
                    )
                )
                continue
            seen.add(identity)

            record = self._record_registry.get(identity)
            if record is None:
                failures.append(
                    CitationFailure(
                        code=CitationFailureCode.RECORD_NOT_FOUND,
                        record_id=citation.record_id,
                        message="Policy record identity is not registered",
                    )
                )
                continue

            active_record = self._record_registry.get_active_by_record_id(
                citation.record_id
            )
            if active_record is None or active_record.identity != identity:
                failures.append(
                    CitationFailure(
                        code=CitationFailureCode.RECORD_INACTIVE,
                        record_id=citation.record_id,
                        message="Cited policy-record version is not active",
                    )
                )
                continue

            if self._record_registry.eligible_for_citation(identity) is not True:
                failures.append(
                    CitationFailure(
                        code=CitationFailureCode.CITATION_INELIGIBLE,
                        record_id=citation.record_id,
                        message="Policy record is not eligible for citation",
                    )
                )
                continue

            if binding_use:
                binding_failure = self._binding_failure(record)
                if binding_failure is not None:
                    failures.append(binding_failure)
                    continue

            verified.append(citation.record_id)

        return CitationVerificationResult(
            valid=not failures,
            verified_record_ids=tuple(sorted(set(verified))),
            failures=tuple(failures),
        )

    @staticmethod
    def _parse_reference(
        citation: Mapping[str, Any] | CitationReference,
    ) -> CitationReference | CitationFailure:
        if isinstance(citation, CitationReference):
            return citation
        if not isinstance(citation, Mapping):
            return CitationFailure(
                code=CitationFailureCode.INVALID_STRUCTURE,
                message="Citation must be a structured mapping",
            )

        keys = set(citation)
        identity_keys = {"record_id", "version_id", "source_id"}
        if identity_keys.issubset(keys):
            try:
                return CitationReference(
                    record_id=citation["record_id"],
                    version_id=citation["version_id"],
                    source_id=citation["source_id"],
                )
            except (TypeError, ValueError):
                return CitationFailure(
                    code=CitationFailureCode.INVALID_STRUCTURE,
                    message="Citation identity fields must be nonempty strings",
                )

        if {"source_id", "locator"}.issubset(keys):
            return CitationFailure(
                code=CitationFailureCode.LOCATOR_ONLY_UNVERIFIED,
                message=(
                    "Source-and-locator citations cannot support verified "
                    "policy-record evidence"
                ),
            )

        return CitationFailure(
            code=CitationFailureCode.INVALID_STRUCTURE,
            message="Citation fields do not match a supported structure",
        )

    @staticmethod
    def _binding_failure(record: PolicyRecord) -> CitationFailure | None:
        eligible = getattr(record, "eligible_for_project_enforcement", None)
        if type(eligible) is not bool or not eligible:
            return CitationFailure(
                code=CitationFailureCode.BINDING_EVIDENCE_INELIGIBLE,
                record_id=record.identity.record_id,
                message="Policy record is not eligible for project enforcement",
            )

        if record.binding_level is not BindingLevel.PROJECT_CONTROL:
            return CitationFailure(
                code=CitationFailureCode.BINDING_LEVEL_INELIGIBLE,
                record_id=record.identity.record_id,
                message=(
                    "Policy-record binding level is not eligible for the "
                    "project-enforcement boundary"
                ),
            )
        return None
