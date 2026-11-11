from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Iterator, Mapping, Sequence, TypeVar, overload

from amba_ai.config import SQLITE_PATH, ensure_directories
from amba_ai.exceptions import DatabaseError
from amba_ai.logger import logger
from amba_ai.models.schemas import (
    ChatLog,
    Flashcard,
    HITLFeedback,
    IngestedDocument,
    MCQ,
    Summary,
    TextChunk,
)

T = TypeVar("T")

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source_path TEXT NOT NULL,
    kind TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    source_ref TEXT,
    page_start INTEGER,
    page_end INTEGER,
    heading_path TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
    UNIQUE(document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    summary_markdown TEXT NOT NULL,
    model_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS flashcards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    source_ref TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mcqs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    choices_json TEXT NOT NULL,
    correct_answer TEXT NOT NULL,
    explanation TEXT NOT NULL,
    source_ref TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    message TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hitl_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL,
    item_id INTEGER,
    rating INTEGER,
    comment TEXT,
    anonymized_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_id_created
ON documents(id DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chunks_document_ordinal
ON chunks(document_id, chunk_index ASC);

CREATE INDEX IF NOT EXISTS idx_summaries_document_id_id
ON summaries(document_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_flashcards_document_id_id
ON flashcards(document_id, id ASC);

CREATE INDEX IF NOT EXISTS idx_mcqs_document_id_id
ON mcqs(document_id, id ASC);

CREATE INDEX IF NOT EXISTS idx_hitl_feedback_item
ON hitl_feedback(item_type, item_id);
"""

FTS_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    source_ref,
    content='chunks',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, source_ref)
    VALUES (new.id, new.text, new.source_ref);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, source_ref)
    VALUES('delete', old.id, old.text, old.source_ref);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, source_ref)
    VALUES('delete', old.id, old.text, old.source_ref);
    INSERT INTO chunks_fts(rowid, text, source_ref)
    VALUES (new.id, new.text, new.source_ref);
END;
"""


@dataclass(frozen=True, slots=True)
class DocumentListingRecord:
    id: int
    document_id: int
    title: str
    source_path: str
    kind: str
    metadata: dict[str, Any]
    created_at: str


class Database:
    def __init__(self, path: Path = SQLITE_PATH) -> None:
        ensure_directories()
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(
        self,
        *,
        operation: str = "connect",
        context: Mapping[str, Any] | None = None,
    ) -> Iterator[sqlite3.Connection]:
        context_data = dict(context or {})
        context_data.pop("operation", None)

        error_context = self._context(
            operation=operation,
            **context_data,
        )

        conn = sqlite3.connect(
            str(self.path),
            timeout=30.0,
            check_same_thread=False,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row

        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            conn.execute("COMMIT;")

        except Exception as exc:
            try:
                conn.execute("ROLLBACK;")
            except sqlite3.Error:
                pass

            if isinstance(exc, (DatabaseError, LookupError, ValueError)):
                raise exc

            logger.exception(
                "SQLite transaction failed",
                extra={"context": error_context},
            )
            raise DatabaseError(
                f"SQLite transaction failed during {operation}",
                context=error_context,
            ) from exc

        finally:
            conn.close()

    def initialize(self) -> None:
        context = self._context(operation="initialize")
        conn = sqlite3.connect(str(self.path), timeout=30.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute("PRAGMA foreign_keys = ON;")
            with conn:
                conn.executescript(SCHEMA_SQL)
                self._run_lightweight_migrations(conn)
                try:
                    conn.executescript(FTS_SCHEMA_SQL)
                except sqlite3.OperationalError as fts_err:
                    logger.warning(
                        "FTS5 initialization warning; continuing without full-text index",
                        extra={"context": {**context, "error": str(fts_err)}},
                    )
            logger.info("Database initialized successfully", extra={"context": context})

        except sqlite3.Error as exc:
            logger.exception(
                "Failed to initialize database schema",
                extra={"context": context},
            )
            raise DatabaseError(
                "Failed to initialize database schema",
                context=context,
            ) from exc
        finally:
            conn.close()

    def _run_lightweight_migrations(self, conn: sqlite3.Connection) -> None:
        self._ensure_column(
            conn,
            table="documents",
            column="metadata_json",
            definition="TEXT NOT NULL DEFAULT '{}'",
        )
        self._ensure_column(
            conn,
            table="documents",
            column="created_at",
            definition="TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        )
        self._ensure_column(
            conn,
            table="chunks",
            column="page_start",
            definition="INTEGER",
        )
        self._ensure_column(
            conn,
            table="chunks",
            column="page_end",
            definition="INTEGER",
        )
        self._ensure_column(
            conn,
            table="chunks",
            column="heading_path",
            definition="TEXT NOT NULL DEFAULT '[]'",
        )
        self._ensure_column(
            conn,
            table="chunks",
            column="metadata_json",
            definition="TEXT NOT NULL DEFAULT '{}'",
        )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        *,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        if not table.isidentifier() or not column.isidentifier():
            raise ValueError(f"Invalid database identifier: {table}.{column}")

        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {str(row["name"]) for row in rows}

        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition};")

    def _context(self, *, operation: str, **extra: Any) -> dict[str, Any]:
        return {
            "operation": operation,
            "db_path": str(self.path),
            **extra,
        }

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def _json_loads(
        self,
        value: str | None,
        *,
        operation: str,
        field: str,
        fallback: Any,
        context: Mapping[str, Any] | None = None,
    ) -> Any:
        if not value or not str(value).strip():
            return fallback

        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning(
                "Failed to parse JSON field; falling back to default",
                extra={
                    "context": self._context(
                        operation=operation,
                        field=field,
                        **(context or {}),
                    ),
                    "raw_value": str(value)[:300],
                },
            )
            return fallback

    @staticmethod
    def _row_to_mapping(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
        return dict(row)

    @staticmethod
    def _build_dto(dto_cls: type[T], data: Mapping[str, Any]) -> T:
        if not is_dataclass(dto_cls):
            return dto_cls(**data)  # type: ignore[call-arg]

        allowed_fields = {f.name for f in fields(dto_cls)}
        filtered = {k: v for k, v in data.items() if k in allowed_fields}
        return dto_cls(**filtered)  # type: ignore[call-arg]

    def update_document_metadata(
        self,
        document_id: int,
        updates: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized_id = int(document_id)
        if normalized_id <= 0:
            raise ValueError("document_id must be a positive integer")

        normalized_updates = {
            str(k): v
            for k, v in dict(updates or {}).items()
            if str(k).strip()
        }

        if not normalized_updates:
            return self.get_document_metadata(normalized_id)

        context = self._context(
            operation="update_document_metadata",
            document_id=normalized_id,
        )

        with self.connect(operation="update_document_metadata", context=context) as conn:
            row = conn.execute(
                "SELECT metadata_json FROM documents WHERE id = ?;",
                (normalized_id,),
            ).fetchone()

            if row is None:
                raise LookupError(f"Document {normalized_id} does not exist.")

            raw_metadata = row["metadata_json"]
            metadata = self._json_loads(
                raw_metadata,
                operation="update_document_metadata",
                field="metadata_json",
                fallback={},
                context=context,
            )

            if not isinstance(metadata, dict):
                metadata = {}

            metadata.update(normalized_updates)
            serialized = self._json_dumps(metadata)

            conn.execute(
                "UPDATE documents SET metadata_json = ? WHERE id = ?;",
                (serialized, normalized_id),
            )

        logger.info(
            "Updated document metadata",
            extra={
                "context": {
                    **context,
                    "updated_keys": sorted(normalized_updates.keys()),
                }
            },
        )
        return metadata

    def get_document_metadata(self, document_id: int) -> dict[str, Any]:
        normalized_id = int(document_id)
        if normalized_id <= 0:
            raise ValueError("document_id must be a positive integer")

        context = self._context(
            operation="get_document_metadata",
            document_id=normalized_id,
        )

        with self.connect(operation="get_document_metadata", context=context) as conn:
            row = conn.execute(
                "SELECT metadata_json FROM documents WHERE id = ?;",
                (normalized_id,),
            ).fetchone()

        if row is None:
            raise LookupError(f"Document {normalized_id} does not exist.")

        return self._json_loads(
            row["metadata_json"],
            operation="get_document_metadata",
            field="metadata_json",
            fallback={},
            context=context,
        )

    def insert_governed_document_with_chunker(
        self,
        doc: IngestedDocument,
        *,
        text: str,
        chunker: Any,
    ) -> tuple[int, tuple[int, ...]]:
        """Allocate the document ID, construct valid chunks, and persist atomically."""
        title = str(doc.title or "Untitled")
        source_path = str(doc.source_path or "")
        kind = str(doc.kind or "unknown")
        raw_text = str(text or doc.raw_text or "")
        metadata = dict(doc.metadata or {})
        if not raw_text.strip():
            raise ValueError("Governed ingestion requires non-empty extracted text.")
        if not callable(chunker):
            raise TypeError("chunker must be callable")

        with self.connect(operation="insert_governed_document_with_chunker") as conn:
            cursor = conn.execute(
                "INSERT INTO documents(title,source_path,kind,raw_text,metadata_json) VALUES(?,?,?,?,?);",
                (title, source_path, kind, raw_text, self._json_dumps(metadata)),
            )
            document_id = int(cursor.lastrowid)
            if document_id <= 0:
                raise DatabaseError("Database did not allocate a positive document ID.")

            chunks = list(chunker(document_id=document_id, text=raw_text))
            if not chunks:
                raise ValueError("Governed ingestion requires at least one chunk.")

            chunk_ids: list[int] = []
            for index, chunk in enumerate(chunks):
                raw_chunk_document_id = getattr(chunk, "doc_id", None)
                if raw_chunk_document_id is None:
                    raw_chunk_document_id = getattr(chunk, "document_id", None)
                if (
                    raw_chunk_document_id is not None
                    and int(raw_chunk_document_id) != document_id
                ):
                    raise ValueError(
                        f"Chunk {index} document ID does not match allocated document ID."
                    )
                chunk_text = str(getattr(chunk, "text", "") or "").strip()
                if not chunk_text:
                    raise ValueError(f"Chunk {index} has no text.")
                chunk_index = int(getattr(chunk, "chunk_index", index))
                source_ref = getattr(chunk, "source_ref", None)
                page_start = getattr(chunk, "page_start", None)
                page_end = getattr(chunk, "page_end", None)
                heading_path = getattr(chunk, "heading_path", ())
                chunk_metadata = getattr(chunk, "metadata", {}) or {}
                row = conn.execute(
                    """
                    INSERT INTO chunks(
                        document_id,chunk_index,text,source_ref,page_start,page_end,
                        heading_path,metadata_json
                    ) VALUES(?,?,?,?,?,?,?,?);
                    """,
                    (
                        document_id,
                        chunk_index,
                        chunk_text,
                        source_ref,
                        int(page_start) if page_start is not None else None,
                        int(page_end) if page_end is not None else None,
                        self._json_dumps(
                            list(heading_path)
                            if isinstance(heading_path, (list, tuple))
                            else []
                        ),
                        self._json_dumps(
                            dict(chunk_metadata)
                            if isinstance(chunk_metadata, Mapping)
                            else {}
                        ),
                    ),
                )
                chunk_ids.append(int(row.lastrowid))

        return document_id, tuple(chunk_ids)

    def insert_governed_document(
        self,
        doc: IngestedDocument,
        chunks: Sequence[Any],
    ) -> tuple[int, tuple[int, ...]]:
        """Persist a document and all chunks in one SQLite transaction."""
        title = str(doc.title or "Untitled")
        source_path = str(doc.source_path or "")
        kind = str(doc.kind or "unknown")
        raw_text = str(doc.raw_text or "")
        metadata = dict(doc.metadata or {})
        if not raw_text.strip():
            raise ValueError("Governed ingestion requires non-empty extracted text.")
        rows = list(chunks)
        if not rows:
            raise ValueError("Governed ingestion requires at least one chunk.")
        with self.connect(operation="insert_governed_document") as conn:
            cursor = conn.execute(
                "INSERT INTO documents(title,source_path,kind,raw_text,metadata_json) VALUES(?,?,?,?,?);",
                (title, source_path, kind, raw_text, self._json_dumps(metadata)),
            )
            document_id = int(cursor.lastrowid)
            chunk_ids: list[int] = []
            for index, chunk in enumerate(rows):
                text = str(getattr(chunk, "text", "") or "").strip()
                if not text:
                    raise ValueError(f"Chunk {index} has no text.")
                chunk_index = int(getattr(chunk, "chunk_index", index))
                source_ref = getattr(chunk, "source_ref", None)
                row = conn.execute(
                    "INSERT INTO chunks(document_id,chunk_index,text,source_ref,metadata_json) VALUES(?,?,?,?,?);",
                    (document_id, chunk_index, text, source_ref, self._json_dumps({})),
                )
                chunk_ids.append(int(row.lastrowid))
        return document_id, tuple(chunk_ids)

    def insert_document(self, doc: IngestedDocument | None = None, **kwargs: Any) -> int:
        if doc is None:
            doc = IngestedDocument(
                title=str(kwargs.get("title") or "Untitled"),
                source_path=str(kwargs.get("source_path") or ""),
                kind=str(kwargs.get("kind") or "unknown"),
                raw_text=str(kwargs.get("raw_text") or ""),
                metadata=dict(kwargs.get("metadata") or {}),
            )

        title = str(getattr(doc, "title", "Untitled") or "Untitled")
        source_path = str(getattr(doc, "source_path", "") or "")
        kind = str(getattr(doc, "kind", "unknown") or "unknown")
        raw_text = str(getattr(doc, "raw_text", "") or "")
        metadata = dict(getattr(doc, "metadata", {}) or {})

        context = self._context(
            operation="insert_document",
            title=title,
            source_path=source_path,
            kind=kind,
        )

        with self.connect(operation="insert_document", context=context) as conn:
            cur = conn.execute(
                """
                INSERT INTO documents (
                    title,
                    source_path,
                    kind,
                    raw_text,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    title,
                    source_path,
                    kind,
                    raw_text,
                    self._json_dumps(metadata),
                ),
            )
            document_id = int(cur.lastrowid)

        logger.info(
            "Inserted document",
            extra={"context": {**context, "document_id": document_id}},
        )
        return document_id

    def get_document(self, document_id: int) -> sqlite3.Row | None:
        normalized_id = int(document_id)
        context = self._context(operation="get_document", document_id=normalized_id)

        with self.connect(operation="get_document", context=context) as conn:
            return conn.execute(
                "SELECT * FROM documents WHERE id = ?;",
                (normalized_id,),
            ).fetchone()

    def get_document_typed(self, document_id: int) -> IngestedDocument | None:
        normalized_id = int(document_id)
        context = self._context(operation="get_document_typed", document_id=normalized_id)

        row = self.get_document(normalized_id)
        if row is None:
            return None

        data = self._row_to_mapping(row)
        data["metadata"] = self._json_loads(
            data.pop("metadata_json", None),
            operation="get_document_typed",
            field="metadata_json",
            fallback={},
            context=context,
        )

        return self._build_dto(IngestedDocument, data)

    def list_documents(
        self,
        *,
        limit: int = 10_000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        context = self._context(
            operation="list_documents",
            limit=limit,
            offset=offset,
        )

        with self.connect(operation="list_documents", context=context) as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    id AS document_id,
                    title,
                    source_path,
                    kind,
                    raw_text,
                    metadata_json,
                    created_at
                FROM documents
                ORDER BY id DESC
                LIMIT ?
                OFFSET ?;
                """,
                (limit, offset),
            ).fetchall()

        output: list[dict[str, Any]] = []
        for row in rows:
            data = self._row_to_mapping(row)
            doc_id = int(data["id"])
            metadata = self._json_loads(
                data.get("metadata_json"),
                operation="list_documents",
                field="metadata_json",
                fallback={},
                context={**context, "document_id": doc_id},
            )

            output.append(
                {
                    "id": doc_id,
                    "document_id": doc_id,
                    "title": str(data.get("title") or f"Document {doc_id}"),
                    "source_path": str(data.get("source_path") or ""),
                    "kind": str(data.get("kind") or "unknown"),
                    "raw_text": str(data.get("raw_text") or ""),
                    "metadata": metadata,
                    "metadata_json": data.get("metadata_json") or "{}",
                    "created_at": str(data.get("created_at") or ""),
                }
            )

        return output

    def list_documents_typed(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DocumentListingRecord]:
        return [
            DocumentListingRecord(
                id=int(item["id"]),
                document_id=int(item["document_id"]),
                title=str(item["title"]),
                source_path=str(item["source_path"]),
                kind=str(item["kind"]),
                metadata=dict(item.get("metadata") or {}),
                created_at=str(item.get("created_at") or ""),
            )
            for item in self.list_documents(limit=limit, offset=offset)
        ]

    def delete_document(self, document_id: int) -> bool:
        normalized_id = int(document_id)
        context = self._context(operation="delete_document", document_id=normalized_id)

        with self.connect(operation="delete_document", context=context) as conn:
            cur = conn.execute("DELETE FROM documents WHERE id = ?;", (normalized_id,))
            deleted = cur.rowcount > 0

        logger.info(
            "Deleted document",
            extra={"context": {**context, "deleted": deleted}},
        )
        return deleted

    def delete_governed_document_data(self, document_id: int) -> dict[str, int]:
        normalized_id = int(document_id)
        if normalized_id <= 0:
            raise ValueError("document_id must be a positive integer")
        with self.connect(operation="delete_governed_document_data", context={"document_id": normalized_id}) as conn:
            exists = conn.execute("SELECT 1 FROM documents WHERE id=?", (normalized_id,)).fetchone()
            if exists is None:
                raise LookupError(f"Document {normalized_id} does not exist.")
            counts = {
                "chunks": int(conn.execute("SELECT COUNT(*) FROM chunks WHERE document_id=?", (normalized_id,)).fetchone()[0]),
                "summaries": int(conn.execute("SELECT COUNT(*) FROM summaries WHERE document_id=?", (normalized_id,)).fetchone()[0]),
                "flashcards": int(conn.execute("SELECT COUNT(*) FROM flashcards WHERE document_id=?", (normalized_id,)).fetchone()[0]),
                "mcqs": int(conn.execute("SELECT COUNT(*) FROM mcqs WHERE document_id=?", (normalized_id,)).fetchone()[0]),
            }
            # Chat rows are deleted only when governed context explicitly links them to the document.
            pattern = f'%"document_id": {normalized_id}%'
            linked = int(conn.execute("SELECT COUNT(*) FROM chat_logs WHERE context_json LIKE ?", (pattern,)).fetchone()[0])
            conn.execute("DELETE FROM chat_logs WHERE context_json LIKE ?", (pattern,))
            counts["chat_logs"] = linked
            conn.execute("DELETE FROM documents WHERE id=?", (normalized_id,))
        return counts

    @overload
    def insert_chunks(self, chunks: Sequence[Any]) -> None: ...

    @overload
    def insert_chunks(self, document_id: int, chunks: Sequence[Mapping[str, Any]]) -> None: ...

    def insert_chunks(self, *args: Any) -> None:
        if len(args) == 1:
            chunks = list(args[0])
            if not chunks:
                return

            document_id = int(
                getattr(
                    chunks[0],
                    "doc_id",
                    getattr(chunks[0], "document_id", 0),
                )
            )

            rows = []
            for chunk in chunks:
                doc_id = int(getattr(chunk, "doc_id", getattr(chunk, "document_id", document_id)))
                idx = int(getattr(chunk, "chunk_index", getattr(chunk, "ordinal", 0)))
                text = str(getattr(chunk, "text", ""))
                s_ref = getattr(chunk, "source_ref", None)
                p_start = getattr(chunk, "page_start", None)
                p_end = getattr(chunk, "page_end", None)
                h_path = getattr(chunk, "heading_path", ())
                meta = getattr(chunk, "metadata", {}) or {}

                rows.append(
                    (
                        doc_id,
                        idx,
                        text,
                        s_ref,
                        int(p_start) if p_start is not None else None,
                        int(p_end) if p_end is not None else None,
                        self._json_dumps(list(h_path) if isinstance(h_path, (list, tuple)) else []),
                        self._json_dumps(dict(meta) if isinstance(meta, Mapping) else {}),
                    )
                )

        elif len(args) == 2:
            document_id = int(args[0])
            raw_chunks = list(args[1])
            if not raw_chunks:
                return

            rows = []
            for index, chunk in enumerate(raw_chunks):
                idx = int(chunk.get("chunk_index", chunk.get("ordinal", index)))
                text = str(chunk.get("text", chunk.get("content", "")))
                s_ref = chunk.get("source_ref")
                p_start = chunk.get("page_start")
                p_end = chunk.get("page_end", p_start)
                h_path = chunk.get("heading_path", [])
                meta = chunk.get("metadata", {})

                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}

                rows.append(
                    (
                        document_id,
                        idx,
                        text,
                        s_ref,
                        int(p_start) if p_start is not None else None,
                        int(p_end) if p_end is not None else None,
                        self._json_dumps(list(h_path) if isinstance(h_path, (list, tuple)) else []),
                        self._json_dumps(dict(meta) if isinstance(meta, Mapping) else {}),
                    )
                )
        else:
            raise TypeError("insert_chunks expects chunks or (document_id, chunks)")

        context = self._context(
            operation="insert_chunks",
            document_id=document_id,
            count=len(rows),
        )

        with self.connect(operation="insert_chunks", context=context) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO chunks (
                    document_id,
                    chunk_index,
                    text,
                    source_ref,
                    page_start,
                    page_end,
                    heading_path,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                rows,
            )

        logger.info("Inserted chunks successfully", extra={"context": context})

    def get_chunks(self, document_id: int) -> list[sqlite3.Row]:
        normalized_id = int(document_id)
        context = self._context(operation="get_chunks", document_id=normalized_id)

        with self.connect(operation="get_chunks", context=context) as conn:
            return list(
                conn.execute(
                    """
                    SELECT
                        id,
                        document_id,
                        document_id AS doc_id,
                        chunk_index,
                        text,
                        source_ref,
                        page_start,
                        page_end,
                        heading_path,
                        metadata_json,
                        created_at
                    FROM chunks
                    WHERE document_id = ?
                    ORDER BY chunk_index ASC;
                    """,
                    (normalized_id,),
                ).fetchall()
            )

    def get_chunks_typed(self, document_id: int) -> list[TextChunk]:
        rows = self.get_chunks(document_id)
        chunks: list[TextChunk] = []
        for row in rows:
            data = self._row_to_mapping(row)
            data["metadata"] = self._json_loads(
                data.pop("metadata_json", None),
                operation="get_chunks_typed",
                field="metadata_json",
                fallback={},
            )
            data["heading_path"] = self._json_loads(
                data.pop("heading_path", None),
                operation="get_chunks_typed",
                field="heading_path",
                fallback=[],
            )
            chunks.append(self._build_dto(TextChunk, data))
        return chunks

    def insert_summary(
        self,
        document_id: int,
        summary_markdown: str,
        model_name: str,
    ) -> int:
        normalized_id = int(document_id)
        context = self._context(
            operation="insert_summary",
            document_id=normalized_id,
            model_name=model_name,
        )

        with self.connect(operation="insert_summary", context=context) as conn:
            cur = conn.execute(
                """
                INSERT INTO summaries (
                    document_id,
                    summary_markdown,
                    model_name
                )
                VALUES (?, ?, ?);
                """,
                (normalized_id, summary_markdown, model_name),
            )
            summary_id = int(cur.lastrowid)

        logger.info(
            "Inserted summary",
            extra={"context": {**context, "summary_id": summary_id}},
        )
        return summary_id

    def latest_summary(self, document_id: int) -> sqlite3.Row | None:
        normalized_id = int(document_id)
        context = self._context(operation="latest_summary", document_id=normalized_id)

        with self.connect(operation="latest_summary", context=context) as conn:
            return conn.execute(
                """
                SELECT *
                FROM summaries
                WHERE document_id = ?
                ORDER BY id DESC
                LIMIT 1;
                """,
                (normalized_id,),
            ).fetchone()

    def latest_summary_typed(self, document_id: int) -> Summary | None:
        row = self.latest_summary(document_id)
        if row is None:
            return None
        return self._build_dto(Summary, self._row_to_mapping(row))

    def list_summaries_typed(self, document_id: int) -> list[Summary]:
        normalized_id = int(document_id)
        context = self._context(operation="list_summaries_typed", document_id=normalized_id)

        with self.connect(operation="list_summaries_typed", context=context) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM summaries
                WHERE document_id = ?
                ORDER BY id DESC;
                """,
                (normalized_id,),
            ).fetchall()

        return [self._build_dto(Summary, self._row_to_mapping(row)) for row in rows]

    def insert_flashcards(
        self,
        document_id: int,
        cards: Sequence[Flashcard],
    ) -> None:
        normalized_id = int(document_id)
        card_list = list(cards or [])
        context = self._context(
            operation="insert_flashcards",
            document_id=normalized_id,
            count=len(card_list),
        )

        if not card_list:
            return

        with self.connect(operation="insert_flashcards", context=context) as conn:
            conn.executemany(
                """
                INSERT INTO flashcards (
                    document_id,
                    question,
                    answer,
                    source_ref
                )
                VALUES (?, ?, ?, ?);
                """,
                [
                    (
                        normalized_id,
                        card.question,
                        card.answer,
                        card.source_ref,
                    )
                    for card in card_list
                ],
            )

        logger.info("Inserted flashcards successfully", extra={"context": context})

    def get_flashcards(self, document_id: int) -> list[sqlite3.Row]:
        normalized_id = int(document_id)
        context = self._context(operation="get_flashcards", document_id=normalized_id)

        with self.connect(operation="get_flashcards", context=context) as conn:
            return list(
                conn.execute(
                    """
                    SELECT *
                    FROM flashcards
                    WHERE document_id = ?
                    ORDER BY id ASC;
                    """,
                    (normalized_id,),
                ).fetchall()
            )

    def get_flashcards_typed(self, document_id: int) -> list[Flashcard]:
        return [
            self._build_dto(Flashcard, self._row_to_mapping(row))
            for row in self.get_flashcards(document_id)
        ]

    def insert_mcqs(
        self,
        document_id: int,
        mcqs: Sequence[MCQ],
    ) -> None:
        normalized_id = int(document_id)
        mcq_list = list(mcqs or [])
        context = self._context(
            operation="insert_mcqs",
            document_id=normalized_id,
            count=len(mcq_list),
        )

        if not mcq_list:
            return

        with self.connect(operation="insert_mcqs", context=context) as conn:
            conn.executemany(
                """
                INSERT INTO mcqs (
                    document_id,
                    question,
                    choices_json,
                    correct_answer,
                    explanation,
                    source_ref
                )
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                [
                    (
                        normalized_id,
                        mcq.question,
                        self._json_dumps(list(mcq.choices)),
                        mcq.correct_answer,
                        mcq.explanation,
                        mcq.source_ref,
                    )
                    for mcq in mcq_list
                ],
            )

        logger.info("Inserted MCQs successfully", extra={"context": context})

    def get_mcqs_dicts(self, document_id: int) -> list[dict[str, Any]]:
        normalized_id = int(document_id)
        context = self._context(operation="get_mcqs_dicts", document_id=normalized_id)

        with self.connect(operation="get_mcqs_dicts", context=context) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM mcqs
                WHERE document_id = ?
                ORDER BY id ASC;
                """,
                (normalized_id,),
            ).fetchall()

        output: list[dict[str, Any]] = []
        for row in rows:
            data = self._row_to_mapping(row)
            data["choices"] = self._json_loads(
                data.pop("choices_json", None),
                operation="get_mcqs_dicts",
                field="choices_json",
                fallback=[],
                context={**context, "mcq_id": data.get("id")},
            )
            output.append(data)

        return output

    def get_mcqs_typed(self, document_id: int) -> list[MCQ]:
        return [
            self._build_dto(MCQ, item)
            for item in self.get_mcqs_dicts(document_id)
        ]

    def log_chat(
        self,
        role: str,
        message: str,
        context_items: Sequence[Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> int:
        if context_items is None and "context" in kwargs:
            context_items = kwargs.get("context")

        log_context = self._context(operation="log_chat", role=role)

        with self.connect(operation="log_chat", context=log_context) as conn:
            cur = conn.execute(
                """
                INSERT INTO chat_logs (
                    role,
                    message,
                    context_json
                )
                VALUES (?, ?, ?);
                """,
                (
                    role,
                    message,
                    self._json_dumps(list(context_items or [])),
                ),
            )
            chat_log_id = int(cur.lastrowid)

        logger.info(
            "Inserted chat log",
            extra={"context": {**log_context, "chat_log_id": chat_log_id}},
        )
        return chat_log_id

    def list_chat_logs_typed(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChatLog]:
        context = self._context(
            operation="list_chat_logs_typed",
            limit=limit,
            offset=offset,
        )

        with self.connect(operation="list_chat_logs_typed", context=context) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM chat_logs
                ORDER BY id DESC
                LIMIT ?
                OFFSET ?;
                """,
                (limit, offset),
            ).fetchall()

        output: list[ChatLog] = []
        for row in rows:
            data = self._row_to_mapping(row)
            data["context"] = self._json_loads(
                data.pop("context_json", None),
                operation="list_chat_logs_typed",
                field="context_json",
                fallback=[],
                context={**context, "chat_log_id": data.get("id")},
            )
            output.append(self._build_dto(ChatLog, data))

        return output

    def clear_chat_logs(self) -> int:
        context = self._context(operation="clear_chat_logs")

        with self.connect(operation="clear_chat_logs", context=context) as conn:
            cur = conn.execute("DELETE FROM chat_logs;")
            deleted_count = int(cur.rowcount)

        logger.info(
            "Cleared chat logs",
            extra={"context": {**context, "deleted_count": deleted_count}},
        )
        return deleted_count

    def insert_hitl_feedback(
        self,
        item_type: str,
        item_id: int | None = None,
        rating: int | None = None,
        comment: str | None = None,
        anonymized_payload: Mapping[str, Any] | None = None,
    ) -> int:
        context = self._context(
            operation="insert_hitl_feedback",
            item_type=item_type,
            item_id=item_id,
            rating=rating,
        )

        with self.connect(operation="insert_hitl_feedback", context=context) as conn:
            cur = conn.execute(
                """
                INSERT INTO hitl_feedback (
                    item_type,
                    item_id,
                    rating,
                    comment,
                    anonymized_payload_json
                )
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    item_type,
                    item_id,
                    rating,
                    comment,
                    self._json_dumps(dict(anonymized_payload or {})),
                ),
            )
            feedback_id = int(cur.lastrowid)

        logger.info(
            "Inserted HITL feedback",
            extra={"context": {**context, "feedback_id": feedback_id}},
        )
        return feedback_id

    def list_hitl_feedback_typed(
        self,
        *,
        item_type: str | None = None,
        item_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HITLFeedback]:
        context = self._context(
            operation="list_hitl_feedback_typed",
            item_type=item_type,
            item_id=item_id,
            limit=limit,
            offset=offset,
        )

        with self.connect(operation="list_hitl_feedback_typed", context=context) as conn:
            if item_type is not None and item_id is not None:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM hitl_feedback
                    WHERE item_type = ?
                      AND item_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    OFFSET ?;
                    """,
                    (item_type, item_id, limit, offset),
                ).fetchall()

            elif item_type is not None:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM hitl_feedback
                    WHERE item_type = ?
                    ORDER BY id DESC
                    LIMIT ?
                    OFFSET ?;
                    """,
                    (item_type, limit, offset),
                ).fetchall()

            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM hitl_feedback
                    ORDER BY id DESC
                    LIMIT ?
                    OFFSET ?;
                    """,
                    (limit, offset),
                ).fetchall()

        output: list[HITLFeedback] = []
        for row in rows:
            data = self._row_to_mapping(row)
            data["anonymized_payload"] = self._json_loads(
                data.pop("anonymized_payload_json", None),
                operation="list_hitl_feedback_typed",
                field="anonymized_payload_json",
                fallback={},
                context={**context, "feedback_id": data.get("id")},
            )
            output.append(self._build_dto(HITLFeedback, data))

        return output

    def search_chunks_fts(
        self,
        query: str,
        *,
        limit: int = 20,
        document_id: int | None = None,
    ) -> list[dict[str, Any]]:
        clean_query = query.strip()
        if not clean_query:
            return []

        fts_tokens = [f'"{token}"' for token in clean_query.split() if token.isalnum()]
        if not fts_tokens:
            return []
        match_query = " ".join(fts_tokens)

        context = self._context(
            operation="search_chunks_fts",
            query=clean_query,
            document_id=document_id,
        )

        with self.connect(operation="search_chunks_fts", context=context) as conn:
            has_fts = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts';"
            ).fetchone()

            if not has_fts:
                return []

            if document_id is not None:
                rows = conn.execute(
                    """
                    SELECT
                        c.id,
                        c.document_id,
                        c.chunk_index,
                        c.text,
                        c.source_ref,
                        c.page_start,
                        c.page_end,
                        c.heading_path,
                        c.metadata_json,
                        bm25(chunks_fts) AS rank_score
                    FROM chunks_fts f
                    JOIN chunks c ON f.rowid = c.id
                    WHERE chunks_fts MATCH ?
                      AND c.document_id = ?
                    ORDER BY rank_score ASC
                    LIMIT ?;
                    """,
                    (match_query, document_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT
                        c.id,
                        c.document_id,
                        c.chunk_index,
                        c.text,
                        c.source_ref,
                        c.page_start,
                        c.page_end,
                        c.heading_path,
                        c.metadata_json,
                        bm25(chunks_fts) AS rank_score
                    FROM chunks_fts f
                    JOIN chunks c ON f.rowid = c.id
                    WHERE chunks_fts MATCH ?
                    ORDER BY rank_score ASC
                    LIMIT ?;
                    """,
                    (match_query, limit),
                ).fetchall()

        output: list[dict[str, Any]] = []
        for row in rows:
            item = self._row_to_mapping(row)
            item["metadata"] = self._json_loads(
                item.get("metadata_json"),
                operation="search_chunks_fts",
                field="metadata_json",
                fallback={},
                context=context,
            )
            item["heading_path"] = self._json_loads(
                item.get("heading_path"),
                operation="search_chunks_fts",
                field="heading_path",
                fallback=[],
                context=context,
            )
            output.append(item)

        return output

    def health_check(self) -> bool:
        context = self._context(operation="health_check")
        conn = None
        try:
            conn = sqlite3.connect(str(self.path), timeout=5.0)
            conn.execute("PRAGMA busy_timeout = 5000;")
            result = conn.execute("SELECT 1;").fetchone()

            if result is None or result[0] != 1:
                raise DatabaseError("Database health check failed", context=context)

            return True

        except DatabaseError:
            raise

        except sqlite3.Error as exc:
            logger.exception("Database health check failed", extra={"context": context})
            raise DatabaseError("Database health check failed", context=context) from exc
        finally:
            if conn is not None:
                conn.close()

    def vacuum(self) -> None:
        context = self._context(operation="vacuum")
        attempts = 2
        last_exc: sqlite3.Error | None = None

        for attempt in range(1, attempts + 1):
            attempt_context = {
                **context,
                "attempt": attempt,
                "max_attempts": attempts,
            }

            conn = None
            try:
                conn = sqlite3.connect(str(self.path), timeout=30.0)
                conn.execute("PRAGMA busy_timeout = 30000;")
                conn.execute("VACUUM;")

                logger.info(
                    "Database vacuum completed",
                    extra={"context": attempt_context},
                )
                return

            except sqlite3.Error as exc:
                last_exc = exc

                if attempt < attempts:
                    logger.warning(
                        "Database vacuum failed; retrying once",
                        extra={"context": attempt_context},
                    )
                    time.sleep(0.5)
                    continue

                logger.exception(
                    "Database vacuum failed",
                    extra={"context": attempt_context},
                )
            finally:
                if conn is not None:
                    conn.close()

        raise DatabaseError(
            "Database vacuum failed",
            context={**context, "attempts": attempts},
        ) from last_exc