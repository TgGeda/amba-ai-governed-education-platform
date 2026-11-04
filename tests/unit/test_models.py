from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any

import pytest

from amba_ai.governance.models import (
    ActivationStatus,
    ApplicabilityStatus,
    ArtifactIntegrityStatus,
    AuthorizationBasis,
    AuthorizationBasisType,
    BindingLevel,
    ContentSafetyResult,
    EnforcementAction,
    EvidenceSufficiency,
    FailureBehavior,
    FindingSeverity,
    GateResult,
    GateStatus,
    InvalidOperationConfigurationError,
    InvalidPolicyRecordError,
    LegalReviewStatus,
    LocatorVerificationStatus,
    MetadataVerificationStatus,
    OperationProtectionClass,
    PipelineEvent,
    PolicyEvaluationBundle,
    PolicyFinding,
    PolicyRecommendation,
    PolicyRecord,
    PolicyRecordIdentity,
    PolicyVerdict,
    ResolvedOperation,
    SequentialIdentifierProvider,
    TranslationStatus,
    UUIDIdentifierProvider,
    deep_freeze,
    to_canonical_json,
)


VALID_SHA = hashlib.sha256(b"artifact").hexdigest()
NORMATIVE_TEXT = "Synthetic project rule."
NORMATIVE_SHA = hashlib.sha256(NORMATIVE_TEXT.encode("utf-8")).hexdigest()
NOW = "2026-06-01T12:00:00Z"


def make_identity(
    *,
    record_id: str = "PROJECT-CONTROL-TEST-V1",
    version_id: str = "1.0.0",
    source_id: str = "AMBA-SAFEGUARDS",
) -> PolicyRecordIdentity:
    return PolicyRecordIdentity(
        record_id=record_id,
        version_id=version_id,
        source_id=source_id,
    )


def make_basis(**overrides: Any) -> AuthorizationBasis:
    values: dict[str, Any] = {
        "basis_id": "BASIS-001",
        "basis_type": AuthorizationBasisType.PROJECT_FIXTURE,
        "subject_category": "synthetic_learner",
        "authority_reference": "fixture://authorization/BASIS-001",
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


def make_record(**overrides: Any) -> PolicyRecord:
    normative_text = overrides.get("normative_text", NORMATIVE_TEXT)
    values: dict[str, Any] = {
        "identity": make_identity(),
        "document_title": "Synthetic Safeguards",
        "authority": "Amba governance",
        "jurisdiction": "project_sandbox",
        "scope": "Synthetic education sandbox",
        "binding_level": BindingLevel.PROJECT_CONTROL,
        "official_locator": "controls.test",
        "page_start": None,
        "page_end": None,
        "normative_text": normative_text,
        "reviewed_summary": "Reviewed synthetic control.",
        "regulated_actor": "Sandbox components",
        "protected_subject": "Synthetic participants",
        "conditions": {"nested": {"enabled": True}},
        "prohibitions": (),
        "exceptions": (),
        "artifact_integrity_status": ArtifactIntegrityStatus.VERIFIED,
        "metadata_verification_status": MetadataVerificationStatus.VERIFIED,
        "locator_verification_status": LocatorVerificationStatus.VERIFIED_STRUCTURAL,
        "translation_status": TranslationStatus.NOT_APPLICABLE,
        "legal_review_status": LegalReviewStatus.NOT_APPLICABLE,
        "applicability_status": ApplicabilityStatus.APPLICABLE,
        "activation_status": ActivationStatus.ACTIVE,
        "artifact_sha256": VALID_SHA,
        "normative_unit_sha256": hashlib.sha256(
            normative_text.encode("utf-8")
        ).hexdigest(),
        "eligible_for_project_enforcement": True,
        "eligible_for_national_legal_finding": False,
        "national_binding_status": False,
        "synthetic_only": True,
        "legal_effect": False,
        "eligible_for_citation": True,
    }
    values.update(overrides)
    return PolicyRecord(**values)


def make_operation(**overrides: Any) -> ResolvedOperation:
    values: dict[str, Any] = {
        "operation_id": "classroom_exercise_telemetry",
        "protection_class": OperationProtectionClass.PROTECTED,
        "pre_gate_required": True,
        "post_gate_required": True,
        "authorization_basis_required": True,
        "allowed_authorization_basis_types": ("project_fixture",),
        "required_evaluator_ids": ("evaluator-b", "evaluator-a"),
        "required_policy_record_ids": ("record-b", "record-a"),
        "approval_required": False,
        "approval_role": None,
        "failure_behavior": FailureBehavior.BLOCK,
    }
    values.update(overrides)
    return ResolvedOperation(**values)


def make_event(**overrides: Any) -> PipelineEvent:
    values: dict[str, Any] = {
        "event_id": "EVENT-001",
        "timestamp": NOW,
        "operation_id": "classroom_exercise_telemetry",
        "source_node": "SOURCE-001",
        "destination_id": "SYNTHETIC-TEACHER-UI",
        "payload_type": "telemetry",
        "payload": {"nested": {"items": [1, 2]}},
        "authorization_basis": make_basis(),
        "synthetic_flag": True,
    }
    values.update(overrides)
    return PipelineEvent(**values)


def make_finding(**overrides: Any) -> PolicyFinding:
    values: dict[str, Any] = {
        "finding_id": "FINDING-001",
        "event_id": "EVENT-001",
        "finding_code": "PROJECT_CONTROL_CHECK",
        "basis_category": BindingLevel.PROJECT_CONTROL,
        "severity": FindingSeverity.INFO,
        "verdict": PolicyVerdict.COMPLIANT,
        "evaluator_id": "evaluator-a",
        "primary_records": (make_identity(),),
        "supporting_records": (),
        "rationale": "The synthetic event satisfies the project control.",
        "evidence_sufficiency": EvidenceSufficiency.SUFFICIENT,
        "deterministic_result": True,
        "applicability_details": {"scope": {"applicable": True}},
    }
    values.update(overrides)
    return PolicyFinding(**values)


def make_recommendation(**overrides: Any) -> PolicyRecommendation:
    values: dict[str, Any] = {
        "recommendation_id": "REC-001",
        "event_id": "EVENT-001",
        "recommended_action": EnforcementAction.PROCEED,
        "mitigation_steps": (),
        "requires_approval": False,
        "escalation_role": None,
    }
    values.update(overrides)
    return PolicyRecommendation(**values)


# Canonical data handling

def test_deep_freeze_recursively_freezes_mappings_and_sequences() -> None:
    frozen = deep_freeze({"outer": {"items": [1, {"ok": True}]}})

    assert isinstance(frozen, MappingProxyType)
    assert isinstance(frozen["outer"], MappingProxyType)
    assert isinstance(frozen["outer"]["items"], tuple)
    with pytest.raises(TypeError):
        frozen["new"] = "value"  # type: ignore[index]


@pytest.mark.parametrize("value", [{1, 2}, frozenset({1, 2})])
def test_deep_freeze_rejects_sets(value: object) -> None:
    with pytest.raises(TypeError, match="Set types are prohibited"):
        deep_freeze(value)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_deep_freeze_rejects_nonfinite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="NaN and Infinity"):
        deep_freeze({"value": value})


