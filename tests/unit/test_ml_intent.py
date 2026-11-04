from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from amba_ai.standards.ml_intent import (
    ML_INTENT_MAPPING_TYPE,
    ML_INTENT_SCHEMA_VERSION,
    ML_INTENT_STANDARD_LOCATOR,
    ML_INTENT_STANDARD_REFERENCE,
    REQUIRED_ALLOWED_MODEL_ROLES,
    REQUIRED_PROHIBITED_MODEL_ROLES,
    SECURITY_CRITICAL_MODEL_ROLES,
    MLIntent,
    MLIntentGovernanceRequirements,
    MLIntentStandardReference,
    MLIntentSyntheticScope,
    load_ml_intent,
)
from amba_ai.standards.y3172_models import (
    Y3172ConfigurationError,
    Y3172Node,
    Y3172_NODE_ORDER,
)


def _standard_reference(
    **overrides,
) -> MLIntentStandardReference:
    values = {
        "recommendation": (
            ML_INTENT_STANDARD_REFERENCE
        ),
        "locator": ML_INTENT_STANDARD_LOCATOR,
        "mapping_type": ML_INTENT_MAPPING_TYPE,
        "conformance_claimed": False,
    }
    values.update(overrides)

    return MLIntentStandardReference(**values)


def _governance(
    **overrides,
) -> MLIntentGovernanceRequirements:
    values = {
        "deterministic_policy_node_required": True,
        "human_approval_required_when_configured": True,
        "typed_execution_required": True,
        "registered_destination_required": True,
        "audit_required": True,
        "readiness_runtime_separation_required": True,
    }
    values.update(overrides)

    return MLIntentGovernanceRequirements(
        **values
    )


def _synthetic_scope(
    **overrides,
) -> MLIntentSyntheticScope:
    values = {
        "required": True,
        "legal_effect": False,
    }
    values.update(overrides)

    return MLIntentSyntheticScope(**values)


def _intent(
    **overrides,
) -> MLIntent:
    values = {
        "schema_version": (
            ML_INTENT_SCHEMA_VERSION
        ),
        "intent_id": "AMBA-GOV-ML-INTENT-V1",
        "title": (
            "Synthetic Education Governance "
            "Pipeline Intent"
        ),
        "objective": (
            "Provide evidence-grounded educational "
            "assistance under deterministic governance."
        ),
        "standard_reference": (
            _standard_reference()
        ),
        "allowed_model_roles": tuple(
            sorted(REQUIRED_ALLOWED_MODEL_ROLES)
        ),
        "prohibited_model_roles": tuple(
            sorted(REQUIRED_PROHIBITED_MODEL_ROLES)
        ),
        "required_nodes": Y3172_NODE_ORDER,
        "governance": _governance(),
        "synthetic_scope": _synthetic_scope(),
        "metadata": {},
    }
    values.update(overrides)

    return MLIntent(**values)


def _document() -> dict:
    return {
        "schema_version": (
            ML_INTENT_SCHEMA_VERSION
        ),
        "ml_intent": {
            "intent_id": (
                "AMBA-GOV-ML-INTENT-V1"
            ),
            "title": (
                "Synthetic Education Governance "
                "Pipeline Intent"
            ),
            "standard_reference": {
                "recommendation": (
                    ML_INTENT_STANDARD_REFERENCE
                ),
                "locator": (
                    ML_INTENT_STANDARD_LOCATOR
                ),
                "mapping_type": (
                    ML_INTENT_MAPPING_TYPE
                ),
                "conformance_claimed": False,
            },
            "objective": (
                "Provide evidence-grounded "
                "educational assistance."
            ),
            "allowed_model_roles": [
                "policy_evidence_retrieval",
                "educational_explanation",
                "document_summary",
                "institutional_context_preparation",
                "policy_gap_candidate_identification",
            ],
            "prohibited_model_roles": [
                "runtime_authorization",
                "human_approval_substitution",
                "national_legal_determination",
                "execution_receipt_fabrication",
                "audit_verification_fabrication",
                "readiness_score_authorization",
            ],
            "pipeline": {
                "required_nodes": [
                    node.value
                    for node in Y3172_NODE_ORDER
                ],
            },
            "governance": {
                "deterministic_policy_node_required": True,
                "human_approval_required_when_configured": True,
                "typed_execution_required": True,
                "registered_destination_required": True,
                "audit_required": True,
                "readiness_runtime_separation_required": True,
            },
            "synthetic_scope": {
                "required": True,
                "legal_effect": False,
            },
        },
    }


