from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from amba_ai.standards.y3172_models import (
    AMBA_GOV_Y3172_INTERPRETATION_ID,
    Y3172ConfigurationError,
    Y3172Node,
    Y3172_NODE_ORDER,
)
from amba_ai.standards.y3172_registry import (
    EXPECTED_RECOMMENDATION,
    Y3172CodeReference,
    Y3172ImplementationStatus,
    Y3172MappingIdentity,
    Y3172MappingType,
    Y3172NodeDefinition,
    Y3172ProjectExtension,
    Y3172ReferenceVerificationStatus,
    Y3172Registry,
)


def _identity(
    **overrides,
) -> Y3172MappingIdentity:
    values = {
        "recommendation": EXPECTED_RECOMMENDATION,
        "edition": "1.0",
        "approval_date": "2019-06-22",
        "persistent_uri": (
            "https://handle.itu.int/11.1002/1000/13894"
        ),
    }
    values.update(overrides)
    return Y3172MappingIdentity(**values)


def _definition(
    node: Y3172Node,
    *,
    status: Y3172ImplementationStatus = (
        Y3172ImplementationStatus.IMPLEMENTED_UNVERIFIED
    ),
) -> Y3172NodeDefinition:
    return Y3172NodeDefinition(
        node=node,
        official_locator="Clause 8.1",
        official_function=f"Official role for {node.value}",
        amba_component=f"Amba component for {node.value}",
        mapping_type=Y3172MappingType.INTERPRETED,
        implementation_status=status,
        code_references=(
            Y3172CodeReference(
                reference=(
                    f"amba_ai.example.{node.value.lower()}"
                ),
            ),
        ),
        limitations=(
            "Application-level interpreted mapping.",
        ),
    )


def _definitions() -> tuple[Y3172NodeDefinition, ...]:
    return tuple(
        _definition(node)
        for node in Y3172_NODE_ORDER
    )


def _registry(
    **overrides,
) -> Y3172Registry:
    values = {
        "schema_version": "1.0.0",
        "identity": _identity(),
        "definitions": _definitions(),
        "extensions": (),
    }
    values.update(overrides)
    return Y3172Registry(**values)


def _node_document(
    node: Y3172Node,
) -> dict:
    return {
        "node_id": node.value,
        "official_locator": "Clause 8.1",
        "official_function": (
            f"Official function for {node.value}"
        ),
        "amba_component": (
            f"Amba component for {node.value}"
        ),
        "mapping_type": "interpreted",
        "implementation_status": (
            "implemented_unverified"
        ),
        "code_references": [
            {
                "reference": (
                    f"amba_ai.example.{node.value.lower()}"
                ),
                "verification_status": "declared",
                "evidence_ids": [],
            }
        ],
        "limitations": [
            "Application-level interpreted mapping."
        ],
    }


def _document() -> dict:
    return {
        "schema_version": "1.0.0",
        "standard": {
            "recommendation": EXPECTED_RECOMMENDATION,
            "edition": "1.0",
            "approval_date": "2019-06-22",
            "persistent_uri": (
                "https://handle.itu.int/11.1002/1000/13894"
            ),
            "interpretation_id": (
                AMBA_GOV_Y3172_INTERPRETATION_ID
            ),
            "mapping_type": (
                "application_level_interpreted"
            ),
            "formal_conformance_claimed": False,
            "certification_claimed": False,
            "legal_authority_created": False,
        },
        "pipeline": [
            _node_document(node)
            for node in Y3172_NODE_ORDER
        ],
        "extensions": [
            {
                "extension_id": (
                    "deterministic_policy_gate"
                ),
                "name": (
                    "Deterministic policy gate"
                ),
                "rationale": (
                    "Separates model analysis from "
                    "runtime authorization."
                ),
                "classification": (
                    "amba_gov_extension"
                ),
                "evidence_ids": [],
            }
        ],
        "metadata": {
            "scope": "hackathon_sandbox",
        },
    }


def _write_yaml(
    tmp_path: Path,
    document: object,
    *,
    filename: str = "y3172_mapping.yaml",
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


def test_registry_requires_canonical_node_order() -> None:
    definitions = list(_definitions())
    definitions[0], definitions[1] = (
        definitions[1],
        definitions[0],
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="canonical order",
    ):
        _registry(
            definitions=tuple(definitions),
        )


def test_registry_require_returns_registered_node() -> None:
    registry = _registry()

    definition = registry.require(
        Y3172Node.P
    )

    assert definition.node is Y3172Node.P
    assert (
        definition.mapping_type
        is Y3172MappingType.INTERPRETED
    )


def test_registry_require_rejects_wrong_type() -> None:
    registry = _registry()

    with pytest.raises(TypeError):
        registry.require("P")  # type: ignore[arg-type]


def test_mapping_identity_rejects_wrong_recommendation() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="recommendation must be",
    ):
        _identity(
            recommendation="ITU-T Y.3117",
        )


