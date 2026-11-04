from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from amba_ai.governance.evaluator_registry import EvaluatorRegistry
from amba_ai.governance.models import (
    BindingLevel,
    EnforcementAction,
    EvidenceSufficiency,
    FailureBehavior,
    FindingSeverity,
    GovernanceConfigurationError,
    GovernanceError,
    OperationProtectionClass,
    PipelineEvent,
    PolicyFinding,
    PolicyRecordAmbiguityError,
    PolicyVerdict,
    ResolvedOperation,
    SequentialIdentifierProvider,
)
from amba_ai.governance.operation_registry import OperationRegistry
from amba_ai.governance.policy_engine import PolicyEngine
from amba_ai.governance.record_registry import PolicyRecordRegistry


NOW = "2026-06-01T12:00:00Z"
EVALUATOR_ID = "EVAL-TEST"
RECORD_ID = "PROJECT-CONTROL-EDUCATIONAL-PROCESSING-V1"


def safeguards_document() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "policy_id": "AMBA-SAFEGUARDS",
        "policy_version": "1.0.0",
        "authority": "Amba governance test authority",
        "scope": "Synthetic education sandbox",
        "binding_level": "project_control",
        "national_binding_status": False,
        "synthetic_only": True,
        "legal_effect": False,
        "controls": {
            "educational_processing": {
                "locator": "controls.educational_processing",
                "rule": "Educational processing must remain within project controls.",
            }
        },
    }


@pytest.fixture
def records(tmp_path: Path) -> PolicyRecordRegistry:
    path = tmp_path / "safeguards.yaml"
    path.write_text(
        yaml.safe_dump(safeguards_document(), sort_keys=False),
        encoding="utf-8",
    )
    return PolicyRecordRegistry.load_from_safeguards_yaml(path)


def make_operation(
    *,
    operation_id: str = "test_operation",
    protection_class: OperationProtectionClass = OperationProtectionClass.PROTECTED,
    failure_behavior: FailureBehavior = FailureBehavior.BLOCK,
    required_evaluator_ids: tuple[str, ...] = (EVALUATOR_ID,),
    required_policy_record_ids: tuple[str, ...] = (),
    approval_required: bool = False,
    approval_role: str | None = None,
) -> ResolvedOperation:
    return ResolvedOperation(
        operation_id=operation_id,
        protection_class=protection_class,
        pre_gate_required=True,
        post_gate_required=True,
        authorization_basis_required=False,
        allowed_authorization_basis_types=(),
        required_evaluator_ids=required_evaluator_ids,
        required_policy_record_ids=required_policy_record_ids,
        approval_required=approval_required,
        approval_role=approval_role,
        failure_behavior=failure_behavior,
    )


def make_event(
    operation_id: str = "test_operation",
) -> PipelineEvent:
    return PipelineEvent(
        event_id="EVENT-001",
        timestamp=NOW,
        operation_id=operation_id,
        source_node="SOURCE-001",
        destination_id="DEST-001",
        payload_type="test_payload",
        payload={},
        authorization_basis=None,
        synthetic_flag=True,
    )


def make_finding(
    *,
    finding_id: str = "FINDING-001",
    event_id: str = "EVENT-001",
    evaluator_id: str = EVALUATOR_ID,
    severity: FindingSeverity = FindingSeverity.INFO,
    verdict: PolicyVerdict = PolicyVerdict.COMPLIANT,
    rationale: str = "Evaluation completed.",
) -> PolicyFinding:
    return PolicyFinding(
        finding_id=finding_id,
        event_id=event_id,
        finding_code="TEST_FINDING",
        basis_category=BindingLevel.PROJECT_CONTROL,
        severity=severity,
        verdict=verdict,
        evaluator_id=evaluator_id,
        primary_records=(),
        supporting_records=(),
        rationale=rationale,
        evidence_sufficiency=(
            EvidenceSufficiency.INSUFFICIENT
            if verdict
            in {
                PolicyVerdict.INSUFFICIENT_EVIDENCE,
                PolicyVerdict.CONFIGURATION_FAILURE,
            }
            else EvidenceSufficiency.SUFFICIENT
        ),
        deterministic_result=True,
        applicability_details={},
    )


