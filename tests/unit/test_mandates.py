from __future__ import annotations

from pathlib import Path
import threading

import pytest
import yaml

from amba_ai.governance.mandates import (
    MANDATE_SCHEMA_VERSION,
    MandateDefinition,
    MandateRegistry,
)
from amba_ai.governance.models import (
    GovernanceConfigurationError,
    to_canonical_json,
)


ACTIVE_FROM = "2026-01-01T00:00:00Z"
EXPIRES_AT = "2027-01-01T00:00:00Z"
NOW_ACTIVE = "2026-06-01T12:00:00Z"


def make_mandate(
    *,
    mandate_id: str = "MANDATE-01",
    principal_id: str = "PRINCIPAL-01",
    role: str = "school_administrator",
    permitted_operations: tuple[str, ...] = (
        "commercial_purchase_request",
        "classroom_instruction_delivery",
    ),
    permitted_decisions: tuple[str, ...] = (
        "approve_review_queue",
        "deny_commercial_purchase",
    ),
    synthetic: bool = True,
    legal_effect: bool = False,
    active_from: str = ACTIVE_FROM,
    expires_at: str = EXPIRES_AT,
    revoked_at: str | None = None,
) -> MandateDefinition:
    return MandateDefinition(
        mandate_id=mandate_id,
        principal_id=principal_id,
        role=role,
        permitted_operations=permitted_operations,
        permitted_decisions=permitted_decisions,
        synthetic=synthetic,
        legal_effect=legal_effect,
        active_from=active_from,
        expires_at=expires_at,
        revoked_at=revoked_at,
    )


def valid_yaml_document() -> dict[str, object]:
    return {
        "schema_version": MANDATE_SCHEMA_VERSION,
        "mandates": {
            "MANDATE-01": {
                "principal_id": "PRINCIPAL-01",
                "role": "school_administrator",
                "permitted_operations": [
                    "commercial_purchase_request",
                    "classroom_instruction_delivery",
                ],
                "permitted_decisions": [
                    "approve_review_queue",
                    "deny_commercial_purchase",
                ],
                "synthetic": True,
                "legal_effect": False,
                "active_from": ACTIVE_FROM,
                "expires_at": EXPIRES_AT,
                "revoked_at": None,
            }
        },
    }


def write_yaml(path: Path, data: object) -> Path:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )
    return path


def test_definition_normalizes_fields_and_permission_order() -> None:
    mandate = make_mandate(
        mandate_id="  MANDATE-01  ",
        principal_id="  PRINCIPAL-01  ",
        role="  school_administrator  ",
        permitted_operations=(
            " classroom_instruction_delivery ",
            " commercial_purchase_request ",
        ),
        permitted_decisions=(
            " deny_commercial_purchase ",
            " approve_review_queue ",
        ),
    )

    assert mandate.mandate_id == "MANDATE-01"
    assert mandate.principal_id == "PRINCIPAL-01"
    assert mandate.role == "school_administrator"
    assert mandate.permitted_operations == (
        "classroom_instruction_delivery",
        "commercial_purchase_request",
    )
    assert mandate.permitted_decisions == (
        "approve_review_queue",
        "deny_commercial_purchase",
    )
    assert mandate.active_from == "2026-01-01T00:00:00+00:00"
    assert mandate.expires_at == "2027-01-01T00:00:00+00:00"


