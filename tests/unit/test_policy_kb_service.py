from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

import pytest

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
    TranslationStatus,
)
from amba_ai.governance.record_registry import (
    PolicyRecordRegistry,
)
from amba_ai.rag.policy_query import (
    PolicyQueryAdapter,
    PolicySourceReference,
)
from amba_ai.services.policy_kb_service import (
    MAX_POLICY_QUERY_LIMIT,
    PolicyEvidenceSummary,
    PolicyKBQueryResponse,
    PolicyKBSearchError,
    PolicyKBService,
    PolicyKBServiceError,
)


@dataclass(slots=True)
class SearchHit:
    chunk_id: object
    document_id: object
    text: str
    source_ref: str | None
    score: float


class SearchEngineStub:
    def __init__(
        self,
        results: object,
    ) -> None:
        self.results = results
        self.calls: list[
            tuple[str, int, float]
        ] = []

    def search(
        self,
        query: str,
        top_k: int = 10,
        min_similarity: float = 0.40,
    ) -> list:
        self.calls.append(
            (
                query,
                top_k,
                min_similarity,
            )
        )

        if isinstance(
            self.results,
            BaseException,
        ):
            raise self.results

        return self.results

def _digest(
    value: str,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def _record(
    *,
    record_id: str = "RECORD-001",
    binding_level: BindingLevel = (
        BindingLevel.PROJECT_CONTROL
    ),
    activation_status: ActivationStatus = (
        ActivationStatus.ACTIVE
    ),
    applicability_status: ApplicabilityStatus = (
        ApplicabilityStatus.APPLICABLE
    ),
    legal_review_status: LegalReviewStatus = (
        LegalReviewStatus.NOT_APPLICABLE
    ),
    national_binding_status: bool = False,
    eligible_for_project_enforcement: bool = True,
    eligible_for_national_legal_finding: bool = False,
    eligible_for_citation: bool = True,
) -> PolicyRecord:
    text = (
        "Synthetic project policy control."
    )

    return PolicyRecord(
        identity=PolicyRecordIdentity(
            record_id=record_id,
            version_id="v1",
            source_id="SOURCE-001",
        ),
        document_title="Synthetic Policy Source",
        authority="Amba-Gov Project",
        jurisdiction="project_sandbox",
        scope="Synthetic education governance",
        binding_level=binding_level,
        official_locator="Control 1",
        page_start=None,
        page_end=None,
        normative_text=text,
        reviewed_summary="Reviewed synthetic summary.",
        regulated_actor="Amba-Gov sandbox",
        protected_subject="Synthetic learner",
        conditions={},
        prohibitions=(),
        exceptions=(),
        artifact_integrity_status=(
            ArtifactIntegrityStatus.VERIFIED
        ),
        metadata_verification_status=(
            MetadataVerificationStatus.VERIFIED
        ),
        locator_verification_status=(
            LocatorVerificationStatus.VERIFIED_STRUCTURAL
        ),
        translation_status=(
            TranslationStatus.NOT_APPLICABLE
        ),
        legal_review_status=(
            legal_review_status
        ),
        applicability_status=(
            applicability_status
        ),
        activation_status=(
            activation_status
        ),
        artifact_sha256=_digest(
            "artifact"
        ),
        normative_unit_sha256=_digest(
            text
        ),
        eligible_for_project_enforcement=(
            eligible_for_project_enforcement
        ),
        eligible_for_national_legal_finding=(
            eligible_for_national_legal_finding
        ),
        national_binding_status=(
            national_binding_status
        ),
        synthetic_only=True,
        legal_effect=False,
        eligible_for_citation=(
            eligible_for_citation
        ),
    )


def _registry(
    *records: PolicyRecord,
) -> PolicyRecordRegistry:
    registry = PolicyRecordRegistry()

    for record in records:
        registry.register(
            record
        )

    return registry


def _source_ref(
    record: PolicyRecord,
    *,
    chunk_id: str = "1",
) -> str:
    return PolicySourceReference(
        source_id=record.identity.source_id,
        record_id=record.identity.record_id,
        version_id=record.identity.version_id,
        chunk_id=chunk_id,
        locator=record.official_locator,
    ).to_uri()


def _hit(
    record: PolicyRecord,
    *,
    chunk_id: int = 1,
    score: float = 0.9,
) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        document_id=100,
        text="Retrieved synthetic policy text.",
        source_ref=_source_ref(
            record,
            chunk_id=str(chunk_id),
        ),
        score=score,
    )


def _service(
    *,
    records: tuple[PolicyRecord, ...] = (),
    hits: object = (),
) -> tuple[
    PolicyKBService,
    SearchEngineStub,
]:
    engine = SearchEngineStub(
        hits
    )
    adapter = PolicyQueryAdapter(
        _registry(*records)
    )

    return (
        PolicyKBService(
            search_engine=engine,
            query_adapter=adapter,
        ),
        engine,
    )


