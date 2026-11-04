from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from amba_ai.governance.models import (
    FailureBehavior,
    InvalidOperationConfigurationError,
    OperationProtectionClass,
    UnknownOperationError,
    to_canonical_json,
)
from amba_ai.governance.operation_registry import (
    DESTINATION_SCHEMA_VERSION,
    OPERATION_SCHEMA_VERSION,
    DestinationRegistry,
    DestinationRules,
    DestinationSpecification,
    OperationRegistry,
)


def write_yaml(path: Path, data: object) -> Path:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )
    return path


def valid_destination_document() -> dict[str, Any]:
    return {
        "schema_version": DESTINATION_SCHEMA_VERSION,
        "destination_rules": {
            "unknown_destination": FailureBehavior.CONFIGURATION_FAILURE.value,
            "unregistered_destination": FailureBehavior.BLOCK.value,
            "operation_not_allowed": FailureBehavior.BLOCK.value,
            "empty_destination": FailureBehavior.CONFIGURATION_FAILURE.value,
            "wildcard_operations_allowed": False,
        },
        "destinations": {
            "DEST-B": {
                "destination_class": "review_queue",
                "registered": False,
                "synthetic": True,
                "allowed_operations": ["operation-b"],
            },
            "DEST-A": {
                "destination_class": "delivery",
                "registered": True,
                "synthetic": True,
                "allowed_operations": ["operation-b", "operation-a"],
            },
        },
    }


def valid_operation_document() -> dict[str, Any]:
    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operations": {
            "operation-b": {
                "protection_class": OperationProtectionClass.PROTECTED.value,
                "pre_gate_required": True,
                "post_gate_required": True,
                "authorization_basis_required": False,
                "allowed_authorization_basis_types": [],
                "required_evaluators": ["evaluator-b"],
                "required_policy_records": ["record-b"],
                "approval_required": True,
                "approval_role": "reviewer",
                "failure_behavior": FailureBehavior.BLOCK.value,
            },
            "operation-a": {
                "protection_class": OperationProtectionClass.PROTECTED.value,
                "pre_gate_required": True,
                "post_gate_required": False,
                "authorization_basis_required": False,
                "allowed_authorization_basis_types": [],
                "required_evaluators": ["evaluator-b", "evaluator-a"],
                "required_policy_records": ["record-b", "record-a"],
                "approval_required": False,
                "approval_role": None,
                "failure_behavior": FailureBehavior.BLOCK.value,
            },
        },
    }


def destination_rules(
    *,
    wildcard_operations_allowed: bool = False,
) -> DestinationRules:
    return DestinationRules(
        unknown_destination=FailureBehavior.CONFIGURATION_FAILURE,
        unregistered_destination=FailureBehavior.BLOCK,
        operation_not_allowed=FailureBehavior.BLOCK,
        empty_destination=FailureBehavior.CONFIGURATION_FAILURE,
        wildcard_operations_allowed=wildcard_operations_allowed,
    )


def test_destination_specification_normalizes_and_serializes() -> None:
    specification = DestinationSpecification(
        destination_id=" DEST-A ",
        destination_class=" delivery ",
        registered=True,
        synthetic=True,
        allowed_operations=(" operation-b ", " operation-a "),
    )

    assert specification.destination_id == "DEST-A"
    assert specification.destination_class == "delivery"
    assert specification.allowed_operations == (
        "operation-a",
        "operation-b",
    )
    assert specification.to_dict() == {
        "destination_id": "DEST-A",
        "destination_class": "delivery",
        "registered": True,
        "synthetic": True,
        "allowed_operations": ["operation-a", "operation-b"],
    }
    assert specification.to_canonical_json() == to_canonical_json(
        specification.to_dict()
    )


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"destination_id": " "}, "destination_id must not be empty"),
        ({"destination_class": " "}, "destination_class must not be empty"),
        ({"registered": 1}, "registered must be a strict Boolean"),
        ({"synthetic": 0}, "synthetic must be a strict Boolean"),
        (
            {"allowed_operations": ["operation-a"]},
            "allowed_operations must be a tuple",
        ),
        (
            {"allowed_operations": ("operation-a", "operation-a")},
            "allowed_operations cannot contain duplicates",
        ),
        (
            {"allowed_operations": (" ",)},
            "allowed_operations must not be empty",
        ),
    ],
)
def test_destination_specification_rejects_invalid_values(
    kwargs: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "destination_id": "DEST-A",
        "destination_class": "delivery",
        "registered": True,
        "synthetic": True,
        "allowed_operations": ("operation-a",),
    }
    values.update(kwargs)

    with pytest.raises(InvalidOperationConfigurationError, match=message):
        DestinationSpecification(**values)  # type: ignore[arg-type]