@pytest.mark.parametrize(
    "field_name, overrides",
    [
        ("mandate_id", {"mandate_id": " "}),
        ("principal_id", {"principal_id": " "}),
        ("role", {"role": " "}),
    ],
)
def test_definition_rejects_empty_identifiers(
    field_name: str,
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        make_mandate(**overrides)


@pytest.mark.parametrize(
    "field_name, overrides",
    [
        ("synthetic", {"synthetic": 1}),
        ("legal_effect", {"legal_effect": 0}),
    ],
)
def test_definition_requires_strict_booleans(
    field_name: str,
    overrides: dict[str, object],
) -> None:
    with pytest.raises(TypeError, match=f"{field_name} must be a strict Boolean"):
        make_mandate(**overrides)


def test_definition_rejects_synthetic_legal_effect() -> None:
    with pytest.raises(
        ValueError,
        match="Synthetic mandate cannot claim legal effect",
    ):
        make_mandate(synthetic=True, legal_effect=True)


@pytest.mark.parametrize(
    "field_name, overrides",
    [
        ("permitted_operations", {"permitted_operations": ()}),
        ("permitted_decisions", {"permitted_decisions": ()}),
    ],
)
def test_definition_rejects_empty_permission_sets(
    field_name: str,
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        make_mandate(**overrides)


@pytest.mark.parametrize(
    "field_name, overrides",
    [
        (
            "permitted_operations",
            {"permitted_operations": ("operation-a", "operation-a")},
        ),
        (
            "permitted_decisions",
            {"permitted_decisions": ("decision-a", "decision-a")},
        ),
    ],
)
def test_definition_rejects_duplicate_permissions(
    field_name: str,
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match=f"{field_name} cannot contain duplicates"):
        make_mandate(**overrides)


@pytest.mark.parametrize(
    "field_name, overrides",
    [
        (
            "permitted_operations",
            {"permitted_operations": ["operation-a"]},
        ),
        (
            "permitted_decisions",
            {"permitted_decisions": ["decision-a"]},
        ),
    ],
)
def test_definition_requires_permission_tuples(
    field_name: str,
    overrides: dict[str, object],
) -> None:
    with pytest.raises(TypeError, match=f"{field_name} must be a tuple"):
        make_mandate(**overrides)


@pytest.mark.parametrize(
    "active_from, expires_at, message",
    [
        (
            "2027-01-01T00:00:00Z",
            "2027-01-01T00:00:00Z",
            "expires_at must be later than active_from",
        ),
        (
            "2027-01-02T00:00:00Z",
            "2027-01-01T00:00:00Z",
            "expires_at must be later than active_from",
        ),
    ],
)
def test_definition_rejects_invalid_active_window(
    active_from: str,
    expires_at: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        make_mandate(active_from=active_from, expires_at=expires_at)


@pytest.mark.parametrize(
    "revoked_at, message",
    [
        (
            "2025-12-31T23:59:59Z",
            "revoked_at cannot precede active_from",
        ),
        (
            "2027-01-01T00:00:00Z",
            "revoked_at must precede expires_at",
        ),
        (
            "2035-01-01T00:00:00Z",
            "revoked_at must precede expires_at",
        ),
    ],
)
def test_definition_rejects_invalid_revocation_time(
    revoked_at: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        make_mandate(revoked_at=revoked_at)


def test_definition_allows_immediate_revocation() -> None:
    mandate = make_mandate(revoked_at=ACTIVE_FROM)

    assert mandate.revoked_at == "2026-01-01T00:00:00+00:00"
    assert mandate.is_active(ACTIVE_FROM) is False


@pytest.mark.parametrize(
    "now_iso, expected",
    [
        ("2025-12-31T23:59:59Z", False),
        ("2026-01-01T00:00:00Z", True),
        ("2026-06-01T12:00:00Z", True),
        ("2027-01-01T00:00:00Z", False),
    ],
)
def test_definition_active_window(
    now_iso: str,
    expected: bool,
) -> None:
    assert make_mandate().is_active(now_iso) is expected


def test_definition_revocation_boundary() -> None:
    mandate = make_mandate(revoked_at="2026-06-01T12:00:00Z")

    assert mandate.is_active("2026-06-01T11:59:59Z") is True
    assert mandate.is_active("2026-06-01T12:00:00Z") is False


def test_definition_permission_helpers() -> None:
    mandate = make_mandate()

    assert mandate.permits_operation("commercial_purchase_request") is True
    assert mandate.permits_operation("unknown_operation") is False
    assert mandate.permits_decision("approve_review_queue") is True
    assert mandate.permits_decision("unknown_decision") is False


def test_definition_serialization_is_deterministic() -> None:
    mandate = make_mandate()

    assert mandate.to_dict() == {
        "mandate_id": "MANDATE-01",
        "principal_id": "PRINCIPAL-01",
        "role": "school_administrator",
        "permitted_operations": [
            "classroom_instruction_delivery",
            "commercial_purchase_request",
        ],
        "permitted_decisions": [
            "approve_review_queue",
            "deny_commercial_purchase",
        ],
        "synthetic": True,
        "legal_effect": False,
        "active_from": "2026-01-01T00:00:00+00:00",
        "expires_at": "2027-01-01T00:00:00+00:00",
        "revoked_at": None,
    }
    assert mandate.to_canonical_json() == to_canonical_json(mandate.to_dict())


def test_registry_registration_lookup_and_ordering() -> None:
    registry = MandateRegistry()
    second = make_mandate(mandate_id="MANDATE-02")
    first = make_mandate(mandate_id="MANDATE-01")

    registry.register(second)
    registry.register(first)
    registry.register(first)

    assert len(registry) == 2
    assert registry.get("MANDATE-01") == first
    assert registry.require("MANDATE-02") == second
    assert registry.list_all() == (first, second)


def test_registry_rejects_invalid_registration_type() -> None:
    registry = MandateRegistry()

    with pytest.raises(TypeError, match="mandate must be a MandateDefinition"):
        registry.register(object())


def test_registry_rejects_conflicting_content() -> None:
    registry = MandateRegistry()
    registry.register(make_mandate())

    with pytest.raises(
        GovernanceConfigurationError,
        match="same identifier has conflicting content",
    ):
        registry.register(
            make_mandate(role="different_role")
        )


def test_registry_require_rejects_missing_mandate() -> None:
    registry = MandateRegistry()

    with pytest.raises(
        GovernanceConfigurationError,
        match="Required mandate is not registered",
    ):
        registry.require("MISSING")


@pytest.mark.parametrize(
    "method_name",
    ["get", "require", "is_active"],
)
def test_registry_rejects_empty_mandate_identifiers(
    method_name: str,
) -> None:
    registry = MandateRegistry()
    method = getattr(registry, method_name)

    with pytest.raises(ValueError, match="mandate_id must not be empty"):
        if method_name == "is_active":
            method(" ", NOW_ACTIVE)
        else:
            method(" ")


def test_registry_lists_for_principal() -> None:
    registry = MandateRegistry()
    principal_one_first = make_mandate(mandate_id="MANDATE-02")
    principal_one_second = make_mandate(mandate_id="MANDATE-01")
    principal_two = make_mandate(
        mandate_id="MANDATE-03",
        principal_id="PRINCIPAL-02",
    )

    for mandate in (
        principal_one_first,
        principal_one_second,
        principal_two,
    ):
        registry.register(mandate)

    assert registry.list_for_principal("PRINCIPAL-01") == (
        principal_one_second,
        principal_one_first,
    )
    assert registry.list_for_principal("PRINCIPAL-02") == (
        principal_two,
    )


def test_registry_authorizes_complete_match() -> None:
    registry = MandateRegistry()
    registry.register(make_mandate())

    assert registry.authorize(
        mandate_id="MANDATE-01",
        principal_id="PRINCIPAL-01",
        role="school_administrator",
        operation_id="commercial_purchase_request",
        decision="approve_review_queue",
        now_iso=NOW_ACTIVE,
    ) is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"mandate_id": "MISSING"},
        {"principal_id": "PRINCIPAL-OTHER"},
        {"role": "wrong_role"},
        {"operation_id": "unknown_operation"},
        {"decision": "unknown_decision"},
        {"now_iso": "2027-01-01T00:00:00Z"},
    ],
)
def test_registry_authorization_fails_closed(
    overrides: dict[str, str],
) -> None:
    registry = MandateRegistry()
    registry.register(make_mandate())
    arguments = {
        "mandate_id": "MANDATE-01",
        "principal_id": "PRINCIPAL-01",
        "role": "school_administrator",
        "operation_id": "commercial_purchase_request",
        "decision": "approve_review_queue",
        "now_iso": NOW_ACTIVE,
    }
    arguments.update(overrides)

    assert registry.authorize(**arguments) is False


def test_registry_concurrent_identical_registration() -> None:
    registry = MandateRegistry()
    mandate = make_mandate()
    failures: list[Exception] = []

    def register() -> None:
        try:
            registry.register(mandate)
        except Exception as error:
            failures.append(error)

    threads = [threading.Thread(target=register) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert len(registry) == 1
    assert registry.require("MANDATE-01") == mandate


def test_load_from_yaml_success(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path / "mandates.yaml",
        valid_yaml_document(),
    )

    registry = MandateRegistry.load_from_yaml(path)

    assert len(registry) == 1
    mandate = registry.require("MANDATE-01")
    assert mandate.principal_id == "PRINCIPAL-01"
    assert mandate.permitted_operations == (
        "classroom_instruction_delivery",
        "commercial_purchase_request",
    )


def test_load_from_yaml_missing_file(tmp_path: Path) -> None:
    with pytest.raises(
        GovernanceConfigurationError,
        match="Mandate configuration file does not exist",
    ):
        MandateRegistry.load_from_yaml(tmp_path / "missing.yaml")


def test_load_from_yaml_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("   ", encoding="utf-8")

    with pytest.raises(
        GovernanceConfigurationError,
        match="Mandate configuration file is empty",
    ):
        MandateRegistry.load_from_yaml(path)


def test_load_from_yaml_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("mandates: [", encoding="utf-8")

    with pytest.raises(
        GovernanceConfigurationError,
        match="Mandate configuration could not be loaded",
    ):
        MandateRegistry.load_from_yaml(path)


@pytest.mark.parametrize(
    "document, message",
    [
        ([], "root must be a mapping"),
        (
            {"schema_version": MANDATE_SCHEMA_VERSION},
            "requires a mandates mapping",
        ),
        (
            {
                "schema_version": MANDATE_SCHEMA_VERSION,
                "mandates": {},
            },
            "must define at least one mandate",
        ),
        (
            {
                "schema_version": "9.9.9",
                "mandates": {"MANDATE-01": {}},
            },
            "schema version is unsupported",
        ),
        (
            {
                "schema_version": MANDATE_SCHEMA_VERSION,
                "mandates": {"MANDATE-01": {}},
                "unexpected": True,
            },
            "unknown root fields: unexpected",
        ),
    ],
)
def test_load_from_yaml_rejects_invalid_root_configuration(
    tmp_path: Path,
    document: object,
    message: str,
) -> None:
    path = write_yaml(tmp_path / "invalid-root.yaml", document)

    with pytest.raises(GovernanceConfigurationError, match=message):
        MandateRegistry.load_from_yaml(path)


def test_load_from_yaml_reports_missing_fields(tmp_path: Path) -> None:
    document = valid_yaml_document()
    mandate = document["mandates"]["MANDATE-01"]
    del mandate["role"]
    del mandate["expires_at"]
    path = write_yaml(tmp_path / "missing-fields.yaml", document)

    with pytest.raises(
        GovernanceConfigurationError,
        match="missing required fields: expires_at, role",
    ):
        MandateRegistry.load_from_yaml(path)


def test_load_from_yaml_reports_unknown_fields(tmp_path: Path) -> None:
    document = valid_yaml_document()
    document["mandates"]["MANDATE-01"]["unexpected"] = True
    path = write_yaml(tmp_path / "unknown-fields.yaml", document)

    with pytest.raises(
        GovernanceConfigurationError,
        match="unknown fields: unexpected",
    ):
        MandateRegistry.load_from_yaml(path)


@pytest.mark.parametrize(
    "field_name, value, message",
    [
        ("synthetic", "true", "synthetic must be a YAML Boolean"),
        ("legal_effect", 0, "legal_effect must be a YAML Boolean"),
        (
            "permitted_operations",
            "commercial_purchase_request",
            "permitted_operations must be a list",
        ),
        (
            "permitted_decisions",
            "approve_review_queue",
            "permitted_decisions must be a list",
        ),
        (
            "permitted_operations",
            ["operation", 1],
            "permitted_operations values must be strings",
        ),
        (
            "permitted_decisions",
            ["decision", False],
            "permitted_decisions values must be strings",
        ),
    ],
)
def test_load_from_yaml_rejects_invalid_field_types(
    tmp_path: Path,
    field_name: str,
    value: object,
    message: str,
) -> None:
    document = valid_yaml_document()
    document["mandates"]["MANDATE-01"][field_name] = value
    path = write_yaml(tmp_path / f"invalid-{field_name}.yaml", document)

    with pytest.raises(GovernanceConfigurationError, match=message):
        MandateRegistry.load_from_yaml(path)


def test_load_from_yaml_rejects_nonmapping_definition(
    tmp_path: Path,
) -> None:
    document = {
        "schema_version": MANDATE_SCHEMA_VERSION,
        "mandates": {"MANDATE-01": []},
    }
    path = write_yaml(tmp_path / "nonmapping.yaml", document)

    with pytest.raises(
        GovernanceConfigurationError,
        match="Mandate definition must be a mapping",
    ):
        MandateRegistry.load_from_yaml(path)


def test_load_from_yaml_rejects_nonstring_mandate_id(
    tmp_path: Path,
) -> None:
    document = valid_yaml_document()
    definition = document["mandates"].pop("MANDATE-01")
    document["mandates"][1] = definition
    path = write_yaml(tmp_path / "nonstring-id.yaml", document)

    with pytest.raises(
        GovernanceConfigurationError,
        match="Mandate identifiers must be strings",
    ):
        MandateRegistry.load_from_yaml(path)


def test_load_from_yaml_rejects_invalid_definition(
    tmp_path: Path,
) -> None:
    document = valid_yaml_document()
    document["mandates"]["MANDATE-01"]["revoked_at"] = EXPIRES_AT
    path = write_yaml(tmp_path / "invalid-definition.yaml", document)

    with pytest.raises(
        GovernanceConfigurationError,
        match="Mandate definition is invalid",
    ):
        MandateRegistry.load_from_yaml(path)