def test_constructor_requires_search_engine() -> None:
    with pytest.raises(
        TypeError,
        match="search_engine",
    ):
        PolicyKBService(
            search_engine=object(),
            query_adapter=PolicyQueryAdapter(
                _registry()
            ),
        )


def test_constructor_requires_query_adapter() -> None:
    engine = SearchEngineStub(
        []
    )

    with pytest.raises(
        TypeError,
        match="query_adapter",
    ):
        PolicyKBService(
            search_engine=engine,
            query_adapter=object(),
        )


def test_query_delegates_to_search_engine() -> None:
    record = _record()
    service, engine = _service(
        records=(record,),
        hits=[_hit(record)],
    )

    response = service.query(
        "  commercial   purchasing  ",
        limit=5,
        min_similarity=0.65,
    )

    assert engine.calls == [
        (
            "commercial purchasing",
            5,
            0.65,
        )
    ]
    assert len(response.results) == 1


def test_query_delegates_every_hit_to_adapter() -> None:
    first = _record(
        record_id="RECORD-001"
    )
    second = _record(
        record_id="RECORD-002"
    )

    service, _ = _service(
        records=(first, second),
        hits=[
            _hit(
                first,
                chunk_id=1,
                score=0.95,
            ),
            _hit(
                second,
                chunk_id=2,
                score=0.85,
            ),
        ],
    )

    response = service.query(
        "commercial purchasing",
        limit=2,
    )

    assert len(response.results) == 2
    assert tuple(
        result.retrieval_rank
        for result in response.results
    ) == (1, 2)


def test_empty_results_report_explicit_gaps() -> None:
    service, _ = _service(
        hits=[],
    )

    response = service.query(
        "unavailable policy evidence"
    )

    assert response.summary.retrieved_count == 0
    assert response.summary.resolved_count == 0

    assert (
        "no_relevant_policy_evidence_retrieved"
        in response.evidence_gaps
    )
    assert (
        "no_project_enforcement_eligible_record"
        in response.evidence_gaps
    )
    assert (
        "no_binding_finding_eligible_record"
        in response.evidence_gaps
    )
    assert (
        "no_supporting_evidence_eligible_record"
        in response.evidence_gaps
    )


def test_unresolved_results_report_gaps() -> None:
    service, _ = _service(
        hits=[
            SearchHit(
                chunk_id=1,
                document_id=100,
                text="Uncontrolled retrieved content.",
                source_ref=None,
                score=0.9,
            )
        ],
    )

    response = service.query(
        "unresolved evidence"
    )

    assert response.summary.retrieved_count == 1
    assert response.summary.resolved_count == 0
    assert response.summary.unresolved_count == 1

    assert (
        "retrieved_results_do_not_resolve_to_registered_policy_records"
        in response.evidence_gaps
    )
    assert (
        "one_or_more_retrieved_results_are_unresolved"
        in response.evidence_gaps
    )


def test_project_control_is_not_binding_evidence() -> None:
    record = _record()

    service, _ = _service(
        records=(record,),
        hits=[_hit(record)],
    )

    response = service.query(
        "project safeguard"
    )

    assert (
        response
        .has_project_enforcement_evidence
        is True
    )
    assert (
        response
        .has_binding_finding_evidence
        is False
    )
    assert (
        response.has_supporting_evidence
        is True
    )

    assert (
        "no_binding_finding_eligible_record"
        in response.evidence_gaps
    )


def test_unresolved_applicability_is_reported() -> None:
    record = _record(
        applicability_status=(
            ApplicabilityStatus.UNRESOLVED
        ),
    )

    service, _ = _service(
        records=(record,),
        hits=[_hit(record)],
    )

    response = service.query(
        "unresolved applicability"
    )

    assert (
        response
        .has_project_enforcement_evidence
        is False
    )

    assert (
        "policy_applicability_requires_resolution"
        in response.evidence_gaps
    )


def test_international_guidance_is_supporting_only() -> None:
    record = _record(
        binding_level=(
            BindingLevel.INTERNATIONAL_GUIDANCE
        ),
        legal_review_status=(
            LegalReviewStatus.NOT_PERFORMED
        ),
        eligible_for_project_enforcement=False,
    )

    service, _ = _service(
        records=(record,),
        hits=[_hit(record)],
    )

    response = service.query(
        "international guidance"
    )

    assert (
        response
        .has_project_enforcement_evidence
        is False
    )
    assert (
        response
        .has_binding_finding_evidence
        is False
    )
    assert (
        response.has_supporting_evidence
        is True
    )

    assert (
        "international_or_comparative_guidance_is_supporting_only"
        in response.evidence_gaps
    )


def test_response_includes_non_authorizing_limitations() -> None:
    service, _ = _service(
        hits=[],
    )

    response = service.query(
        "policy evidence"
    )

    assert (
        "semantic_relevance_does_not_establish_authority"
        in response.limitations
    )
    assert (
        "retrieval_does_not_establish_legal_applicability"
        in response.limitations
    )
    assert (
        "absence_from_the_registered_corpus_does_not_prove_absence_of_law"
        in response.limitations
    )
    assert (
        "policy_kb_results_do_not_authorize_runtime_execution"
        in response.limitations
    )