def test_destination_rules_validate_and_serialize() -> None:
    rules = destination_rules()

    assert rules.to_dict() == {
        "unknown_destination": FailureBehavior.CONFIGURATION_FAILURE.value,
        "unregistered_destination": FailureBehavior.BLOCK.value,
        "operation_not_allowed": FailureBehavior.BLOCK.value,
        "empty_destination": FailureBehavior.CONFIGURATION_FAILURE.value,
        "wildcard_operations_allowed": False,
    }


@pytest.mark.parametrize(
    "field_name, value, message",
    [
        (
            "unknown_destination",
            "block",
            "unknown_destination must be a FailureBehavior",
        ),
        (
            "wildcard_operations_allowed",
            1,
            "wildcard_operations_allowed must be a strict Boolean",
        ),
    ],
)
def test_destination_rules_reject_invalid_values(
    field_name: str,
    value: object,
    message: str,
) -> None:
    values: dict[str, object] = {
        "unknown_destination": FailureBehavior.CONFIGURATION_FAILURE,
        "unregistered_destination": FailureBehavior.BLOCK,
        "operation_not_allowed": FailureBehavior.BLOCK,
        "empty_destination": FailureBehavior.CONFIGURATION_FAILURE,
        "wildcard_operations_allowed": False,
    }
    values[field_name] = value

    with pytest.raises(InvalidOperationConfigurationError, match=message):
        DestinationRules(**values)  # type: ignore[arg-type]


def test_destination_registry_lookup_membership_and_ordering() -> None:
    first = DestinationSpecification(
        "DEST-A", "delivery", True, True, ("operation-a",)
    )
    second = DestinationSpecification(
        "DEST-B", "review", False, True, ("operation-b",)
    )
    registry = DestinationRegistry(
        {"DEST-B": second, "DEST-A": first},
        destination_rules(),
    )

    assert len(registry) == 2
    assert tuple(registry) == (first, second)
    assert registry.list_destinations() == (first, second)
    assert "DEST-A" in registry
    assert " DEST-A " in registry
    assert 1 not in registry
    assert registry.get(" DEST-A ") == first
    assert registry.require("DEST-A") == first
    assert registry.is_registered("DEST-A") is True
    assert registry.is_registered("DEST-B") is False
    assert registry.is_allowed_for_operation("DEST-A", "operation-a") is True
    assert registry.is_allowed_for_operation("DEST-A", "operation-b") is False
    assert registry.is_allowed_for_operation("DEST-B", "operation-b") is False


def test_destination_registry_wildcard_behavior() -> None:
    specification = DestinationSpecification(
        "DEST-WILD", "delivery", True, True, ("*",)
    )
    registry = DestinationRegistry(
        {"DEST-WILD": specification},
        destination_rules(wildcard_operations_allowed=True),
    )

    assert registry.is_allowed_for_operation("DEST-WILD", "anything") is True