def test_deep_freeze_rejects_normalized_key_collisions() -> None:
    with pytest.raises(ValueError, match="keys collide"):
        deep_freeze({1: "first", "1": "second"})


def test_canonical_json_is_sorted_compact_unicode_and_enum_aware() -> None:
    encoded = to_canonical_json(
        {
            "z": "የትምህርት",
            "a": BindingLevel.PROJECT_CONTROL,
            "items": (2, 1),
        }
    )

    assert encoded == (
        '{"a":"project_control","items":[2,1],"z":"የትምህርት"}'
    )
    assert json.loads(encoded)["a"] == "project_control"


@pytest.mark.parametrize("value", [{"value": math.nan}, {"value": {1}}])
def test_canonical_json_rejects_unsafe_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        to_canonical_json(value)


def test_canonical_json_uses_model_to_dict() -> None:
    identity = make_identity()

    assert to_canonical_json(identity) == (
        '{"record_id":"PROJECT-CONTROL-TEST-V1",'
        '"source_id":"AMBA-SAFEGUARDS","version_id":"1.0.0"}'
    )


# Identifier providers

def test_sequential_identifier_provider_is_deterministic() -> None:
    provider = SequentialIdentifierProvider(initial_index=7)

    assert provider.new_id("item") == "item_000007"
    assert provider.new_id(" item ") == "item_000008"


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_sequential_identifier_provider_rejects_invalid_start(value: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        SequentialIdentifierProvider(value)  # type: ignore[arg-type]


def test_sequential_identifier_provider_is_thread_safe() -> None:
    provider = SequentialIdentifierProvider()

    with ThreadPoolExecutor(max_workers=16) as executor:
        identifiers = tuple(executor.map(lambda _: provider.new_id("id"), range(200)))

    assert len(identifiers) == 200
    assert len(set(identifiers)) == 200
    assert set(identifiers) == {f"id_{index:06d}" for index in range(1, 201)}


def test_uuid_identifier_provider_validates_prefix_and_is_unique() -> None:
    provider = UUIDIdentifierProvider()
    identifiers = {provider.new_id("uuid") for _ in range(20)}

    assert len(identifiers) == 20
    assert all(identifier.startswith("uuid_") for identifier in identifiers)
    assert all(len(identifier) == len("uuid_") + 12 for identifier in identifiers)

    with pytest.raises(ValueError, match="prefix must not be empty"):
        provider.new_id(" ")


# Content safety and identity

def test_content_safety_result_normalizes_and_serializes() -> None:
    result = ContentSafetyResult(
        evaluated=True,
        is_safe=True,
        finding_codes=(" B ", " A "),
        evaluator_id=" evaluator ",
        rationale=" safe ",
        timestamp="2026-06-01T14:00:00+02:00",
    )

    assert result.finding_codes == ("A", "B")
    assert result.timestamp == "2026-06-01T12:00:00+00:00"
    assert result.to_dict()["evaluator_id"] == "evaluator"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"evaluated": False, "is_safe": True}, "unevaluated"),
        ({"evaluated": True, "is_safe": None}, "requires a safety verdict"),
        ({"evaluated": 1}, "evaluated must be a strict Boolean"),
        ({"finding_codes": ("A", "A")}, "cannot contain duplicates"),
        ({"finding_codes": (" ",)}, "finding_codes must not be empty"),
    ],
)
def test_content_safety_result_rejects_invalid_states(
    kwargs: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "evaluated": True,
        "is_safe": True,
        "finding_codes": (),
        "evaluator_id": "evaluator",
        "rationale": "valid",
    }
    values.update(kwargs)
    with pytest.raises((TypeError, ValueError), match=message):
        ContentSafetyResult(**values)  # type: ignore[arg-type]


