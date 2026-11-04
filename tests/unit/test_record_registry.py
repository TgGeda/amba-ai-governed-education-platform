from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import threading
from typing import Any

import pytest
import yaml

from amba_ai.governance.models import (
    ActivationStatus,
    ArtifactIntegrityStatus,
    DuplicatePolicyRecordError,
    GovernanceConfigurationError,
    LocatorVerificationStatus,
    PolicyRecord,
    PolicyRecordAmbiguityError,
    PolicyRecordIdentity,
    PolicyRecordNotFoundError,
)
from amba_ai.governance.record_registry import (
    SAFEGUARDS_SCHEMA_VERSION,
    STABLE_RECORD_ID_MAP,
    PolicyRecordRegistry,
)


def valid_safeguards_document(
    *,
    policy_id: str = "AMBA-SAFEGUARDS",
    policy_version: str = "1.0.0",
) -> dict[str, Any]:
    return {
        "schema_version": SAFEGUARDS_SCHEMA_VERSION,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "authority": "Amba governance test authority",
        "scope": "Synthetic education sandbox",
        "binding_level": "project_control",
        "national_binding_status": False,
        "synthetic_only": True,
        "legal_effect": False,
        "controls": {
            "educational_processing": {
                "locator": "controls.educational_processing",
                "rule": "Educational processing must remain within the sandbox.",
            },
            "commercial_purchases": {
                "locator": "controls.commercial_purchases",
                "rule": "Commercial purchases require governance review.",
            },
        },
    }


def write_yaml(path: Path, document: object) -> Path:
    path.write_text(
        yaml.safe_dump(document, sort_keys=False),
        encoding="utf-8",
    )
    return path


def load_registry(
    tmp_path: Path,
    *,
    document: dict[str, Any] | None = None,
    filename: str = "safeguards.yaml",
) -> PolicyRecordRegistry:
    path = write_yaml(
        tmp_path / filename,
        document or valid_safeguards_document(),
    )
    return PolicyRecordRegistry.load_from_safeguards_yaml(path)


def first_record(registry: PolicyRecordRegistry) -> PolicyRecord:
    records = registry.list_all()
    assert records
    return records[0]


def test_load_valid_safeguards_creates_deterministic_records(
    tmp_path: Path,
) -> None:
    document = valid_safeguards_document()
    path = write_yaml(tmp_path / "safeguards.yaml", document)
    raw_bytes = path.read_bytes()

    registry = PolicyRecordRegistry.load_from_safeguards_yaml(path)

    assert len(registry) == 2
    assert tuple(record.identity.record_id for record in registry) == (
        STABLE_RECORD_ID_MAP["commercial_purchases"],
        STABLE_RECORD_ID_MAP["educational_processing"],
    )

    artifact_digest = hashlib.sha256(raw_bytes).hexdigest()
    for record in registry:
        assert record.artifact_sha256 == artifact_digest
        assert record.activation_status == ActivationStatus.ACTIVE
        assert record.eligible_for_project_enforcement is True
        assert record.eligible_for_national_legal_finding is False
        assert record.eligible_for_citation is True
        assert record.synthetic_only is True
        assert record.legal_effect is False


def test_normative_text_is_normalized_and_hashed(tmp_path: Path) -> None:
    document = valid_safeguards_document()
    document["controls"] = {
        "custom_control": {
            "locator": " controls.custom_control ",
            "rule": "  A custom\n  governance   rule.  ",
        }
    }

    registry = load_registry(tmp_path, document=document)
    record = registry.list_all()[0]

    assert record.identity.record_id == "PROJECT-CONTROL-CUSTOM-CONTROL-V1"
    assert record.official_locator == "controls.custom_control"
    assert record.normative_text == "A custom governance rule."
    assert record.normative_unit_sha256 == hashlib.sha256(
        b"A custom governance rule."
    ).hexdigest()


