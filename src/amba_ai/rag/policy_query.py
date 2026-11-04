from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Iterable, Mapping
from typing import Any, Protocol, runtime_checkable
from urllib.parse import parse_qs, quote, unquote, urlparse

from amba_ai.governance.models import (
    ActivationStatus,
    ApplicabilityStatus,
    ArtifactIntegrityStatus,
    BindingLevel,
    LegalReviewStatus,
    LocatorVerificationStatus,
    MetadataVerificationStatus,
    PolicyRecord,
    PolicyRecordIdentity,
    deep_freeze,
    to_canonical_json,
)
from amba_ai.governance.record_registry import (
    PolicyRecordRegistry,
)
from amba_ai.rag.provenance import RetrievalProvenance


POLICY_SOURCE_SCHEME = "policy"
POLICY_SOURCE_REFERENCE_VERSION = "1"
DEFAULT_POLICY_QUERY_LIMIT = 10
MAX_POLICY_QUERY_LIMIT = 100

_BINDING_FINDING_LEVELS = frozenset(
    {
        BindingLevel.PRIMARY_LEGISLATION,
        BindingLevel.REGULATION,
        BindingLevel.DIRECTIVE,
    }
)

_SUPPORTING_EVIDENCE_LEVELS = frozenset(
    {
        BindingLevel.PRIMARY_LEGISLATION,
        BindingLevel.REGULATION,
        BindingLevel.DIRECTIVE,
        BindingLevel.NATIONAL_POLICY,
        BindingLevel.INSTITUTIONAL_GUIDANCE,
        BindingLevel.TECHNICAL_STANDARD,
        BindingLevel.INTERNATIONAL_GUIDANCE,
        BindingLevel.COMPARATIVE_GUIDANCE,
        BindingLevel.PROJECT_CONTROL,
        BindingLevel.SYNTHETIC_TEST_RULE,
    }
)


class PolicyQueryError(ValueError):
    pass


class PolicySourceReferenceError(PolicyQueryError):
    pass


@runtime_checkable
class RetrievedChunkProtocol(Protocol):
    chunk_id: object
    document_id: object
    text: str
    source_ref: str | None
    score: float


def _require_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string"
        )

    normalized = value.strip()

    if not normalized:
        raise PolicyQueryError(
            f"{field_name} must not be empty"
        )

    return normalized