def test_destination_registry_rejects_invalid_constructor_values() -> None:
    specification = DestinationSpecification(
        "DEST-A", "delivery", True, True, ("operation-a",)
    )

    with pytest.raises(TypeError, match="destinations must be a mapping"):
        DestinationRegistry([], destination_rules())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="destination_rules must be DestinationRules"):
        DestinationRegistry({"DEST-A": specification}, object())  # type: ignore[arg-type]

    with pytest.raises(
        InvalidOperationConfigurationError,
        match="must contain at least one destination",
    ):
        DestinationRegistry({}, destination_rules())

    with pytest.raises(
        InvalidOperationConfigurationError,
        match="mapping key does not match",
    ):
        DestinationRegistry({"DIFFERENT": specification}, destination_rules())

    with pytest.raises(
        TypeError,
        match="destination values must be DestinationSpecification",
    ):
        DestinationRegistry({"DEST-A": object()}, destination_rules())  # type: ignore[arg-type]


def test_destination_registry_require_rejects_missing() -> None:
    registry = DestinationRegistry(
        {
            "DEST-A": DestinationSpecification(
                "DEST-A", "delivery", True, True, ()
            )
        },
        destination_rules(),
    )

    with pytest.raises(
        InvalidOperationConfigurationError,
        match="Required destination is not registered",
    ):
        registry.require("MISSING")


def test_load_destination_yaml_success(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path / "destinations.yaml",
        valid_destination_document(),
    )

    registry = DestinationRegistry.load_from_yaml(path)

    assert len(registry) == 2
    assert registry.list_destinations()[0].destination_id == "DEST-A"
    assert registry.get("DEST-A").allowed_operations == (
        "operation-a",
        "operation-b",
    )
    assert registry.rules.wildcard_operations_allowed is False


def test_load_operation_yaml_success(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path / "operations.yaml",
        valid_operation_document(),
    )

    registry = OperationRegistry.load_from_yaml(path)

    assert len(registry) == 2
    assert tuple(operation.operation_id for operation in registry) == (
        "operation-a",
        "operation-b",
    )
    first = registry.require("operation-a")
    assert first.required_evaluator_ids == ("evaluator-a", "evaluator-b")
    assert first.required_policy_record_ids == ("record-a", "record-b")
    assert first.approval_required is False
    assert first.approval_role is None


@pytest.mark.parametrize(
    "registry_class, name",
    [
        (DestinationRegistry, "Destination"),
        (OperationRegistry, "Operation"),
    ],
)
def test_yaml_loader_rejects_missing_empty_and_invalid_files(
    tmp_path: Path,
    registry_class: type,
    name: str,
) -> None:
    with pytest.raises(
        InvalidOperationConfigurationError,
        match=f"{name} configuration file does not exist",
    ):
        registry_class.load_from_yaml(tmp_path / "missing.yaml")

    empty = tmp_path / f"empty-{name}.yaml"
    empty.write_text("   ", encoding="utf-8")
    with pytest.raises(
        InvalidOperationConfigurationError,
        match=f"{name} configuration file is empty",
    ):
        registry_class.load_from_yaml(empty)

    invalid = tmp_path / f"invalid-{name}.yaml"
    invalid.write_text("root: [", encoding="utf-8")
    with pytest.raises(
        InvalidOperationConfigurationError,
        match=f"{name} configuration could not be parsed",
    ):
        registry_class.load_from_yaml(invalid)


def test_destination_yaml_rejects_schema_and_field_errors(tmp_path: Path) -> None:
    document = valid_destination_document()
    document["schema_version"] = "9.9.9"
    path = write_yaml(tmp_path / "bad-version.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="schema version is unsupported",
    ):
        DestinationRegistry.load_from_yaml(path)

    document = valid_destination_document()
    document["unknown"] = True
    path = write_yaml(tmp_path / "unknown-root.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="unknown fields: unknown",
    ):
        DestinationRegistry.load_from_yaml(path)

    document = valid_destination_document()
    del document["destination_rules"]["empty_destination"]
    path = write_yaml(tmp_path / "missing-rule.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="missing required fields: empty_destination",
    ):
        DestinationRegistry.load_from_yaml(path)

    document = valid_destination_document()
    document["destinations"]["DEST-A"]["unexpected"] = True
    path = write_yaml(tmp_path / "unknown-destination-field.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="unknown fields: unexpected",
    ):
        DestinationRegistry.load_from_yaml(path)


