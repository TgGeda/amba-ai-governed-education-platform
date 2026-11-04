from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amba_ai.governance.models import (
    EnforcementAction,
    EvidenceSufficiency,
    FailureBehavior,
    FindingSeverity,
    PolicyFinding,
    PolicyVerdict,
    to_canonical_json,
)


_ACTION_RANK: dict[EnforcementAction, int] = {
    EnforcementAction.PROCEED: 0,
    EnforcementAction.CONFIRM: 1,
    EnforcementAction.MODIFY: 2,
    EnforcementAction.ABSTAIN: 3,
    EnforcementAction.HOLD_FOR_REVIEW: 4,
    EnforcementAction.BLOCK: 5,
}


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(field_name, str):
        raise TypeError("field_name must be a string")

    normalized_field_name = field_name.strip()
    if not normalized_field_name:
        raise ValueError("field_name must not be empty")

    if not isinstance(value, str):
        raise TypeError(f"{normalized_field_name} must be a string")

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{normalized_field_name} must not be empty")

    return normalized_value


def _failure_action(failure_behavior: FailureBehavior) -> EnforcementAction:
    if failure_behavior is FailureBehavior.BLOCK:
        return EnforcementAction.BLOCK
    if failure_behavior is FailureBehavior.ABSTAIN:
        return EnforcementAction.ABSTAIN
    if failure_behavior is FailureBehavior.HOLD_FOR_REVIEW:
        return EnforcementAction.HOLD_FOR_REVIEW

    # A permissive failure behavior must never authorize an empty,
    # insufficient, or invalid governance result.
    return EnforcementAction.HOLD_FOR_REVIEW


@dataclass(frozen=True, slots=True)
class RecommendationDecision:
    action: EnforcementAction
    requires_approval: bool
    escalation_role: str | None
    rationale_codes: tuple[str, ...]
    unresolved_questions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.action, EnforcementAction):
            raise TypeError("action must be an EnforcementAction")
        if type(self.requires_approval) is not bool:
            raise TypeError("requires_approval must be a strict Boolean")
        if not isinstance(self.rationale_codes, tuple):
            raise TypeError("rationale_codes must be a tuple")
        if not isinstance(self.unresolved_questions, tuple):
            raise TypeError("unresolved_questions must be a tuple")

        rationale_codes = tuple(
            sorted(
                _require_text(value, "rationale_code")
                for value in self.rationale_codes
            )
        )
        unresolved_questions = tuple(
            sorted(
                _require_text(value, "unresolved_question")
                for value in self.unresolved_questions
            )
        )

        if not rationale_codes:
            raise ValueError("rationale_codes must not be empty")
        if len(rationale_codes) != len(set(rationale_codes)):
            raise ValueError("rationale_codes cannot contain duplicates")
        if len(unresolved_questions) != len(set(unresolved_questions)):
            raise ValueError("unresolved_questions cannot contain duplicates")

        role = self.escalation_role
        if role is not None:
            role = _require_text(role, "escalation_role")

        if self.requires_approval and role is None:
            raise ValueError("requires_approval=True requires escalation_role")
        if not self.requires_approval and role is not None:
            raise ValueError("requires_approval=False requires escalation_role=None")

        object.__setattr__(self, "escalation_role", role)
        object.__setattr__(self, "rationale_codes", rationale_codes)
        object.__setattr__(self, "unresolved_questions", unresolved_questions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "requires_approval": self.requires_approval,
            "escalation_role": self.escalation_role,
            "rationale_codes": list(self.rationale_codes),
            "unresolved_questions": list(self.unresolved_questions),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


def _action_for_finding(
    finding: PolicyFinding,
    *,
    failure_behavior: FailureBehavior,
) -> EnforcementAction:
    if finding.verdict is PolicyVerdict.COMPLIANT:
        return EnforcementAction.PROCEED

    if finding.verdict is PolicyVerdict.NONCOMPLIANT:
        if finding.severity is FindingSeverity.CRITICAL:
            return EnforcementAction.BLOCK
        return EnforcementAction.HOLD_FOR_REVIEW

    if finding.verdict is PolicyVerdict.POTENTIAL_GAP:
        return EnforcementAction.ABSTAIN

    if finding.verdict in {
        PolicyVerdict.INSUFFICIENT_EVIDENCE,
        PolicyVerdict.CONFIGURATION_FAILURE,
    }:
        return _failure_action(failure_behavior)

    raise ValueError(f"Unsupported policy verdict: {finding.verdict.value}")


def derive_recommendation(
    findings: tuple[PolicyFinding, ...],
    *,
    unresolved_questions: tuple[str, ...] = (),
    failure_behavior: FailureBehavior = FailureBehavior.HOLD_FOR_REVIEW,
    approval_required: bool = False,
    approval_role: str | None = None,
) -> RecommendationDecision:
    if not isinstance(findings, tuple):
        raise TypeError("findings must be a tuple")
    if not isinstance(unresolved_questions, tuple):
        raise TypeError("unresolved_questions must be a tuple")
    if not isinstance(failure_behavior, FailureBehavior):
        raise TypeError("failure_behavior must be a FailureBehavior")
    if type(approval_required) is not bool:
        raise TypeError("approval_required must be a strict Boolean")

    for finding in findings:
        if not isinstance(finding, PolicyFinding):
            raise TypeError("findings must contain only PolicyFinding values")

    normalized_questions = tuple(
        sorted(
            _require_text(question, "unresolved_question")
            for question in unresolved_questions
        )
    )
    if len(normalized_questions) != len(set(normalized_questions)):
        raise ValueError("unresolved_questions cannot contain duplicates")

    role = approval_role
    if role is not None:
        role = _require_text(role, "approval_role")
    if approval_required and role is None:
        raise ValueError("approval_required=True requires approval_role")
    if not approval_required and role is not None:
        raise ValueError("approval_required=False requires approval_role=None")

    if not findings:
        return RecommendationDecision(
            action=_failure_action(failure_behavior),
            requires_approval=approval_required,
            escalation_role=role,
            rationale_codes=("NO_POLICY_FINDINGS",),
            unresolved_questions=(
                normalized_questions
                or ("No policy findings were available for recommendation",)
            ),
        )

    event_ids = {finding.event_id for finding in findings}
    if len(event_ids) != 1:
        raise ValueError("findings must belong to the same event")

    finding_ids = tuple(finding.finding_id for finding in findings)
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("findings cannot contain duplicate finding IDs")

    actions = tuple(
        _action_for_finding(
            finding,
            failure_behavior=failure_behavior,
        )
        for finding in findings
    )
    action = max(actions, key=_ACTION_RANK.__getitem__)

    rationale_codes = tuple(
        sorted({finding.finding_code for finding in findings})
    )

    # Insufficient evidence and configuration failures must remain visible
    # even when the caller has not supplied a human-readable question.
    derived_questions = {
        f"Resolve finding {finding.finding_code}"
        for finding in findings
        if finding.evidence_sufficiency is EvidenceSufficiency.INSUFFICIENT
        or finding.verdict is PolicyVerdict.CONFIGURATION_FAILURE
    }
    combined_questions = tuple(
        sorted(set(normalized_questions).union(derived_questions))
    )

    return RecommendationDecision(
        action=action,
        requires_approval=approval_required,
        escalation_role=role,
        rationale_codes=rationale_codes,
        unresolved_questions=combined_questions,
    )