def test_mapping_identity_rejects_formal_conformance() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="formal_conformance_claimed",
    ):
        _identity(
            formal_conformance_claimed=True,
        )


def test_mapping_identity_rejects_certification() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="certification_claimed",
    ):
        _identity(
            certification_claimed=True,
        )


def test_mapping_identity_requires_strict_boolean() -> None:
    with pytest.raises(TypeError):
        _identity(
            certification_claimed=0,
        )


def test_mapping_identity_rejects_legal_authority() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="legal_authority_created",
    ):
        _identity(
            legal_authority_created=True,
        )


def test_mapping_identity_has_fixed_interpretation() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="interpretation_id",
    ):
        _identity(
            interpretation_id="OTHER-INTERPRETATION",
        )


def test_verified_code_reference_requires_evidence() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="requires evidence_ids",
    ):
        Y3172CodeReference(
            reference="amba_ai.example.Component",
            verification_status=(
                Y3172ReferenceVerificationStatus.VERIFIED
            ),
        )


def test_declared_code_reference_does_not_claim_verification() -> None:
    reference = Y3172CodeReference(
        reference="amba_ai.example.Component",
    )

    assert (
        reference.verification_status
        is Y3172ReferenceVerificationStatus.DECLARED
    )
    assert reference.evidence_ids == ()


def test_node_definition_rejects_duplicate_references() -> None:
    reference = Y3172CodeReference(
        reference="amba_ai.example.Component",
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="must not contain duplicates",
    ):
        Y3172NodeDefinition(
            node=Y3172Node.P,
            official_locator="Clause 8.1",
            official_function="Policy function",
            amba_component="PolicyEngine",
            mapping_type=Y3172MappingType.INTERPRETED,
            implementation_status=(
                Y3172ImplementationStatus.PARTIAL
            ),
            code_references=(
                reference,
                reference,
            ),
        )


def test_node_metadata_is_deeply_immutable() -> None:
    definition = Y3172NodeDefinition(
        node=Y3172Node.P,
        official_locator="Clause 8.1",
        official_function="Policy function",
        amba_component="PolicyEngine",
        mapping_type=Y3172MappingType.INTERPRETED,
        implementation_status=(
            Y3172ImplementationStatus.PARTIAL
        ),
        metadata={
            "nested": {
                "status": "declared",
            },
        },
    )

    with pytest.raises(TypeError):
        definition.metadata["other"] = "value"

    with pytest.raises(TypeError):
        definition.metadata["nested"]["status"] = "changed"


def test_extension_must_be_project_extension() -> None:
    with pytest.raises(
        Y3172ConfigurationError,
        match="classification",
    ):
        Y3172ProjectExtension(
            extension_id="EXT-001",
            name="Extension",
            rationale="Project-specific behavior.",
            classification="standard_requirement",
        )
def test_extension_id_and_name_are_distinct_fields(
    tmp_path: Path,
) -> None:
    document = _document()
    document["extensions"] = [
        {
            "extension_id": "deterministic_policy_gate",
            "name": "Deterministic policy gate",
            "rationale": (
                "Separates model analysis from runtime authorization."
            ),
            "classification": "amba_gov_extension",
            "evidence_ids": [],
        }
    ]

    path = _write_yaml(
        tmp_path,
        document,
    )

    registry = Y3172Registry.load_from_yaml(
        path,
        allowed_root=tmp_path,
    )

    extension = registry.require_extension(
        "deterministic_policy_gate"
    )

    assert extension.extension_id == (
        "deterministic_policy_gate"
    )
    assert extension.name == (
        "Deterministic policy gate"
    )


def test_extension_name_is_legacy_identifier_when_id_absent(
    tmp_path: Path,
) -> None:
    document = _document()
    document["extensions"] = [
        {
            "name": "Multi-Agent Institutional Review",
            "rationale": (
                "Provides project-specific institutional coordination."
            ),
            "classification": "amba_gov_extension",
            "evidence_ids": [],
        }
    ]

    path = _write_yaml(
        tmp_path,
        document,
    )

    registry = Y3172Registry.load_from_yaml(
        path,
        allowed_root=tmp_path,
    )

    extension = registry.require_extension(
        "Multi-Agent Institutional Review"
    )

    assert extension.extension_id == (
        "Multi-Agent Institutional Review"
    )
    assert extension.name == (
        "Multi-Agent Institutional Review"
    )


