from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

import pytest

from amba_ai.db.policy_record_repository import PolicyRecordRepository
from amba_ai.governance.models import (
    ActivationStatus,
    ApplicabilityStatus,
    ArtifactIntegrityStatus,
    BindingLevel,
    GovernanceConfigurationError,
    LegalReviewStatus,
    LocatorVerificationStatus,
    MetadataVerificationStatus,
    PolicyRecord,
    PolicyRecordIdentity,
    TranslationStatus,
)


CREATE_POLICY_RECORDS_SQL = """
CREATE TABLE policy_records (
    record_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    record_digest TEXT NOT NULL,
    activation_status TEXT NOT NULL,
    PRIMARY KEY (record_id, version_id, source_id),
    CHECK (length(record_digest) = 64),
    CHECK (record_digest = lower(record_digest)),
    CHECK (
        activation_status IN (
            'active',
            'inactive',
            'quarantined',
            'superseded',
            'draft'
        )
    )
);

CREATE INDEX idx_policy_records_record_id
ON policy_records (record_id);

CREATE INDEX idx_policy_records_activation
ON policy_records (record_id, activation_status);
"""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _create_schema(db_path: Path) -> None:
    connection = sqlite3.connect(str(db_path))
    try:
        connection.executescript(CREATE_POLICY_RECORDS_SQL)
        connection.commit()
    finally:
        connection.close()


def make_record(
    *,
    record_id: str = "SYNTH-PROJECT-CONTROL",
    version_id: str = "1.0.0",
    source_id: str = "SYNTHETIC-SAFEGUARDS",
    normative_text: str = "Synthetic distribution requires governance approval.",
    reviewed_summary: str = "Synthetic project-control summary.",
    activation_status: ActivationStatus = ActivationStatus.ACTIVE,
) -> PolicyRecord:
    return PolicyRecord(
        identity=PolicyRecordIdentity(
            record_id=record_id,
            version_id=version_id,
            source_id=source_id,
        ),
        document_title="Synthetic Project Control",
        authority="Amba-Gov project",
        jurisdiction="project_sandbox",
        scope="synthetic governance validation",
        binding_level=BindingLevel.PROJECT_CONTROL,
        official_locator="synthetic://project-controls/distribution",
        page_start=1,
        page_end=1,
        normative_text=normative_text,
        reviewed_summary=reviewed_summary,
        regulated_actor="Amba-Gov synthetic components",
        protected_subject="synthetic education participants",
        conditions={
            "environment": "synthetic",
            "distribution": {
                "approval_required": True,
            },
        },
        prohibitions=("unapproved_distribution",),
        exceptions=(),
        artifact_integrity_status=ArtifactIntegrityStatus.VERIFIED,
        metadata_verification_status=MetadataVerificationStatus.VERIFIED,
        locator_verification_status=(
            LocatorVerificationStatus.VERIFIED_STRUCTURAL
        ),
        translation_status=TranslationStatus.NOT_APPLICABLE,
        legal_review_status=LegalReviewStatus.NOT_APPLICABLE,
        applicability_status=ApplicabilityStatus.APPLICABLE,
        activation_status=activation_status,
        artifact_sha256=_sha256_text("synthetic-artifact"),
        normative_unit_sha256=_sha256_text(normative_text),
        eligible_for_project_enforcement=(
            activation_status is ActivationStatus.ACTIVE
        ),
        eligible_for_national_legal_finding=False,
        national_binding_status=False,
        synthetic_only=True,
        legal_effect=False,
        eligible_for_citation=(
            activation_status is ActivationStatus.ACTIVE
        ),
    )


@pytest.fixture
def repository_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "policy_records.db"
        _create_schema(db_path)
        repository = PolicyRecordRepository(db_path)
        yield {
            "db_path": db_path,
            "repository": repository,
        }


def test_constructor_rejects_missing_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "missing_schema.db"

    with pytest.raises(
        GovernanceConfigurationError,
        match="policy_records table is missing",
    ):
        PolicyRecordRepository(db_path)


def test_constructor_rejects_incomplete_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "incomplete_schema.db"
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute(
            "CREATE TABLE policy_records (record_id TEXT PRIMARY KEY);"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        GovernanceConfigurationError,
        match="missing required columns",
    ):
        PolicyRecordRepository(db_path)


def test_register_get_require_and_list(repository_env) -> None:
    repository = repository_env["repository"]
    record = make_record()

    stored = repository.register(record)

    assert stored == record
    assert repository.get(record.identity) == record
    assert repository.require(record.identity) == record
    assert repository.list_versions(record.identity.record_id) == (record,)
    assert repository.list_all() == (record,)


