from __future__ import annotations

import hashlib
import pytest

from amba_ai.governance.models import (
    BindingLevel, EnforcementAction, EvidenceSufficiency, FailureBehavior,
    FindingSeverity, PolicyFinding, PolicyVerdict,
)
from amba_ai.governance.recommendation import derive_recommendation


def _finding(fid: str, code: str, severity: FindingSeverity, verdict: PolicyVerdict, *, event: str = "event") -> PolicyFinding:
    return PolicyFinding(
        finding_id=fid,
        event_id=event,
        finding_code=code,
        basis_category=BindingLevel.PROJECT_CONTROL,
        severity=severity,
        verdict=verdict,
        evaluator_id="evaluator",
        primary_records=(),
        supporting_records=(),
        rationale="Synthetic finding.",
        evidence_sufficiency=(EvidenceSufficiency.INSUFFICIENT if verdict in {PolicyVerdict.INSUFFICIENT_EVIDENCE, PolicyVerdict.CONFIGURATION_FAILURE} else EvidenceSufficiency.SUFFICIENT),
        deterministic_result=True,
        applicability_details={},
    )


def test_most_restrictive_action_wins_without_short_circuiting() -> None:
    findings = (
        _finding("one", "REVIEW", FindingSeverity.WARNING, PolicyVerdict.NONCOMPLIANT),
        _finding("two", "BLOCK", FindingSeverity.CRITICAL, PolicyVerdict.NONCOMPLIANT),
    )
    result = derive_recommendation(findings, unresolved_questions=("B", "A"))
    assert result.action is EnforcementAction.BLOCK
    assert result.rationale_codes == ("BLOCK", "REVIEW")
    assert result.unresolved_questions == ("A", "B")


def test_empty_findings_fail_closed() -> None:
    result = derive_recommendation(())
    assert result.action is EnforcementAction.HOLD_FOR_REVIEW
    assert result.rationale_codes == ("NO_POLICY_FINDINGS",)
    assert result.unresolved_questions


def test_duplicate_findings_and_mixed_events_are_rejected() -> None:
    finding = _finding("one", "A", FindingSeverity.INFO, PolicyVerdict.COMPLIANT)
    with pytest.raises(ValueError, match="duplicate"):
        derive_recommendation((finding, finding))
    with pytest.raises(ValueError, match="same event"):
        derive_recommendation((finding, _finding("two", "B", FindingSeverity.INFO, PolicyVerdict.COMPLIANT, event="other")))


def test_approval_role_consistency() -> None:
    finding = _finding("one", "A", FindingSeverity.INFO, PolicyVerdict.COMPLIANT)
    with pytest.raises(ValueError, match="approval_role"):
        derive_recommendation((finding,), approval_required=True)
    result = derive_recommendation((finding,), approval_required=True, approval_role=" reviewer ")
    assert result.requires_approval is True
    assert result.escalation_role == "reviewer"


def test_insufficient_evidence_retains_uncertainty() -> None:
    finding = _finding("one", "EVIDENCE", FindingSeverity.WARNING, PolicyVerdict.INSUFFICIENT_EVIDENCE)
    result = derive_recommendation((finding,), failure_behavior=FailureBehavior.HOLD_FOR_REVIEW)
    assert result.action is EnforcementAction.HOLD_FOR_REVIEW
    assert result.unresolved_questions == ("Resolve finding EVIDENCE",)


def test_recommendation_is_data_not_execution() -> None:
    finding = _finding("one", "A", FindingSeverity.INFO, PolicyVerdict.COMPLIANT)
    result = derive_recommendation((finding,))
    assert not hasattr(result, "execute")
    assert not hasattr(result, "approve")
    assert result.to_canonical_json() == result.to_canonical_json()