def test_implemented_unit_verified_is_supported() -> None:
    definition = _definition(
        Y3172Node.C,
        status=(
            Y3172ImplementationStatus
            .IMPLEMENTED_UNIT_VERIFIED
        ),
    )

    assert definition.implementation_status is (
        Y3172ImplementationStatus
        .IMPLEMENTED_UNIT_VERIFIED
    )

def test_registry_rejects_duplicate_extension_ids() -> None:
    extension = Y3172ProjectExtension(
        extension_id="EXT-001",
        name="Extension",
        rationale="Project-specific behavior.",
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="extension IDs",
    ):
        _registry(
            extensions=(
                extension,
                extension,
            ),
        )


def test_load_valid_mapping(
    tmp_path: Path,
) -> None:
    path = _write_yaml(
        tmp_path,
        _document(),
    )

    registry = Y3172Registry.load_from_yaml(
        path,
        allowed_root=tmp_path,
    )

    assert len(registry.list()) == 7
    assert (
        tuple(
            definition.node
            for definition in registry.list()
        )
        == Y3172_NODE_ORDER
    )
    assert registry.identity.recommendation == (
        EXPECTED_RECOMMENDATION
    )
    assert (
        registry.identity.formal_conformance_claimed
        is False
    )
    assert (
        registry.identity.certification_claimed
        is False
    )