def test_policy_record_identity_normalizes_and_formats() -> None:
    identity = PolicyRecordIdentity(" RECORD ", " 1.0 ", " SOURCE ")

    assert str(identity) == "RECORD@1.0#SOURCE"
    assert identity.to_dict() == {
        "record_id": "RECORD",
        "version_id": "1.0",
        "source_id": "SOURCE",
    }


# Authorization basis

def test_authorization_basis_normalizes_and_validates_lifecycle() -> None:
    basis = make_basis(
        purposes=(" second ", " first "),
        data_categories=(" beta ", " alpha "),
        processing_operations=(" operation-b ", " operation-a "),
        effective_from="2026-01-01T02:00:00+02:00",
    )

    assert basis.purposes == ("first", "second")
    assert basis.data_categories == ("alpha", "beta")
    assert basis.processing_operations == ("operation-a", "operation-b")
    assert basis.effective_from == "2026-01-01T00:00:00+00:00"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"basis_type": "project_fixture"}, "basis_type must be"),
        ({"purposes": []}, "purposes must be a tuple"),
        ({"purposes": ()}, "purposes must not be empty"),
        ({"synthetic": 1}, "synthetic must be a strict Boolean"),
        ({"synthetic": False}, "PROJECT_FIXTURE"),
        ({"legal_effect": True}, "PROJECT_FIXTURE"),
        ({"expires_at": "2026-01-01T00:00:00Z"}, "strictly greater"),
        ({"revoked_at": "2025-12-31T00:00:00Z"}, "cannot precede"),
        ({"revoked_at": "2027-01-01T00:00:00Z"}, "must precede expires_at"),
    ],
)
def test_authorization_basis_rejects_invalid_states(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError, InvalidPolicyRecordError), match=message):
        make_basis(**kwargs)


def test_authorization_basis_validity_boundaries() -> None:
    basis = make_basis(revoked_at="2026-07-01T00:00:00Z")

    assert basis.is_valid("education", "classroom_exercise_telemetry", NOW) is True
    assert basis.is_valid("wrong", "classroom_exercise_telemetry", NOW) is False
    assert basis.is_valid("education", "wrong", NOW) is False
    assert basis.is_valid(
        "education",
        "classroom_exercise_telemetry",
        "2026-07-01T00:00:00Z",
    ) is False

    with pytest.raises(ValueError, match="now_iso"):
        basis.is_valid("education", "classroom_exercise_telemetry", "not-a-date")


# Policy record

def test_policy_record_freezes_conditions_and_serializes() -> None:
    record = make_record(
        prohibitions=(" prohibition-b ", " prohibition-a "),
        exceptions=(" exception-b ", " exception-a "),
    )

    assert isinstance(record.conditions, MappingProxyType)
    assert isinstance(record.conditions["nested"], MappingProxyType)
    assert record.prohibitions == ("prohibition-a", "prohibition-b")
    assert record.exceptions == ("exception-a", "exception-b")
    assert json.loads(record.to_canonical_json())["identity"]["record_id"] == (
        "PROJECT-CONTROL-TEST-V1"
    )