def test_destination_yaml_rejects_invalid_rules_and_specs(tmp_path: Path) -> None:
    document = valid_destination_document()
    document["destination_rules"]["wildcard_operations_allowed"] = "false"
    path = write_yaml(tmp_path / "bad-wildcard-boolean.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="must be a YAML Boolean",
    ):
        DestinationRegistry.load_from_yaml(path)

    document = valid_destination_document()
    document["destination_rules"]["unknown_destination"] = "invalid"
    path = write_yaml(tmp_path / "bad-failure-behavior.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="invalid failure behavior",
    ):
        DestinationRegistry.load_from_yaml(path)

    document = valid_destination_document()
    document["destinations"]["DEST-A"]["allowed_operations"] = [
        "operation-a",
        "operation-a",
    ]
    path = write_yaml(tmp_path / "duplicate-operations.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="allowed_operations cannot contain duplicates",
    ):
        DestinationRegistry.load_from_yaml(path)

    document = valid_destination_document()
    document["destinations"]["DEST-A"]["allowed_operations"] = [1]
    path = write_yaml(tmp_path / "nonstring-operation.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="allowed_operations values must be strings",
    ):
        DestinationRegistry.load_from_yaml(path)


def test_destination_yaml_rejects_prohibited_wildcard(tmp_path: Path) -> None:
    document = valid_destination_document()
    document["destinations"]["DEST-A"]["allowed_operations"] = ["*"]
    path = write_yaml(tmp_path / "prohibited-wildcard.yaml", document)

    with pytest.raises(
        InvalidOperationConfigurationError,
        match="uses a prohibited wildcard operation",
    ):
        DestinationRegistry.load_from_yaml(path)


def test_operation_registry_lookup_membership_and_ordering(tmp_path: Path) -> None:
    registry = OperationRegistry.load_from_yaml(
        write_yaml(tmp_path / "operations.yaml", valid_operation_document())
    )

    first = registry.require("operation-a")
    second = registry.require("operation-b")

    assert len(registry) == 2
    assert registry.get(" operation-a ") == first
    assert registry.resolve("operation-a") == first
    assert registry.contains("operation-a") is True
    assert "operation-a" in registry
    assert 1 not in registry
    assert registry.list_operations() == (first, second)

    with pytest.raises(
        UnknownOperationError,
        match="Operation 'missing' is not registered",
    ):
        registry.require("missing")


def test_operation_registry_constructor_validation(tmp_path: Path) -> None:
    loaded = OperationRegistry.load_from_yaml(
        write_yaml(tmp_path / "operations.yaml", valid_operation_document())
    )
    operation = loaded.require("operation-a")

    with pytest.raises(TypeError, match="operations must be a mapping"):
        OperationRegistry([])  # type: ignore[arg-type]

    with pytest.raises(
        InvalidOperationConfigurationError,
        match="must contain at least one operation",
    ):
        OperationRegistry({})

    with pytest.raises(
        TypeError,
        match="operation values must be ResolvedOperation",
    ):
        OperationRegistry({"operation-a": object()})  # type: ignore[arg-type]

    with pytest.raises(
        InvalidOperationConfigurationError,
        match="mapping key does not match",
    ):
        OperationRegistry({"different": operation})


def test_operation_yaml_rejects_schema_and_field_errors(tmp_path: Path) -> None:
    document = valid_operation_document()
    document["schema_version"] = "9.9.9"
    path = write_yaml(tmp_path / "bad-version.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="schema version is unsupported",
    ):
        OperationRegistry.load_from_yaml(path)

    document = valid_operation_document()
    document["unexpected"] = True
    path = write_yaml(tmp_path / "unknown-root.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="unknown fields: unexpected",
    ):
        OperationRegistry.load_from_yaml(path)

    document = valid_operation_document()
    del document["operations"]["operation-a"]["failure_behavior"]
    path = write_yaml(tmp_path / "missing-field.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="missing required fields: failure_behavior",
    ):
        OperationRegistry.load_from_yaml(path)

    document = valid_operation_document()
    document["operations"]["operation-a"]["unexpected"] = True
    path = write_yaml(tmp_path / "unknown-field.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="unknown fields: unexpected",
    ):
        OperationRegistry.load_from_yaml(path)


