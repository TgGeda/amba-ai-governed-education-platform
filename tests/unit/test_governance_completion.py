from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest

from amba_ai.governance.applicability import (
    PolicyApplicabilityEvaluation,
    aggregate_applicability,
)
from amba_ai.governance.distribution import (
    DistributionBlockExecutor,
    DistributionDisposition,
    DistributionEffect,
    DistributionPermitExecutor,
    ReviewQueueExecutor,
)
from amba_ai.governance.errors import GovernanceApplicabilityError
from amba_ai.governance.manifest_verifier import (
    ManifestFailureCode,
    ManifestVerifier,
)
from amba_ai.governance.models import (
    ApplicabilityStatus,
    BindingLevel,
    EnforcementAction,
    EvidenceSufficiency,
    FindingSeverity,
    PolicyFinding,
    PolicyVerdict,
)
from amba_ai.governance.recommendation import derive_recommendation
from amba_ai.rag.policy_chunking import PolicyStructureChunker


def make_recommendation_finding(
    *,
    finding_id: str,
    finding_code: str,
    severity: FindingSeverity,
    verdict: PolicyVerdict,
    evidence_sufficiency: EvidenceSufficiency = EvidenceSufficiency.SUFFICIENT,
) -> PolicyFinding:
    return PolicyFinding(
        finding_id=finding_id,
        event_id="SYNTHETIC-EVENT",
        finding_code=finding_code,
        basis_category=BindingLevel.PROJECT_CONTROL,
        severity=severity,
        verdict=verdict,
        evaluator_id="recommendation-evaluator",
        primary_records=(),
        supporting_records=(),
        rationale="Synthetic governance evaluation completed.",
        evidence_sufficiency=evidence_sufficiency,
        deterministic_result=True,
        applicability_details={
            "scope": {
                "applicable": True,
            },
        },
    )


def test_unresolved_applicability_fails_closed() -> None:
    evaluation = PolicyApplicabilityEvaluation(
        evaluator_id="applicability-evaluator",
        event_id="synthetic-event",
        policy_record_id="SYNTH-PROJECT-CONTROL",
        status=ApplicabilityStatus.UNRESOLVED,
        rationale_code="MISSING_EVIDENCE",
        unresolved_questions=("Which active record applies?",),
    )

    with pytest.raises(
        GovernanceApplicabilityError,
        match="Applicability is unresolved",
    ):
        evaluation.require_resolved()

    assert aggregate_applicability((evaluation,)) is ApplicabilityStatus.UNRESOLVED


def test_recommendation_aggregates_all_findings_deterministically() -> None:
    findings = (
        make_recommendation_finding(
            finding_id="FINDING-REVIEW",
            finding_code="REVIEW_REQUIRED",
            severity=FindingSeverity.RESTRICTIVE,
            verdict=PolicyVerdict.NONCOMPLIANT,
        ),
        make_recommendation_finding(
            finding_id="FINDING-BLOCK",
            finding_code="BLOCK_REQUIRED",
            severity=FindingSeverity.CRITICAL,
            verdict=PolicyVerdict.NONCOMPLIANT,
        ),
    )

    decision = derive_recommendation(
        findings,
        unresolved_questions=(
            "UNRESOLVED-REVIEW",
            "UNRESOLVED-BLOCK",
        ),
    )

    assert decision.action is EnforcementAction.BLOCK
    assert decision.rationale_codes == (
        "BLOCK_REQUIRED",
        "REVIEW_REQUIRED",
    )
    assert decision.unresolved_questions == (
        "UNRESOLVED-BLOCK",
        "UNRESOLVED-REVIEW",
    )
    assert decision.to_canonical_json()


def test_recommendation_derives_question_for_insufficient_evidence() -> None:
    finding = make_recommendation_finding(
        finding_id="FINDING-EVIDENCE",
        finding_code="EVIDENCE_REQUIRED",
        severity=FindingSeverity.WARNING,
        verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
        evidence_sufficiency=EvidenceSufficiency.INSUFFICIENT,
    )

    decision = derive_recommendation((finding,))

    assert decision.action is EnforcementAction.HOLD_FOR_REVIEW
    assert decision.unresolved_questions == (
        "Resolve finding EVIDENCE_REQUIRED",
    )


