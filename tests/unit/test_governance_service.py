from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from amba_ai.governance.models import (
    BindingLevel,
    EnforcementAction,
    EvidenceSufficiency,
    FailureBehavior,
    FindingSeverity,
    GovernanceConfigurationError,
    OperationProtectionClass,
    PipelineEvent,
    PolicyEvaluationBundle,
    PolicyFinding,
    PolicyRecommendation,
    PolicyVerdict,
    ResolvedOperation,
)
from amba_ai.services.governance_service import (
    GovernanceEvaluationResult,
    GovernanceService,
)


NOW = "2026-06-01T12:00:00Z"


def make_event(
    *,
    event_id: str = "SYNTHETIC-EVENT",
    operation_id: str = "synthetic-governed-operation",
) -> PipelineEvent:
    return PipelineEvent(
        event_id=event_id,
        timestamp=NOW,
        operation_id=operation_id,
        source_node="SYNTHETIC-SOURCE",
        destination_id="SYNTHETIC-DESTINATION",
        payload_type="synthetic_payload",
        payload={"synthetic": True},
        authorization_basis=None,
        synthetic_flag=True,
    )


def make_operation(
    *,
    operation_id: str = "synthetic-governed-operation",
) -> ResolvedOperation:
    return ResolvedOperation(
        operation_id=operation_id,
        protection_class=OperationProtectionClass.PROTECTED,
        pre_gate_required=True,
        post_gate_required=True,
        authorization_basis_required=False,
        allowed_authorization_basis_types=(),
        required_evaluator_ids=("synthetic-evaluator",),
        required_policy_record_ids=(),
        approval_required=False,
        approval_role=None,
        failure_behavior=FailureBehavior.HOLD_FOR_REVIEW,
    )


def make_finding(
    *,
    event_id: str = "SYNTHETIC-EVENT",
    finding_id: str = "SYNTHETIC-FINDING",
) -> PolicyFinding:
    return PolicyFinding(
        finding_id=finding_id,
        event_id=event_id,
        finding_code="SYNTHETIC_CONTROL_PASSED",
        basis_category=BindingLevel.PROJECT_CONTROL,
        severity=FindingSeverity.INFO,
        verdict=PolicyVerdict.COMPLIANT,
        evaluator_id="synthetic-evaluator",
        primary_records=(),
        supporting_records=(),
        rationale="Synthetic policy evaluation completed.",
        evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
        deterministic_result=True,
        applicability_details={"applicable": True},
    )


def make_recommendation(
    *,
    event_id: str = "SYNTHETIC-EVENT",
) -> PolicyRecommendation:
    return PolicyRecommendation(
        recommendation_id="SYNTHETIC-RECOMMENDATION",
        event_id=event_id,
        recommended_action=EnforcementAction.PROCEED,
        mitigation_steps=(),
        requires_approval=False,
        escalation_role=None,
    )


def make_bundle(
    *,
    event_id: str = "SYNTHETIC-EVENT",
    operation_id: str = "synthetic-governed-operation",
    unresolved_questions: tuple[str, ...] = (),
) -> PolicyEvaluationBundle:
    return PolicyEvaluationBundle(
        event_id=event_id,
        operation=make_operation(operation_id=operation_id),
        findings=(make_finding(event_id=event_id),),
        recommendation=make_recommendation(event_id=event_id),
        unresolved_questions=unresolved_questions,
    )


@dataclass
class StaticPolicyEngine:
    bundle: object
    evaluation_count: int = 0
    last_event: PipelineEvent | None = None

    def evaluate_pipeline_event(
        self,
        event: PipelineEvent,
    ) -> Any:
        self.evaluation_count += 1
        self.last_event = event
        return self.bundle


@pytest.mark.parametrize("value", [None, object()])
def test_governance_service_rejects_invalid_policy_engine(
    value: object,
) -> None:
    with pytest.raises(TypeError, match="policy_engine"):
        GovernanceService(value)  # type: ignore[arg-type]


def test_governance_service_rejects_invalid_event() -> None:
    service = GovernanceService(
        StaticPolicyEngine(make_bundle())
    )

    with pytest.raises(TypeError, match="event must be a PipelineEvent"):
        service.evaluate(object())  # type: ignore[arg-type]


def test_governance_service_delegates_once_and_preserves_results() -> None:
    event = make_event()
    bundle = make_bundle(
        unresolved_questions=("Confirm synthetic evidence scope",),
    )
    engine = StaticPolicyEngine(bundle)
    service = GovernanceService(engine)

    result = service.evaluate(event)

    assert isinstance(result, GovernanceEvaluationResult)
    assert engine.evaluation_count == 1
    assert engine.last_event is event
    assert result.event is event
    assert result.bundle is bundle
    assert result.findings is bundle.findings
    assert result.recommendation is bundle.recommendation
    assert result.unresolved_questions == (
        "Confirm synthetic evidence scope",
    )


def test_governance_service_does_not_approve_or_execute() -> None:
    event = make_event()
    engine = StaticPolicyEngine(make_bundle())
    service = GovernanceService(engine)

    result = service.evaluate(event)

    assert engine.evaluation_count == 1
    assert not hasattr(service, "approve")
    assert not hasattr(service, "execute")
    assert not hasattr(service, "distribute")
    assert result.recommendation.recommended_action is EnforcementAction.PROCEED


def test_governance_service_rejects_invalid_engine_result() -> None:
    event = make_event()
    service = GovernanceService(
        StaticPolicyEngine(object())
    )

    with pytest.raises(
        GovernanceConfigurationError,
        match="invalid evaluation result",
    ):
        service.evaluate(event)


def test_governance_service_rejects_bundle_for_different_event() -> None:
    event = make_event(event_id="SYNTHETIC-EVENT-A")
    bundle = make_bundle(event_id="SYNTHETIC-EVENT-B")
    service = GovernanceService(StaticPolicyEngine(bundle))

    with pytest.raises(
        GovernanceConfigurationError,
        match="bundle event identifier",
    ):
        service.evaluate(event)


def test_governance_service_rejects_bundle_for_different_operation() -> None:
    event = make_event(operation_id="synthetic-operation-a")
    bundle = make_bundle(operation_id="synthetic-operation-b")
    service = GovernanceService(StaticPolicyEngine(bundle))

    with pytest.raises(
        GovernanceConfigurationError,
        match="bundle operation identifier",
    ):
        service.evaluate(event)


def test_governance_evaluation_result_serializes_deterministically() -> None:
    result = GovernanceEvaluationResult(
        event=make_event(),
        bundle=make_bundle(),
    )

    serialized = result.to_dict()

    assert serialized["event"]["event_id"] == "SYNTHETIC-EVENT"
    assert serialized["bundle"]["event_id"] == "SYNTHETIC-EVENT"
    assert result.to_canonical_json() == result.to_canonical_json()
