from __future__ import annotations

import hashlib

import pytest

from amba_ai.governance.models import (
    ActivationStatus,
    ApplicabilityStatus,
    ArtifactIntegrityStatus,
    AuthorizationBasis,
    AuthorizationBasisType,
    BindingLevel,
    FailureBehavior,
    InvalidOperationConfigurationError,
    LegalReviewStatus,
    LocatorVerificationStatus,
    MetadataVerificationStatus,
    OperationProtectionClass,
    PolicyRecord,
    PolicyRecordIdentity,
    ResolvedOperation,
    TranslationStatus,
)


VALID_HEX_64 = hashlib.sha256(b"TEST_VALID_PAYLOAD").hexdigest()
NORMATIVE_TEXT = "Normative rule text"
NORM_HEX_64 = hashlib.sha256(
    NORMATIVE_TEXT.encode("utf-8")
).hexdigest()


def test_valid_policy_record_construction() -> None:
    identity = PolicyRecordIdentity(
        "REC-001 ",
        " 1.0.0 ",
        " DOC-001",
    )

    assert identity.record_id == "REC-001"
    assert identity.version_id == "1.0.0"
    assert identity.source_id == "DOC-001"

    record = PolicyRecord(
        identity=identity,
        document_title="Test Project Control",
        authority="Amba-Gov project",
        jurisdiction="project_sandbox",
        scope="synthetic education-governance sandbox",
        binding_level=BindingLevel.PROJECT_CONTROL,
        official_locator="/controls/test",
        page_start=1,
        page_end=2,
        normative_text=NORMATIVE_TEXT,
        reviewed_summary="Summary of rule",
        regulated_actor="Amba-Gov sandbox components",
        protected_subject="synthetic education participants",
        conditions={"key": "value"},
        prohibitions=("no_commercial",),
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
        applicability_status=ApplicabilityStatus.APPLICABLE,
        activation_status=ActivationStatus.ACTIVE,
        artifact_sha256=VALID_HEX_64,
        normative_unit_sha256=NORM_HEX_64,
        eligible_for_project_enforcement=True,
        eligible_for_national_legal_finding=False,
        national_binding_status=False,
        synthetic_only=True,
        legal_effect=False,
        eligible_for_citation=True,
    )

    serialized = record.to_dict()

    assert serialized["binding_level"] == "project_control"
    assert serialized["national_binding_status"] is False
    assert serialized["legal_effect"] is False
    assert serialized["eligible_for_citation"] is True
    assert isinstance(serialized["prohibitions"], list)


def test_authorization_basis_temporal_order_enforced() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "expires_at must be strictly greater than "
            "effective_from"
        ),
    ):
        AuthorizationBasis(
            basis_id="AUTH-01",
            basis_type=AuthorizationBasisType.PROJECT_FIXTURE,
            subject_category="learner",
            authority_reference="SCHOOL",
            purposes=("classroom_telemetry",),
            data_categories=("metrics",),
            processing_operations=(
                "classroom_exercise_telemetry",
            ),
            effective_from="2026-06-01T00:00:00Z",
            expires_at="2026-06-01T00:00:00Z",
            revoked_at=None,
            artifact_hash=VALID_HEX_64,
            verifier_id="VERIFIER",
            synthetic=True,
            legal_effect=False,
        )

    with pytest.raises(
        ValueError,
        match="revoked_at cannot precede effective_from",
    ):
        AuthorizationBasis(
            basis_id="AUTH-01",
            basis_type=AuthorizationBasisType.PROJECT_FIXTURE,
            subject_category="learner",
            authority_reference="SCHOOL",
            purposes=("classroom_telemetry",),
            data_categories=("metrics",),
            processing_operations=(
                "classroom_exercise_telemetry",
            ),
            effective_from="2026-06-01T00:00:00Z",
            expires_at="2027-01-01T00:00:00Z",
            revoked_at="2026-05-01T00:00:00Z",
            artifact_hash=VALID_HEX_64,
            verifier_id="VERIFIER",
            synthetic=True,
            legal_effect=False,
        )


def test_authorization_basis_fixture_boundary_enforced() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "PROJECT_FIXTURE basis requires synthetic=True "
            "and legal_effect=False"
        ),
    ):
        AuthorizationBasis(
            basis_id="AUTH-01",
            basis_type=AuthorizationBasisType.PROJECT_FIXTURE,
            subject_category="learner",
            authority_reference="SCHOOL",
            purposes=("classroom_telemetry",),
            data_categories=("metrics",),
            processing_operations=(
                "classroom_exercise_telemetry",
            ),
            effective_from="2026-01-01T00:00:00Z",
            expires_at="2027-01-01T00:00:00Z",
            revoked_at=None,
            artifact_hash=VALID_HEX_64,
            verifier_id="VERIFIER",
            synthetic=False,
            legal_effect=False,
        )


def test_authorization_basis_tuple_duplicates_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="purposes cannot contain duplicates",
    ):
        AuthorizationBasis(
            basis_id="AUTH-01",
            basis_type=AuthorizationBasisType.PROJECT_FIXTURE,
            subject_category="learner",
            authority_reference="SCHOOL",
            purposes=(
                "classroom_telemetry",
                "classroom_telemetry",
            ),
            data_categories=("metrics",),
            processing_operations=(
                "classroom_exercise_telemetry",
            ),
            effective_from="2026-01-01T00:00:00Z",
            expires_at="2027-01-01T00:00:00Z",
            revoked_at=None,
            artifact_hash=VALID_HEX_64,
            verifier_id="VERIFIER",
            synthetic=True,
            legal_effect=False,
        )


def test_resolved_operation_strict_validation() -> None:
    with pytest.raises(
        InvalidOperationConfigurationError,
        match=(
            "Authorization-basis requirement and allowed types "
            "are inconsistent"
        ),
    ):
        ResolvedOperation(
            operation_id="op_auth_req",
            protection_class=OperationProtectionClass.PROTECTED,
            pre_gate_required=True,
            post_gate_required=False,
            authorization_basis_required=True,
            allowed_authorization_basis_types=(),
            required_evaluator_ids=("EVAL-1",),
            required_policy_record_ids=(),
            approval_required=False,
            approval_role=None,
            failure_behavior=FailureBehavior.HOLD_FOR_REVIEW,
        )

    with pytest.raises(
        InvalidOperationConfigurationError,
        match=(
            "Approval requirement and approval_role "
            "are inconsistent"
        ),
    ):
        ResolvedOperation(
            operation_id="op_app_req",
            protection_class=OperationProtectionClass.HIGH_RISK,
            pre_gate_required=True,
            post_gate_required=False,
            authorization_basis_required=False,
            allowed_authorization_basis_types=(),
            required_evaluator_ids=("EVAL-1",),
            required_policy_record_ids=(),
            approval_required=True,
            approval_role=None,
            failure_behavior=FailureBehavior.HOLD_FOR_REVIEW,
        )
