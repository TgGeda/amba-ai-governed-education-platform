# src/amba_ai/core/rlhf_service.py
from __future__ import annotations

import csv
import json
import sqlite3
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from amba_ai.logger import logger
from amba_ai.exceptions import FeedbackError


# ---------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------

FeedbackErrorType = Literal[
    "validation_error",
    "db_error",
    "serialization_error",
]


@dataclass(frozen=True)
class FeedbackEvent:
    """
    Input DTO for recording feedback.
    """

    feature: str
    rating: int  # must be -1, 0, or 1
    prompt: str
    response: str
    document_id: int | None = None
    comment: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    error_type: FeedbackErrorType | None = None
    created_at: float = 0.0


@dataclass(frozen=True)
class FeedbackRecord:
    """
    Persisted feedback record.
    """

    id: int
    document_id: int | None
    feature: str
    rating: int
    prompt: str
    response: str
    comment: str
    metadata: dict[str, Any]
    created_at: float


@dataclass(frozen=True)
class FeedbackRecordResult:
    """
    Result returned by RLHFService.record_feedback().
    """

    id: int
    document_id: int | None
    feature: str
    rating: int
    created_at: float


# ---------------------------------------------------------------------
# Store layer
# ---------------------------------------------------------------------


class RLHFStore:
    """
    SQLite-backed storage for RLHF / HITL feedback.

    Guarantees:
    - Atomic writes
    - Forward-compatible schema migrations
    - Typed return objects
    """

    CURRENT_SCHEMA_VERSION = 2

    def __init__(self, db_path: str = "study_feedback.db") -> None:
        self.db_path = str(Path(db_path).expanduser())
        self._init_db()

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL
                )
                """
            )

            version_row = conn.execute(
                "SELECT version FROM schema_version LIMIT 1"
            ).fetchone()

            current_version = version_row["version"] if version_row else 0

            if current_version < 1:
                self._migrate_v1(conn)

            if current_version < 2:
                self._migrate_v2(conn)

            conn.execute("DELETE FROM schema_version")
            conn.execute(
                "INSERT INTO schema_version(version) VALUES (?)",
                (self.CURRENT_SCHEMA_VERSION,),
            )
            conn.commit()

    def _migrate_v1(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NULL,
                feature TEXT NOT NULL,
                rating INTEGER NOT NULL,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                comment TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feedback_document "
            "ON feedback_events(document_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feedback_feature "
            "ON feedback_events(feature)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feedback_created "
            "ON feedback_events(created_at)"
        )

    def _migrate_v2(self, conn: sqlite3.Connection) -> None:
        """
        Placeholder for future migrations (e.g., user_id, session_id).
        """
        # No-op for now; table is forward-compatible.
        pass

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def record(self, event: FeedbackEvent) -> FeedbackRecord:
        context = {
            "operation": "record_feedback",
            "document_id": event.document_id,
            "feature": event.feature,
            "rating": event.rating,
        }

        logger.info(
            "Recording feedback started",
            extra={"context": context},
        )

        if event.rating not in (-1, 0, 1):
            raise FeedbackError(
                "Rating must be one of -1, 0, or 1.",
                context={
                    **context,
                    "error_type": "validation_error",
                },
            )

        if not event.prompt.strip() or not event.response.strip():
            raise FeedbackError(
                "Prompt and response must be non-empty.",
                context={
                    **context,
                    "error_type": "validation_error",
                },
            )

        created_at = event.created_at or time.time()

        try:
            metadata_json = json.dumps(event.metadata or {}, ensure_ascii=False)
        except Exception as exc:
            raise FeedbackError(
                "Failed to serialize metadata.",
                context={
                    **context,
                    "error_type": "serialization_error",
                },
            ) from exc

        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO feedback_events (
                        document_id,
                        feature,
                        rating,
                        prompt,
                        response,
                        comment,
                        metadata_json,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.document_id,
                        event.feature,
                        int(event.rating),
                        event.prompt,
                        event.response,
                        event.comment,
                        metadata_json,
                        created_at,
                    ),
                )
                conn.commit()

                record_id = int(cur.lastrowid)

        except sqlite3.Error as exc:
            logger.exception(
                "Feedback DB insert failed",
                extra={"context": context},
            )
            raise FeedbackError(
                "Database error while recording feedback.",
                context={
                    **context,
                    "error_type": "db_error",
                },
            ) from exc

        logger.info(
            "Recording feedback completed",
            extra={
                "context": {
                    **context,
                    "record_id": record_id,
                }
            },
        )

        return FeedbackRecord(
            id=record_id,
            document_id=event.document_id,
            feature=event.feature,
            rating=event.rating,
            prompt=event.prompt,
            response=event.response,
            comment=event.comment,
            metadata=event.metadata,
            created_at=created_at,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_recent(self, limit: int = 100) -> list[FeedbackRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM feedback_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        records: list[FeedbackRecord] = []

        for row in rows:
            records.append(
                FeedbackRecord(
                    id=row["id"],
                    document_id=row["document_id"],
                    feature=row["feature"],
                    rating=row["rating"],
                    prompt=row["prompt"],
                    response=row["response"],
                    comment=row["comment"],
                    metadata=json.loads(row["metadata_json"] or "{}"),
                    created_at=row["created_at"],
                )
            )

        return records

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_jsonl(self, output_path: str, *, overwrite: bool = False) -> int:
        path = Path(output_path).expanduser()

        if path.exists() and not overwrite:
            raise FeedbackError(
                "Output file already exists.",
                context={
                    "operation": "export_jsonl",
                    "output_path": str(path),
                },
            )

        records = self.list_recent(limit=1_000_000)

        logger.info(
            "Exporting feedback to JSONL",
            extra={
                "context": {
                    "operation": "export_jsonl",
                    "output_path": str(path),
                    "count": len(records),
                }
            },
        )

        with path.open("w", encoding="utf-8") as f:
            for record in reversed(records):
                f.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")

        return len(records)

    def export_csv(self, output_path: str, *, overwrite: bool = False) -> int:
        path = Path(output_path).expanduser()

        if path.exists() and not overwrite:
            raise FeedbackError(
                "Output file already exists.",
                context={
                    "operation": "export_csv",
                    "output_path": str(path),
                },
            )

        records = self.list_recent(limit=1_000_000)

        logger.info(
            "Exporting feedback to CSV",
            extra={
                "context": {
                    "operation": "export_csv",
                    "output_path": str(path),
                    "count": len(records),
                }
            },
        )

        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "document_id",
                    "feature",
                    "rating",
                    "prompt",
                    "response",
                    "comment",
                    "created_at",
                ]
            )

            for r in records:
                writer.writerow(
                    [
                        r.id,
                        r.document_id,
                        r.feature,
                        r.rating,
                        r.prompt,
                        r.response,
                        r.comment,
                        r.created_at,
                    ]
                )

        return len(records)

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def aggregate_feedback(self) -> list[dict[str, Any]]:
        """
        Compute average rating per feature and document.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    feature,
                    document_id,
                    COUNT(*) AS count,
                    AVG(rating) AS avg_rating
                FROM feedback_events
                GROUP BY feature, document_id
                """
            ).fetchall()

        return [
            {
                "feature": row["feature"],
                "document_id": row["document_id"],
                "count": row["count"],
                "avg_rating": round(row["avg_rating"], 4)
                if row["avg_rating"] is not None
                else None,
            }
            for row in rows
        ]


# ---------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------


class RLHFService:
    """
    High-level API for recording and querying feedback.
    """

    def __init__(self, store: RLHFStore | None = None) -> None:
        self.store = store or RLHFStore()

    def record_feedback(
        self,
        *,
        feature: str,
        rating: int,
        prompt: str,
        response: str,
        document_id: int | None = None,
        comment: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> FeedbackRecordResult:
        event = FeedbackEvent(
            feature=feature,
            rating=rating,
            prompt=prompt,
            response=response,
            document_id=document_id,
            comment=comment,
            metadata=metadata or {},
            created_at=time.time(),
        )

        record = self.store.record(event)

        return FeedbackRecordResult(
            id=record.id,
            document_id=record.document_id,
            feature=record.feature,
            rating=record.rating,
            created_at=record.created_at,
        )

    def recent_feedback(self, limit: int = 100) -> list[FeedbackRecord]:
        return self.store.list_recent(limit)

    def aggregate_feedback(self) -> list[dict[str, Any]]:
        return self.store.aggregate_feedback()