def test_registry_registration_lookup_membership_and_iteration(
    tmp_path: Path,
) -> None:
    source = load_registry(tmp_path)
    records = source.list_all()
    registry = PolicyRecordRegistry()

    for record in reversed(records):
        registry.register(record)
        registry.register(record)

    assert len(registry) == len(records)
    assert tuple(registry) == records
    assert registry.list_all() == records

    for record in records:
        assert record.identity in registry
        assert registry.get(record.identity) == record
        assert registry.require(record.identity) == record

    assert "not-an-identity" not in registry


def test_registry_rejects_invalid_record_type() -> None:
    with pytest.raises(TypeError, match="record must be a PolicyRecord"):
        PolicyRecordRegistry().register(object())  # type: ignore[arg-type]


def test_registry_rejects_invalid_identity_type() -> None:
    registry = PolicyRecordRegistry()

    with pytest.raises(
        TypeError,
        match="identity must be a PolicyRecordIdentity",
    ):
        registry.get("identity")  # type: ignore[arg-type]


def test_registry_rejects_conflicting_record(tmp_path: Path) -> None:
    record = first_record(load_registry(tmp_path))
    conflicting = replace(
        record,
        reviewed_summary="Conflicting summary",
    )
    registry = PolicyRecordRegistry()
    registry.register(record)

    with pytest.raises(
        DuplicatePolicyRecordError,
        match="already registered with conflicting content",
    ):
        registry.register(conflicting)


def test_require_rejects_missing_record(tmp_path: Path) -> None:
    record = first_record(load_registry(tmp_path))
    missing_identity = PolicyRecordIdentity(
        record_id="MISSING-RECORD",
        version_id=record.identity.version_id,
        source_id=record.identity.source_id,
    )

    with pytest.raises(
        PolicyRecordNotFoundError,
        match="is not registered",
    ):
        PolicyRecordRegistry().require(missing_identity)


def test_get_versions_is_sorted_and_validates_record_id(
    tmp_path: Path,
) -> None:
    first = first_record(
        load_registry(
            tmp_path,
            document=valid_safeguards_document(policy_version="2.0.0"),
            filename="v2.yaml",
        )
    )
    second = first_record(
        load_registry(
            tmp_path,
            document=valid_safeguards_document(policy_version="1.0.0"),
            filename="v1.yaml",
        )
    )
    registry = PolicyRecordRegistry()
    registry.register(first)
    registry.register(second)

    versions = registry.get_versions(first.identity.record_id)

    assert versions == tuple(
        sorted((first, second), key=lambda record: str(record.identity))
    )

    with pytest.raises(
        GovernanceConfigurationError,
        match="record_id must not be empty",
    ):
        registry.get_versions(" ")


def test_active_version_lookup_and_require(tmp_path: Path) -> None:
    record = first_record(load_registry(tmp_path))
    registry = PolicyRecordRegistry()
    registry.register(record)

    assert registry.get_active_by_record_id(record.identity.record_id) == record
    assert registry.require_active_by_record_id(record.identity.record_id) == record
    assert registry.get_active_by_record_id("UNKNOWN") is None

    with pytest.raises(
        PolicyRecordNotFoundError,
        match="No active record is registered",
    ):
        registry.require_active_by_record_id("UNKNOWN")


def test_multiple_active_versions_are_ambiguous(tmp_path: Path) -> None:
    first = first_record(
        load_registry(
            tmp_path,
            document=valid_safeguards_document(policy_version="1.0.0"),
            filename="v1.yaml",
        )
    )
    second = first_record(
        load_registry(
            tmp_path,
            document=valid_safeguards_document(policy_version="2.0.0"),
            filename="v2.yaml",
        )
    )
    registry = PolicyRecordRegistry()
    registry.register(first)
    registry.register(second)

    with pytest.raises(
        PolicyRecordAmbiguityError,
        match="has multiple active versions",
    ):
        registry.get_active_by_record_id(first.identity.record_id)


