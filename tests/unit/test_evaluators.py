from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pytest
import yaml

from amba_ai.governance.evaluators import (
    AuthorizationBasisEvaluator,
    ChildSafeguardingEvaluator,
    CitationIntegrityEvaluator,
    ContentSafetyChecker,
    ContentSafetyEvaluator,
    DestinationEvaluator,
    InferenceDataEvaluator,
    ProjectCommercialControlEvaluator,
    ProjectEducationalProcessingEvaluator,
    ProjectTargetedAdControlEvaluator,
)
from amba_ai.governance.models import (
    AuthorizationBasis,
    AuthorizationBasisType,
    ContentSafetyResult,
    FailureBehavior,
    GovernanceConfigurationError,
    OperationProtectionClass,
    PipelineEvent,
    PolicyRecordAmbiguityError,
    PolicyVerdict,
    ResolvedOperation,
    SequentialIdentifierProvider,
)
from amba_ai.governance.operation_registry import (
    DestinationRegistry,
    DestinationRules,
    DestinationSpecification,
)
from amba_ai.governance.record_registry import PolicyRecordRegistry


NOW = "2026-06-01T12:00:00Z"
VALID_SHA = "a" * 64
EXACT_SIGNAL = "simulated_prohibited_inference_signal_v1"


def safeguards_document() -> dict[str, Any]:
    controls = {
        "restricted_destinations": {
            "locator": "controls.restricted_destinations",
            "rule": "Only registered destinations may receive governed output.",
        },
        "educational_processing": {
            "locator": "controls.educational_processing",
            "rule": "Educational processing must remain noncommercial.",
        },
        "commercial_purchases": {
            "locator": "controls.commercial_purchases",
            "rule": "Commercial purchases require governance intervention.",
        },
        "targeted_advertising": {
            "locator": "controls.targeted_advertising",
            "rule": "Targeted advertising is prohibited in the sandbox.",
        },
    }
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
        "controls": controls,
    }


@pytest.fixture
def record_registry(tmp_path: Path) -> PolicyRecordRegistry:
    path = tmp_path / "safeguards.yaml"
    path.write_text(
        yaml.safe_dump(safeguards_document(), sort_keys=False),
        encoding="utf-8",
    )
    return PolicyRecordRegistry.load_from_safeguards_yaml(path)


def destination_registry() -> DestinationRegistry:
    rules = DestinationRules(
        unknown_destination=FailureBehavior.CONFIGURATION_FAILURE,
        unregistered_destination=FailureBehavior.BLOCK,
        operation_not_allowed=FailureBehavior.BLOCK,
        empty_destination=FailureBehavior.CONFIGURATION_FAILURE,
        wildcard_operations_allowed=False,
    )
    destinations = {
        "DEST-ALLOWED": DestinationSpecification(
            destination_id="DEST-ALLOWED",
            destination_class="delivery",
            registered=True,
            synthetic=True,
            allowed_operations=("classroom_exercise_telemetry",),
        ),
        "DEST-WRONG-OP": DestinationSpecification(
            destination_id="DEST-WRONG-OP",
            destination_class="delivery",
            registered=True,
            synthetic=True,
            allowed_operations=("other_operation",),
        ),
        "DEST-UNREGISTERED": DestinationSpecification(
            destination_id="DEST-UNREGISTERED",
            destination_class="delivery",
            registered=False,
            synthetic=True,
            allowed_operations=("classroom_exercise_telemetry",),
        ),
    }
    return DestinationRegistry(destinations, rules)


def make_basis(**overrides: Any) -> AuthorizationBasis:
    values: dict[str, Any] = {
        "basis_id": "BASIS-001",
        "basis_type": AuthorizationBasisType.PROJECT_FIXTURE,
        "subject_category": "synthetic_learner",
        "authority_reference": "fixture://basis/BASIS-001",
        "purposes": ("education",),
        "data_categories": ("telemetry",),
        "processing_operations": ("classroom_exercise_telemetry",),
        "effective_from": "2026-01-01T00:00:00Z",
        "expires_at": "2027-01-01T00:00:00Z",
        "revoked_at": None,
        "artifact_hash": VALID_SHA,
        "verifier_id": "VERIFIER-001",
        "synthetic": True,
        "legal_effect": False,
    }
    values.update(overrides)
    return AuthorizationBasis(**values)


