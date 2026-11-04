from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterator, Mapping

from amba_ai.db.governance_repository import create_sqlite_connection
from amba_ai.governance.models import (
    ActivationStatus,
    ApplicabilityStatus,
    ArtifactIntegrityStatus,
    BindingLevel,
    GovernanceConfigurationError,
    InvalidPolicyRecordError,
    LegalReviewStatus,
    LocatorVerificationStatus,
    MetadataVerificationStatus,
    PolicyRecord,
    PolicyRecordIdentity,
    TranslationStatus,
    to_canonical_json,
)


_TABLE_NAME = "policy_records"
_REQUIRED_COLUMNS = frozenset(
    {
        "record_id",
        "version_id",
        "source_id",
        "record_json",
        "record_digest",
        "activation_status",
    }
)


class PolicyRecordRepository:
    """SQLite persistence boundary for immutable policy-record versions.

    The repository stores canonical serialized records as append-only versions.
    Repeating an identical write is idempotent. Reusing the same record identity
    with different content fails closed. Activation changes create no mutation
    of normative content and are limited to the activation-status column.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._validate_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        connection = create_sqlite_connection(self.db_path)
        try:
            yield connection
        finally:
            connection.close()

    def register(self, record: PolicyRecord) -> PolicyRecord:
        if not isinstance(record, PolicyRecord):
            raise TypeError("record must be a PolicyRecord")

        identity = record.identity
        record_json = record.to_canonical_json()
        record_digest = self._record_digest(record_json)

        with self._lock, self._conn() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE;")
                existing = connection.execute(
                    f"""
                    SELECT record_json, record_digest
                    FROM {_TABLE_NAME}
                    WHERE record_id = ?
                      AND version_id = ?
                      AND source_id = ?;
                    """,
                    (
                        identity.record_id,
                        identity.version_id,
                        identity.source_id,
                    ),
                ).fetchone()

                if existing is not None:
                    if (
                        str(existing["record_digest"]) == record_digest
                        and str(existing["record_json"]) == record_json
                    ):
                        connection.commit()
                        return record

                    raise GovernanceConfigurationError(
                        "A policy record with the same identity has "
                        "conflicting persisted content"
                    )

                connection.execute(
                    f"""
                    INSERT INTO {_TABLE_NAME} (
                        record_id,
                        version_id,
                        source_id,
                        record_json,
                        record_digest,
                        activation_status
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        identity.record_id,
                        identity.version_id,
                        identity.source_id,
                        record_json,
                        record_digest,
                        record.activation_status.value,
                    ),
                )
                connection.commit()
                return record
            except GovernanceConfigurationError:
                if connection.in_transaction:
                    connection.rollback()
                raise
            except sqlite3.IntegrityError as error:
                if connection.in_transaction:
                    connection.rollback()
                raise GovernanceConfigurationError(
                    "Policy-record persistence integrity constraint violated"
                ) from error
            except sqlite3.Error as error:
                if connection.in_transaction:
                    connection.rollback()
                raise GovernanceConfigurationError(
                    "Policy-record persistence transaction failed"
                ) from error
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise

    def get(self, identity: PolicyRecordIdentity) -> PolicyRecord | None:
        if not isinstance(identity, PolicyRecordIdentity):
            raise TypeError("identity must be a PolicyRecordIdentity")

        with self._lock, self._conn() as connection:
            row = connection.execute(
                f"""
                SELECT record_json, record_digest, activation_status
                FROM {_TABLE_NAME}
                WHERE record_id = ?
                  AND version_id = ?
                  AND source_id = ?;
                """,
                (
                    identity.record_id,
                    identity.version_id,
                    identity.source_id,
                ),
            ).fetchone()

        return None if row is None else self._row_to_record(row)

    def require(self, identity: PolicyRecordIdentity) -> PolicyRecord:
        record = self.get(identity)
        if record is None:
            raise GovernanceConfigurationError(
                "Required policy record is not persisted"
            )
        return record

    def list_versions(self, record_id: str) -> tuple[PolicyRecord, ...]:
        normalized = self._require_text(record_id, "record_id")

        with self._lock, self._conn() as connection:
            rows = connection.execute(
                f"""
                SELECT record_json, record_digest, activation_status
                FROM {_TABLE_NAME}
                WHERE record_id = ?
                ORDER BY version_id ASC, source_id ASC;
                """,
                (normalized,),
            ).fetchall()

        return tuple(self._row_to_record(row) for row in rows)

    def list_all(self) -> tuple[PolicyRecord, ...]:
        with self._lock, self._conn() as connection:
            rows = connection.execute(
                f"""
                SELECT record_json, record_digest, activation_status
                FROM {_TABLE_NAME}
                ORDER BY record_id ASC, version_id ASC, source_id ASC;
                """
            ).fetchall()

        return tuple(self._row_to_record(row) for row in rows)

    def get_active_by_record_id(self, record_id: str) -> PolicyRecord | None:
        normalized = self._require_text(record_id, "record_id")

        with self._lock, self._conn() as connection:
            rows = connection.execute(
                f"""
                SELECT record_json, record_digest, activation_status
                FROM {_TABLE_NAME}
                WHERE record_id = ?
                  AND activation_status = ?
                ORDER BY version_id DESC, source_id ASC;
                """,
                (normalized, ActivationStatus.ACTIVE.value),
            ).fetchall()

        if not rows:
            return None
        if len(rows) != 1:
            raise GovernanceConfigurationError(
                "Multiple active versions exist for the policy record"
            )
        return self._row_to_record(rows[0])

    def require_active_by_record_id(self, record_id: str) -> PolicyRecord:
        record = self.get_active_by_record_id(record_id)
        if record is None:
            raise GovernanceConfigurationError(
                "Required active policy record is not persisted"
            )
        return record

    def set_activation_status(
        self,
        identity: PolicyRecordIdentity,
        status: ActivationStatus,
    ) -> PolicyRecord:
        if not isinstance(identity, PolicyRecordIdentity):
            raise TypeError("identity must be a PolicyRecordIdentity")
        if not isinstance(status, ActivationStatus):
            raise TypeError("status must be an ActivationStatus")

        with self._lock, self._conn() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE;")
                row = connection.execute(
                    f"""
                    SELECT record_json, record_digest, activation_status
                    FROM {_TABLE_NAME}
                    WHERE record_id = ?
                      AND version_id = ?
                      AND source_id = ?;
                    """,
                    (
                        identity.record_id,
                        identity.version_id,
                        identity.source_id,
                    ),
                ).fetchone()
                if row is None:
                    raise GovernanceConfigurationError(
                        "Policy record to activate is not persisted"
                    )

                record = self._row_to_record(row)
                updated = self._replace_activation_status(record, status)
                updated_json = updated.to_canonical_json()
                updated_digest = self._record_digest(updated_json)

                if status is ActivationStatus.ACTIVE:
                    conflict = connection.execute(
                        f"""
                        SELECT 1
                        FROM {_TABLE_NAME}
                        WHERE record_id = ?
                          AND activation_status = ?
                          AND NOT (
                              version_id = ? AND source_id = ?
                          )
                        LIMIT 1;
                        """,
                        (
                            identity.record_id,
                            ActivationStatus.ACTIVE.value,
                            identity.version_id,
                            identity.source_id,
                        ),
                    ).fetchone()
                    if conflict is not None:
                        raise GovernanceConfigurationError(
                            "Another version of the policy record is already active"
                        )

                connection.execute(
                    f"""
                    UPDATE {_TABLE_NAME}
                    SET activation_status = ?,
                        record_json = ?,
                        record_digest = ?
                    WHERE record_id = ?
                      AND version_id = ?
                      AND source_id = ?;
                    """,
                    (
                        status.value,
                        updated_json,
                        updated_digest,
                        identity.record_id,
                        identity.version_id,
                        identity.source_id,
                    ),
                )
                connection.commit()
                return updated
            except GovernanceConfigurationError:
                if connection.in_transaction:
                    connection.rollback()
                raise
            except (sqlite3.Error, InvalidPolicyRecordError, TypeError, ValueError) as error:
                if connection.in_transaction:
                    connection.rollback()
                raise GovernanceConfigurationError(
                    "Policy-record activation transaction failed"
                ) from error

    def _validate_schema(self) -> None:
        with self._conn() as connection:
            rows = connection.execute(
                f"PRAGMA table_info({_TABLE_NAME});"
            ).fetchall()

        if not rows:
            raise GovernanceConfigurationError(
                "Required policy_records table is missing; apply the governance migration"
            )

        available = {str(row["name"]) for row in rows}
        missing = sorted(_REQUIRED_COLUMNS - available)
        if missing:
            raise GovernanceConfigurationError(
                "policy_records table is missing required columns: "
                + ", ".join(missing)
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> PolicyRecord:
        record_json = str(row["record_json"])
        digest = str(row["record_digest"])
        if PolicyRecordRepository._record_digest(record_json) != digest:
            raise GovernanceConfigurationError(
                "Persisted policy record digest is invalid"
            )

        try:
            material = json.loads(record_json)
        except json.JSONDecodeError as error:
            raise GovernanceConfigurationError(
                "Persisted policy record is not valid JSON"
            ) from error

        if not isinstance(material, Mapping):
            raise GovernanceConfigurationError(
                "Persisted policy record must decode to a mapping"
            )

        try:
            identity_material = material["identity"]
            if not isinstance(identity_material, Mapping):
                raise TypeError("identity must be a mapping")

            record = PolicyRecord(
                identity=PolicyRecordIdentity(
                    record_id=identity_material["record_id"],
                    version_id=identity_material["version_id"],
                    source_id=identity_material["source_id"],
                ),
                document_title=material["document_title"],
                authority=material["authority"],
                jurisdiction=material["jurisdiction"],
                scope=material["scope"],
                binding_level=BindingLevel(material["binding_level"]),
                official_locator=material["official_locator"],
                page_start=material["page_start"],
                page_end=material["page_end"],
                normative_text=material["normative_text"],
                reviewed_summary=material["reviewed_summary"],
                regulated_actor=material["regulated_actor"],
                protected_subject=material["protected_subject"],
                conditions=material["conditions"],
                prohibitions=tuple(material["prohibitions"]),
                exceptions=tuple(material["exceptions"]),
                artifact_integrity_status=ArtifactIntegrityStatus(
                    material["artifact_integrity_status"]
                ),
                metadata_verification_status=MetadataVerificationStatus(
                    material["metadata_verification_status"]
                ),
                locator_verification_status=LocatorVerificationStatus(
                    material["locator_verification_status"]
                ),
                translation_status=TranslationStatus(
                    material["translation_status"]
                ),
                legal_review_status=LegalReviewStatus(
                    material["legal_review_status"]
                ),
                applicability_status=ApplicabilityStatus(
                    material["applicability_status"]
                ),
                activation_status=ActivationStatus(
                    material["activation_status"]
                ),
                artifact_sha256=material["artifact_sha256"],
                normative_unit_sha256=material["normative_unit_sha256"],
                eligible_for_project_enforcement=material[
                    "eligible_for_project_enforcement"
                ],
                eligible_for_national_legal_finding=material[
                    "eligible_for_national_legal_finding"
                ],
                national_binding_status=material["national_binding_status"],
                synthetic_only=material["synthetic_only"],
                legal_effect=material["legal_effect"],
                eligible_for_citation=material["eligible_for_citation"],
            )
        except (KeyError, TypeError, ValueError, InvalidPolicyRecordError) as error:
            raise GovernanceConfigurationError(
                "Persisted policy record is invalid"
            ) from error

        stored_status = str(row["activation_status"])
        if record.activation_status.value != stored_status:
            raise GovernanceConfigurationError(
                "Persisted policy-record activation status is inconsistent"
            )
        return record

    @staticmethod
    def _replace_activation_status(
        record: PolicyRecord,
        status: ActivationStatus,
    ) -> PolicyRecord:
        if not isinstance(record, PolicyRecord):
            raise TypeError(
                "record must be a PolicyRecord"
            )

        if not isinstance(status, ActivationStatus):
            raise TypeError(
                "status must be an ActivationStatus"
            )

        material = record.to_dict()
        material["activation_status"] = status.value

        if status is not ActivationStatus.ACTIVE:
            material[
                "eligible_for_project_enforcement"
            ] = False
            material[
                "eligible_for_national_legal_finding"
            ] = False
            material[
                "eligible_for_citation"
            ] = False

        identity_material = material["identity"]

        if not isinstance(identity_material, Mapping):
            raise GovernanceConfigurationError(
                "Policy record identity must serialize "
                "to a mapping"
            )

        try:
            return PolicyRecord(
                identity=PolicyRecordIdentity(
                    record_id=identity_material[
                        "record_id"
                    ],
                    version_id=identity_material[
                        "version_id"
                    ],
                    source_id=identity_material[
                        "source_id"
                    ],
                ),
                document_title=material[
                    "document_title"
                ],
                authority=material["authority"],
                jurisdiction=material["jurisdiction"],
                scope=material["scope"],
                binding_level=BindingLevel(
                    material["binding_level"]
                ),
                official_locator=material[
                    "official_locator"
                ],
                page_start=material["page_start"],
                page_end=material["page_end"],
                normative_text=material[
                    "normative_text"
                ],
                reviewed_summary=material[
                    "reviewed_summary"
                ],
                regulated_actor=material[
                    "regulated_actor"
                ],
                protected_subject=material[
                    "protected_subject"
                ],
                conditions=material["conditions"],
                prohibitions=tuple(
                    material["prohibitions"]
                ),
                exceptions=tuple(
                    material["exceptions"]
                ),
                artifact_integrity_status=(
                    ArtifactIntegrityStatus(
                        material[
                            "artifact_integrity_status"
                        ]
                    )
                ),
                metadata_verification_status=(
                    MetadataVerificationStatus(
                        material[
                            "metadata_verification_status"
                        ]
                    )
                ),
                locator_verification_status=(
                    LocatorVerificationStatus(
                        material[
                            "locator_verification_status"
                        ]
                    )
                ),
                translation_status=TranslationStatus(
                    material["translation_status"]
                ),
                legal_review_status=LegalReviewStatus(
                    material["legal_review_status"]
                ),
                applicability_status=ApplicabilityStatus(
                    material["applicability_status"]
                ),
                activation_status=status,
                artifact_sha256=material[
                    "artifact_sha256"
                ],
                normative_unit_sha256=material[
                    "normative_unit_sha256"
                ],
                eligible_for_project_enforcement=(
                    material[
                        "eligible_for_project_enforcement"
                    ]
                ),
                eligible_for_national_legal_finding=(
                    material[
                        "eligible_for_national_legal_finding"
                    ]
                ),
                national_binding_status=material[
                    "national_binding_status"
                ],
                synthetic_only=material[
                    "synthetic_only"
                ],
                legal_effect=material[
                    "legal_effect"
                ],
                eligible_for_citation=material[
                    "eligible_for_citation"
                ],
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            InvalidPolicyRecordError,
        ) as error:
            raise GovernanceConfigurationError(
                "Policy record activation transition "
                "produced invalid content"
            ) from error

    @staticmethod
    def _record_digest(record_json: str) -> str:
        import hashlib

        return hashlib.sha256(record_json.encode("utf-8")).hexdigest()

    @staticmethod
    def _require_text(value: object, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must not be empty")
        return normalized