def test_distribution_permit_records_delivery() -> None:
    effect = DistributionPermitExecutor().execute(
        "SYNTHETIC-DESTINATION",
        {"request_id": "SYNTHETIC-REQUEST"},
    )

    assert effect.disposition is DistributionDisposition.DELIVERED
    assert effect.delivered is True
    assert effect.prevented is False
    assert effect.queued_for_review is False
    assert effect.details["delivery_recorded"] is True
    assert effect.details["simulated"] is True
    assert effect.details["legal_effect"] is False


def test_distribution_block_has_observable_effect() -> None:
    effect = DistributionBlockExecutor().execute(
        "SYNTHETIC-DESTINATION",
        {"request_id": "SYNTHETIC-REQUEST"},
    )

    assert effect.disposition is DistributionDisposition.PREVENTED
    assert effect.prevented is True
    assert effect.delivered is False
    assert effect.queued_for_review is False
    assert effect.details["distribution_prevented"] is True
    assert effect.details["simulated"] is True
    assert effect.details["legal_effect"] is False


def test_review_queue_has_distinct_effect() -> None:
    effect = ReviewQueueExecutor().execute(
        "SYNTHETIC-REVIEW-QUEUE",
        {"request_id": "SYNTHETIC-REQUEST"},
    )

    assert effect.disposition is DistributionDisposition.QUEUED_FOR_REVIEW
    assert effect.queued_for_review is True
    assert effect.delivered is False
    assert effect.prevented is False
    assert effect.details["queued_for_review"] is True
    assert effect.details["delivery_recorded"] is False


def test_distribution_effect_details_are_deeply_immutable() -> None:
    source = {
        "nested": {
            "values": [1, 2],
        },
    }

    effect = DistributionEffect(
        executor_id="test-executor",
        destination_id="SYNTHETIC-DESTINATION",
        disposition=DistributionDisposition.PREVENTED,
        effect_code="TEST_EFFECT",
        details=source,
    )

    source["nested"]["values"].append(3)

    assert isinstance(effect.details, MappingProxyType)
    assert isinstance(effect.details["nested"], MappingProxyType)
    assert effect.details["nested"]["values"] == (1, 2)

    with pytest.raises(TypeError):
        effect.details["new"] = True

    assert effect.to_dict()["details"] == {
        "nested": {
            "values": [1, 2],
        },
    }
    assert effect.to_canonical_json()


@pytest.mark.parametrize(
    "executor",
    (
        DistributionPermitExecutor(),
        DistributionBlockExecutor(),
        ReviewQueueExecutor(),
    ),
)
def test_distribution_executors_validate_requests(executor: object) -> None:
    with pytest.raises(TypeError, match="destination_id must be a string"):
        executor.execute(123, {})  # type: ignore[attr-defined, arg-type]

    with pytest.raises(ValueError, match="destination_id must not be empty"):
        executor.execute(" ", {})  # type: ignore[attr-defined]

    with pytest.raises(TypeError, match="payload must be a mapping"):
        executor.execute(  # type: ignore[attr-defined, arg-type]
            "SYNTHETIC-DESTINATION",
            ["not", "a", "mapping"],
        )


def test_manifest_verifier_detects_wrong_checksum(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("content", encoding="utf-8")

    manifest = tmp_path / "manifest.sha256"
    manifest.write_text(
        f"{'0' * 64}  artifact.txt\n",
        encoding="utf-8",
    )

    result = ManifestVerifier(tmp_path).verify_checksum_manifest(manifest)

    assert result.valid is False
    assert result.verified_count == 0
    assert result.failures[0].code is ManifestFailureCode.CHECKSUM_MISMATCH


def test_policy_chunking_preserves_structural_units() -> None:
    chunks = PolicyStructureChunker().chunk(
        record_id="SYNTH-PROJECT-CONTROL",
        text=(
            "Clause Scope\n"
            "Applies here.\n"
            "Clause Rule\n"
            "Do not distribute."
        ),
        locator="synthetic://control",
    )

    assert len(chunks) == 2
    assert chunks[0].text.startswith("Clause Scope")
    assert chunks[1].text.startswith("Clause Rule")