def make_operation(
    operation_id: str = "classroom_exercise_telemetry",
    **overrides: Any,
) -> ResolvedOperation:
    values: dict[str, Any] = {
        "operation_id": operation_id,
        "protection_class": OperationProtectionClass.PROTECTED,
        "pre_gate_required": True,
        "post_gate_required": True,
        "authorization_basis_required": False,
        "allowed_authorization_basis_types": (),
        "required_evaluator_ids": ("EVAL-TEST",),
        "required_policy_record_ids": (),
        "approval_required": False,
        "approval_role": None,
        "failure_behavior": FailureBehavior.BLOCK,
    }
    values.update(overrides)
    return ResolvedOperation(**values)


def make_event(
    *,
    operation_id: str = "classroom_exercise_telemetry",
    destination_id: str = "DEST-ALLOWED",
    payload: Mapping[str, Any] | None = None,
    authorization_basis: AuthorizationBasis | None = None,
) -> PipelineEvent:
    return PipelineEvent(
        event_id="EVENT-001",
        timestamp=NOW,
        operation_id=operation_id,
        source_node="SOURCE-001",
        destination_id=destination_id,
        payload_type="test_payload",
        payload=dict(payload or {}),
        authorization_basis=authorization_basis,
        synthetic_flag=True,
    )


def evaluate(
    evaluator: Any,
    *,
    event: PipelineEvent,
    operation: ResolvedOperation,
    registry: PolicyRecordRegistry,
):
    finding = evaluator.evaluate(event, operation, registry)
    assert finding.event_id == event.event_id
    assert finding.evaluator_id == evaluator.evaluator_id
    assert finding.deterministic_result is True
    return finding


# Shared construction and input validation

@pytest.mark.parametrize(
    "evaluator_type",
    [
        AuthorizationBasisEvaluator,
        ProjectEducationalProcessingEvaluator,
        CitationIntegrityEvaluator,
        ContentSafetyEvaluator,
        ProjectCommercialControlEvaluator,
        ChildSafeguardingEvaluator,
        ProjectTargetedAdControlEvaluator,
        InferenceDataEvaluator,
    ],
)
def test_evaluators_require_identifier_provider(evaluator_type: type) -> None:
    with pytest.raises(
        GovernanceConfigurationError,
        match="id_provider is required",
    ):
        evaluator_type(None)


def test_evaluator_rejects_malformed_identifier_provider() -> None:
    with pytest.raises(TypeError, match="IdentifierProvider"):
        AuthorizationBasisEvaluator(object())


def test_destination_evaluator_validates_registry_dependency() -> None:
    ids = SequentialIdentifierProvider()
    with pytest.raises(
        GovernanceConfigurationError,
        match="destination_registry is required",
    ):
        DestinationEvaluator(ids, None)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="must be a DestinationRegistry"):
        DestinationEvaluator(ids, object())  # type: ignore[arg-type]


def test_evaluator_rejects_event_operation_mismatch(
    record_registry: PolicyRecordRegistry,
) -> None:
    evaluator = AuthorizationBasisEvaluator(SequentialIdentifierProvider())
    event = make_event(operation_id="classroom_exercise_telemetry")
    operation = make_operation(operation_id="other_operation")

    with pytest.raises(
        GovernanceConfigurationError,
        match="Event operation does not match",
    ):
        evaluator.evaluate(event, operation, record_registry)


def test_evaluator_validates_runtime_input_types(
    record_registry: PolicyRecordRegistry,
) -> None:
    evaluator = AuthorizationBasisEvaluator(SequentialIdentifierProvider())
    operation = make_operation()
    event = make_event()

    with pytest.raises(TypeError, match="event must be"):
        evaluator.evaluate(object(), operation, record_registry)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="operation must be"):
        evaluator.evaluate(event, object(), record_registry)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="record_registry must be"):
        evaluator.evaluate(event, operation, object())  # type: ignore[arg-type]


# AuthorizationBasisEvaluator


