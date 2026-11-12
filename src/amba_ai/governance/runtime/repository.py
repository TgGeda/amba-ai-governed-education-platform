from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from amba_ai.governance.learning_operations import (
    canonical_learning_operation,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_document_governance(id INTEGER PRIMARY KEY,document_id INTEGER UNIQUE,source_sha256 TEXT NOT NULL,decision TEXT NOT NULL,permitted_json TEXT NOT NULL,restricted_json TEXT NOT NULL,controls_json TEXT NOT NULL,findings_json TEXT NOT NULL,receipt_id TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime_chunk_governance(id INTEGER PRIMARY KEY,chunk_id INTEGER UNIQUE NOT NULL,document_id INTEGER NOT NULL,chunk_sha256 TEXT NOT NULL,decision TEXT NOT NULL,trust_level TEXT NOT NULL,indexing_permitted INTEGER NOT NULL,generation_eligible INTEGER NOT NULL,operations_json TEXT NOT NULL,findings_json TEXT NOT NULL,controls_json TEXT NOT NULL,review_status TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_runtime_chunk_document ON runtime_chunk_governance(document_id);
CREATE TABLE IF NOT EXISTS runtime_generation_governance(id INTEGER PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,document_id INTEGER NOT NULL,operation TEXT NOT NULL,decision TEXT NOT NULL,source_sha256 TEXT NOT NULL,details_json TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime_output_governance(id INTEGER PRIMARY KEY,output_id TEXT UNIQUE NOT NULL,request_id TEXT,document_id INTEGER NOT NULL,operation TEXT NOT NULL,decision TEXT NOT NULL,raw_output_sha256 TEXT NOT NULL,sanitized_output_sha256 TEXT NOT NULL,evidence_json TEXT NOT NULL,trace_id TEXT NOT NULL,receipt_id TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_runtime_output_document ON runtime_output_governance(document_id);
CREATE TABLE IF NOT EXISTS runtime_governance_receipts(id INTEGER PRIMARY KEY,receipt_id TEXT UNIQUE NOT NULL,event_type TEXT NOT NULL,document_id INTEGER,operation TEXT,payload_json TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime_governance_reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,review_id TEXT UNIQUE NOT NULL,subject_type TEXT NOT NULL,subject_id TEXT NOT NULL,document_id INTEGER NOT NULL,disposition TEXT NOT NULL,reviewer_role TEXT NOT NULL,rationale TEXT NOT NULL,redactions_json TEXT NOT NULL,supersedes_review_id TEXT,decided_at TEXT NOT NULL,receipt_id TEXT NOT NULL,published_at TEXT,effective_text TEXT,FOREIGN KEY(supersedes_review_id) REFERENCES runtime_governance_reviews(review_id));
CREATE INDEX IF NOT EXISTS idx_runtime_reviews_subject ON runtime_governance_reviews(subject_type,subject_id,id);
CREATE INDEX IF NOT EXISTS idx_runtime_reviews_document ON runtime_governance_reviews(document_id,id);
CREATE TABLE IF NOT EXISTS runtime_document_tombstones(id INTEGER PRIMARY KEY AUTOINCREMENT,document_id INTEGER UNIQUE NOT NULL,subject_id TEXT NOT NULL,source_sha256 TEXT NOT NULL,chunk_set_sha256 TEXT NOT NULL,event_type TEXT NOT NULL,decision TEXT NOT NULL,status TEXT NOT NULL,trace_id TEXT NOT NULL,receipt_id TEXT,requested_at TEXT NOT NULL,completed_at TEXT);
"""


def _canonical_operation_identifier(
    value: object,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            "operation identifier must be a string"
        )

    normalized = value.strip()

    if not normalized:
        raise ValueError(
            "operation identifier must not be empty"
        )

    try:
        return canonical_learning_operation(
            normalized
        )
    except KeyError:
        return normalized


def _canonical_operations(
    values: object,
) -> tuple[str, ...]:
    if not isinstance(
        values,
        (
            list,
            tuple,
            set,
            frozenset,
        ),
    ):
        raise TypeError(
            "operations_permitted must be a collection"
        )

    normalized: set[str] = set()

    for value in values:
        if not isinstance(value, str):
            raise TypeError(
                "operations_permitted must contain strings"
            )

        operation = value.strip()

        if not operation:
            raise ValueError(
                "operations_permitted must not contain empty values"
            )

        normalized.add(
            _canonical_operation_identifier(
                operation
            )
        )

    return tuple(sorted(normalized))


def _canonical_operations_json(
    values: object,
) -> str:
    return json.dumps(
        _canonical_operations(values),
        separators=(",", ":"),
    )


class RuntimeGovernanceRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.ensure_schema()

    def _connect(self):
        connection = sqlite3.connect(
            str(self.path)
        )
        connection.row_factory = sqlite3.Row
        return connection

    def ensure_schema(self):
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

        self._migrate_operation_identifiers()

    def _migrate_operation_identifiers(
        self,
    ) -> int:
        updated_count = 0

        with self._connect() as connection:
            chunk_rows = connection.execute(
                """
                SELECT
                    chunk_id,
                    operations_json
                FROM runtime_chunk_governance
                ORDER BY chunk_id
                """
            ).fetchall()

            for row in chunk_rows:
                canonical_json = (
                    _canonical_operations_json(
                        json.loads(
                            row["operations_json"]
                        )
                    )
                )

                if canonical_json == row[
                    "operations_json"
                ]:
                    continue

                connection.execute(
                    """
                    UPDATE runtime_chunk_governance
                    SET operations_json = ?
                    WHERE chunk_id = ?
                    """,
                    (
                        canonical_json,
                        int(row["chunk_id"]),
                    ),
                )
                updated_count += 1

            document_rows = connection.execute(
                """
                SELECT
                    document_id,
                    permitted_json,
                    restricted_json
                FROM runtime_document_governance
                ORDER BY document_id
                """
            ).fetchall()

            for row in document_rows:
                permitted_json = (
                    _canonical_operations_json(
                        json.loads(
                            row["permitted_json"]
                        )
                    )
                )
                restricted_json = (
                    _canonical_operations_json(
                        json.loads(
                            row["restricted_json"]
                        )
                    )
                )

                if (
                    permitted_json
                    == row["permitted_json"]
                    and restricted_json
                    == row["restricted_json"]
                ):
                    continue

                connection.execute(
                    """
                    UPDATE runtime_document_governance
                    SET
                        permitted_json = ?,
                        restricted_json = ?
                    WHERE document_id = ?
                    """,
                    (
                        permitted_json,
                        restricted_json,
                        int(row["document_id"]),
                    ),
                )
                updated_count += 1

            generation_rows = connection.execute(
                """
                SELECT request_id, operation
                FROM runtime_generation_governance
                ORDER BY id
                """
            ).fetchall()

            for row in generation_rows:
                canonical_operation = (
                    _canonical_operation_identifier(
                        row["operation"]
                    )
                )
                if canonical_operation == row["operation"]:
                    continue
                connection.execute(
                    """
                    UPDATE runtime_generation_governance
                    SET operation = ?
                    WHERE request_id = ?
                    """,
                    (
                        canonical_operation,
                        row["request_id"],
                    ),
                )
                updated_count += 1

            output_rows = connection.execute(
                """
                SELECT output_id, operation
                FROM runtime_output_governance
                ORDER BY id
                """
            ).fetchall()

            for row in output_rows:
                canonical_operation = (
                    _canonical_operation_identifier(
                        row["operation"]
                    )
                )
                if canonical_operation == row["operation"]:
                    continue
                connection.execute(
                    """
                    UPDATE runtime_output_governance
                    SET operation = ?
                    WHERE output_id = ?
                    """,
                    (
                        canonical_operation,
                        row["output_id"],
                    ),
                )
                updated_count += 1

            receipt_rows = connection.execute(
                """
                SELECT receipt_id, operation
                FROM runtime_governance_receipts
                WHERE operation IS NOT NULL
                ORDER BY id
                """
            ).fetchall()

            for row in receipt_rows:
                canonical_operation = (
                    _canonical_operation_identifier(
                        row["operation"]
                    )
                )
                if canonical_operation == row["operation"]:
                    continue
                connection.execute(
                    """
                    UPDATE runtime_governance_receipts
                    SET operation = ?
                    WHERE receipt_id = ?
                    """,
                    (
                        canonical_operation,
                        row["receipt_id"],
                    ),
                )
                updated_count += 1

        return updated_count

    def receipt(
        self,
        event_type: str,
        payload: dict[str, Any],
        document_id: int | None = None,
        operation: str | None = None,
    ) -> str:
        receipt_id = (
            "EDU-GOV-"
            + uuid.uuid4().hex[:20].upper()
        )
        now = datetime.now(
            timezone.utc
        ).isoformat()
        canonical_operation = (
            None
            if operation is None
            else _canonical_operation_identifier(
                operation
            )
        )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_governance_receipts (
                    receipt_id,
                    event_type,
                    document_id,
                    operation,
                    payload_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt_id,
                    event_type,
                    document_id,
                    canonical_operation,
                    json.dumps(
                        payload,
                        sort_keys=True,
                        default=str,
                    ),
                    now,
                ),
            )

        return receipt_id

    def save_document(
        self,
        document_id: int,
        decision: dict[str, Any],
    ):
        now = datetime.now(
            timezone.utc
        ).isoformat()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO runtime_document_governance (
                    document_id,
                    source_sha256,
                    decision,
                    permitted_json,
                    restricted_json,
                    controls_json,
                    findings_json,
                    receipt_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    decision["source_sha256"],
                    decision["decision"],
                    _canonical_operations_json(
                        decision[
                            "permitted_operations"
                        ]
                    ),
                    _canonical_operations_json(
                        decision[
                            "restricted_operations"
                        ]
                    ),
                    json.dumps(
                        decision["controls"]
                    ),
                    json.dumps(
                        decision["findings"]
                    ),
                    decision["receipt_id"],
                    now,
                ),
            )

    def get_document(
        self,
        document_id: int,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM runtime_document_governance
                WHERE document_id = ?
                """,
                (int(document_id),),
            ).fetchone()

        if not row:
            return None

        data = dict(row)
        data["permitted"] = (
            _canonical_operations(
                json.loads(
                    data.pop("permitted_json")
                )
            )
        )
        data["restricted"] = (
            _canonical_operations(
                json.loads(
                    data.pop("restricted_json")
                )
            )
        )
        data["controls"] = json.loads(
            data.pop("controls_json")
        )
        data["findings"] = json.loads(
            data.pop("findings_json")
        )
        return data

    def record_generation(
        self,
        request_id: str,
        document_id: int,
        operation: str,
        decision: str,
        source_sha256: str,
        details: dict[str, Any],
    ):
        canonical_operation = (
            _canonical_operation_identifier(
                operation
            )
        )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_generation_governance (
                    request_id,
                    document_id,
                    operation,
                    decision,
                    source_sha256,
                    details_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    document_id,
                    canonical_operation,
                    decision,
                    source_sha256,
                    json.dumps(
                        details,
                        sort_keys=True,
                        default=str,
                    ),
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
                ),
            )

    def save_chunk_decisions(
        self,
        decisions: list[dict[str, Any]],
    ):
        now = datetime.now(
            timezone.utc
        ).isoformat()
        rows = [
            (
                int(decision["chunk_id"]),
                int(decision["document_id"]),
                decision["chunk_sha256"],
                decision["decision"],
                decision["trust_level"],
                int(
                    bool(
                        decision[
                            "indexing_permitted"
                        ]
                    )
                ),
                int(
                    bool(
                        decision[
                            "generation_eligible"
                        ]
                    )
                ),
                _canonical_operations_json(
                    decision[
                        "operations_permitted"
                    ]
                ),
                json.dumps(
                    decision["findings"]
                ),
                json.dumps(
                    decision["controls"]
                ),
                decision["review_status"],
                now,
            )
            for decision in decisions
        ]

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO runtime_chunk_governance (
                    chunk_id,
                    document_id,
                    chunk_sha256,
                    decision,
                    trust_level,
                    indexing_permitted,
                    generation_eligible,
                    operations_json,
                    findings_json,
                    controls_json,
                    review_status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def _base_chunk_decisions(
        self,
        document_id: int,
    ):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM runtime_chunk_governance
                WHERE document_id = ?
                ORDER BY chunk_id
                """,
                (int(document_id),),
            ).fetchall()

        output = []
        for row in rows:
            data = dict(row)
            data["operations_permitted"] = (
                _canonical_operations(
                    json.loads(
                        data.pop(
                            "operations_json"
                        )
                    )
                )
            )
            data["findings"] = json.loads(
                data.pop("findings_json")
            )
            data["controls"] = json.loads(
                data.pop("controls_json")
            )
            data["indexing_permitted"] = bool(
                data["indexing_permitted"]
            )
            data["generation_eligible"] = bool(
                data["generation_eligible"]
            )
            output.append(data)

        return output

    def _document_learning_operations(
        self,
        document_id: int,
    ) -> tuple[str, ...]:
        document = self.get_document(document_id)
        if not document:
            return ()

        operations: set[str] = set()
        for value in document["permitted"]:
            normalized = _canonical_operation_identifier(value)
            if normalized.startswith("learning."):
                operations.add(normalized)

        return tuple(sorted(operations))

    def get_chunk_decisions(
        self,
        document_id: int,
    ) -> list[dict[str, Any]]:
        output = self._base_chunk_decisions(
            document_id
        )

        for data in output:
            review = self.effective_review(
                "chunk",
                str(data["chunk_id"]),
            )
            if not review:
                continue

            data["effective_review_id"] = (
                review.review_id
            )
            disposition = review.disposition.value

            if disposition in {
                "approve",
                "approve_with_redactions",
                "supersede",
            }:
                data["indexing_permitted"] = True
                data["generation_eligible"] = True
                data["review_status"] = "approved"
                base_operations = _canonical_operations(
                    data["operations_permitted"]
                )
                data["operations_permitted"] = (
                    base_operations
                    if base_operations
                    else self._document_learning_operations(
                        int(data["document_id"])
                    )
                )
            elif disposition == "reject":
                data["indexing_permitted"] = False
                data["generation_eligible"] = False
                data["review_status"] = "rejected"
            elif disposition == "revoke":
                data["indexing_permitted"] = False
                data["generation_eligible"] = False
                data["review_status"] = "revoked"

        return output

    def permitted_chunk_ids(
        self,
        document_id: int,
        operation: str,
    ) -> frozenset[int]:
        canonical_operation = (
            _canonical_operation_identifier(
                operation
            )
        )

        return frozenset(
            int(data["chunk_id"])
            for data in self.get_chunk_decisions(
                document_id
            )
            if data["indexing_permitted"]
            and data["generation_eligible"]
            and data["review_status"]
            == "approved"
            and canonical_operation
            in set(
                data["operations_permitted"]
            )
        )

    def chunk_allowed(
        self,
        chunk_id: int,
        operation: str,
    ) -> bool:
        normalized_chunk_id = int(chunk_id)

        if normalized_chunk_id <= 0:
            raise ValueError(
                "chunk_id must be a positive integer"
            )

        canonical_operation = (
            _canonical_operation_identifier(
                operation
            )
        )

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    document_id,
                    indexing_permitted,
                    generation_eligible,
                    operations_json,
                    review_status
                FROM runtime_chunk_governance
                WHERE chunk_id = ?
                """,
                (normalized_chunk_id,),
            ).fetchone()

        if not row:
            return False

        permitted_operations = frozenset(
            _canonical_operations(
                json.loads(
                    row["operations_json"]
                )
            )
        )

        review = self.effective_review(
            "chunk",
            str(normalized_chunk_id),
        )

        if review is not None:
            disposition = review.disposition.value

            if disposition in {
                "reject",
                "revoke",
            }:
                return False

            if disposition not in {
                "approve",
                "approve_with_redactions",
                "supersede",
            }:
                return False

            if not permitted_operations:
                permitted_operations = frozenset(
                    self._document_learning_operations(
                        int(row["document_id"])
                    )
                )

        return (
            bool(row["indexing_permitted"])
            and bool(row["generation_eligible"])
            and row["review_status"]
            == "approved"
            and canonical_operation
            in permitted_operations
        )

    def chunk_is_permitted(
        self,
        chunk_id: int,
        operation: str,
    ) -> bool:
        return self.chunk_allowed(
            chunk_id,
            operation,
        )

    def save_output_validation(
        self,
        record: dict[str, Any],
    ):
        canonical_operation = (
            _canonical_operation_identifier(
                record["operation"]
            )
        )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_output_governance (
                    output_id,
                    request_id,
                    document_id,
                    operation,
                    decision,
                    raw_output_sha256,
                    sanitized_output_sha256,
                    evidence_json,
                    trace_id,
                    receipt_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["output_id"],
                    record.get("request_id"),
                    record["document_id"],
                    canonical_operation,
                    record["decision"],
                    record["raw_output_sha256"],
                    record[
                        "sanitized_output_sha256"
                    ],
                    json.dumps(
                        record["evidence"],
                        sort_keys=True,
                        default=str,
                    ),
                    record["trace_id"],
                    record["receipt_id"],
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
                ),
            )

    def excluded_chunk_ids(
        self,
        document_id: int,
    ) -> frozenset[int]:
        return frozenset(
            int(data["chunk_id"])
            for data in self.get_chunk_decisions(
                document_id
            )
            if not data["indexing_permitted"]
            or not data["generation_eligible"]
            or data["review_status"]
            != "approved"
        )

    def delete_document_records(
        self,
        document_id: int,
    ):
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM runtime_chunk_governance
                WHERE document_id = ?
                """,
                (document_id,),
            )
            connection.execute(
                """
                DELETE FROM runtime_generation_governance
                WHERE document_id = ?
                """,
                (document_id,),
            )
            connection.execute(
                """
                DELETE FROM runtime_output_governance
                WHERE document_id = ?
                """,
                (document_id,),
            )
            connection.execute(
                """
                DELETE FROM runtime_document_governance
                WHERE document_id = ?
                """,
                (document_id,),
            )

    def append_review(
        self,
        decision: Any,
    ):
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_governance_reviews (
                    review_id,
                    subject_type,
                    subject_id,
                    document_id,
                    disposition,
                    reviewer_role,
                    rationale,
                    redactions_json,
                    supersedes_review_id,
                    decided_at,
                    receipt_id,
                    published_at,
                    effective_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.review_id,
                    decision.subject_type,
                    decision.subject_id,
                    decision.document_id,
                    decision.disposition.value,
                    decision.reviewer_role,
                    decision.rationale,
                    json.dumps(
                        decision.redactions
                    ),
                    decision.supersedes_review_id,
                    decision.decided_at,
                    decision.receipt_id,
                    decision.published_at,
                    decision.effective_text,
                ),
            )

    def publish_review(
        self,
        review_id: str,
        published_at: str,
    ):
        normalized_review_id = str(
            review_id
        ).strip()
        normalized_published_at = str(
            published_at
        ).strip()

        if not normalized_review_id:
            raise ValueError(
                "review_id must not be empty"
            )
        if not normalized_published_at:
            raise ValueError(
                "published_at must not be empty"
            )

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT published_at
                FROM runtime_governance_reviews
                WHERE review_id = ?
                """,
                (normalized_review_id,),
            ).fetchone()

            if not row:
                raise LookupError(
                    f"Review {normalized_review_id} "
                    "does not exist."
                )

            existing = row["published_at"]

            if existing is not None:
                if existing == normalized_published_at:
                    return

                raise ValueError(
                    f"Review {normalized_review_id} "
                    "was already published at "
                    f"{existing}."
                )

            connection.execute(
                """
                UPDATE runtime_governance_reviews
                SET published_at = ?
                WHERE review_id = ?
                """,
                (
                    normalized_published_at,
                    normalized_review_id,
                ),
            )

    def unpublish_review(
        self,
        review_id: str,
    ):
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE runtime_governance_reviews
                SET published_at = NULL
                WHERE review_id = ?
                """,
                (review_id,),
            )

    def get_review(
        self,
        review_id: str,
    ):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM runtime_governance_reviews
                WHERE review_id = ?
                """,
                (review_id,),
            ).fetchone()
        return self._review_from_row(row)

    def list_reviews(
        self,
        subject_type: str,
        subject_id: str,
    ):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM runtime_governance_reviews
                WHERE subject_type = ?
                  AND subject_id = ?
                ORDER BY id
                """,
                (
                    subject_type,
                    subject_id,
                ),
            ).fetchall()
        return [
            self._review_from_row(row)
            for row in rows
        ]

    def effective_review(
        self,
        subject_type: str,
        subject_id: str,
    ):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM runtime_governance_reviews
                WHERE subject_type = ?
                  AND subject_id = ?
                  AND published_at IS NOT NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    subject_type,
                    subject_id,
                ),
            ).fetchone()
        return self._review_from_row(row)

    def _review_from_row(
        self,
        row,
    ):
        if not row:
            return None

        from .review_models import (
            GovernanceReviewDecision,
            ReviewDisposition,
        )

        data = dict(row)
        return GovernanceReviewDecision(
            data["review_id"],
            data["subject_type"],
            data["subject_id"],
            int(data["document_id"]),
            ReviewDisposition(
                data["disposition"]
            ),
            data["reviewer_role"],
            data["rationale"],
            tuple(
                json.loads(
                    data["redactions_json"]
                )
            ),
            data["supersedes_review_id"],
            data["decided_at"],
            data["receipt_id"],
            data["published_at"],
            data["effective_text"],
        )

    def effective_chunk_text(
        self,
        chunk_id: int,
        original_text: str,
    ) -> str:
        review = self.effective_review(
            "chunk",
            str(chunk_id),
        )
        return (
            review.effective_text
            if review
            and review.effective_text is not None
            else original_text
        )

    def begin_document_deletion(
        self,
        *,
        document_id: int,
        subject_id: str,
        source_sha256: str,
        chunk_set_sha256: str,
        trace_id: str,
        requested_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_document_tombstones (
                    document_id,
                    subject_id,
                    source_sha256,
                    chunk_set_sha256,
                    event_type,
                    decision,
                    status,
                    trace_id,
                    requested_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    subject_id,
                    source_sha256,
                    chunk_set_sha256,
                    "document_deleted",
                    "authorized",
                    "pending",
                    trace_id,
                    requested_at,
                ),
            )

    def set_document_deletion_status(
        self,
        document_id: int,
        status: str,
        *,
        receipt_id: str | None = None,
        completed_at: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE runtime_document_tombstones
                SET
                    status = ?,
                    receipt_id = COALESCE(?, receipt_id),
                    completed_at = COALESCE(?, completed_at)
                WHERE document_id = ?
                """,
                (
                    status,
                    receipt_id,
                    completed_at,
                    document_id,
                ),
            )

    def get_document_tombstone(
        self,
        document_id: int,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    document_id,
                    subject_id,
                    source_sha256,
                    chunk_set_sha256,
                    event_type,
                    decision,
                    status,
                    trace_id,
                    receipt_id,
                    requested_at,
                    completed_at
                FROM runtime_document_tombstones
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
        return dict(row) if row else None

    def revoke_document_chunks(
        self,
        document_id: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE runtime_chunk_governance
                SET
                    indexing_permitted = 0,
                    generation_eligible = 0,
                    operations_json = '[]',
                    review_status = 'revoked'
                WHERE document_id = ?
                """,
                (document_id,),
            )

    def privacy_purge_document_records(
        self,
        document_id: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM runtime_governance_reviews
                WHERE document_id = ?
                """,
                (document_id,),
            )
            connection.execute(
                """
                DELETE FROM runtime_generation_governance
                WHERE document_id = ?
                """,
                (document_id,),
            )
            connection.execute(
                """
                DELETE FROM runtime_output_governance
                WHERE document_id = ?
                """,
                (document_id,),
            )
            connection.execute(
                """
                DELETE FROM runtime_chunk_governance
                WHERE document_id = ?
                """,
                (document_id,),
            )
            connection.execute(
                """
                DELETE FROM runtime_document_governance
                WHERE document_id = ?
                """,
                (document_id,),
            )