def test_load_mapping_outside_allowed_root_fails(
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
        Y3172Registry.load_from_yaml(
            outside,
            allowed_root=allowed_root,
        )


def test_load_symlink_mapping_fails(
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
        Y3172Registry.load_from_yaml(
            link,
            allowed_root=tmp_path,
        )


def test_load_empty_mapping_fails(
    tmp_path: Path,
) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(
        Y3172ConfigurationError,
        match="must not be empty",
    ):
        Y3172Registry.load_from_yaml(
            path,
            allowed_root=tmp_path,
        )


def test_load_non_mapping_yaml_fails(
    tmp_path: Path,
) -> None:
    path = _write_yaml(
        tmp_path,
        ["not", "a", "mapping"],
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="root must be a mapping",
    ):
        Y3172Registry.load_from_yaml(
            path,
            allowed_root=tmp_path,
        )


def test_load_oversize_mapping_fails(
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
        Y3172Registry.load_from_yaml(
            path,
            allowed_root=tmp_path,
            max_bytes=1,
        )


def test_load_rejects_wrong_pipeline_length(
    tmp_path: Path,
) -> None:
    document = _document()
    document["pipeline"] = document["pipeline"][:-1]

    path = _write_yaml(
        tmp_path,
        document,
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="exactly seven",
    ):
        Y3172Registry.load_from_yaml(
            path,
            allowed_root=tmp_path,
        )


def test_load_rejects_wrong_node_order(
    tmp_path: Path,
) -> None:
    document = _document()
    document["pipeline"][0], document["pipeline"][1] = (
        document["pipeline"][1],
        document["pipeline"][0],
    )

    path = _write_yaml(
        tmp_path,
        document,
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="must define SRC",
    ):
        Y3172Registry.load_from_yaml(
            path,
            allowed_root=tmp_path,
        )


def test_load_rejects_unknown_implementation_status(
    tmp_path: Path,
) -> None:
    document = _document()
    document["pipeline"][0][
        "implementation_status"
    ] = "complete"

    path = _write_yaml(
        tmp_path,
        document,
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="implementation_status must be one of",
    ):
        Y3172Registry.load_from_yaml(
            path,
            allowed_root=tmp_path,
        )


def test_load_rejects_conformance_claim(
    tmp_path: Path,
) -> None:
    document = _document()
    document["standard"][
        "formal_conformance_claimed"
    ] = True

    path = _write_yaml(
        tmp_path,
        document,
    )

    with pytest.raises(
        Y3172ConfigurationError,
        match="formal_conformance_claimed",
    ):
        Y3172Registry.load_from_yaml(
            path,
            allowed_root=tmp_path,
        )


def test_load_legacy_verified_reference_is_only_declared(
    tmp_path: Path,
) -> None:
    document = _document()
    document["pipeline"][0].pop(
        "code_references"
    )
    document["pipeline"][0][
        "verified_code_references"
    ] = [
        "amba_ai.example.Source"
    ]

    path = _write_yaml(
        tmp_path,
        document,
    )

    registry = Y3172Registry.load_from_yaml(
        path,
        allowed_root=tmp_path,
    )

    reference = registry.require(
        Y3172Node.SRC
    ).code_references[0]

    assert (
        reference.verification_status
        is Y3172ReferenceVerificationStatus.DECLARED
    )
    assert reference.evidence_ids == ()


def test_verified_references_are_returned_deterministically() -> None:
    evidence_reference = Y3172CodeReference(
        reference="amba_ai.example.Verified",
        verification_status=(
            Y3172ReferenceVerificationStatus.VERIFIED
        ),
        evidence_ids=(
            "TEST-EVIDENCE-001",
        ),
    )

    definitions = list(_definitions())
    p_index = Y3172_NODE_ORDER.index(
        Y3172Node.P
    )

    definitions[p_index] = Y3172NodeDefinition(
        node=Y3172Node.P,
        official_locator="Clause 8.1",
        official_function="Policy function",
        amba_component="PolicyEngine",
        mapping_type=Y3172MappingType.INTERPRETED,
        implementation_status=(
            Y3172ImplementationStatus.VERIFIED_FOR_DEFINED_SCOPE
        ),
        code_references=(
            evidence_reference,
        ),
        limitations=(
            "Application-level mapping.",
        ),
    )

    registry = _registry(
        definitions=tuple(definitions),
    )

    assert registry.verified_code_references() == (
        evidence_reference,
    )


def test_canonical_json_is_deterministic() -> None:
    first = _registry(
        metadata={
            "scope": "hackathon",
            "status": "interpreted",
        },
    )
    second = _registry(
        metadata={
            "status": "interpreted",
            "scope": "hackathon",
        },
    )

    assert (
        first.to_canonical_json()
        == second.to_canonical_json()
    )


def test_registry_serializes_claim_boundary() -> None:
    payload = _registry().to_dict()

    assert (
        payload["standard"][
            "formal_conformance_claimed"
        ]
        is False
    )
    assert (
        payload["standard"][
            "certification_claimed"
        ]
        is False
    )
    assert (
        payload["standard"][
            "legal_authority_created"
        ]
        is False
    )

def test_partially_implemented_unit_verified_is_supported() -> None:
    definition = _definition(
        Y3172Node.PP,
        status=(
            Y3172ImplementationStatus
            .PARTIALLY_IMPLEMENTED_UNIT_VERIFIED
        ),
    )

    assert definition.implementation_status is (
        Y3172ImplementationStatus
        .PARTIALLY_IMPLEMENTED_UNIT_VERIFIED
    )

def test_load_partially_implemented_unit_verified(
    tmp_path: Path,
) -> None:
    document = _document()

    document["pipeline"][2][
        "implementation_status"
    ] = "partially_implemented_unit_verified"

    path = _write_yaml(
        tmp_path,
        document,
    )

    registry = Y3172Registry.load_from_yaml(
        path,
        allowed_root=tmp_path,
    )

    assert (
        registry.require(
            Y3172Node.PP
        ).implementation_status
        is Y3172ImplementationStatus
        .PARTIALLY_IMPLEMENTED_UNIT_VERIFIED
    )

def test_existing_not_operationally_verified_status_is_supported() -> None:
    definition = _definition(
        Y3172Node.M,
        status=(
            Y3172ImplementationStatus
            .EXISTING_NOT_OPERATIONALLY_VERIFIED_IN_THIS_MAPPING
        ),
    )

    assert definition.implementation_status is (
        Y3172ImplementationStatus
        .EXISTING_NOT_OPERATIONALLY_VERIFIED_IN_THIS_MAPPING
    )

def test_load_existing_not_operationally_verified_status(
    tmp_path: Path,
) -> None:
    document = _document()

    document["pipeline"][3][
        "implementation_status"
    ] = (
        "existing_not_operationally_verified_in_this_mapping"
    )

    path = _write_yaml(
        tmp_path,
        document,
    )

    registry = Y3172Registry.load_from_yaml(
        path,
        allowed_root=tmp_path,
    )

    model_definition = registry.require(
        Y3172Node.M
    )

    assert model_definition.implementation_status is (
        Y3172ImplementationStatus
        .EXISTING_NOT_OPERATIONALLY_VERIFIED_IN_THIS_MAPPING
    )
def test_extension_may_omit_rationale() -> None:
    extension = Y3172ProjectExtension(
        extension_id="AMBA-GOV-EXT-LEGAL-APPLICABILITY",
        name="Ethiopian legal applicability",
    )

    assert extension.rationale is None

    assert extension.limitations == (
        "No reviewed extension rationale is recorded "
        "in the mapping.",
    )


def test_extension_without_rationale_preserves_explicit_limitation() -> None:
    extension = Y3172ProjectExtension(
        extension_id="AMBA-GOV-EXT-LEGAL-APPLICABILITY",
        name="Ethiopian legal applicability",
        limitations=(
            "Applicability remains unresolved pending review.",
        ),
    )

    assert extension.rationale is None

    assert extension.limitations == (
        "Applicability remains unresolved pending review.",
    )


def test_load_extension_without_rationale(
    tmp_path: Path,
) -> None:
    document = _document()

    document["extensions"] = [
        {
            "extension_id": (
                "AMBA-GOV-EXT-LEGAL-APPLICABILITY"
            ),
            "name": "Ethiopian legal applicability",
            "classification": "amba_gov_extension",
        }
    ]

    path = _write_yaml(
        tmp_path,
        document,
    )

    registry = Y3172Registry.load_from_yaml(
        path,
        allowed_root=tmp_path,
    )

    extension = registry.require_extension(
        "AMBA-GOV-EXT-LEGAL-APPLICABILITY"
    )

    assert extension.name == (
        "Ethiopian legal applicability"
    )
    assert extension.rationale is None

    assert extension.limitations == (
        "No reviewed extension rationale is recorded "
        "in the mapping.",
    )


def test_extension_serialization_preserves_missing_rationale() -> None:
    extension = Y3172ProjectExtension(
        extension_id="EXT-NO-RATIONALE",
        name="Extension without reviewed rationale",
    )

    payload = extension.to_dict()

    assert payload["rationale"] is None
    assert payload["classification"] == (
        "amba_gov_extension"
    )


def test_load_repository_mapping_file() -> None:
    mapping_path = Path(
        "kb/mappings/y3172_mapping.yaml"
    )

    assert mapping_path.is_file()

    registry = Y3172Registry.load_from_yaml(
        mapping_path,
        allowed_root=Path.cwd(),
    )

    assert len(registry.list()) == 7

    assert (
        tuple(
            definition.node
            for definition in registry.list()
        )
        == Y3172_NODE_ORDER
    )

    assert (
        registry.identity.interpretation_id
        == AMBA_GOV_Y3172_INTERPRETATION_ID
    )

    assert (
        registry.identity.formal_conformance_claimed
        is False
    )

    assert (
        registry.identity.certification_claimed
        is False
    )

    assert (
        registry.identity.legal_authority_created
        is False
    )

    expected_statuses = {
        Y3172Node.SRC: (
            Y3172ImplementationStatus.PLANNED
        ),
        Y3172Node.C: (
            Y3172ImplementationStatus
            .IMPLEMENTED_UNIT_VERIFIED
        ),
        Y3172Node.PP: (
            Y3172ImplementationStatus
            .PARTIALLY_IMPLEMENTED_UNIT_VERIFIED
        ),
        Y3172Node.M: (
            Y3172ImplementationStatus
            .EXISTING_NOT_OPERATIONALLY_VERIFIED_IN_THIS_MAPPING
        ),
        Y3172Node.P: (
            Y3172ImplementationStatus
            .IMPLEMENTED_UNIT_VERIFIED
        ),
        Y3172Node.D: (
            Y3172ImplementationStatus
            .IMPLEMENTED_UNIT_VERIFIED
        ),
        Y3172Node.SINK: (
            Y3172ImplementationStatus
            .PARTIALLY_IMPLEMENTED_UNIT_VERIFIED
        ),
    }

    actual_statuses = {
        definition.node: definition.implementation_status
        for definition in registry.list()
    }
    legal_applicability_extension = (
        registry.require_extension(
            "AMBA-GOV-EXT-LEGAL-APPLICABILITY"
        )
    )

    assert legal_applicability_extension.name == (
        "Ethiopian legal applicability"
    )

    assert (
        legal_applicability_extension.rationale
        is None
    )

    assert (
        legal_applicability_extension.classification
        == "amba_gov_extension"
    )
    assert actual_statuses == expected_statuses