def _optional_text(
    value: object | None,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    return _require_text(
        value,
        field_name,
    )


def _normalize_score(
    value: object,
) -> float:
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise TypeError(
            "retrieval_score must be numeric"
        )

    normalized = float(value)

    if math.isnan(normalized) or math.isinf(normalized):
        raise PolicyQueryError(
            "retrieval_score must be finite"
        )

    if normalized < 0.0 or normalized > 1.0:
        raise PolicyQueryError(
            "retrieval_score must be between 0 and 1"
        )

    return normalized


def _normalize_rank(
    value: object,
) -> int:
    if isinstance(value, bool) or not isinstance(
        value,
        int,
    ):
        raise TypeError(
            "retrieval_rank must be an integer"
        )

    if value < 1:
        raise PolicyQueryError(
            "retrieval_rank must be positive"
        )

    return value


def _normalize_limit(
    value: object,
) -> int:
    if isinstance(value, bool) or not isinstance(
        value,
        int,
    ):
        raise TypeError(
            "limit must be an integer"
        )

    if value < 1 or value > MAX_POLICY_QUERY_LIMIT:
        raise PolicyQueryError(
            f"limit must be between 1 and "
            f"{MAX_POLICY_QUERY_LIMIT}"
        )

    return value


def _normalize_text_tuple(
    value: object,
    field_name: str,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(
            f"{field_name} must be a tuple"
        )

    normalized = tuple(
        _require_text(
            item,
            f"{field_name} item",
        )
        for item in value
    )

    if len(normalized) != len(set(normalized)):
        raise PolicyQueryError(
            f"{field_name} must not contain duplicates"
        )

    return normalized


def _record_is_quarantined(
    record: PolicyRecord,
) -> bool:
    return (
        record.activation_status
        is ActivationStatus.QUARANTINED
        or record.legal_review_status
        is LegalReviewStatus.QUARANTINED_PENDING_EXTRACTION
        or record.artifact_integrity_status
        in {
            ArtifactIntegrityStatus.MISMATCH,
            ArtifactIntegrityStatus.CORRUPTED,
        }
    )


def _project_enforcement_eligible(
    record: PolicyRecord,
) -> bool:
    return bool(
        record.activation_status
        is ActivationStatus.ACTIVE
        and not _record_is_quarantined(record)
        and record.eligible_for_project_enforcement
        and record.artifact_integrity_status
        is ArtifactIntegrityStatus.VERIFIED
        and record.metadata_verification_status
        in {
            MetadataVerificationStatus.VERIFIED,
            MetadataVerificationStatus.PARTIALLY_VERIFIED,
        }
        and record.locator_verification_status
        in {
            LocatorVerificationStatus.VERIFIED_EXACT,
            LocatorVerificationStatus.VERIFIED_STRUCTURAL,
        }
        and record.applicability_status
        is ApplicabilityStatus.APPLICABLE
    )


def _binding_finding_eligible(
    record: PolicyRecord,
) -> bool:
    return bool(
        record.activation_status
        is ActivationStatus.ACTIVE
        and not _record_is_quarantined(record)
        and record.binding_level
        in _BINDING_FINDING_LEVELS
        and record.eligible_for_national_legal_finding
        and record.national_binding_status
        and record.artifact_integrity_status
        is ArtifactIntegrityStatus.VERIFIED
        and record.metadata_verification_status
        is MetadataVerificationStatus.VERIFIED
        and record.locator_verification_status
        is LocatorVerificationStatus.VERIFIED_EXACT
        and record.legal_review_status
        is LegalReviewStatus.CONFIRMED_APPLICABLE
        and record.applicability_status
        is ApplicabilityStatus.APPLICABLE
    )


def _supporting_evidence_eligible(
    record: PolicyRecord,
) -> bool:
    return bool(
        record.activation_status
        is ActivationStatus.ACTIVE
        and not _record_is_quarantined(record)
        and record.binding_level
        in _SUPPORTING_EVIDENCE_LEVELS
        and record.eligible_for_citation
        and record.artifact_integrity_status
        is ArtifactIntegrityStatus.VERIFIED
        and record.locator_verification_status
        in {
            LocatorVerificationStatus.VERIFIED_EXACT,
            LocatorVerificationStatus.VERIFIED_STRUCTURAL,
        }
    )


def _derive_limitations(
    record: PolicyRecord | None,
    *,
    source_reference_resolved: bool,
    locator_matches: bool,
) -> tuple[str, ...]:
    limitations: list[str] = []

    if not source_reference_resolved:
        limitations.append(
            "source_reference_unresolved"
        )

    if record is None:
        limitations.append(
            "policy_record_not_registered"
        )

        return tuple(limitations)

    if not locator_matches:
        limitations.append(
            "retrieval_locator_does_not_match_registered_record"
        )

    if record.activation_status is not ActivationStatus.ACTIVE:
        limitations.append(
            f"record_activation_status_{record.activation_status.value}"
        )

    if _record_is_quarantined(record):
        limitations.append(
            "record_quarantined_or_integrity_restricted"
        )

    if (
        record.artifact_integrity_status
        is not ArtifactIntegrityStatus.VERIFIED
    ):
        limitations.append(
            "artifact_integrity_not_verified"
        )

    if record.metadata_verification_status not in {
        MetadataVerificationStatus.VERIFIED,
        MetadataVerificationStatus.PARTIALLY_VERIFIED,
    }:
        limitations.append(
            "metadata_not_verified"
        )

    if record.locator_verification_status not in {
        LocatorVerificationStatus.VERIFIED_EXACT,
        LocatorVerificationStatus.VERIFIED_STRUCTURAL,
    }:
        limitations.append(
            "locator_not_verified"
        )

    if record.applicability_status is ApplicabilityStatus.UNRESOLVED:
        limitations.append(
            "applicability_unresolved"
        )

    if record.applicability_status is ApplicabilityStatus.NOT_ASSESSED:
        limitations.append(
            "applicability_not_assessed"
        )

    if record.applicability_status is ApplicabilityStatus.INAPPLICABLE:
        limitations.append(
            "record_inapplicable"
        )

    if (
        record.binding_level
        in {
            BindingLevel.INTERNATIONAL_GUIDANCE,
            BindingLevel.COMPARATIVE_GUIDANCE,
        }
        and not record.national_binding_status
    ):
        limitations.append(
            "international_or_comparative_guidance_is_not_nationally_binding"
        )

    if (
        record.binding_level
        is BindingLevel.PROJECT_CONTROL
    ):
        limitations.append(
            "project_control_has_no_national_legal_effect"
        )

    if not record.eligible_for_citation:
        limitations.append(
            "record_not_eligible_for_citation"
        )

    if not record.eligible_for_project_enforcement:
        limitations.append(
            "record_not_eligible_for_project_enforcement"
        )

    if not record.eligible_for_national_legal_finding:
        limitations.append(
            "record_not_eligible_for_national_legal_finding"
        )

    return tuple(
        sorted(set(limitations))
    )


@dataclass(frozen=True, slots=True)
class PolicySourceReference:
    source_id: str
    record_id: str
    version_id: str
    chunk_id: str
    locator: str

    def __post_init__(self) -> None:
        source_id = _require_text(
            self.source_id,
            "source_id",
        )
        record_id = _require_text(
            self.record_id,
            "record_id",
        )
        version_id = _require_text(
            self.version_id,
            "version_id",
        )
        chunk_id = _require_text(
            self.chunk_id,
            "chunk_id",
        )
        locator = _require_text(
            self.locator,
            "locator",
        )

        for field_name, value in (
            ("source_id", source_id),
            ("record_id", record_id),
            ("version_id", version_id),
            ("chunk_id", chunk_id),
        ):
            if "/" in value:
                raise PolicySourceReferenceError(
                    f"{field_name} must not contain '/'"
                )

        object.__setattr__(
            self,
            "source_id",
            source_id,
        )
        object.__setattr__(
            self,
            "record_id",
            record_id,
        )
        object.__setattr__(
            self,
            "version_id",
            version_id,
        )
        object.__setattr__(
            self,
            "chunk_id",
            chunk_id,
        )
        object.__setattr__(
            self,
            "locator",
            locator,
        )

    @property
    def identity(
        self,
    ) -> PolicyRecordIdentity:
        return PolicyRecordIdentity(
            record_id=self.record_id,
            version_id=self.version_id,
            source_id=self.source_id,
        )

    def to_uri(self) -> str:
        return (
            f"{POLICY_SOURCE_SCHEME}://"
            f"{quote(self.source_id, safe='')}/"
            f"{quote(self.record_id, safe='')}/"
            f"{quote(self.version_id, safe='')}/"
            f"{quote(self.chunk_id, safe='')}"
            f"?locator={quote(self.locator, safe='')}"
            f"&ref_version="
            f"{POLICY_SOURCE_REFERENCE_VERSION}"
        )

    @classmethod
    def parse(
        cls,
        value: str,
    ) -> "PolicySourceReference":
        source_ref = _require_text(
            value,
            "source_ref",
        )

        try:
            parsed = urlparse(
                source_ref
            )
        except ValueError as exc:
            raise PolicySourceReferenceError(
                "source_ref is not a valid URI"
            ) from exc

        if parsed.scheme != POLICY_SOURCE_SCHEME:
            raise PolicySourceReferenceError(
                "source_ref must use the policy scheme"
            )

        if parsed.username is not None or parsed.password is not None:
            raise PolicySourceReferenceError(
                "source_ref must not contain user information"
            )

        if parsed.fragment:
            raise PolicySourceReferenceError(
                "source_ref must not contain a fragment"
            )

        netloc = parsed.netloc

        if not netloc:
            raise PolicySourceReferenceError(
                "source_ref requires a source identifier"
            )

        if "@" in netloc:
            raise PolicySourceReferenceError(
                "source_ref must not contain user information"
            )

        if ":" in netloc:
            raise PolicySourceReferenceError(
                "source_ref must not contain a port"
            )

        source_id = unquote(netloc)

        path_parts = tuple(
            unquote(item)
            for item in parsed.path.split("/")
            if item
        )

        if any(
            part in {".", ".."}
            for part in path_parts
        ):
            raise PolicySourceReferenceError(
                "source_ref path traversal is prohibited"
            )

        if len(path_parts) != 3:
            raise PolicySourceReferenceError(
                "source_ref path must contain "
                "record_id, version_id, and chunk_id"
            )

        query = parse_qs(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
        )

        allowed_parameters = {
            "locator",
            "ref_version",
        }

        unknown_parameters = (
            set(query)
            - allowed_parameters
        )

        if unknown_parameters:
            raise PolicySourceReferenceError(
                "source_ref contains unsupported query parameters"
            )

        locator_values = query.get(
            "locator",
            [],
        )
        version_values = query.get(
            "ref_version",
            [],
        )

        if len(locator_values) != 1:
            raise PolicySourceReferenceError(
                "source_ref requires exactly one locator"
            )

        if len(version_values) != 1:
            raise PolicySourceReferenceError(
                "source_ref requires exactly one ref_version"
            )

        if (
            version_values[0]
            != POLICY_SOURCE_REFERENCE_VERSION
        ):
            raise PolicySourceReferenceError(
                "source_ref version is unsupported"
            )

        return cls(
            source_id=source_id,
            record_id=path_parts[0],
            version_id=path_parts[1],
            chunk_id=path_parts[2],
            locator=unquote(
                locator_values[0]
            ),
        )


@dataclass(frozen=True, slots=True)
class PolicyQueryResult:
    retrieval_rank: int
    retrieval_score: float
    selection_reason: str
    chunk_id: str
    document_id: str
    source_ref: str | None
    provenance: RetrievalProvenance | None
    policy_record: PolicyRecord | None
    source_reference_resolved: bool
    locator_matches_registered_record: bool
    eligible_for_project_enforcement: bool
    eligible_for_binding_findings: bool
    eligible_for_supporting_evidence: bool
    limitations: tuple[str, ...]
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        retrieval_rank = _normalize_rank(
            self.retrieval_rank
        )
        retrieval_score = _normalize_score(
            self.retrieval_score
        )
        selection_reason = _require_text(
            self.selection_reason,
            "selection_reason",
        )
        chunk_id = _require_text(
            self.chunk_id,
            "chunk_id",
        )
        document_id = _require_text(
            self.document_id,
            "document_id",
        )
        source_ref = _optional_text(
            self.source_ref,
            "source_ref",
        )

        if (
            self.provenance is not None
            and not isinstance(
                self.provenance,
                RetrievalProvenance,
            )
        ):
            raise TypeError(
                "provenance must be a "
                "RetrievalProvenance or None"
            )

        if (
            self.policy_record is not None
            and not isinstance(
                self.policy_record,
                PolicyRecord,
            )
        ):
            raise TypeError(
                "policy_record must be a PolicyRecord or None"
            )

        for field_name in (
            "source_reference_resolved",
            "locator_matches_registered_record",
            "eligible_for_project_enforcement",
            "eligible_for_binding_findings",
            "eligible_for_supporting_evidence",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(
                    f"{field_name} must be a strict Boolean"
                )

        limitations = _normalize_text_tuple(
            self.limitations,
            "limitations",
        )

        if not isinstance(self.metadata, Mapping):
            raise TypeError(
                "metadata must be a mapping"
            )

        if (
            self.source_reference_resolved
            != (
                self.provenance is not None
                and self.policy_record is not None
            )
        ):
            raise PolicyQueryError(
                "source reference resolution state is inconsistent"
            )

        if (
            self.locator_matches_registered_record
            and not self.source_reference_resolved
        ):
            raise PolicyQueryError(
                "locator match requires a resolved source reference"
            )

        if any(
            (
                self.eligible_for_project_enforcement,
                self.eligible_for_binding_findings,
                self.eligible_for_supporting_evidence,
            )
        ) and not self.source_reference_resolved:
            raise PolicyQueryError(
                "unresolved results cannot be eligible"
            )

        if self.policy_record is not None:
            expected_project = (
                _project_enforcement_eligible(
                    self.policy_record
                )
                and self.locator_matches_registered_record
            )
            expected_binding = (
                _binding_finding_eligible(
                    self.policy_record
                )
                and self.locator_matches_registered_record
            )
            expected_supporting = (
                _supporting_evidence_eligible(
                    self.policy_record
                )
                and self.locator_matches_registered_record
            )

            if (
                self.eligible_for_project_enforcement
                is not expected_project
            ):
                raise PolicyQueryError(
                    "project enforcement eligibility is inconsistent"
                )

            if (
                self.eligible_for_binding_findings
                is not expected_binding
            ):
                raise PolicyQueryError(
                    "binding-finding eligibility is inconsistent"
                )

            if (
                self.eligible_for_supporting_evidence
                is not expected_supporting
            ):
                raise PolicyQueryError(
                    "supporting-evidence eligibility is inconsistent"
                )

        frozen_metadata = deep_freeze(
            self.metadata
        )

        object.__setattr__(
            self,
            "retrieval_rank",
            retrieval_rank,
        )
        object.__setattr__(
            self,
            "retrieval_score",
            retrieval_score,
        )
        object.__setattr__(
            self,
            "selection_reason",
            selection_reason,
        )
        object.__setattr__(
            self,
            "chunk_id",
            chunk_id,
        )
        object.__setattr__(
            self,
            "document_id",
            document_id,
        )
        object.__setattr__(
            self,
            "source_ref",
            source_ref,
        )
        object.__setattr__(
            self,
            "limitations",
            limitations,
        )
        object.__setattr__(
            self,
            "metadata",
            frozen_metadata,
        )

        to_canonical_json(
            self.to_dict()
        )

    @property
    def resolved(
        self,
    ) -> bool:
        return self.source_reference_resolved

    @property
    def authority_class(
        self,
    ) -> str | None:
        if self.policy_record is None:
            return None

        return self.policy_record.binding_level.value

    @property
    def applicability_status(
        self,
    ) -> str | None:
        if self.policy_record is None:
            return None

        return self.policy_record.applicability_status.value

    @property
    def activation_status(
        self,
    ) -> str | None:
        if self.policy_record is None:
            return None

        return self.policy_record.activation_status.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval_rank": self.retrieval_rank,
            "retrieval_score": self.retrieval_score,
            "selection_reason": self.selection_reason,
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "source_ref": self.source_ref,
            "provenance": (
                None
                if self.provenance is None
                else self.provenance.to_dict()
            ),
            "policy_record": (
                None
                if self.policy_record is None
                else self.policy_record.to_dict()
            ),
            "source_reference_resolved": (
                self.source_reference_resolved
            ),
            "locator_matches_registered_record": (
                self.locator_matches_registered_record
            ),
            "authority_class": self.authority_class,
            "applicability_status": (
                self.applicability_status
            ),
            "activation_status": (
                self.activation_status
            ),
            "eligible_for_project_enforcement": (
                self.eligible_for_project_enforcement
            ),
            "eligible_for_binding_findings": (
                self.eligible_for_binding_findings
            ),
            "eligible_for_supporting_evidence": (
                self.eligible_for_supporting_evidence
            ),
            "limitations": list(self.limitations),
            "metadata": self.metadata,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(
            self.to_dict()
        )


class PolicyQueryAdapter:
    def __init__(
        self,
        registry: PolicyRecordRegistry,
    ) -> None:
        if not isinstance(
            registry,
            PolicyRecordRegistry,
        ):
            raise TypeError(
                "registry must be a PolicyRecordRegistry"
            )

        self._registry = registry

    @property
    def registry(
        self,
    ) -> PolicyRecordRegistry:
        return self._registry

    def adapt(
        self,
        hits: Iterable[RetrievedChunkProtocol],
        *,
        limit: int = DEFAULT_POLICY_QUERY_LIMIT,
    ) -> tuple[PolicyQueryResult, ...]:
        normalized_limit = _normalize_limit(
            limit
        )

        if isinstance(
            hits,
            (
                str,
                bytes,
                bytearray,
                Mapping,
            ),
        ):
            raise TypeError(
                "hits must be an iterable of retrieved chunks"
            )

        try:
            materialized = tuple(hits)
        except TypeError as exc:
            raise TypeError(
                "hits must be iterable"
            ) from exc

        results: list[PolicyQueryResult] = []

        for rank, hit in enumerate(
            materialized[:normalized_limit],
            start=1,
        ):
            results.append(
                self._adapt_hit(
                    hit,
                    retrieval_rank=rank,
                )
            )

        return tuple(results)

    def _adapt_hit(
        self,
        hit: RetrievedChunkProtocol,
        *,
        retrieval_rank: int,
    ) -> PolicyQueryResult:
        if not isinstance(
            hit,
            RetrievedChunkProtocol,
        ):
            raise TypeError(
                "hits must provide chunk_id, document_id, "
                "text, source_ref, and score"
            )

        chunk_id = _require_text(
            str(hit.chunk_id),
            "chunk_id",
        )
        document_id = _require_text(
            str(hit.document_id),
            "document_id",
        )
        text = _require_text(
            hit.text,
            "text",
        )
        retrieval_score = _normalize_score(
            hit.score
        )
        source_ref = _optional_text(
            hit.source_ref,
            "source_ref",
        )

        reference: PolicySourceReference | None = None
        record: PolicyRecord | None = None
        provenance: RetrievalProvenance | None = None
        locator_matches = False
        resolution_error: str | None = None

        if source_ref is None:
            resolution_error = (
                "missing_policy_source_reference"
            )
        else:
            try:
                reference = PolicySourceReference.parse(
                    source_ref
                )
            except (
                TypeError,
                ValueError,
                PolicySourceReferenceError,
            ) as exc:
                resolution_error = (
                    f"invalid_policy_source_reference:"
                    f"{type(exc).__name__}"
                )

        if reference is not None:
            if reference.chunk_id != chunk_id:
                resolution_error = (
                    "source_reference_chunk_mismatch"
                )
            else:
                record = self._registry.get(
                    reference.identity
                )

                if record is None:
                    resolution_error = (
                        "registered_policy_record_not_found"
                    )
                else:
                    locator_matches = (
                        reference.locator
                        == record.official_locator
                    )

                    if not locator_matches:
                        resolution_error = (
                            "registered_policy_locator_mismatch"
                        )
                    else:
                        provenance = RetrievalProvenance(
                            source_id=(
                                reference.source_id
                            ),
                            document_version_id=(
                                reference.version_id
                            ),
                            policy_record_id=(
                                reference.record_id
                            ),
                            chunk_id=(
                                reference.chunk_id
                            ),
                            locator=(
                                reference.locator
                            ),
                            page_start=(
                                record.page_start
                            ),
                            page_end=(
                                record.page_end
                            ),
                        )

        source_reference_resolved = bool(
            record is not None
            and provenance is not None
            and locator_matches
        )

        project_eligible = bool(
            source_reference_resolved
            and _project_enforcement_eligible(
                record
            )
        )

        binding_eligible = bool(
            source_reference_resolved
            and _binding_finding_eligible(
                record
            )
        )

        supporting_eligible = bool(
            source_reference_resolved
            and _supporting_evidence_eligible(
                record
            )
        )

        limitations = list(
            _derive_limitations(
                record,
                source_reference_resolved=(
                    source_reference_resolved
                ),
                locator_matches=locator_matches,
            )
        )

        if resolution_error is not None:
            limitations.append(
                resolution_error
            )

        selection_reason = (
            "Semantic retrieval result. Authority, "
            "applicability, activation, and eligibility "
            "were resolved independently through the "
            "policy-record registry."
        )

        return PolicyQueryResult(
            retrieval_rank=retrieval_rank,
            retrieval_score=retrieval_score,
            selection_reason=selection_reason,
            chunk_id=chunk_id,
            document_id=document_id,
            source_ref=source_ref,
            provenance=provenance,
            policy_record=record,
            source_reference_resolved=(
                source_reference_resolved
            ),
            locator_matches_registered_record=(
                locator_matches
            ),
            eligible_for_project_enforcement=(
                project_eligible
            ),
            eligible_for_binding_findings=(
                binding_eligible
            ),
            eligible_for_supporting_evidence=(
                supporting_eligible
            ),
            limitations=tuple(
                sorted(set(limitations))
            ),
            metadata={
                "retrieved_text_sha256": __import__(
                    "hashlib"
                ).sha256(
                    text.encode("utf-8")
                ).hexdigest(),
                "semantic_relevance_only": True,
                "authority_derived_from_score": False,
            },
        )


def build_policy_source_reference(
    *,
    provenance: RetrievalProvenance,
) -> str:
    if not isinstance(
        provenance,
        RetrievalProvenance,
    ):
        raise TypeError(
            "provenance must be a RetrievalProvenance"
        )

    return PolicySourceReference(
        source_id=provenance.source_id,
        record_id=provenance.policy_record_id,
        version_id=provenance.document_version_id,
        chunk_id=provenance.chunk_id,
        locator=provenance.locator,
    ).to_uri()
