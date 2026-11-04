from __future__ import annotations

from dataclasses import dataclass
import hashlib

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
    MAX_POLICY_QUERY_LIMIT,
    PolicyQueryAdapter,
    PolicyQueryError,
    PolicySourceReference,
    PolicySourceReferenceError,
    build_policy_source_reference,
)
from amba_ai.rag.provenance import (
    RetrievalProvenance,
)


@dataclass(slots=True)
class RetrievedChunkFixture:
    chunk_id: int
    document_id: int
    text: str
    source_ref: str | None
    score: float


def _digest(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def _record(
    *,
    record_id: str = "RECORD-001",
    version_id: str = "v1",
    source_id: str = "SOURCE-001",
    binding_level: BindingLevel = (
        BindingLevel.PROJECT_CONTROL
    ),
    activation_status: ActivationStatus = (
        ActivationStatus.ACTIVE
    ),
    applicability_status: ApplicabilityStatus = (
        ApplicabilityStatus.APPLICABLE
    ),
    artifact_integrity_status: ArtifactIntegrityStatus = (
        ArtifactIntegrityStatus.VERIFIED
    ),
    metadata_verification_status: MetadataVerificationStatus = (
        MetadataVerificationStatus.VERIFIED
    ),
    locator_verification_status: LocatorVerificationStatus = (
        LocatorVerificationStatus.VERIFIED_STRUCTURAL
    ),
    legal_review_status: LegalReviewStatus = (
        LegalReviewStatus.NOT_APPLICABLE
    ),
    eligible_for_project_enforcement: bool = True,
    eligible_for_national_legal_finding: bool = False,
    national_binding_status: bool = False,
    eligible_for_citation: bool = True,
    locator: str = "Control 1",
) -> PolicyRecord:
    normative_text = (
        "Synthetic project control rule."
    )

    return PolicyRecord(
        identity=PolicyRecordIdentity(
            record_id=record_id,
            version_id=version_id,
            source_id=source_id,
        ),
        document_title="Policy Source",
        authority="Amba-Gov Project",
        jurisdiction="project_sandbox",
        scope="Synthetic education governance",
        binding_level=binding_level,
        official_locator=locator,
        page_start=None,
        page_end=None,
        normative_text=normative_text,
        reviewed_summary="Reviewed project summary.",
        regulated_actor="Amba-Gov sandbox",
        protected_subject="Synthetic learner",
        conditions={},
        prohibitions=(),
        exceptions=(),
        artifact_integrity_status=(
            artifact_integrity_status
        ),
        metadata_verification_status=(
            metadata_verification_status
        ),
        locator_verification_status=(
            locator_verification_status
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
            normative_text
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
        registry.register(record)

    return registry


def _source_ref(
    record: PolicyRecord,
    *,
    chunk_id: str = "1",
    locator: str | None = None,
) -> str:
    return PolicySourceReference(
        source_id=record.identity.source_id,
        record_id=record.identity.record_id,
        version_id=record.identity.version_id,
        chunk_id=chunk_id,
        locator=(
            record.official_locator
            if locator is None
            else locator
        ),
    ).to_uri()


def _hit(
    record: PolicyRecord | None,
    *,
    chunk_id: int = 1,
    score: float = 0.9,
    source_ref: str | None = None,
) -> RetrievedChunkFixture:
    resolved_ref = source_ref

    if resolved_ref is None and record is not None:
        resolved_ref = _source_ref(
            record,
            chunk_id=str(chunk_id),
        )

    return RetrievedChunkFixture(
        chunk_id=chunk_id,
        document_id=101,
        text="Retrieved policy text",
        source_ref=resolved_ref,
        score=score,
    )


def test_source_reference_round_trip() -> None:
    reference = PolicySourceReference(
        source_id="SOURCE-001",
        record_id="RECORD-001",
        version_id="v1",
        chunk_id="1",
        locator="Article 4 / Section 2",
    )

    parsed = PolicySourceReference.parse(
        reference.to_uri()
    )

    assert parsed == reference



def test_source_reference_preserves_source_id_case() -> None:
    reference = PolicySourceReference(
        source_id="SOURCE-Case-001",
        record_id="RECORD-001",
        version_id="v1",
        chunk_id="1",
        locator="Article 4",
    )
    parsed = PolicySourceReference.parse(reference.to_uri())
    assert parsed.source_id == "SOURCE-Case-001"


def test_source_reference_rejects_path_traversal() -> None:
    with pytest.raises(PolicySourceReferenceError, match="path traversal"):
        PolicySourceReference.parse("policy://SOURCE-001/../RECORD-001/v1?locator=Article%204&ref_version=1")

def test_source_reference_builds_from_provenance() -> None:
    provenance = RetrievalProvenance(
        source_id="SOURCE-001",
        document_version_id="v1",
        policy_record_id="RECORD-001",
        chunk_id="1",
        locator="Article 4",
    )

    parsed = PolicySourceReference.parse(
        build_policy_source_reference(
            provenance=provenance,
        )
    )

    assert parsed.identity == PolicyRecordIdentity(
        record_id="RECORD-001",
        version_id="v1",
        source_id="SOURCE-001",
    )


def test_source_reference_rejects_wrong_scheme() -> None:
    with pytest.raises(
        PolicySourceReferenceError,
        match="policy scheme",
    ):
        PolicySourceReference.parse(
            "https://example.invalid/policy"
        )


def test_source_reference_rejects_fragment() -> None:
    reference = PolicySourceReference(
        source_id="SOURCE-001",
        record_id="RECORD-001",
        version_id="v1",
        chunk_id="1",
        locator="Article 4",
    ).to_uri()

    with pytest.raises(
        PolicySourceReferenceError,
        match="fragment",
    ):
        PolicySourceReference.parse(
            f"{reference}#fragment"
        )


def test_source_reference_rejects_unknown_parameter() -> None:
    reference = PolicySourceReference(
        source_id="SOURCE-001",
        record_id="RECORD-001",
        version_id="v1",
        chunk_id="1",
        locator="Article 4",
    ).to_uri()

    with pytest.raises(
        PolicySourceReferenceError,
        match="unsupported query parameters",
    ):
        PolicySourceReference.parse(
            f"{reference}&override=true"
        )


def test_adapter_resolves_project_control() -> None:
    record = _record()
    adapter = PolicyQueryAdapter(
        _registry(record)
    )

    result = adapter.adapt(
        [_hit(record)]
    )[0]

    assert result.resolved is True
    assert result.policy_record == record
    assert result.provenance is not None
    assert (
        result.eligible_for_project_enforcement
        is True
    )
    assert (
        result.eligible_for_binding_findings
        is False
    )
    assert (
        result.eligible_for_supporting_evidence
        is True
    )
    assert (
        "project_control_has_no_national_legal_effect"
        in result.limitations
    )


def test_retrieval_score_does_not_create_authority() -> None:
    adapter = PolicyQueryAdapter(
        _registry()
    )

    hit = RetrievedChunkFixture(
        chunk_id=1,
        document_id=101,
        text="Fabricated authority text",
        source_ref=(
            "policy://FAKE/FAKE/v1/1"
            "?locator=Article%201"
            "&ref_version=1"
        ),
        score=1.0,
    )

    result = adapter.adapt(
        [hit]
    )[0]

    assert result.retrieval_score == 1.0
    assert result.resolved is False
    assert (
        result.eligible_for_project_enforcement
        is False
    )
    assert (
        result.eligible_for_binding_findings
        is False
    )
    assert (
        result.eligible_for_supporting_evidence
        is False
    )


def test_missing_source_reference_is_unresolved() -> None:
    result = PolicyQueryAdapter(
        _registry()
    ).adapt(
        [
            RetrievedChunkFixture(
                chunk_id=1,
                document_id=101,
                text="Uncontrolled text",
                source_ref=None,
                score=0.8,
            )
        ]
    )[0]

    assert result.resolved is False
    assert (
        "missing_policy_source_reference"
        in result.limitations
    )


def test_chunk_mismatch_is_unresolved() -> None:
    record = _record()

    result = PolicyQueryAdapter(
        _registry(record)
    ).adapt(
        [
            _hit(
                record,
                chunk_id=2,
                source_ref=_source_ref(
                    record,
                    chunk_id="1",
                ),
            )
        ]
    )[0]

    assert result.resolved is False
    assert (
        "source_reference_chunk_mismatch"
        in result.limitations
    )


def test_locator_mismatch_is_unresolved() -> None:
    record = _record()

    result = PolicyQueryAdapter(
        _registry(record)
    ).adapt(
        [
            _hit(
                record,
                source_ref=_source_ref(
                    record,
                    locator="Wrong locator",
                ),
            )
        ]
    )[0]

    assert result.resolved is False
    assert (
        "registered_policy_locator_mismatch"
        in result.limitations
    )


def test_unresolved_applicability_blocks_enforcement() -> None:
    record = _record(
        applicability_status=(
            ApplicabilityStatus.UNRESOLVED
        ),
    )

    result = PolicyQueryAdapter(
        _registry(record)
    ).adapt(
        [_hit(record)]
    )[0]

    assert result.resolved is True
    assert (
        result.eligible_for_project_enforcement
        is False
    )
    assert (
        "applicability_unresolved"
        in result.limitations
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
        eligible_for_national_legal_finding=False,
        national_binding_status=False,
    )

    result = PolicyQueryAdapter(
        _registry(record)
    ).adapt(
        [_hit(record)]
    )[0]

    assert (
        result.eligible_for_project_enforcement
        is False
    )
    assert (
        result.eligible_for_binding_findings
        is False
    )
    assert (
        result.eligible_for_supporting_evidence
        is True
    )
    assert (
        "international_or_comparative_guidance_is_not_nationally_binding"
        in result.limitations
    )


def test_inactive_record_is_unresolved_for_eligibility() -> None:
    normative_text = (
        "Inactive synthetic policy record."
    )
    record = PolicyRecord(
        identity=PolicyRecordIdentity(
            record_id="RECORD-INACTIVE",
            version_id="v1",
            source_id="SOURCE-001",
        ),
        document_title="Inactive Source",
        authority="Synthetic Authority",
        jurisdiction="project_sandbox",
        scope="Synthetic test",
        binding_level=BindingLevel.PROJECT_CONTROL,
        official_locator="Control 2",
        page_start=None,
        page_end=None,
        normative_text=normative_text,
        reviewed_summary="Inactive record.",
        regulated_actor="Synthetic actor",
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
            LegalReviewStatus.NOT_APPLICABLE
        ),
        applicability_status=(
            ApplicabilityStatus.APPLICABLE
        ),
        activation_status=ActivationStatus.INACTIVE,
        artifact_sha256=_digest(
            "inactive-artifact"
        ),
        normative_unit_sha256=_digest(
            normative_text
        ),
        eligible_for_project_enforcement=False,
        eligible_for_national_legal_finding=False,
        national_binding_status=False,
        synthetic_only=True,
        legal_effect=False,
        eligible_for_citation=False,
    )

    result = PolicyQueryAdapter(
        _registry(record)
    ).adapt(
        [_hit(record)]
    )[0]

    assert result.resolved is True
    assert (
        result.eligible_for_project_enforcement
        is False
    )
    assert (
        result.eligible_for_supporting_evidence
        is False
    )
    assert (
        "record_activation_status_inactive"
        in result.limitations
    )


def test_adapter_preserves_input_ranking() -> None:
    first = _record(
        record_id="RECORD-001"
    )
    second = _record(
        record_id="RECORD-002"
    )

    results = PolicyQueryAdapter(
        _registry(first, second)
    ).adapt(
        [
            _hit(
                first,
                score=0.95,
            ),
            _hit(
                second,
                score=0.75,
            ),
        ]
    )

    assert tuple(
        item.retrieval_rank
        for item in results
    ) == (1, 2)

    assert tuple(
        item.retrieval_score
        for item in results
    ) == (0.95, 0.75)


def test_adapter_applies_limit() -> None:
    record = _record()

    results = PolicyQueryAdapter(
        _registry(record)
    ).adapt(
        [
            _hit(
                record,
                chunk_id=index,
            )
            for index in range(1, 6)
        ],
        limit=2,
    )

    assert len(results) == 2


@pytest.mark.parametrize(
    "invalid_limit",
    [
        0,
        -1,
        MAX_POLICY_QUERY_LIMIT + 1,
        True,
        1.5,
    ],
)
def test_adapter_rejects_invalid_limit(
    invalid_limit: object,
) -> None:
    with pytest.raises(
        (TypeError, PolicyQueryError),
    ):
        PolicyQueryAdapter(
            _registry()
        ).adapt(
            [],
            limit=invalid_limit,
        )


@pytest.mark.parametrize(
    "score",
    [
        -0.1,
        1.1,
        float("nan"),
        float("inf"),
        True,
        "0.9",
    ],
)
def test_adapter_rejects_invalid_scores(
    score: object,
) -> None:
    with pytest.raises(
        (TypeError, PolicyQueryError),
    ):
        PolicyQueryAdapter(
            _registry()
        ).adapt(
            [
                RetrievedChunkFixture(
                    chunk_id=1,
                    document_id=101,
                    text="Text",
                    source_ref=None,
                    score=score,
                )
            ]
        )


def test_result_metadata_is_immutable() -> None:
    record = _record()

    result = PolicyQueryAdapter(
        _registry(record)
    ).adapt(
        [_hit(record)]
    )[0]

    with pytest.raises(TypeError):
        result.metadata["changed"] = True


def test_result_canonical_json_is_deterministic() -> None:
    record = _record()
    adapter = PolicyQueryAdapter(
        _registry(record)
    )

    first = adapter.adapt(
        [_hit(record)]
    )[0]
    second = adapter.adapt(
        [_hit(record)]
    )[0]

    assert (
        first.to_canonical_json()
        == second.to_canonical_json()
    )