def test_policy_record_rejects_mismatched_normative_digest() -> None:
    with pytest.raises(
        InvalidPolicyRecordError,
        match="does not match normative_text",
    ):
        make_record(normative_unit_sha256=VALID_SHA)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"artifact_sha256": "0" * 64}, "cannot be all zeros"),
        ({"artifact_sha256": "A" * 64}, "lowercase SHA-256"),
        ({"page_start": 0}, "positive integer"),
        ({"page_start": 3, "page_end": 2}, "cannot precede"),
        ({"conditions": []}, "conditions must be a mapping"),
        ({"eligible_for_project_enforcement": 1}, "strict Boolean"),
        ({"national_binding_status": True}, "project_control"),
        ({"legal_effect": True}, "project_control"),
    ],
)
def test_policy_record_rejects_invalid_values(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(InvalidPolicyRecordError, match=message):
        make_record(**kwargs)


def test_inactive_policy_record_cannot_claim_eligibility() -> None:
    with pytest.raises(InvalidPolicyRecordError, match="Inactive records"):
        make_record(
            activation_status=ActivationStatus.QUARANTINED,
            eligible_for_project_enforcement=True,
            eligible_for_citation=False,
        )


def test_citation_requires_verified_integrity_and_locator() -> None:
    with pytest.raises(InvalidPolicyRecordError, match="verified artifact"):
        make_record(
            artifact_integrity_status=ArtifactIntegrityStatus.UNVERIFIED,
            eligible_for_project_enforcement=False,
        )

    with pytest.raises(InvalidPolicyRecordError, match="verified locator"):
        make_record(
            locator_verification_status=LocatorVerificationStatus.UNVERIFIED,
            eligible_for_project_enforcement=False,
        )


# Operations and events

def test_resolved_operation_normalizes_dependencies() -> None:
    operation = make_operation()

    assert operation.required_evaluator_ids == ("evaluator-a", "evaluator-b")
    assert operation.required_policy_record_ids == ("record-a", "record-b")
    assert operation.allowed_authorization_basis_types == ("project_fixture",)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"protection_class": "protected"}, "protection_class must be"),
        ({"pre_gate_required": 1}, "strict Boolean"),
        ({"required_evaluator_ids": []}, "must be a tuple"),
        ({"required_evaluator_ids": ()}, "must configure required evaluators"),
        (
            {"authorization_basis_required": False},
            "Authorization-basis requirement",
        ),
        ({"approval_required": True}, "Approval requirement"),
        ({"failure_behavior": FailureBehavior.PROCEED}, "cannot configure"),
    ],
)
def test_resolved_operation_rejects_invalid_states(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(InvalidOperationConfigurationError, match=message):
        make_operation(**kwargs)


def test_pipeline_event_normalizes_and_freezes_payload() -> None:
    event = make_event(timestamp="2026-06-01T14:00:00+02:00")

    assert event.timestamp == "2026-06-01T12:00:00+00:00"
    assert isinstance(event.payload, MappingProxyType)
    assert isinstance(event.payload["nested"], MappingProxyType)
    assert event.payload["nested"]["items"] == (1, 2)


@pytest.mark.parametrize(
    "kwargs, exception, message",
    [
        ({"event_id": " "}, ValueError, "event_id must not be empty"),
        ({"payload": []}, TypeError, "payload must be a mapping"),
        ({"synthetic_flag": 1}, ValueError, "strict Boolean"),
        ({"authorization_basis": object()}, TypeError, "AuthorizationBasis"),
    ],
)
def test_pipeline_event_rejects_invalid_values(
    kwargs: dict[str, object],
    exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception, match=message):
        make_event(**kwargs)


# Findings, recommendations, bundles, and gates

def test_policy_finding_normalizes_records_and_details() -> None:
    identity_b = make_identity(record_id="RECORD-B")
    identity_a = make_identity(record_id="RECORD-A")
    finding = make_finding(primary_records=(identity_b, identity_a))

    assert tuple(item.record_id for item in finding.primary_records) == (
        "RECORD-A",
        "RECORD-B",
    )
    assert isinstance(finding.applicability_details, MappingProxyType)


@pytest.mark.parametrize(
    "kwargs, exception, message",
    [
        ({"deterministic_result": 1}, ValueError, "strict Boolean"),
        ({"primary_records": []}, TypeError, "record collections must be tuples"),
        (
            {"primary_records": (make_identity(), make_identity())},
            ValueError,
            "cannot contain duplicates",
        ),
        (
            {"supporting_records": (make_identity(),)},
            ValueError,
            "both primary and supporting",
        ),
        ({"applicability_details": []}, TypeError, "must be a mapping"),
    ],
)
def test_policy_finding_rejects_invalid_states(
    kwargs: dict[str, object],
    exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception, match=message):
        make_finding(**kwargs)


def test_policy_recommendation_normalizes_steps_and_approval_role() -> None:
    recommendation = make_recommendation(
        recommended_action=EnforcementAction.REQUIRE_APPROVAL,
        mitigation_steps=(" step-b ", " step-a "),
        requires_approval=True,
        escalation_role=" reviewer ",
    )

    assert recommendation.mitigation_steps == ("step-a", "step-b")
    assert recommendation.escalation_role == "reviewer"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"mitigation_steps": (" ",)}, "mitigation_steps must not be empty"),
        (
            {"mitigation_steps": ("step", "step")},
            "cannot contain duplicates",
        ),
        ({"requires_approval": 1}, "strict Boolean"),
        ({"requires_approval": True}, "Approval requirement"),
        ({"escalation_role": "reviewer"}, "Approval requirement"),
    ],
)
def test_policy_recommendation_rejects_invalid_states(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        make_recommendation(**kwargs)


def test_policy_evaluation_bundle_validates_relationships_and_order() -> None:
    finding_b = make_finding(finding_id="FINDING-B")
    finding_a = make_finding(finding_id="FINDING-A")
    bundle = PolicyEvaluationBundle(
        event_id="EVENT-001",
        operation=make_operation(),
        findings=(finding_b, finding_a),
        recommendation=make_recommendation(),
        unresolved_questions=(" question-b ", " question-a "),
    )

    assert tuple(item.finding_id for item in bundle.findings) == (
        "FINDING-A",
        "FINDING-B",
    )
    assert bundle.unresolved_questions == ("question-a", "question-b")


@pytest.mark.parametrize(
    "kwargs, exception, message",
    [
        (
            {"recommendation": make_recommendation(event_id="OTHER")},
            ValueError,
            "Recommendation event identifier",
        ),
        (
            {"findings": (make_finding(event_id="OTHER"),)},
            ValueError,
            "Finding event identifier",
        ),
        (
            {"findings": (make_finding(), make_finding())},
            ValueError,
            "duplicate finding IDs",
        ),
        ({"findings": []}, TypeError, "tuple of PolicyFinding"),
        (
            {"unresolved_questions": ("same", "same")},
            ValueError,
            "cannot contain duplicates",
        ),
    ],
)
def test_policy_evaluation_bundle_rejects_invalid_states(
    kwargs: dict[str, object],
    exception: type[Exception],
    message: str,
) -> None:
    values = {
        "event_id": "EVENT-001",
        "operation": make_operation(),
        "findings": (make_finding(),),
        "recommendation": make_recommendation(),
        "unresolved_questions": (),
    }
    values.update(kwargs)
    with pytest.raises(exception, match=message):
        PolicyEvaluationBundle(**values)  # type: ignore[arg-type]


def test_gate_result_validates_state_and_serializes() -> None:
    result = GateResult(
        allowed=True,
        status=GateStatus.PASSED,
        operation_id=" operation ",
        finding_ids=(" finding-b ", " finding-a "),
        recommendation_id=" recommendation ",
        receipt_id=" receipt ",
        rationale=" passed ",
    )

    assert result.operation_id == "operation"
    assert result.finding_ids == ("finding-a", "finding-b")
    assert json.loads(result.to_canonical_json())["status"] == "passed"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"allowed": 1}, "allowed must be a strict Boolean"),
        ({"allowed": True, "status": GateStatus.BLOCKED}, "inconsistent"),
        ({"allowed": False, "status": GateStatus.PASSED}, "inconsistent"),
        ({"finding_ids": ("same", "same")}, "cannot contain duplicates"),
        ({"rationale": " "}, "rationale must not be empty"),
    ],
)
def test_gate_result_rejects_invalid_states(
    kwargs: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "allowed": False,
        "status": GateStatus.BLOCKED,
        "operation_id": "operation",
        "finding_ids": (),
        "recommendation_id": None,
        "receipt_id": None,
        "rationale": "blocked",
    }
    values.update(kwargs)
    with pytest.raises((TypeError, ValueError), match=message):
        GateResult(**values)  # type: ignore[arg-type]