def _write_yaml(
    tmp_path: Path,
    document: object,
    *,
    filename: str = "ml_intent.yaml",
) -> Path:
    path = tmp_path / filename

    path.write_text(
        yaml.safe_dump(
            document,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    return path


def test_standard_reference_is_valid() -> None:
    reference = _standard_reference()

    assert (
        reference.recommendation
        == ML_INTENT_STANDARD_REFERENCE
    )
    assert (
        reference.conformance_claimed
        is False
    )


def test_standard_reference_rejects_wrong_recommendation() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="recommendation must be",
    ):
        _standard_reference(
            recommendation="ITU-T Y.3117",
        )


def test_standard_reference_rejects_wrong_locator() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="locator must be",
    ):
        _standard_reference(
            locator="Clause 8.1",
        )


def test_standard_reference_rejects_formal_conformance() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="conformance",
    ):
        _standard_reference(
            conformance_claimed=True,
        )


def test_standard_reference_requires_strict_boolean() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="strict Boolean",
    ):
        _standard_reference(
            conformance_claimed=0,
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "deterministic_policy_node_required",
        "human_approval_required_when_configured",
        "typed_execution_required",
        "registered_destination_required",
        "audit_required",
        "readiness_runtime_separation_required",
    ],
)
def test_governance_requirement_cannot_be_disabled(
    field_name: str,
) -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match=f"{field_name} must remain true",
    ):
        _governance(
            **{field_name: False}
        )


def test_governance_requirement_requires_strict_boolean() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="strict Boolean",
    ):
        _governance(
            audit_required=1,
        )


def test_synthetic_scope_is_required() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="must remain required",
    ):
        _synthetic_scope(
            required=False,
        )


def test_synthetic_scope_prohibits_legal_effect() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="must not create legal effect",
    ):
        _synthetic_scope(
            legal_effect=True,
        )


def test_synthetic_scope_requires_strict_boolean() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="strict Boolean",
    ):
        _synthetic_scope(
            legal_effect=0,
        )


def test_intent_requires_supported_schema() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="unsupported ML intent schema",
    ):
        _intent(
            schema_version="2.0.0",
        )


def test_intent_rejects_role_overlap() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="both allowed and prohibited",
    ):
        _intent(
            allowed_model_roles=(
                tuple(
                    sorted(
                        REQUIRED_ALLOWED_MODEL_ROLES
                    )
                )
                + ("runtime_authorization",)
            ),
        )


def test_intent_rejects_missing_allowed_role() -> None:
    roles = set(
        REQUIRED_ALLOWED_MODEL_ROLES
    )
    roles.remove(
        "policy_evidence_retrieval"
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="required allowed model roles",
    ):
        _intent(
            allowed_model_roles=tuple(
                sorted(roles)
            ),
        )


def test_intent_rejects_missing_prohibited_role() -> None:
    roles = set(
        REQUIRED_PROHIBITED_MODEL_ROLES
    )
    roles.remove(
        "runtime_authorization"
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="required prohibited model roles",
    ):
        _intent(
            prohibited_model_roles=tuple(
                sorted(roles)
            ),
        )


def test_intent_rejects_duplicate_allowed_roles() -> None:
    roles = tuple(
        sorted(REQUIRED_ALLOWED_MODEL_ROLES)
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="must not contain duplicates",
    ):
        _intent(
            allowed_model_roles=(
                roles
                + (roles[0],)
            ),
        )


def test_intent_rejects_invalid_role_name() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="lowercase snake_case",
    ):
        _intent(
            allowed_model_roles=(
                "Policy Evidence Retrieval",
                *tuple(
                    sorted(
                        REQUIRED_ALLOWED_MODEL_ROLES
                        - {
                            "policy_evidence_retrieval"
                        }
                    )
                ),
            ),
        )