@dataclass
class StaticEvaluator:
    finding: Any
    evaluator_id: str = EVALUATOR_ID
    evaluator_version: str = "1.0.0"

    def evaluate(
        self,
        event: PipelineEvent,
        operation: ResolvedOperation,
        record_registry: PolicyRecordRegistry,
    ) -> Any:
        return self.finding


@dataclass
class RaisingEvaluator:
    error: Exception
    evaluator_id: str = EVALUATOR_ID
    evaluator_version: str = "1.0.0"

    def evaluate(
        self,
        event: PipelineEvent,
        operation: ResolvedOperation,
        record_registry: PolicyRecordRegistry,
    ) -> PolicyFinding:
        raise self.error


def make_engine(
    *,
    records: PolicyRecordRegistry,
    operation: ResolvedOperation,
    evaluator: Any | None = None,
) -> PolicyEngine:
    evaluators = EvaluatorRegistry()
    if evaluator is not None:
        evaluators.register(evaluator)
    return PolicyEngine(
        record_registry=records,
        operation_registry=OperationRegistry(
            {operation.operation_id: operation}
        ),
        evaluator_registry=evaluators,
        identifier_provider=SequentialIdentifierProvider(),
    )


def finding_codes(bundle) -> set[str]:
    return {finding.finding_code for finding in bundle.findings}


@pytest.mark.parametrize(
    "field_name, value, message",
    [
        ("record_registry", object(), "record_registry must be"),
        ("operation_registry", object(), "operation_registry must be"),
        ("evaluator_registry", object(), "evaluator_registry must be"),
    ],
)
def test_constructor_validates_registry_dependencies(
    records: PolicyRecordRegistry,
    field_name: str,
    value: object,
    message: str,
) -> None:
    operation = make_operation()
    values: dict[str, Any] = {
        "record_registry": records,
        "operation_registry": OperationRegistry(
            {operation.operation_id: operation}
        ),
        "evaluator_registry": EvaluatorRegistry(),
        "identifier_provider": SequentialIdentifierProvider(),
    }
    values[field_name] = value

    with pytest.raises(TypeError, match=message):
        PolicyEngine(**values)