def test_response_metadata_prohibits_decision_side_effects() -> None:
    service, _ = _service(
        hits=[],
    )

    response = service.query(
        "policy evidence"
    )

    assert (
        response.metadata[
            "governance_decision_created"
        ]
        is False
    )
    assert (
        response.metadata[
            "approval_created"
        ]
        is False
    )
    assert (
        response.metadata[
            "execution_requested"
        ]
        is False
    )
    assert (
        response.metadata[
            "distribution_attempted"
        ]
        is False
    )
    assert (
        response.metadata[
            "audit_verification_claimed"
        ]
        is False
    )


def test_query_normalization_is_deterministic() -> None:
    service, _ = _service(
        hits=[],
    )

    first = service.query(
        "  policy    evidence ",
        limit=5,
        min_similarity=0.5,
    )
    second = service.query(
        "policy evidence",
        limit=5,
        min_similarity=0.5,
    )

    assert first.query == second.query
    assert (
        first.query_digest
        == second.query_digest
    )
    assert (
        first.to_canonical_json()
        == second.to_canonical_json()
    )


@pytest.mark.parametrize(
    "query",
    [
        "",
        " ",
        "\n\t",
        "a",
    ],
)
def test_query_rejects_empty_or_short_input(
    query: str,
) -> None:
    service, _ = _service(
        hits=[],
    )

    with pytest.raises(
        PolicyKBServiceError,
    ):
        service.query(query)


def test_query_rejects_oversized_input() -> None:
    service, _ = _service(
        hits=[],
    )

    with pytest.raises(
        PolicyKBServiceError,
        match="must not exceed",
    ):
        service.query(
            "x" * 4_097
        )


@pytest.mark.parametrize(
    "limit",
    [
        0,
        -1,
        MAX_POLICY_QUERY_LIMIT + 1,
        True,
        1.5,
    ],
)
def test_query_rejects_invalid_limit(
    limit: object,
) -> None:
    service, _ = _service(
        hits=[],
    )

    with pytest.raises(
        (TypeError, PolicyKBServiceError),
    ):
        service.query(
            "policy evidence",
            limit=limit,
        )


@pytest.mark.parametrize(
    "min_similarity",
    [
        -0.1,
        1.1,
        float("nan"),
        float("inf"),
        True,
        "0.5",
    ],
)
def test_query_rejects_invalid_similarity(
    min_similarity: object,
) -> None:
    service, _ = _service(
        hits=[],
    )

    with pytest.raises(
        (TypeError, PolicyKBServiceError),
    ):
        service.query(
            "policy evidence",
            min_similarity=min_similarity,
        )


def test_search_failure_is_wrapped() -> None:
    service, _ = _service(
        hits=RuntimeError(
            "backend unavailable"
        ),
    )

    with pytest.raises(
        PolicyKBSearchError,
        match="search failed",
    ) as captured:
        service.query(
            "policy evidence"
        )

    assert isinstance(
        captured.value.__cause__,
        RuntimeError,
    )


@pytest.mark.parametrize(
    "invalid_results",
    [
        None,
        "invalid",
        b"invalid",
        {
            "invalid": "mapping",
        },
        123,
    ],
)
def test_invalid_search_results_fail_closed(
    invalid_results: object,
) -> None:
    service, _ = _service(
        hits=invalid_results,
    )

    with pytest.raises(
        PolicyKBSearchError,
    ):
        service.query(
            "policy evidence"
        )


def test_response_summary_rejects_inconsistent_counts() -> None:
    with pytest.raises(
        PolicyKBServiceError,
        match="equal retrieved_count",
    ):
        PolicyEvidenceSummary(
            retrieved_count=2,
            resolved_count=1,
            unresolved_count=0,
            project_enforcement_eligible_count=0,
            binding_finding_eligible_count=0,
            supporting_evidence_eligible_count=0,
        )


def test_response_metadata_is_immutable() -> None:
    service, _ = _service(
        hits=[],
    )

    response = service.query(
        "policy evidence"
    )

    with pytest.raises(TypeError):
        response.metadata["changed"] = True


def test_service_exposes_no_decision_or_execution_methods() -> None:
    service, _ = _service(
        hits=[],
    )

    for method_name in (
        "evaluate",
        "recommend",
        "approve",
        "execute",
        "deliver",
        "distribute",
        "audit",
    ):
        assert not hasattr(
            service,
            method_name,
        )


def test_response_is_policy_evidence_only() -> None:
    service, _ = _service(
        hits=[],
    )

    response = service.query(
        "policy evidence"
    )

    assert isinstance(
        response,
        PolicyKBQueryResponse,
    )
    assert not hasattr(
        response,
        "finding"
    )
    assert not hasattr(
        response,
        "recommendation"
    )
    assert not hasattr(
        response,
        "approval"
    )
    assert not hasattr(
        response,
        "execution_receipt"
    )