def test_intent_requires_canonical_nodes() -> None:
    reordered = list(
        Y3172_NODE_ORDER
    )
    reordered[0], reordered[1] = (
        reordered[1],
        reordered[0],
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="canonical order",
    ):
        _intent(
            required_nodes=tuple(reordered),
        )


@pytest.mark.parametrize(
    "role",
    sorted(REQUIRED_ALLOWED_MODEL_ROLES),
)
def test_required_model_roles_are_permitted(
    role: str,
) -> None:
    intent = _intent()

    assert intent.permits_model_role(
        role
    )
    assert not intent.prohibits_model_role(
        role
    )

    intent.require_model_role(role)


@pytest.mark.parametrize(
    "role",
    sorted(SECURITY_CRITICAL_MODEL_ROLES),
)
def test_security_critical_roles_are_prohibited(
    role: str,
) -> None:
    intent = _intent()

    assert not intent.permits_model_role(
        role
    )
    assert intent.prohibits_model_role(
        role
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="model role is not permitted",
    ):
        intent.require_model_role(role)


def test_unknown_model_role_is_denied_by_default() -> None:
    intent = _intent()

    assert not intent.permits_model_role(
        "unregistered_model_capability"
    )

    assert intent.prohibits_model_role(
        "unregistered_model_capability"
    )


def test_metadata_is_deeply_immutable() -> None:
    intent = _intent(
        metadata={
            "nested": {
                "status": "verified",
            },
        },
    )

    with pytest.raises(TypeError):
        intent.metadata["other"] = "value"

    with pytest.raises(TypeError):
        intent.metadata["nested"]["status"] = "changed"


def test_canonical_json_is_deterministic() -> None:
    first = _intent(
        metadata={
            "scope": "synthetic",
            "status": "interpreted",
        },
    )
    second = _intent(
        metadata={
            "status": "interpreted",
            "scope": "synthetic",
        },
    )

    assert (
        first.to_canonical_json()
        == second.to_canonical_json()
    )


def test_load_valid_document(
    tmp_path: Path,
) -> None:
    path = _write_yaml(
        tmp_path,
        _document(),
    )

    intent = load_ml_intent(
        path,
        allowed_root=tmp_path,
    )

    assert intent.intent_id == (
        "AMBA-GOV-ML-INTENT-V1"
    )
    assert (
        intent.required_nodes
        == Y3172_NODE_ORDER
    )
    assert (
        intent.standard_reference
        .conformance_claimed
        is False
    )
    assert (
        intent.synthetic_scope.legal_effect
        is False
    )


def test_load_outside_allowed_root_fails(
    tmp_path: Path,
) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    outside = tmp_path / "outside.yaml"
    outside.write_text(
        yaml.safe_dump(_document()),
        encoding="utf-8",
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="outside the allowed root",
    ):
        load_ml_intent(
            outside,
            allowed_root=allowed_root,
        )


def test_load_symlink_fails(
    tmp_path: Path,
) -> None:
    target = _write_yaml(
        tmp_path,
        _document(),
        filename="target.yaml",
    )
    link = tmp_path / "link.yaml"

    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip(
            "symbolic links are unavailable in this environment"
        )

    with pytest.raises(
        Y3172ConfigurationError,
        match="symbolic link",
    ):
        load_ml_intent(
            link,
            allowed_root=tmp_path,
        )


def test_load_empty_file_fails(
    tmp_path: Path,
) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text(
        "",
        encoding="utf-8",
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="must not be empty",
    ):
        load_ml_intent(
            path,
            allowed_root=tmp_path,
        )