def test_operation_yaml_rejects_invalid_boolean_and_enum(tmp_path: Path) -> None:
    document = valid_operation_document()
    document["operations"]["operation-a"]["pre_gate_required"] = 1
    path = write_yaml(tmp_path / "bad-boolean.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="pre_gate_required must be a YAML Boolean",
    ):
        OperationRegistry.load_from_yaml(path)

    document = valid_operation_document()
    document["operations"]["operation-a"]["protection_class"] = "invalid"
    path = write_yaml(tmp_path / "bad-enum.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="contains an invalid enum value",
    ):
        OperationRegistry.load_from_yaml(path)


def test_operation_yaml_enforces_approval_role_consistency(tmp_path: Path) -> None:
    document = valid_operation_document()
    document["operations"]["operation-b"]["approval_role"] = " "
    path = write_yaml(tmp_path / "missing-approval-role.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="approval_role must not be empty",
    ):
        OperationRegistry.load_from_yaml(path)

    document = valid_operation_document()
    document["operations"]["operation-a"]["approval_role"] = "reviewer"
    path = write_yaml(tmp_path / "unexpected-approval-role.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="approval_role must be null",
    ):
        OperationRegistry.load_from_yaml(path)


def test_operation_yaml_rejects_invalid_dependency_lists(tmp_path: Path) -> None:
    document = valid_operation_document()
    document["operations"]["operation-a"]["required_evaluators"] = "evaluator-a"
    path = write_yaml(tmp_path / "not-list.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="required_evaluators must be a list",
    ):
        OperationRegistry.load_from_yaml(path)

    document = valid_operation_document()
    document["operations"]["operation-a"]["required_evaluators"] = [1]
    path = write_yaml(tmp_path / "nonstring.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="required_evaluators values must be strings",
    ):
        OperationRegistry.load_from_yaml(path)

    document = valid_operation_document()
    document["operations"]["operation-a"]["required_evaluators"] = [
        "evaluator-a",
        "evaluator-a",
    ]
    path = write_yaml(tmp_path / "duplicates.yaml", document)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="required_evaluators cannot contain duplicates",
    ):
        OperationRegistry.load_from_yaml(path)


def test_operation_yaml_requires_authorization_type_when_required(
    tmp_path: Path,
) -> None:
    document = valid_operation_document()
    document["operations"]["operation-a"]["authorization_basis_required"] = True
    document["operations"]["operation-a"]["allowed_authorization_basis_types"] = []
    path = write_yaml(tmp_path / "missing-auth-type.yaml", document)

    with pytest.raises(
        InvalidOperationConfigurationError,
        match="requires at least one authorization basis type",
    ):
        OperationRegistry.load_from_yaml(path)


def test_normalized_identifier_collisions_are_rejected(tmp_path: Path) -> None:
    destinations = valid_destination_document()
    destinations["destinations"][" DEST-A "] = destinations["destinations"][
        "DEST-A"
    ].copy()
    path = write_yaml(tmp_path / "destination-collision.yaml", destinations)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="Destination identifiers conflict after normalization",
    ):
        DestinationRegistry.load_from_yaml(path)

    operations = valid_operation_document()
    operations["operations"][" operation-a "] = operations["operations"][
        "operation-a"
    ].copy()
    path = write_yaml(tmp_path / "operation-collision.yaml", operations)
    with pytest.raises(
        InvalidOperationConfigurationError,
        match="Operation identifiers conflict after normalization",
    ):
        OperationRegistry.load_from_yaml(path)
