from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any, Mapping, Protocol, runtime_checkable

from amba_ai.governance.models import (
    deep_freeze,
    to_canonical_json,
)
from amba_ai.rag.policy_query import (
    DEFAULT_POLICY_QUERY_LIMIT,
    MAX_POLICY_QUERY_LIMIT,
    PolicyQueryAdapter,
    PolicyQueryResult,
)


DEFAULT_MIN_SIMILARITY = 0.40
MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 4_096


class PolicyKBServiceError(ValueError):
    pass


class PolicyKBSearchError(PolicyKBServiceError):
    pass


@runtime_checkable
class PolicySearchEngineProtocol(Protocol):
    def search(
        self,
        query: str,
        top_k: int = DEFAULT_POLICY_QUERY_LIMIT,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> list[Any]:
        ...


def _require_query(
    value: object,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            "query must be a string"
        )

    normalized = " ".join(
        value.split()
    )

    if len(normalized) < MIN_QUERY_LENGTH:
        raise PolicyKBServiceError(
            f"query must contain at least "
            f"{MIN_QUERY_LENGTH} characters"
        )

    if len(normalized) > MAX_QUERY_LENGTH:
        raise PolicyKBServiceError(
            f"query must not exceed "
            f"{MAX_QUERY_LENGTH} characters"
        )

    if "\x00" in normalized:
        raise PolicyKBServiceError(
            "query must not contain null characters"
        )

    return normalized


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

    if (
        value < 1
        or value > MAX_POLICY_QUERY_LIMIT
    ):
        raise PolicyKBServiceError(
            f"limit must be between 1 and "
            f"{MAX_POLICY_QUERY_LIMIT}"
        )

    return value


def _normalize_min_similarity(
    value: object,
) -> float:
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise TypeError(
            "min_similarity must be numeric"
        )

    normalized = float(value)

    if (
        math.isnan(normalized)
        or math.isinf(normalized)
    ):
        raise PolicyKBServiceError(
            "min_similarity must be finite"
        )

    if (
        normalized < 0.0
        or normalized > 1.0
    ):
        raise PolicyKBServiceError(
            "min_similarity must be between 0 and 1"
        )

    return normalized


def _normalize_text_tuple(
    value: object,
    field_name: str,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(
            f"{field_name} must be a tuple"
        )

    normalized: list[str] = []

    for item in value:
        if not isinstance(item, str):
            raise TypeError(
                f"{field_name} items must be strings"
            )

        text = item.strip()

        if not text:
            raise PolicyKBServiceError(
                f"{field_name} items must not be empty"
            )

        normalized.append(text)

    result = tuple(normalized)

    if len(result) != len(set(result)):
        raise PolicyKBServiceError(
            f"{field_name} must not contain duplicates"
        )

    return result


def _query_digest(
    query: str,
    *,
    limit: int,
    min_similarity: float,
) -> str:
    payload = {
        "query": query,
        "limit": limit,
        "min_similarity": min_similarity,
    }

    return hashlib.sha256(
        to_canonical_json(
            payload
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class PolicyEvidenceSummary:
    retrieved_count: int
    resolved_count: int
    unresolved_count: int
    project_enforcement_eligible_count: int
    binding_finding_eligible_count: int
    supporting_evidence_eligible_count: int

    def __post_init__(self) -> None:
        values = {
            "retrieved_count": self.retrieved_count,
            "resolved_count": self.resolved_count,
            "unresolved_count": self.unresolved_count,
            "project_enforcement_eligible_count": (
                self.project_enforcement_eligible_count
            ),
            "binding_finding_eligible_count": (
                self.binding_finding_eligible_count
            ),
            "supporting_evidence_eligible_count": (
                self.supporting_evidence_eligible_count
            ),
        }

        for field_name, value in values.items():
            if isinstance(value, bool) or not isinstance(
                value,
                int,
            ):
                raise TypeError(
                    f"{field_name} must be an integer"
                )

            if value < 0:
                raise PolicyKBServiceError(
                    f"{field_name} must not be negative"
                )

        if (
            self.resolved_count
            + self.unresolved_count
            != self.retrieved_count
        ):
            raise PolicyKBServiceError(
                "resolved and unresolved counts must "
                "equal retrieved_count"
            )

        for field_name in (
            "project_enforcement_eligible_count",
            "binding_finding_eligible_count",
            "supporting_evidence_eligible_count",
        ):
            if (
                getattr(self, field_name)
                > self.resolved_count
            ):
                raise PolicyKBServiceError(
                    f"{field_name} must not exceed "
                    "resolved_count"
                )

    def to_dict(self) -> dict[str, int]:
        return {
            "retrieved_count": self.retrieved_count,
            "resolved_count": self.resolved_count,
            "unresolved_count": self.unresolved_count,
            "project_enforcement_eligible_count": (
                self.project_enforcement_eligible_count
            ),
            "binding_finding_eligible_count": (
                self.binding_finding_eligible_count
            ),
            "supporting_evidence_eligible_count": (
                self.supporting_evidence_eligible_count
            ),
        }


@dataclass(frozen=True, slots=True)
class PolicyKBQueryResponse:
    query: str
    query_digest: str
    limit: int
    min_similarity: float
    results: tuple[PolicyQueryResult, ...]
    summary: PolicyEvidenceSummary
    evidence_gaps: tuple[str, ...]
    limitations: tuple[str, ...]
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        query = _require_query(
            self.query
        )

        if not isinstance(
            self.query_digest,
            str,
        ):
            raise TypeError(
                "query_digest must be a string"
            )

        query_digest = self.query_digest.strip()

        if (
            len(query_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in query_digest
            )
        ):
            raise PolicyKBServiceError(
                "query_digest must be a lowercase "
                "SHA-256 hexadecimal digest"
            )

        limit = _normalize_limit(
            self.limit
        )
        min_similarity = (
            _normalize_min_similarity(
                self.min_similarity
            )
        )

        expected_digest = _query_digest(
            query,
            limit=limit,
            min_similarity=min_similarity,
        )

        if query_digest != expected_digest:
            raise PolicyKBServiceError(
                "query_digest does not match "
                "the normalized query parameters"
            )

        if not isinstance(
            self.results,
            tuple,
        ):
            raise TypeError(
                "results must be a tuple"
            )

        if any(
            not isinstance(
                result,
                PolicyQueryResult,
            )
            for result in self.results
        ):
            raise TypeError(
                "results must contain "
                "PolicyQueryResult objects"
            )

        expected_ranks = tuple(
            range(
                1,
                len(self.results) + 1,
            )
        )
        actual_ranks = tuple(
            result.retrieval_rank
            for result in self.results
        )

        if actual_ranks != expected_ranks:
            raise PolicyKBServiceError(
                "result ranks must be contiguous "
                "and start at one"
            )

        if len(self.results) > limit:
            raise PolicyKBServiceError(
                "result count must not exceed limit"
            )

        if not isinstance(
            self.summary,
            PolicyEvidenceSummary,
        ):
            raise TypeError(
                "summary must be a "
                "PolicyEvidenceSummary"
            )

        if (
            self.summary.retrieved_count
            != len(self.results)
        ):
            raise PolicyKBServiceError(
                "summary retrieved_count does not "
                "match result count"
            )

        evidence_gaps = _normalize_text_tuple(
            self.evidence_gaps,
            "evidence_gaps",
        )
        limitations = _normalize_text_tuple(
            self.limitations,
            "limitations",
        )

        if not isinstance(
            self.metadata,
            Mapping,
        ):
            raise TypeError(
                "metadata must be a mapping"
            )

        frozen_metadata = deep_freeze(
            self.metadata
        )

        object.__setattr__(
            self,
            "query",
            query,
        )
        object.__setattr__(
            self,
            "query_digest",
            query_digest,
        )
        object.__setattr__(
            self,
            "limit",
            limit,
        )
        object.__setattr__(
            self,
            "min_similarity",
            min_similarity,
        )
        object.__setattr__(
            self,
            "evidence_gaps",
            evidence_gaps,
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
    def has_resolved_evidence(
        self,
    ) -> bool:
        return self.summary.resolved_count > 0

    @property
    def has_project_enforcement_evidence(
        self,
    ) -> bool:
        return (
            self.summary
            .project_enforcement_eligible_count
            > 0
        )

    @property
    def has_binding_finding_evidence(
        self,
    ) -> bool:
        return (
            self.summary
            .binding_finding_eligible_count
            > 0
        )

    @property
    def has_supporting_evidence(
        self,
    ) -> bool:
        return (
            self.summary
            .supporting_evidence_eligible_count
            > 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "query_digest": self.query_digest,
            "limit": self.limit,
            "min_similarity": self.min_similarity,
            "results": [
                result.to_dict()
                for result in self.results
            ],
            "summary": self.summary.to_dict(),
            "evidence_gaps": list(
                self.evidence_gaps
            ),
            "limitations": list(
                self.limitations
            ),
            "metadata": self.metadata,
            "has_resolved_evidence": (
                self.has_resolved_evidence
            ),
            "has_project_enforcement_evidence": (
                self.has_project_enforcement_evidence
            ),
            "has_binding_finding_evidence": (
                self.has_binding_finding_evidence
            ),
            "has_supporting_evidence": (
                self.has_supporting_evidence
            ),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(
            self.to_dict()
        )


def _summarize(
    results: tuple[PolicyQueryResult, ...],
) -> PolicyEvidenceSummary:
    resolved_count = sum(
        result.resolved
        for result in results
    )

    return PolicyEvidenceSummary(
        retrieved_count=len(results),
        resolved_count=resolved_count,
        unresolved_count=(
            len(results) - resolved_count
        ),
        project_enforcement_eligible_count=sum(
            result.eligible_for_project_enforcement
            for result in results
        ),
        binding_finding_eligible_count=sum(
            result.eligible_for_binding_findings
            for result in results
        ),
        supporting_evidence_eligible_count=sum(
            result.eligible_for_supporting_evidence
            for result in results
        ),
    )


def _derive_evidence_gaps(
    results: tuple[PolicyQueryResult, ...],
    summary: PolicyEvidenceSummary,
) -> tuple[str, ...]:
    gaps: list[str] = []

    if summary.retrieved_count == 0:
        gaps.append(
            "no_relevant_policy_evidence_retrieved"
        )

    if (
        summary.retrieved_count > 0
        and summary.resolved_count == 0
    ):
        gaps.append(
            "retrieved_results_do_not_resolve_to_registered_policy_records"
        )

    if summary.unresolved_count > 0:
        gaps.append(
            "one_or_more_retrieved_results_are_unresolved"
        )

    if (
        summary
        .project_enforcement_eligible_count
        == 0
    ):
        gaps.append(
            "no_project_enforcement_eligible_record"
        )

    if (
        summary
        .binding_finding_eligible_count
        == 0
    ):
        gaps.append(
            "no_binding_finding_eligible_record"
        )

    if (
        summary
        .supporting_evidence_eligible_count
        == 0
    ):
        gaps.append(
            "no_supporting_evidence_eligible_record"
        )

    if any(
        (
            result.policy_record is not None
            and result.applicability_status
            in {
                "unresolved",
                "not_assessed",
            }
        )
        for result in results
    ):
        gaps.append(
            "policy_applicability_requires_resolution"
        )

    if any(
        "record_quarantined_or_integrity_restricted"
        in result.limitations
        for result in results
    ):
        gaps.append(
            "quarantined_or_integrity_restricted_evidence_present"
        )

    if any(
        "locator_not_verified"
        in result.limitations
        or (
            "retrieval_locator_does_not_match_registered_record"
            in result.limitations
        )
        for result in results
    ):
        gaps.append(
            "one_or_more_policy_locators_are_unverified"
        )

    if any(
        (
            "international_or_comparative_guidance_is_not_nationally_binding"
            in result.limitations
        )
        for result in results
    ):
        gaps.append(
            "international_or_comparative_guidance_is_supporting_only"
        )

    return tuple(
        sorted(set(gaps))
    )


def _derive_limitations(
    results: tuple[PolicyQueryResult, ...],
) -> tuple[str, ...]:
    limitations = {
        "semantic_relevance_does_not_establish_authority",
        "retrieval_does_not_establish_legal_applicability",
        "absence_from_the_registered_corpus_does_not_prove_absence_of_law",
        "policy_kb_results_do_not_authorize_runtime_execution",
    }

    for result in results:
        limitations.update(
            result.limitations
        )

    return tuple(
        sorted(limitations)
    )


class PolicyKBService:
    def __init__(
        self,
        *,
        search_engine: PolicySearchEngineProtocol,
        query_adapter: PolicyQueryAdapter,
    ) -> None:
        if not isinstance(
            search_engine,
            PolicySearchEngineProtocol,
        ):
            raise TypeError(
                "search_engine must implement "
                "PolicySearchEngineProtocol"
            )

        if not isinstance(
            query_adapter,
            PolicyQueryAdapter,
        ):
            raise TypeError(
                "query_adapter must be a "
                "PolicyQueryAdapter"
            )

        self._search_engine = search_engine
        self._query_adapter = query_adapter

    @property
    def search_engine(
        self,
    ) -> PolicySearchEngineProtocol:
        return self._search_engine

    @property
    def query_adapter(
        self,
    ) -> PolicyQueryAdapter:
        return self._query_adapter

    def query(
        self,
        query: str,
        *,
        limit: int = DEFAULT_POLICY_QUERY_LIMIT,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> PolicyKBQueryResponse:
        normalized_query = _require_query(
            query
        )
        normalized_limit = _normalize_limit(
            limit
        )
        normalized_similarity = (
            _normalize_min_similarity(
                min_similarity
            )
        )

        try:
            hits = self._search_engine.search(
                normalized_query,
                top_k=normalized_limit,
                min_similarity=normalized_similarity,
            )
        except Exception as exc:
            raise PolicyKBSearchError(
                "policy knowledge-base search failed"
            ) from exc

        if hits is None:
            raise PolicyKBSearchError(
                "policy knowledge-base search "
                "returned None"
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
            raise PolicyKBSearchError(
                "policy knowledge-base search returned "
                "an invalid result collection"
            )

        try:
            materialized_hits = tuple(
                hits
            )
        except TypeError as exc:
            raise PolicyKBSearchError(
                "policy knowledge-base search returned "
                "a non-iterable result"
            ) from exc

        results = self._query_adapter.adapt(
            materialized_hits,
            limit=normalized_limit,
        )

        summary = _summarize(
            results
        )
        evidence_gaps = (
            _derive_evidence_gaps(
                results,
                summary,
            )
        )
        limitations = _derive_limitations(
            results
        )

        return PolicyKBQueryResponse(
            query=normalized_query,
            query_digest=_query_digest(
                normalized_query,
                limit=normalized_limit,
                min_similarity=normalized_similarity,
            ),
            limit=normalized_limit,
            min_similarity=normalized_similarity,
            results=results,
            summary=summary,
            evidence_gaps=evidence_gaps,
            limitations=limitations,
            metadata={
                "service_role": (
                    "policy_evidence_retrieval"
                ),
                "semantic_relevance_only": True,
                "governance_decision_created": False,
                "approval_created": False,
                "execution_requested": False,
                "distribution_attempted": False,
                "audit_verification_claimed": False,
            },
        )