def test_authorization_not_required(
    record_registry: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    event = make_event()
    finding = evaluate(
        AuthorizationBasisEvaluator(SequentialIdentifierProvider()),
        event=event,
        operation=operation,
        registry=record_registry,
    )

    assert finding.finding_code == "AUTH_NOT_REQUIRED"
    assert finding.verdict == PolicyVerdict.NOT_APPLICABLE


def test_authorization_basis_missing(
    record_registry: PolicyRecordRegistry,
) -> None:
    operation = make_operation(
        authorization_basis_required=True,
        allowed_authorization_basis_types=("project_fixture",),
    )
    finding = evaluate(
        AuthorizationBasisEvaluator(SequentialIdentifierProvider()),
        event=make_event(),
        operation=operation,
        registry=record_registry,
    )

    assert finding.finding_code == "AUTH_BASIS_MISSING"
    assert finding.verdict == PolicyVerdict.INSUFFICIENT_EVIDENCE


def test_authorization_basis_type_not_allowed(
    record_registry: PolicyRecordRegistry,
) -> None:
    operation = make_operation(
        authorization_basis_required=True,
        allowed_authorization_basis_types=("guardian_consent",),
    )
    finding = evaluate(
        AuthorizationBasisEvaluator(SequentialIdentifierProvider()),
        event=make_event(authorization_basis=make_basis()),
        operation=operation,
        registry=record_registry,
    )

    assert finding.finding_code == "AUTH_BASIS_TYPE_NOT_ALLOWED"
    assert finding.verdict == PolicyVerdict.NONCOMPLIANT


def test_authorization_purpose_must_be_string(
    record_registry: PolicyRecordRegistry,
) -> None:
    operation = make_operation(
        authorization_basis_required=True,
        allowed_authorization_basis_types=("project_fixture",),
    )
    finding = evaluate(
        AuthorizationBasisEvaluator(SequentialIdentifierProvider()),
        event=make_event(
            payload={"purpose": 7},
            authorization_basis=make_basis(),
        ),
        operation=operation,
        registry=record_registry,
    )

    assert finding.finding_code == "AUTH_PURPOSE_INVALID"
    assert finding.verdict == PolicyVerdict.CONFIGURATION_FAILURE


def test_authorization_basis_valid_and_invalid(
    record_registry: PolicyRecordRegistry,
) -> None:
    operation = make_operation(
        authorization_basis_required=True,
        allowed_authorization_basis_types=("project_fixture",),
    )
    evaluator = AuthorizationBasisEvaluator(SequentialIdentifierProvider())

    valid = evaluate(
        evaluator,
        event=make_event(
            payload={"purpose": "education"},
            authorization_basis=make_basis(),
        ),
        operation=operation,
        registry=record_registry,
    )
    invalid = evaluate(
        evaluator,
        event=make_event(
            payload={"purpose": "different"},
            authorization_basis=make_basis(),
        ),
        operation=operation,
        registry=record_registry,
    )

    assert valid.finding_code == "AUTH_BASIS_VALID"
    assert valid.verdict == PolicyVerdict.COMPLIANT
    assert invalid.finding_code == "AUTH_BASIS_INVALID_OR_EXPIRED"
    assert invalid.verdict == PolicyVerdict.NONCOMPLIANT


# DestinationEvaluator


def test_destination_evaluator_approved_unknown_unregistered_and_wrong_operation(
    record_registry: PolicyRecordRegistry,
) -> None:
    evaluator = DestinationEvaluator(
        SequentialIdentifierProvider(),
        destination_registry(),
    )
    operation = make_operation()

    approved = evaluate(
        evaluator,
        event=make_event(destination_id="DEST-ALLOWED"),
        operation=operation,
        registry=record_registry,
    )
    unknown = evaluate(
        evaluator,
        event=make_event(destination_id="DEST-UNKNOWN"),
        operation=operation,
        registry=record_registry,
    )
    unregistered = evaluate(
        evaluator,
        event=make_event(destination_id="DEST-UNREGISTERED"),
        operation=operation,
        registry=record_registry,
    )
    wrong_operation = evaluate(
        evaluator,
        event=make_event(destination_id="DEST-WRONG-OP"),
        operation=operation,
        registry=record_registry,
    )

    assert approved.finding_code == "DESTINATION_APPROVED"
    assert approved.verdict == PolicyVerdict.COMPLIANT
    assert unknown.finding_code == "DESTINATION_UNKNOWN"
    assert unknown.verdict == PolicyVerdict.CONFIGURATION_FAILURE
    assert unregistered.finding_code == "DESTINATION_UNREGISTERED"
    assert wrong_operation.finding_code == "DESTINATION_OPERATION_INELIGIBLE"


def test_destination_evaluator_missing_record() -> None:
    evaluator = DestinationEvaluator(
        SequentialIdentifierProvider(),
        destination_registry(),
    )
    finding = evaluate(
        evaluator,
        event=make_event(),
        operation=make_operation(),
        registry=PolicyRecordRegistry(),
    )

    assert finding.finding_code == "DEST_RECORD_INACTIVE"
    assert finding.verdict == PolicyVerdict.INSUFFICIENT_EVIDENCE


def test_destination_evaluator_ambiguous_record(
    monkeypatch: pytest.MonkeyPatch,
    record_registry: PolicyRecordRegistry,
) -> None:
    def ambiguous(self: PolicyRecordRegistry, record_id: str):
        raise PolicyRecordAmbiguityError("internal details")

    monkeypatch.setattr(
        PolicyRecordRegistry,
        "get_active_by_record_id",
        ambiguous,
    )
    evaluator = DestinationEvaluator(
        SequentialIdentifierProvider(),
        destination_registry(),
    )
    finding = evaluate(
        evaluator,
        event=make_event(),
        operation=make_operation(),
        registry=record_registry,
    )

    assert finding.finding_code == "DEST_RECORD_AMBIGUOUS"
    assert finding.verdict == PolicyVerdict.CONFIGURATION_FAILURE
    assert "internal details" not in finding.rationale


# Educational evaluator


def test_educational_processing_nominal_and_commercial_drift(
    record_registry: PolicyRecordRegistry,
) -> None:
    evaluator = ProjectEducationalProcessingEvaluator(
        SequentialIdentifierProvider()
    )
    operation = make_operation()

    nominal = evaluate(
        evaluator,
        event=make_event(payload={"commercial_sdk_active": False}),
        operation=operation,
        registry=record_registry,
    )
    drift = evaluate(
        evaluator,
        event=make_event(payload={"commercial_sdk_active": True}),
        operation=operation,
        registry=record_registry,
    )
    invalid = evaluate(
        evaluator,
        event=make_event(payload={"commercial_sdk_active": "false"}),
        operation=operation,
        registry=record_registry,
    )

    assert nominal.finding_code == "EDU_PROCESSING_COMPLIANT"
    assert drift.finding_code == "PROJECT_CONTROL_COMMERCIAL_DRIFT_HELD"
    assert invalid.finding_code == "COMMERCIAL_SDK_FLAG_INVALID"


def test_educational_processing_missing_record() -> None:
    finding = evaluate(
        ProjectEducationalProcessingEvaluator(
            SequentialIdentifierProvider()
        ),
        event=make_event(),
        operation=make_operation(),
        registry=PolicyRecordRegistry(),
    )

    assert finding.finding_code == "EDU_RECORD_INACTIVE"


# Citation evaluator


def test_citation_evaluator_missing_invalid_collection_and_arbitrary_string(
    record_registry: PolicyRecordRegistry,
) -> None:
    evaluator = CitationIntegrityEvaluator(SequentialIdentifierProvider())
    operation = make_operation()

    missing = evaluate(
        evaluator,
        event=make_event(payload={}),
        operation=operation,
        registry=record_registry,
    )
    invalid_collection = evaluate(
        evaluator,
        event=make_event(payload={"citations": "citation"}),
        operation=operation,
        registry=record_registry,
    )
    arbitrary = evaluate(
        evaluator,
        event=make_event(payload={"citations": ["citation"]}),
        operation=operation,
        registry=record_registry,
    )

    assert missing.finding_code == "CITATION_MISSING"
    assert invalid_collection.finding_code == "CITATION_COLLECTION_INVALID"
    assert arbitrary.finding_code == "CITATION_ARBITRARY_STRING_REJECTED"


def test_citation_evaluator_verified_partial_and_unverified(
    record_registry: PolicyRecordRegistry,
) -> None:
    evaluator = CitationIntegrityEvaluator(SequentialIdentifierProvider())
    operation = make_operation()
    identity = record_registry.list_all()[0].identity
    verified_mapping = identity.to_dict()
    external_mapping = {
        "source_id": "EXTERNAL",
        "locator": "https://example.invalid/source",
    }

    verified = evaluate(
        evaluator,
        event=make_event(payload={"citations": [verified_mapping]}),
        operation=operation,
        registry=record_registry,
    )
    partial = evaluate(
        evaluator,
        event=make_event(
            payload={"citations": [verified_mapping, external_mapping]}
        ),
        operation=operation,
        registry=record_registry,
    )
    unverified = evaluate(
        evaluator,
        event=make_event(payload={"citations": [external_mapping]}),
        operation=operation,
        registry=record_registry,
    )

    assert verified.finding_code == "CITATION_VERIFIED"
    assert verified.verdict == PolicyVerdict.COMPLIANT
    assert partial.finding_code == "CITATION_PARTIALLY_VERIFIED"
    assert unverified.finding_code == "CITATION_STRUCTURALLY_VALID_UNVERIFIED"


def test_citation_evaluator_invalid_structure(
    record_registry: PolicyRecordRegistry,
) -> None:
    evaluator = CitationIntegrityEvaluator(SequentialIdentifierProvider())
    operation = make_operation()

    empty_locator = evaluate(
        evaluator,
        event=make_event(
            payload={
                "citations": [{"source_id": "SOURCE", "locator": " "}]
            }
        ),
        operation=operation,
        registry=record_registry,
    )
    unsupported = evaluate(
        evaluator,
        event=make_event(payload={"citations": [{"unexpected": True}]}),
        operation=operation,
        registry=record_registry,
    )

    assert empty_locator.finding_code == "CITATION_STRUCTURE_INVALID"
    assert unsupported.finding_code == "CITATION_STRUCTURE_INVALID"


# Content safety evaluator


@dataclass
class StaticChecker:
    result: ContentSafetyResult | None

    def check_content(
        self,
        payload: Mapping[str, Any],
    ) -> ContentSafetyResult | None:
        return self.result


class RaisingChecker:
    def check_content(self, payload: Mapping[str, Any]) -> None:
        raise RuntimeError("checker failed")


class InvalidChecker:
    pass


def safety_result(
    *,
    evaluated: bool,
    is_safe: bool | None,
) -> ContentSafetyResult:
    return ContentSafetyResult(
        evaluated=evaluated,
        is_safe=is_safe,
        finding_codes=("CODE-1",) if evaluated else (),
        evaluator_id="SAFETY-CHECKER",
        rationale="Typed safety result",
        timestamp=NOW,
    )


def test_content_safety_checker_protocol() -> None:
    assert isinstance(StaticChecker(None), ContentSafetyChecker)
    assert not isinstance(InvalidChecker(), ContentSafetyChecker)


def test_content_safety_constructor_rejects_invalid_checker() -> None:
    with pytest.raises(TypeError, match="ContentSafetyChecker"):
        ContentSafetyEvaluator(
            SequentialIdentifierProvider(),
            InvalidChecker(),  # type: ignore[arg-type]
        )


def test_content_safety_evaluator_all_outcomes(
    record_registry: PolicyRecordRegistry,
) -> None:
    operation = make_operation()
    event = make_event()

    cases = [
        (None, "SAFETY_ASSESSMENT_UNAVAILABLE"),
        (StaticChecker(None), "SAFETY_RESULT_MISSING"),
        (
            StaticChecker(safety_result(evaluated=False, is_safe=None)),
            "SAFETY_NOT_EVALUATED",
        ),
        (
            StaticChecker(safety_result(evaluated=True, is_safe=False)),
            "CONTENT_SAFETY_VIOLATION",
        ),
        (
            StaticChecker(safety_result(evaluated=True, is_safe=True)),
            "CONTENT_SAFETY_PASSED",
        ),
        (RaisingChecker(), "SAFETY_CHECK_FAILED"),
    ]

    for checker, expected_code in cases:
        finding = evaluate(
            ContentSafetyEvaluator(
                SequentialIdentifierProvider(),
                checker,
            ),
            event=event,
            operation=operation,
            registry=record_registry,
        )
        assert finding.finding_code == expected_code


# Commercial evaluator


def commercial_operation() -> ResolvedOperation:
    return make_operation(operation_id="commercial_purchase_request")


def test_commercial_control_missing_amount_invalid_amount_and_purchase(
    record_registry: PolicyRecordRegistry,
) -> None:
    evaluator = ProjectCommercialControlEvaluator(
        SequentialIdentifierProvider()
    )
    operation = commercial_operation()

    missing = evaluate(
        evaluator,
        event=make_event(operation_id=operation.operation_id),
        operation=operation,
        registry=record_registry,
    )
    malformed = evaluate(
        evaluator,
        event=make_event(
            operation_id=operation.operation_id,
            payload={"synthetic_purchase_amount": True},
        ),
        operation=operation,
        registry=record_registry,
    )
    negative = evaluate(
        evaluator,
        event=make_event(
            operation_id=operation.operation_id,
            payload={"synthetic_purchase_amount": -1},
        ),
        operation=operation,
        registry=record_registry,
    )
    purchase = evaluate(
        evaluator,
        event=make_event(
            operation_id=operation.operation_id,
            payload={"synthetic_purchase_amount": 10.5},
        ),
        operation=operation,
        registry=record_registry,
    )

    assert missing.finding_code == "PURCHASE_AMOUNT_MISSING"
    assert malformed.finding_code == "INVALID_TRANSACTION_AMOUNT"
    assert negative.finding_code == "INVALID_TRANSACTION_AMOUNT"
    assert purchase.finding_code == "PROJECT_CONTROL_COMMERCIAL_DRIFT_HELD"


def test_commercial_control_nominal_and_invalid_flag(
    record_registry: PolicyRecordRegistry,
) -> None:
    evaluator = ProjectCommercialControlEvaluator(
        SequentialIdentifierProvider()
    )
    operation = make_operation()

    nominal = evaluate(
        evaluator,
        event=make_event(payload={}),
        operation=operation,
        registry=record_registry,
    )
    invalid_flag = evaluate(
        evaluator,
        event=make_event(payload={"commercial_purchase_request": "false"}),
        operation=operation,
        registry=record_registry,
    )

    assert nominal.finding_code == "COMMERCIAL_CONTROL_NOMINAL"
    assert invalid_flag.finding_code == "PURCHASE_FLAG_INVALID"


# Child safeguarding evaluator


def test_child_safeguarding_all_outcomes(
    record_registry: PolicyRecordRegistry,
) -> None:
    evaluator = ChildSafeguardingEvaluator(SequentialIdentifierProvider())
    operation = make_operation()

    cases = [
        ({}, "LEARNER_AGE_MISSING"),
        ({"learner_age": True}, "LEARNER_AGE_MALFORMED"),
        ({"learner_age": 0}, "LEARNER_AGE_MALFORMED"),
        (
            {"learner_age": 12, "commercial_sdk_active": "false"},
            "COMMERCIAL_FLAG_INVALID",
        ),
        (
            {"learner_age": 12, "commercial_sdk_active": True},
            "CHILD_COMMERCIAL_EXPOSURE_HELD",
        ),
        ({"learner_age": 12}, "CHILD_SAFEGUARDING_NOMINAL"),
        ({"learner_age": 18}, "CHILD_SAFEGUARDING_NOMINAL"),
    ]

    for payload, expected_code in cases:
        finding = evaluate(
            evaluator,
            event=make_event(payload=payload),
            operation=operation,
            registry=record_registry,
        )
        assert finding.finding_code == expected_code


# Targeted advertising evaluator


def targeted_ad_operation() -> ResolvedOperation:
    return make_operation(operation_id="targeted_ad_dispatch")


def test_targeted_ad_control_all_outcomes(
    record_registry: PolicyRecordRegistry,
) -> None:
    evaluator = ProjectTargetedAdControlEvaluator(
        SequentialIdentifierProvider()
    )
    normal_operation = make_operation()

    nominal = evaluate(
        evaluator,
        event=make_event(payload={}),
        operation=normal_operation,
        registry=record_registry,
    )
    invalid_flag = evaluate(
        evaluator,
        event=make_event(payload={"commercial_ad_delivery": 1}),
        operation=normal_operation,
        registry=record_registry,
    )
    invalid_signal = evaluate(
        evaluator,
        event=make_event(
            payload={"simulated_prohibited_inference_signal": 7}
        ),
        operation=normal_operation,
        registry=record_registry,
    )

    ad_operation = targeted_ad_operation()
    prohibited = evaluate(
        evaluator,
        event=make_event(operation_id=ad_operation.operation_id),
        operation=ad_operation,
        registry=record_registry,
    )
    profiling = evaluate(
        evaluator,
        event=make_event(
            operation_id=ad_operation.operation_id,
            payload={"simulated_prohibited_inference_signal": EXACT_SIGNAL},
        ),
        operation=ad_operation,
        registry=record_registry,
    )

    assert nominal.finding_code == "TARGETED_AD_CONTROL_NOMINAL"
    assert invalid_flag.finding_code == "TARGETED_AD_FLAG_INVALID"
    assert invalid_signal.finding_code == "INFERENCE_SIGNAL_INVALID"
    assert prohibited.finding_code == (
        "PROJECT_CONTROL_TARGETED_AD_OPERATION_PROHIBITED"
    )
    assert profiling.finding_code == "PROJECT_CONTROL_PROFILING_AD_BLOCKED"


def test_targeted_ad_missing_record() -> None:
    evaluator = ProjectTargetedAdControlEvaluator(
        SequentialIdentifierProvider()
    )
    finding = evaluate(
        evaluator,
        event=make_event(),
        operation=make_operation(),
        registry=PolicyRecordRegistry(),
    )

    assert finding.finding_code == "TARGETED_AD_RECORD_INACTIVE"


# Inference data evaluator


def test_inference_data_all_outcomes(
    record_registry: PolicyRecordRegistry,
) -> None:
    evaluator = InferenceDataEvaluator(SequentialIdentifierProvider())
    operation = make_operation()

    cases = [
        ({}, "INFERENCE_DATA_NOMINAL"),
        ({"clinical_diagnosis": "false"}, "DIAGNOSIS_FLAG_INVALID"),
        ({"clinical_diagnosis": True}, "PROHIBITED_DIAGNOSTIC_SUBSTITUTION"),
        ({"diagnostic_label": "label"}, "PROHIBITED_DIAGNOSTIC_SUBSTITUTION"),
        (
            {"simulated_prohibited_inference_signal": 7},
            "INFERENCE_SIGNAL_INVALID",
        ),
        (
            {"simulated_prohibited_inference_signal": EXACT_SIGNAL},
            "EXACT_PROHIBITED_SIGNAL_DETECTED",
        ),
    ]

    for payload, expected_code in cases:
        finding = evaluate(
            evaluator,
            event=make_event(payload=payload),
            operation=operation,
            registry=record_registry,
        )
        assert finding.finding_code == expected_code


# Deterministic identifiers


def test_evaluators_use_expected_identifier_prefixes(
    record_registry: PolicyRecordRegistry,
) -> None:
    cases = [
        (AuthorizationBasisEvaluator, "find_auth_"),
        (ProjectEducationalProcessingEvaluator, "find_edu_"),
        (CitationIntegrityEvaluator, "find_cit_"),
        (ContentSafetyEvaluator, "find_safety_"),
        (ProjectCommercialControlEvaluator, "find_comm_"),
        (ChildSafeguardingEvaluator, "find_child_safe_"),
        (ProjectTargetedAdControlEvaluator, "find_ad_"),
        (InferenceDataEvaluator, "find_inf_"),
    ]

    for evaluator_type, prefix in cases:
        evaluator = evaluator_type(SequentialIdentifierProvider())
        finding = evaluator.evaluate(
            make_event(),
            make_operation(),
            record_registry,
        )
        assert finding.finding_id.startswith(prefix)

    destination = DestinationEvaluator(
        SequentialIdentifierProvider(),
        destination_registry(),
    )
    finding = destination.evaluate(
        make_event(),
        make_operation(),
        record_registry,
    )
    assert finding.finding_id.startswith("find_dest_")