def test_register_is_idempotent_for_identical_content(repository_env) -> None:
    repository = repository_env["repository"]
    record = make_record()

    assert repository.register(record) == record
    assert repository.register(record) == record
    assert repository.list_all() == (record,)


def test_register_rejects_conflicting_content(repository_env) -> None:
    repository = repository_env["repository"]
    original = make_record()
    conflicting = make_record(
        reviewed_summary="Conflicting synthetic summary.",
    )
    repository.register(original)

    with pytest.raises(
        GovernanceConfigurationError,
        match="conflicting persisted content",
    ):
        repository.register(conflicting)

    assert repository.require(original.identity) == original


def test_register_requires_policy_record(repository_env) -> None:
    repository = repository_env["repository"]

    with pytest.raises(TypeError, match="record must be a PolicyRecord"):
        repository.register(object())  # type: ignore[arg-type]


def test_lookup_requires_policy_record_identity(repository_env) -> None:
    repository = repository_env["repository"]

    with pytest.raises(
        TypeError,
        match="identity must be a PolicyRecordIdentity",
    ):
        repository.get("record")  # type: ignore[arg-type]


def test_require_rejects_missing_record(repository_env) -> None:
    repository = repository_env["repository"]
    identity = PolicyRecordIdentity(
        "MISSING-RECORD",
        "1.0.0",
        "SYNTHETIC-SOURCE",
    )

    assert repository.get(identity) is None
    with pytest.raises(
        GovernanceConfigurationError,
        match="Required policy record is not persisted",
    ):
        repository.require(identity)


def test_version_and_full_listing_are_deterministic(repository_env) -> None:
    repository = repository_env["repository"]
    second = make_record(version_id="2.0.0")
    first = make_record(version_id="1.0.0")
    other = make_record(
        record_id="SYNTH-OTHER-CONTROL",
        version_id="1.0.0",
    )

    repository.register(second)
    repository.register(other)
    repository.register(first)

    assert tuple(
        record.identity.version_id
        for record in repository.list_versions(
            "SYNTH-PROJECT-CONTROL"
        )
    ) == ("1.0.0", "2.0.0")
    assert tuple(
        record.identity.record_id
        for record in repository.list_all()
    ) == (
        "SYNTH-OTHER-CONTROL",
        "SYNTH-PROJECT-CONTROL",
        "SYNTH-PROJECT-CONTROL",
    )

def test_quarantine_revokes_all_eligibility_flags(
    repository_env,
) -> None:
    repository = repository_env["repository"]

    active = make_record()

    repository.register(active)

    quarantined = repository.set_activation_status(
        active.identity,
        ActivationStatus.QUARANTINED,
    )

    assert (
        quarantined.eligible_for_project_enforcement
        is False
    )
    assert (
        quarantined.eligible_for_national_legal_finding
        is False
    )
    assert (
        quarantined.eligible_for_citation
        is False
    )

def test_list_versions_rejects_empty_record_id(repository_env) -> None:
    repository = repository_env["repository"]

    with pytest.raises(ValueError, match="record_id must not be empty"):
        repository.list_versions(" ")


def test_active_lookup_and_require(repository_env) -> None:
    repository = repository_env["repository"]
    active = make_record()
    repository.register(active)

    assert repository.get_active_by_record_id(
        active.identity.record_id
    ) == active
    assert repository.require_active_by_record_id(
        active.identity.record_id
    ) == active


def test_active_lookup_rejects_missing_record(repository_env) -> None:
    repository = repository_env["repository"]

    assert repository.get_active_by_record_id("MISSING") is None
    with pytest.raises(
        GovernanceConfigurationError,
        match="Required active policy record is not persisted",
    ):
        repository.require_active_by_record_id("MISSING")


def test_active_lookup_rejects_ambiguous_versions(repository_env) -> None:
    repository = repository_env["repository"]
    first = make_record(version_id="1.0.0")
    second = make_record(version_id="2.0.0")
    repository.register(first)
    repository.register(second)

    with pytest.raises(
        GovernanceConfigurationError,
        match="Multiple active versions",
    ):
        repository.get_active_by_record_id(
            first.identity.record_id
        )