def test_constructor_validates_identifier_provider(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    operation_registry = OperationRegistry(
        {operation.operation_id: operation}
    )

    with pytest.raises(TypeError, match="identifier_provider is required"):
        PolicyEngine(
            records,
            operation_registry,
            EvaluatorRegistry(),
            None,  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="IdentifierProvider"):
        PolicyEngine(
            records,
            operation_registry,
            EvaluatorRegistry(),
            object(),  # type: ignore[arg-type]
        )


def test_evaluate_requires_pipeline_event(
    records: PolicyRecordRegistry,
) -> None:
    engine = make_engine(
        records=records,
        operation=make_operation(),
    )

    with pytest.raises(TypeError, match="event must be a PipelineEvent"):
        engine.evaluate_pipeline_event(object())  # type: ignore[arg-type]


def test_unknown_operation_fails_closed(
    records: PolicyRecordRegistry,
) -> None:
    configured = make_operation(operation_id="configured")
    engine = make_engine(records=records, operation=configured)

    bundle = engine.evaluate_pipeline_event(
        make_event(operation_id="unknown")
    )

    assert bundle.operation is None
    assert finding_codes(bundle) == {"UNRESOLVED_OPERATION_CONFIG"}
    assert bundle.recommendation.recommended_action == (
        EnforcementAction.HOLD_FOR_REVIEW
    )
    assert bundle.recommendation.requires_approval is True
    assert bundle.recommendation.escalation_role == "compliance_officer"
    assert bundle.unresolved_questions


def test_missing_required_evaluator_creates_configuration_finding(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    engine = make_engine(records=records, operation=operation)

    bundle = engine.evaluate_pipeline_event(make_event())

    assert "REQUIRED_EVALUATOR_UNREGISTERED" in finding_codes(bundle)
    assert bundle.recommendation.recommended_action == EnforcementAction.BLOCK
    assert bundle.recommendation.requires_approval is False


def test_missing_required_record_creates_insufficient_evidence(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation(
        required_policy_record_ids=("MISSING-RECORD",),
    )
    evaluator = StaticEvaluator(make_finding())
    engine = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    )

    bundle = engine.evaluate_pipeline_event(make_event())

    assert "REQUIRED_RECORD_INACTIVE" in finding_codes(bundle)
    assert bundle.recommendation.recommended_action == (
        EnforcementAction.HOLD_FOR_REVIEW
    )
    assert bundle.recommendation.requires_approval is True


def test_active_required_record_allows_evaluation(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation(
        required_policy_record_ids=(RECORD_ID,),
    )
    evaluator = StaticEvaluator(make_finding())
    engine = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    )

    bundle = engine.evaluate_pipeline_event(make_event())

    assert finding_codes(bundle) == {"TEST_FINDING"}
    assert bundle.recommendation.recommended_action == EnforcementAction.PROCEED
    assert bundle.unresolved_questions == ()


def test_ambiguous_required_record_is_configuration_failure(
    monkeypatch: pytest.MonkeyPatch,
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation(
        required_policy_record_ids=(RECORD_ID,),
    )
    evaluator = StaticEvaluator(make_finding())
    engine = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    )

    def ambiguous(self: PolicyRecordRegistry, record_id: str):
        raise PolicyRecordAmbiguityError("sensitive details")

    monkeypatch.setattr(
        PolicyRecordRegistry,
        "get_active_by_record_id",
        ambiguous,
    )

    bundle = engine.evaluate_pipeline_event(make_event())

    assert "REQUIRED_RECORD_AMBIGUOUS" in finding_codes(bundle)
    finding = next(
        item
        for item in bundle.findings
        if item.finding_code == "REQUIRED_RECORD_AMBIGUOUS"
    )
    assert "sensitive details" not in finding.rationale
    assert bundle.recommendation.recommended_action == EnforcementAction.BLOCK


def test_governance_evaluator_exception_is_contained(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    evaluator = RaisingEvaluator(
        GovernanceConfigurationError("sensitive governance details")
    )
    engine = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    )

    bundle = engine.evaluate_pipeline_event(make_event())

    assert finding_codes(bundle) == {"EVALUATOR_CONFIGURATION_FAILURE"}
    finding = bundle.findings[0]
    assert finding.applicability_details["error_type"] == (
        "GovernanceConfigurationError"
    )
    assert "sensitive governance details" not in finding.rationale


def test_internal_evaluator_exception_is_contained(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    evaluator = RaisingEvaluator(RuntimeError("sensitive internal details"))
    engine = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    )

    bundle = engine.evaluate_pipeline_event(make_event())

    assert finding_codes(bundle) == {"EVALUATOR_INTERNAL_FAILURE"}
    assert bundle.findings[0].applicability_details["error_type"] == (
        "RuntimeError"
    )
    assert "sensitive internal details" not in bundle.findings[0].rationale


def test_invalid_evaluator_output_is_converted_to_finding(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    engine = make_engine(
        records=records,
        operation=operation,
        evaluator=StaticEvaluator(object()),
    )

    bundle = engine.evaluate_pipeline_event(make_event())

    assert finding_codes(bundle) == {"EVALUATOR_OUTPUT_INVALID"}
    assert bundle.findings[0].applicability_details["returned_type"] == (
        "object"
    )


def test_evaluator_event_mismatch_is_converted_to_finding(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    evaluator = StaticEvaluator(
        make_finding(event_id="OTHER-EVENT")
    )
    engine = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    )

    bundle = engine.evaluate_pipeline_event(make_event())

    assert finding_codes(bundle) == {"EVALUATOR_EVENT_MISMATCH"}


def test_evaluator_identifier_mismatch_is_converted_to_finding(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    evaluator = StaticEvaluator(
        make_finding(evaluator_id="DIFFERENT-EVALUATOR")
    )
    engine = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    )

    bundle = engine.evaluate_pipeline_event(make_event())

    assert finding_codes(bundle) == {"EVALUATOR_ID_MISMATCH"}


def test_duplicate_finding_ids_are_rejected(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation(
        required_evaluator_ids=("EVAL-A", "EVAL-B"),
    )
    evaluators = EvaluatorRegistry()
    evaluators.register(
        StaticEvaluator(
            make_finding(
                finding_id="DUPLICATE",
                evaluator_id="EVAL-A",
            ),
            evaluator_id="EVAL-A",
        )
    )
    evaluators.register(
        StaticEvaluator(
            make_finding(
                finding_id="DUPLICATE",
                evaluator_id="EVAL-B",
            ),
            evaluator_id="EVAL-B",
        )
    )
    engine = PolicyEngine(
        records,
        OperationRegistry({operation.operation_id: operation}),
        evaluators,
        SequentialIdentifierProvider(),
    )

    with pytest.raises(
        GovernanceConfigurationError,
        match="duplicate finding IDs",
    ):
        engine.evaluate_pipeline_event(make_event())


@pytest.mark.parametrize(
    "failure_behavior, expected_action, expected_approval",
    [
        (FailureBehavior.BLOCK, EnforcementAction.BLOCK, False),
        (FailureBehavior.ABSTAIN, EnforcementAction.ABSTAIN, False),
        (
            FailureBehavior.HOLD_FOR_REVIEW,
            EnforcementAction.HOLD_FOR_REVIEW,
            True,
        ),
        (
            FailureBehavior.CONFIGURATION_FAILURE,
            EnforcementAction.HOLD_FOR_REVIEW,
            True,
        ),
    ],
)
def test_configuration_failure_respects_failure_behavior(
    records: PolicyRecordRegistry,
    failure_behavior: FailureBehavior,
    expected_action: EnforcementAction,
    expected_approval: bool,
) -> None:
    operation = make_operation(failure_behavior=failure_behavior)
    evaluator = StaticEvaluator(
        make_finding(
            severity=FindingSeverity.CRITICAL,
            verdict=PolicyVerdict.CONFIGURATION_FAILURE,
        )
    )
    engine = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    )

    recommendation = engine.evaluate_pipeline_event(
        make_event()
    ).recommendation

    assert recommendation.recommended_action == expected_action
    assert recommendation.requires_approval is expected_approval
    assert (
        recommendation.escalation_role == "compliance_officer"
        if expected_approval
        else recommendation.escalation_role is None
    )


def test_prohibited_operation_always_blocks(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation(
        protection_class=(
            OperationProtectionClass.PROHIBITED_BY_PROJECT_CONTROL
        ),
        failure_behavior=FailureBehavior.BLOCK,
    )
    evaluator = StaticEvaluator(
        make_finding(
            verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.WARNING,
        )
    )
    engine = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    )

    recommendation = engine.evaluate_pipeline_event(
        make_event()
    ).recommendation

    assert recommendation.recommended_action == EnforcementAction.BLOCK
    assert recommendation.requires_approval is False
    assert recommendation.escalation_role is None


@pytest.mark.parametrize(
    "protection_class, expected_action, expected_approval",
    [
        (
            OperationProtectionClass.UNPROTECTED,
            EnforcementAction.ABSTAIN,
            False,
        ),
        (
            OperationProtectionClass.LOW_RISK,
            EnforcementAction.ABSTAIN,
            False,
        ),
        (
            OperationProtectionClass.PROTECTED,
            EnforcementAction.HOLD_FOR_REVIEW,
            True,
        ),
    ],
)
def test_insufficient_evidence_aggregation(
    records: PolicyRecordRegistry,
    protection_class: OperationProtectionClass,
    expected_action: EnforcementAction,
    expected_approval: bool,
) -> None:
    operation = make_operation(protection_class=protection_class)
    evaluator = StaticEvaluator(
        make_finding(
            verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
            severity=FindingSeverity.WARNING,
        )
    )
    engine = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    )

    recommendation = engine.evaluate_pipeline_event(
        make_event()
    ).recommendation

    assert recommendation.recommended_action == expected_action
    assert recommendation.requires_approval is expected_approval


def test_critical_noncompliance_blocks(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    evaluator = StaticEvaluator(
        make_finding(
            verdict=PolicyVerdict.NONCOMPLIANT,
            severity=FindingSeverity.CRITICAL,
        )
    )
    bundle = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    ).evaluate_pipeline_event(make_event())

    assert bundle.recommendation.recommended_action == EnforcementAction.BLOCK
    assert bundle.recommendation.requires_approval is False


def test_restrictive_noncompliance_holds_for_review(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation(
        approval_required=True,
        approval_role="school_administrator",
    )
    evaluator = StaticEvaluator(
        make_finding(
            verdict=PolicyVerdict.NONCOMPLIANT,
            severity=FindingSeverity.RESTRICTIVE,
        )
    )
    bundle = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    ).evaluate_pipeline_event(make_event())

    assert bundle.recommendation.recommended_action == (
        EnforcementAction.HOLD_FOR_REVIEW
    )
    assert bundle.recommendation.requires_approval is True
    assert bundle.recommendation.escalation_role == "school_administrator"


def test_policy_exploration_gap_abstains(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation(operation_id="policy_exploration_search")
    evaluator = StaticEvaluator(
        make_finding(verdict=PolicyVerdict.POTENTIAL_GAP)
    )
    bundle = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    ).evaluate_pipeline_event(
        make_event(operation_id=operation.operation_id)
    )

    assert bundle.recommendation.recommended_action == EnforcementAction.ABSTAIN
    assert bundle.recommendation.requires_approval is False


def test_nonexploration_gap_holds_for_review(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    evaluator = StaticEvaluator(
        make_finding(verdict=PolicyVerdict.POTENTIAL_GAP)
    )
    bundle = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    ).evaluate_pipeline_event(make_event())

    assert bundle.recommendation.recommended_action == (
        EnforcementAction.HOLD_FOR_REVIEW
    )
    assert bundle.recommendation.requires_approval is True
    assert bundle.recommendation.escalation_role == "compliance_officer"


def test_compliant_operation_requiring_approval_requires_approval(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation(
        approval_required=True,
        approval_role="reviewer",
    )
    evaluator = StaticEvaluator(make_finding())
    bundle = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    ).evaluate_pipeline_event(make_event())

    assert bundle.recommendation.recommended_action == (
        EnforcementAction.REQUIRE_APPROVAL
    )
    assert bundle.recommendation.requires_approval is True
    assert bundle.recommendation.escalation_role == "reviewer"


def test_compliant_operation_proceeds(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    evaluator = StaticEvaluator(make_finding())
    bundle = make_engine(
        records=records,
        operation=operation,
        evaluator=evaluator,
    ).evaluate_pipeline_event(make_event())

    assert bundle.recommendation.recommended_action == EnforcementAction.PROCEED
    assert bundle.recommendation.requires_approval is False
    assert bundle.recommendation.escalation_role is None


def test_unresolved_questions_are_sorted_and_deduplicated(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation(
        required_evaluator_ids=("EVAL-A", "EVAL-B", "EVAL-C"),
    )
    evaluators = EvaluatorRegistry()
    evaluators.register(
        StaticEvaluator(
            make_finding(
                finding_id="FINDING-A",
                evaluator_id="EVAL-A",
                verdict=PolicyVerdict.POTENTIAL_GAP,
                rationale="Question B",
            ),
            evaluator_id="EVAL-A",
        )
    )
    evaluators.register(
        StaticEvaluator(
            make_finding(
                finding_id="FINDING-B",
                evaluator_id="EVAL-B",
                verdict=PolicyVerdict.INSUFFICIENT_EVIDENCE,
                rationale="Question A",
            ),
            evaluator_id="EVAL-B",
        )
    )
    evaluators.register(
        StaticEvaluator(
            make_finding(
                finding_id="FINDING-C",
                evaluator_id="EVAL-C",
                verdict=PolicyVerdict.POTENTIAL_GAP,
                rationale="Question B",
            ),
            evaluator_id="EVAL-C",
        )
    )
    engine = PolicyEngine(
        records,
        OperationRegistry({operation.operation_id: operation}),
        evaluators,
        SequentialIdentifierProvider(),
    )

    bundle = engine.evaluate_pipeline_event(make_event())

    assert bundle.unresolved_questions == ("Question A", "Question B")


def test_finding_and_recommendation_identifiers_are_deterministic(
    records: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    engine = make_engine(records=records, operation=operation)

    bundle = engine.evaluate_pipeline_event(make_event())

    assert bundle.findings[0].finding_id == "find_missing_eval_000001"
    assert bundle.recommendation.recommendation_id == "rec_000002"