def test_active_and_quarantined_lists(tmp_path: Path) -> None:
    active = first_record(load_registry(tmp_path))
    quarantined = replace(
        active,
        identity=PolicyRecordIdentity(
            record_id="QUARANTINED-RECORD",
            version_id=active.identity.version_id,
            source_id=active.identity.source_id,
        ),
        activation_status=ActivationStatus.QUARANTINED,
        eligible_for_project_enforcement=False,
        eligible_for_national_legal_finding=False,
        eligible_for_citation=False,
    )
    registry = PolicyRecordRegistry()
    registry.register(quarantined)
    registry.register(active)

    assert registry.list_active() == (active,)
    assert registry.list_quarantined() == (quarantined,)


def test_eligibility_checks_fail_closed(tmp_path: Path) -> None:
    record = first_record(load_registry(tmp_path))
    registry = PolicyRecordRegistry()
    registry.register(record)

    assert registry.eligible_for_project_enforcement(record.identity) is True
    assert registry.eligible_for_national_legal_finding(record.identity) is False
    assert registry.eligible_for_citation(record.identity) is True

    quarantined = replace(
        record,
        identity=PolicyRecordIdentity(
            record_id="INACTIVE-RECORD",
            version_id=record.identity.version_id,
            source_id=record.identity.source_id,
        ),
        activation_status=ActivationStatus.QUARANTINED,
        eligible_for_project_enforcement=False,
        eligible_for_national_legal_finding=False,
        eligible_for_citation=False,
    )
    registry.register(quarantined)

    assert registry.eligible_for_project_enforcement(quarantined.identity) is False
    assert registry.eligible_for_national_legal_finding(quarantined.identity) is False
    assert registry.eligible_for_citation(quarantined.identity) is False


def test_citation_requires_verified_artifact_and_locator(tmp_path: Path) -> None:
    record = first_record(load_registry(tmp_path))
    registry = PolicyRecordRegistry()

    unverified_artifact = replace(
        record,
        identity=PolicyRecordIdentity(
            record_id="UNVERIFIED-ARTIFACT",
            version_id=record.identity.version_id,
            source_id=record.identity.source_id,
        ),
        artifact_integrity_status=ArtifactIntegrityStatus.UNVERIFIED,
        eligible_for_project_enforcement=False,
        eligible_for_citation=False,
    )
    unverified_locator = replace(
        record,
        identity=PolicyRecordIdentity(
            record_id="UNVERIFIED-LOCATOR",
            version_id=record.identity.version_id,
            source_id=record.identity.source_id,
        ),
        locator_verification_status=LocatorVerificationStatus.UNVERIFIED,
        eligible_for_project_enforcement=False,
        eligible_for_citation=False,
    )
    registry.register(unverified_artifact)
    registry.register(unverified_locator)

    assert registry.eligible_for_citation(unverified_artifact.identity) is False
    assert registry.eligible_for_citation(unverified_locator.identity) is False