def test_load_invalid_yaml_fails(
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(
        "ml_intent: [",
        encoding="utf-8",
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="invalid YAML",
    ):
        load_ml_intent(
            path,
            allowed_root=tmp_path,
        )


def test_load_non_mapping_document_fails(
    tmp_path: Path,
) -> None:
    path = _write_yaml(
        tmp_path,
        ["not", "a", "mapping"],
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="must be a mapping",
    ):
        load_ml_intent(
            path,
            allowed_root=tmp_path,
        )


def test_load_oversize_file_fails(
    tmp_path: Path,
) -> None:
    path = _write_yaml(
        tmp_path,
        _document(),
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="size limit",
    ):
        load_ml_intent(
            path,
            allowed_root=tmp_path,
            max_bytes=1,
        )


def test_load_rejects_unknown_top_level_field(
    tmp_path: Path,
) -> None:
    document = _document()
    document["unexpected"] = True

    path = _write_yaml(
        tmp_path,
        document,
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="unsupported fields",
    ):
        load_ml_intent(
            path,
            allowed_root=tmp_path,
        )


def test_load_rejects_unknown_governance_field(
    tmp_path: Path,
) -> None:
    document = _document()

    document["ml_intent"]["governance"][
        "model_may_authorize"
    ] = True

    path = _write_yaml(
        tmp_path,
        document,
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="unsupported fields",
    ):
        load_ml_intent(
            path,
            allowed_root=tmp_path,
        )


def test_load_rejects_string_boolean(
    tmp_path: Path,
) -> None:
    document = _document()

    document["ml_intent"]["governance"][
        "audit_required"
    ] = "true"

    path = _write_yaml(
        tmp_path,
        document,
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="strict Boolean",
    ):
        load_ml_intent(
            path,
            allowed_root=tmp_path,
        )


def test_load_rejects_conformance_claim(
    tmp_path: Path,
) -> None:
    document = _document()

    document["ml_intent"][
        "standard_reference"
    ]["conformance_claimed"] = True

    path = _write_yaml(
        tmp_path,
        document,
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="conformance",
    ):
        load_ml_intent(
            path,
            allowed_root=tmp_path,
        )


def test_load_rejects_runtime_authorization_as_allowed(
    tmp_path: Path,
) -> None:
    document = _document()

    document["ml_intent"][
        "allowed_model_roles"
    ].append(
        "runtime_authorization"
    )

    path = _write_yaml(
        tmp_path,
        document,
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="both allowed and prohibited",
    ):
        load_ml_intent(
            path,
            allowed_root=tmp_path,
        )


def test_load_repository_ml_intent() -> None:
    path = Path(
        "config/ml_intent.yaml"
    )

    assert path.is_file()

    intent = load_ml_intent(
        path,
        allowed_root=Path.cwd(),
    )

    assert intent.schema_version == (
        ML_INTENT_SCHEMA_VERSION
    )
    assert intent.intent_id == (
        "AMBA-GOV-ML-INTENT-V1"
    )
    assert intent.required_nodes == (
        Y3172_NODE_ORDER
    )
    assert (
        set(intent.allowed_model_roles)
        == REQUIRED_ALLOWED_MODEL_ROLES
    )
    assert (
        set(intent.prohibited_model_roles)
        == REQUIRED_PROHIBITED_MODEL_ROLES
    )
    assert (
        intent.standard_reference
        .conformance_claimed
        is False
    )
    assert (
        intent.governance
        .deterministic_policy_node_required
        is True
    )
    assert (
        intent.governance
        .human_approval_required_when_configured
        is True
    )
    assert (
        intent.governance
        .typed_execution_required
        is True
    )
    assert (
        intent.governance
        .registered_destination_required
        is True
    )
    assert (
        intent.governance.audit_required
        is True
    )
    assert (
        intent.governance
        .readiness_runtime_separation_required
        is True
    )
    assert (
        intent.synthetic_scope.required
        is True
    )
    assert (
        intent.synthetic_scope.legal_effect
        is False
    )


def test_repository_intent_denies_fabricated_citations() -> None:
    intent = load_ml_intent(
        Path("config/ml_intent.yaml"),
        allowed_root=Path.cwd(),
    )

    assert intent.prohibits_model_role(
        "citation_fabrication"
    )


def test_repository_intent_denies_fabricated_acknowledgments() -> None:
    intent = load_ml_intent(
        Path("config/ml_intent.yaml"),
        allowed_root=Path.cwd(),
    )

    assert intent.prohibits_model_role(
        "distribution_acknowledgment_fabrication"
    )


def test_repository_intent_denies_unknown_roles() -> None:
    intent = load_ml_intent(
        Path("config/ml_intent.yaml"),
        allowed_root=Path.cwd(),
    )

    assert intent.prohibits_model_role(
        "unregistered_future_capability"
    )