def test_set_activation_status_updates_persisted_record(
    repository_env,
) -> None:
    repository = repository_env["repository"]
    active = make_record()
    repository.register(active)

    quarantined = repository.set_activation_status(
        active.identity,
        ActivationStatus.QUARANTINED,
    )

    assert (
        quarantined.activation_status
        is ActivationStatus.QUARANTINED
    )
    assert (
        quarantined.eligible_for_project_enforcement
        is False
    )
    assert (
        quarantined.eligible_for_national_legal_finding
        is False
    )
    assert quarantined.eligible_for_citation is False

    persisted = repository.require(
        active.identity
    )

    assert (
        persisted.activation_status
        is ActivationStatus.QUARANTINED
    )
    assert (
        persisted.eligible_for_project_enforcement
        is False
    )
    assert (
        persisted.eligible_for_national_legal_finding
        is False
    )
    assert persisted.eligible_for_citation is False

    assert repository.get_active_by_record_id(
        active.identity.record_id
    ) is None



def test_set_activation_status_rejects_invalid_inputs(repository_env) -> None:
    repository = repository_env["repository"]
    record = make_record()
    repository.register(record)

    with pytest.raises(
        TypeError,
        match="identity must be a PolicyRecordIdentity",
    ):
        repository.set_activation_status(
            "record",  # type: ignore[arg-type]
            ActivationStatus.QUARANTINED,
        )

    with pytest.raises(
        TypeError,
        match="status must be an ActivationStatus",
    ):
        repository.set_activation_status(
            record.identity,
            "quarantined",  # type: ignore[arg-type]
        )


def test_set_activation_status_rejects_missing_record(repository_env) -> None:
    repository = repository_env["repository"]
    identity = PolicyRecordIdentity(
        "MISSING",
        "1.0.0",
        "SYNTHETIC-SOURCE",
    )

    with pytest.raises(
        GovernanceConfigurationError,
        match="not persisted",
    ):
        repository.set_activation_status(
            identity,
            ActivationStatus.QUARANTINED,
        )


def test_activation_rejects_second_active_version(repository_env) -> None:
    repository = repository_env["repository"]
    active = make_record(version_id="1.0.0")
    quarantined = make_record(
        version_id="2.0.0",
        activation_status=ActivationStatus.QUARANTINED,
    )
    repository.register(active)
    repository.register(quarantined)

    with pytest.raises(
        GovernanceConfigurationError,
        match="already active",
    ):
        repository.set_activation_status(
            quarantined.identity,
            ActivationStatus.ACTIVE,
        )


def test_corrupted_digest_is_rejected(repository_env) -> None:
    repository = repository_env["repository"]
    db_path = repository_env["db_path"]
    record = make_record()
    repository.register(record)

    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute(
            """
            UPDATE policy_records
            SET record_digest = ?
            WHERE record_id = ?
              AND version_id = ?
              AND source_id = ?;
            """,
            (
                _sha256_text("corrupted"),
                record.identity.record_id,
                record.identity.version_id,
                record.identity.source_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        GovernanceConfigurationError,
        match="digest is invalid",
    ):
        repository.require(record.identity)


def test_corrupted_json_is_rejected(repository_env) -> None:
    repository = repository_env["repository"]
    db_path = repository_env["db_path"]
    record = make_record()
    repository.register(record)
    malformed = "{not-json"

    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute(
            """
            UPDATE policy_records
            SET record_json = ?, record_digest = ?
            WHERE record_id = ?
              AND version_id = ?
              AND source_id = ?;
            """,
            (
                malformed,
                _sha256_text(malformed),
                record.identity.record_id,
                record.identity.version_id,
                record.identity.source_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        GovernanceConfigurationError,
        match="not valid JSON",
    ):
        repository.require(record.identity)


def test_activation_column_mismatch_is_rejected(repository_env) -> None:
    repository = repository_env["repository"]
    db_path = repository_env["db_path"]
    record = make_record()
    repository.register(record)

    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute(
            """
            UPDATE policy_records
            SET activation_status = ?
            WHERE record_id = ?
              AND version_id = ?
              AND source_id = ?;
            """,
            (
                ActivationStatus.QUARANTINED.value,
                record.identity.record_id,
                record.identity.version_id,
                record.identity.source_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        GovernanceConfigurationError,
        match="activation status is inconsistent",
    ):
        repository.require(record.identity)


def test_repository_recreation_preserves_records(repository_env) -> None:
    repository = repository_env["repository"]
    db_path = repository_env["db_path"]
    record = make_record()
    repository.register(record)

    reopened = PolicyRecordRepository(db_path)

    assert reopened.require(record.identity) == record
    assert reopened.list_all() == (record,)


def test_repository_releases_database_file_on_windows() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "connection_cleanup.db"
        _create_schema(db_path)
        repository = PolicyRecordRepository(db_path)
        record = make_record()
        repository.register(record)
        assert repository.require(record.identity) == record

    assert not db_path.exists()