def test_concurrent_identical_registration_is_safe(tmp_path: Path) -> None:
    record = first_record(load_registry(tmp_path))
    registry = PolicyRecordRegistry()
    failures: list[Exception] = []

    def register() -> None:
        try:
            registry.register(record)
        except Exception as error:
            failures.append(error)

    threads = [threading.Thread(target=register) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert len(registry) == 1


def test_loader_rejects_missing_empty_non_utf8_and_malformed_files(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        GovernanceConfigurationError,
        match="configuration file does not exist",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(
            tmp_path / "missing.yaml"
        )

    empty = tmp_path / "empty.yaml"
    empty.write_text("   ", encoding="utf-8")
    with pytest.raises(
        GovernanceConfigurationError,
        match="configuration file is empty",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(empty)

    non_utf8 = tmp_path / "non-utf8.yaml"
    non_utf8.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(
        GovernanceConfigurationError,
        match="must be UTF-8",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(non_utf8)

    malformed = tmp_path / "malformed.yaml"
    malformed.write_text("controls: [", encoding="utf-8")
    with pytest.raises(
        GovernanceConfigurationError,
        match="contains malformed YAML",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(malformed)


def test_loader_rejects_invalid_root_schema(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "list.yaml", [])
    with pytest.raises(
        GovernanceConfigurationError,
        match="root must be a mapping",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(path)

    document = valid_safeguards_document()
    del document["authority"]
    path = write_yaml(tmp_path / "missing-field.yaml", document)
    with pytest.raises(
        GovernanceConfigurationError,
        match="missing required fields: authority",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(path)

    document = valid_safeguards_document()
    document["unexpected"] = True
    path = write_yaml(tmp_path / "unknown-field.yaml", document)
    with pytest.raises(
        GovernanceConfigurationError,
        match="unknown fields: unexpected",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(path)

    document = valid_safeguards_document()
    document["schema_version"] = "9.9.9"
    path = write_yaml(tmp_path / "unsupported-version.yaml", document)
    with pytest.raises(
        GovernanceConfigurationError,
        match="schema version is unsupported",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(path)


@pytest.mark.parametrize(
    "field_name, value, message",
    [
        (
            "national_binding_status",
            "false",
            "national_binding_status must be a YAML Boolean",
        ),
        (
            "synthetic_only",
            1,
            "synthetic_only must be a YAML Boolean",
        ),
        (
            "legal_effect",
            "false",
            "legal_effect must be a YAML Boolean",
        ),
        (
            "binding_level",
            "national_law",
            "binding_level must be project_control",
        ),
        (
            "national_binding_status",
            True,
            "national_binding_status must be False",
        ),
        (
            "synthetic_only",
            False,
            "synthetic_only must be True",
        ),
        (
            "legal_effect",
            True,
            "legal_effect must be False",
        ),
    ],
)
def test_loader_enforces_safeguard_boundaries(
    tmp_path: Path,
    field_name: str,
    value: object,
    message: str,
) -> None:
    document = valid_safeguards_document()
    document[field_name] = value
    path = write_yaml(tmp_path / f"invalid-{field_name}.yaml", document)

    with pytest.raises(GovernanceConfigurationError, match=message):
        PolicyRecordRegistry.load_from_safeguards_yaml(path)


def test_loader_rejects_invalid_controls_mapping(tmp_path: Path) -> None:
    document = valid_safeguards_document()
    document["controls"] = {}
    path = write_yaml(tmp_path / "empty-controls.yaml", document)
    with pytest.raises(
        GovernanceConfigurationError,
        match="controls must be a nonempty mapping",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(path)

    document = valid_safeguards_document()
    document["controls"]["educational_processing"] = []
    path = write_yaml(tmp_path / "nonmapping-control.yaml", document)
    with pytest.raises(
        GovernanceConfigurationError,
        match="specification must be a mapping",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(path)


def test_loader_rejects_invalid_control_names(tmp_path: Path) -> None:
    document = valid_safeguards_document()
    definition = document["controls"].pop("educational_processing")
    document["controls"]["Bad-Control"] = definition
    path = write_yaml(tmp_path / "invalid-control-name.yaml", document)

    with pytest.raises(
        GovernanceConfigurationError,
        match="lowercase snake_case",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(path)


def test_loader_rejects_control_schema_and_text_errors(tmp_path: Path) -> None:
    document = valid_safeguards_document()
    del document["controls"]["educational_processing"]["locator"]
    path = write_yaml(tmp_path / "missing-locator.yaml", document)
    with pytest.raises(
        GovernanceConfigurationError,
        match="missing required fields: locator",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(path)

    document = valid_safeguards_document()
    document["controls"]["educational_processing"]["unexpected"] = True
    path = write_yaml(tmp_path / "unknown-control-field.yaml", document)
    with pytest.raises(
        GovernanceConfigurationError,
        match="unknown fields: unexpected",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(path)

    document = valid_safeguards_document()
    document["controls"]["educational_processing"]["locator"] = " "
    path = write_yaml(tmp_path / "empty-locator.yaml", document)
    with pytest.raises(
        GovernanceConfigurationError,
        match="locator must not be empty",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(path)

    document = valid_safeguards_document()
    document["controls"]["educational_processing"]["rule"] = " "
    path = write_yaml(tmp_path / "empty-rule.yaml", document)
    with pytest.raises(
        GovernanceConfigurationError,
        match="rule must not be empty",
    ):
        PolicyRecordRegistry.load_from_safeguards_yaml(path)
