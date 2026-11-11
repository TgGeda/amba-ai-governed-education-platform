from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import time
from typing import Any, Callable, Collection, Literal, Sequence, TypeVar

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from amba_ai.config import EMBEDDING_MODEL_NAME, PERSONAL_KB_DIR
from amba_ai.db.database import Database
from amba_ai.exceptions import RAGError
from amba_ai.logger import logger
from amba_ai.models.schemas import RetrievedChunk
from amba_ai.rag.index_policy import IndexRebuildPolicy, IndexRebuildResult
from amba_ai.rag.corpus_revision import RetrievalCorpusCache

SimilarityMetric = Literal["cosine", "dot"]
T = TypeVar("T")


class EmbeddingModelRegistry:
    _lock = threading.Lock()
    _instances: dict[str, SentenceTransformer] = {}

    @classmethod
    def get_model(cls, model_name: str) -> SentenceTransformer:
        with cls._lock:
            if model_name not in cls._instances:
                cls._instances[model_name] = SentenceTransformer(model_name)
            return cls._instances[model_name]


@dataclass(frozen=True, slots=True)
class _ChunkRecord:
    chunk_id: int | None
    document_id: int
    text: str
    source_ref: str | None = None


class FaissRAGEngine:
    INDEX_FILENAME = "index.faiss"
    DB_FILENAME = "rag_metadata.db"
    DEFAULT_MIN_SIMILARITY: float = 0.40
    CACHE_TTL_SECONDS: float = 86400.0 * 30.0

    def __init__(
        self,
        db: Database,
        kb_dir: Path = PERSONAL_KB_DIR,
        embedding_model_name: str = EMBEDDING_MODEL_NAME,
        *,
        similarity_metric: SimilarityMetric = "cosine",
        auto_rebuild_on_mismatch: bool = True,
        rebuild_policy_provider: Callable[[], IndexRebuildPolicy | None] | None = None,
    ) -> None:
        self.db = db
        self.kb_dir = Path(kb_dir)
        self.embedding_model_name = embedding_model_name
        self.similarity_metric = similarity_metric
        self.auto_rebuild_on_mismatch = auto_rebuild_on_mismatch
        self.rebuild_policy_provider = rebuild_policy_provider
        self.corpus_cache = RetrievalCorpusCache()

        self._rw_lock = threading.RLock()
        self.index_path = self.kb_dir / self.INDEX_FILENAME
        self.sqlite_path = self.kb_dir / self.DB_FILENAME

        self.model = EmbeddingModelRegistry.get_model(embedding_model_name)
        self.embedding_dim = int(self.model.get_sentence_embedding_dimension())

        self.index: faiss.IndexIDMap2 | None = None

        self._ensure_kb_dir()
        self._init_sqlite()
        self.load_or_create()

    def _context(
        self,
        *,
        operation: str,
        query: str | None = None,
        question: str | None = None,
        top_k: int | None = None,
        document_id: int | None = None,
        chunk_count: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "operation": operation,
            "kb_dir": str(self.kb_dir),
            "index_path": str(self.index_path),
            "sqlite_path": str(self.sqlite_path),
            "embedding_model_name": self.embedding_model_name,
            "embedding_dim": self.embedding_dim,
            "similarity_metric": self.similarity_metric,
            "index_size": self.index.ntotal if self.index is not None else None,
        }

        if query is not None:
            context["query_length"] = len(query)

        if question is not None:
            context["question_length"] = len(question)

        if top_k is not None:
            context["top_k"] = top_k

        if document_id is not None:
            context["document_id"] = document_id

        if chunk_count is not None:
            context["chunk_count"] = chunk_count

        context.update(extra)
        return context

    @staticmethod
    def _build_dto(dto_cls: type[T], data: dict[str, Any]) -> T:
        if not is_dataclass(dto_cls):
            return dto_cls(**data)  # type: ignore[misc, call-arg]

        allowed = {f.name for f in fields(dto_cls)}
        filtered = {k: v for k, v in data.items() if k in allowed}
        return dto_cls(**filtered)  # type: ignore[call-arg]

    def _ensure_kb_dir(self) -> None:
        context = self._context(operation="ensure_kb_dir")
        try:
            self.kb_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.exception(
                "Failed to create RAG knowledge-base directory",
                extra={"context": context},
            )
            raise RAGError(
                "Failed to create RAG knowledge-base directory.",
                context=context,
            ) from exc

    def _require_index(self, *, operation: str) -> faiss.IndexIDMap2:
        if self.index is None:
            context = self._context(operation=operation)
            raise RAGError(
                "FAISS index is not initialized.",
                context=context,
            )
        return self.index

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.sqlite_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_sqlite(self) -> None:
        context = self._context(operation="init_sqlite")
        try:
            with self._get_connection() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS rag_chunks (
                        faiss_id INTEGER PRIMARY KEY,
                        chunk_id INTEGER NULL,
                        document_id INTEGER NOT NULL,
                        text TEXT NOT NULL,
                        source_ref TEXT NULL,
                        text_hash TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_rag_doc ON rag_chunks(document_id);
                    CREATE INDEX IF NOT EXISTS idx_rag_hash ON rag_chunks(text_hash);

                    CREATE TABLE IF NOT EXISTS embedding_cache (
                        text_hash TEXT PRIMARY KEY,
                        vector_blob BLOB NOT NULL,
                        dimension INTEGER NOT NULL,
                        last_accessed REAL NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_cache_accessed ON embedding_cache(last_accessed);
                    """
                )
        except Exception as exc:
            logger.exception(
                "Failed to initialize RAG metadata database",
                extra={"context": context},
            )
            raise RAGError(
                "Failed to initialize RAG metadata database.",
                context=context,
            ) from exc

    def prune_stale_cache(self, ttl_seconds: float = CACHE_TTL_SECONDS) -> int:
        cutoff = time.time() - ttl_seconds
        with self._rw_lock:
            with self._get_connection() as conn:
                cur = conn.execute("DELETE FROM embedding_cache WHERE last_accessed < ?", (cutoff,))
                pruned = cur.rowcount
            logger.info(
                "Pruned expired entries from embedding cache",
                extra={"context": self._context(operation="prune_stale_cache", pruned_count=pruned)},
            )
            return pruned

    def _create_base_index(self) -> faiss.IndexIDMap2:
        if self.similarity_metric in ("cosine", "dot"):
            sub = faiss.IndexFlatIP(self.embedding_dim)
            return faiss.IndexIDMap2(sub)
        raise ValueError(f"Unsupported similarity metric: {self.similarity_metric}")

    def validate_index_integrity(
        self, *, operation: str = "validate_index_integrity", verify_ids: bool = False
    ) -> None:
        index = self._require_index(operation=operation)
        context = self._context(operation=operation)

        try:
            index_dim = int(index.d)
            if index_dim != self.embedding_dim:
                raise RAGError(
                    "FAISS index dimension does not match embedding model dimension.",
                    context={
                        **context,
                        "error_type": "dimension_mismatch",
                        "index_dim": index_dim,
                        "expected_dim": self.embedding_dim,
                    },
                )

            with self._get_connection() as conn:
                cur = conn.execute("SELECT COUNT(*) AS total FROM rag_chunks")
                db_count = cur.fetchone()["total"]

                if index.ntotal != db_count:
                    raise RAGError(
                        "FAISS index and metadata database counts are out of sync.",
                        context={
                            **context,
                            "error_type": "sync_mismatch",
                            "index_size": index.ntotal,
                            "metadata_db_count": db_count,
                        },
                    )

                if verify_ids and index.ntotal > 0:
                    faiss_id_array = faiss.vector_to_array(index.id_map)
                    faiss_ids = set(map(int, faiss_id_array))
                    cur = conn.execute("SELECT faiss_id FROM rag_chunks")
                    db_ids = {int(row["faiss_id"]) for row in cur.fetchall()}

                    if faiss_ids != db_ids:
                        raise RAGError(
                            "FAISS index ID alignment mismatch with SQLite metadata.",
                            context={
                                **context,
                                "error_type": "id_alignment_mismatch",
                                "missing_in_db": len(faiss_ids - db_ids),
                                "missing_in_index": len(db_ids - faiss_ids),
                            },
                        )

        except RAGError:
            raise
        except Exception as exc:
            logger.exception("Index integrity validation failed", extra={"context": context})
            raise RAGError("Index integrity validation failed.", context=context) from exc

    def _rebuild_after_recovery_failure(self) -> IndexRebuildResult:
        policy = (
            self.rebuild_policy_provider()
            if self.rebuild_policy_provider is not None
            else None
        )
        return self.rebuild_from_source_documents(policy=policy)

    def load_or_create(self) -> None:
        context = self._context(operation="load_or_create")

        with self._rw_lock:
            if self.index_path.exists() and self.sqlite_path.exists():
                try:
                    loaded = faiss.read_index(str(self.index_path))
                    if isinstance(loaded, faiss.IndexIDMap2):
                        self.index = loaded
                    elif isinstance(loaded, faiss.IndexFlat):
                        self.index = faiss.IndexIDMap2(loaded)
                    else:
                        raise TypeError(f"Loaded index cannot be adapted to IndexIDMap2: {type(loaded)}")

                    self.validate_index_integrity(
                        operation="load_or_create_validate", verify_ids=True
                    )

                    logger.info(
                        "FAISS index and metadata store loaded successfully",
                        extra={"context": self._context(operation="load_or_create_success")},
                    )
                    return

                except RAGError:
                    if self.auto_rebuild_on_mismatch:
                        logger.warning(
                            "FAISS validation failed; rebuilding from primary document store",
                            extra={"context": context},
                        )
                        self._rebuild_after_recovery_failure()
                        return
                    raise

                except Exception as exc:
                    error_context = {**context, "error_type": "index_load_error"}
                    logger.exception("Failed to load FAISS index", extra={"context": error_context})
                    if self.auto_rebuild_on_mismatch:
                        logger.warning(
                            "Attempting full reconstruction after index load failure",
                            extra={"context": error_context},
                        )
                        self._rebuild_after_recovery_failure()
                        return
                    raise RAGError("Failed to load FAISS index.", context=error_context) from exc

            self.index = self._create_base_index()
            self.save()
            logger.info("Initialized fresh FAISS index", extra={"context": self._context(operation="init_empty")})

    def save(self) -> None:
        index = self._require_index(operation="save")
        context = self._context(operation="save")
        tmp_index_path = self.index_path.with_suffix(".faiss.tmp")

        with self._rw_lock:
            try:
                self.validate_index_integrity(operation="save_validate", verify_ids=False)
                faiss.write_index(index, str(tmp_index_path))
                os.replace(tmp_index_path, self.index_path)

                logger.info(
                    "FAISS index saved atomically",
                    extra={"context": self._context(operation="save_success")},
                )
            except RAGError:
                self._cleanup_temp_files(tmp_index_path)
                raise
            except Exception as exc:
                self._cleanup_temp_files(tmp_index_path)
                error_context = {**context, "error_type": "atomic_save_error"}
                logger.exception("Failed to save FAISS index atomically", extra={"context": error_context})
                raise RAGError("Failed to save FAISS index atomically.", context=error_context) from exc

    @staticmethod
    def _cleanup_temp_files(*paths: Path) -> None:
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def backup(self, backup_dir: Path | None = None) -> Path:
        backup_root = Path(backup_dir or self.kb_dir / "backups")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        target_dir = backup_root / timestamp
        context = self._context(operation="backup", backup_dir=str(target_dir))

        with self._rw_lock:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                if self.index_path.exists():
                    shutil.copy2(self.index_path, target_dir / self.INDEX_FILENAME)

                backup_db_path = target_dir / self.DB_FILENAME
                with self._get_connection() as src_conn:
                    with sqlite3.connect(str(backup_db_path)) as dest_conn:
                        src_conn.backup(dest_conn)

                logger.info("RAG index and metadata store backed up successfully", extra={"context": context})
                return target_dir

            except OSError as exc:
                logger.exception("FAISS index backup failed", extra={"context": context})
                raise RAGError("FAISS index backup failed.", context=context) from exc

    def restore(self, backup_dir: Path) -> None:
        source_dir = Path(backup_dir)
        context = self._context(operation="restore", backup_dir=str(source_dir))

        with self._rw_lock:
            try:
                backup_index = source_dir / self.INDEX_FILENAME
                backup_db = source_dir / self.DB_FILENAME

                if not backup_index.exists() or not backup_db.exists():
                    raise RAGError(
                        "Backup directory does not contain required RAG index or database files.",
                        context={**context, "error_type": "backup_files_missing"},
                    )

                shutil.copy2(backup_index, self.index_path)
                shutil.copy2(backup_db, self.sqlite_path)

                self.load_or_create()
                self.validate_index_integrity(operation="restore_validate", verify_ids=True)

                logger.info("RAG index restored from backup successfully", extra={"context": context})
            except RAGError:
                raise
            except OSError as exc:
                logger.exception("FAISS index restore failed", extra={"context": context})
                raise RAGError("FAISS index restore failed.", context=context) from exc

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        context = self._context(operation="embed", chunk_count=len(texts))

        if not texts:
            return np.empty((0, self.embedding_dim), dtype="float32")

        hashes = [self._hash_text(t) for t in texts]
        vectors: list[np.ndarray | None] = [None] * len(texts)
        missing_indices: list[int] = []
        missing_texts: list[str] = []
        now = time.time()

        try:
            placeholders = ",".join("?" for _ in hashes)
            with self._get_connection() as conn:
                cur = conn.execute(
                    f"""
                    SELECT text_hash, vector_blob
                    FROM embedding_cache
                    WHERE dimension = ? AND text_hash IN ({placeholders})
                    """,
                    [self.embedding_dim] + hashes,
                )
                cache_hits = {
                    row["text_hash"]: np.frombuffer(row["vector_blob"], dtype="float32")
                    for row in cur.fetchall()
                }

                for idx, h in enumerate(hashes):
                    if h in cache_hits:
                        vectors[idx] = cache_hits[h]
                    else:
                        missing_indices.append(idx)
                        missing_texts.append(texts[idx])

                if cache_hits:
                    hit_placeholders = ",".join("?" for _ in cache_hits)
                    conn.execute(
                        f"UPDATE embedding_cache SET last_accessed = ? WHERE text_hash IN ({hit_placeholders})",
                        [now] + list(cache_hits.keys()),
                    )

            if missing_texts:
                normalize = self.similarity_metric == "cosine"
                encoded = self.model.encode(
                    missing_texts,
                    convert_to_numpy=True,
                    normalize_embeddings=normalize,
                    show_progress_bar=False,
                )
                encoded = np.asarray(encoded, dtype="float32")

                if encoded.ndim != 2 or encoded.shape[1] != self.embedding_dim:
                    raise RAGError(
                        "Embedding dimension mismatch during generation.",
                        context={
                            **context,
                            "error_type": "embedding_dimension_mismatch",
                            "actual_shape": tuple(encoded.shape),
                            "expected_dim": self.embedding_dim,
                        },
                    )

                with self._get_connection() as conn:
                    for idx, vector in zip(missing_indices, encoded):
                        vectors[idx] = vector
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO embedding_cache
                            (text_hash, vector_blob, dimension, last_accessed)
                            VALUES (?, ?, ?, ?)
                            """,
                            (hashes[idx], vector.tobytes(), self.embedding_dim, now),
                        )

            return np.vstack(vectors).astype("float32")

        except RAGError:
            raise
        except Exception as exc:
            logger.exception("Embedding generation failed", extra={"context": context})
            raise RAGError("Embedding generation failed.", context=context) from exc

    def _row_or_dto_to_chunk_record(self, item: Any) -> _ChunkRecord:
        if isinstance(item, dict):
            data = item
        elif hasattr(item, "keys"):
            data = dict(item)
        elif is_dataclass(item):
            data = asdict(item)
        else:
            data = {
                "chunk_id": getattr(item, "chunk_id", None),
                "id": getattr(item, "id", None),
                "document_id": getattr(item, "document_id", None),
                "doc_id": getattr(item, "doc_id", None),
                "text": getattr(item, "text", None),
                "source_ref": getattr(item, "source_ref", None),
            }

        chunk_id = data.get("chunk_id", data.get("id"))
        document_id = data.get("document_id", data.get("doc_id"))

        if document_id is None:
            raise RAGError(
                "Chunk record is missing document_id.",
                context={"operation": "row_to_record", "error_type": "missing_document_id"},
            )

        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise RAGError(
                "Chunk record is missing text.",
                context={"operation": "row_to_record", "document_id": document_id, "error_type": "missing_text"},
            )

        return _ChunkRecord(
            chunk_id=int(chunk_id) if chunk_id is not None else None,
            document_id=int(document_id),
            text=text.strip(),
            source_ref=data.get("source_ref"),
        )

    def _fetch_chunks_for_document(self, document_id: int) -> list[_ChunkRecord]:
        context = self._context(operation="fetch_chunks_for_document", document_id=document_id)
        try:
            if hasattr(self.db, "get_chunks_typed"):
                raw_chunks = self.db.get_chunks_typed(document_id)
            else:
                raw_chunks = self.db.get_chunks(document_id)

            return [self._row_or_dto_to_chunk_record(chunk) for chunk in raw_chunks]
        except RAGError:
            raise
        except Exception as exc:
            logger.exception("Failed to fetch document chunks from database", extra={"context": context})
            raise RAGError("Failed to fetch document chunks from database.", context=context) from exc

    def _list_document_ids(self) -> list[int]:
        context = self._context(operation="list_document_ids")
        try:
            if hasattr(self.db, "list_documents_typed"):
                docs = self.db.list_documents_typed(limit=100_000, offset=0)
            else:
                docs = self.db.list_documents()

            doc_ids: list[int] = []
            for doc in docs:
                val = doc.get("id") if isinstance(doc, dict) or hasattr(doc, "keys") else getattr(doc, "id", None)
                if val is not None:
                    doc_ids.append(int(val))
            return doc_ids
        except Exception as exc:
            logger.exception("Failed to list document IDs from database", extra={"context": context})
            raise RAGError("Failed to list document IDs from database.", context=context) from exc

    def _invalidate_corpus_cache(self) -> None:
        cache = getattr(self, "corpus_cache", None)
        if cache is not None:
            cache.invalidate()

    def indexed_chunk_ids(self) -> frozenset[int]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT chunk_id FROM rag_chunks WHERE chunk_id IS NOT NULL"
            ).fetchall()
        return frozenset(int(row["chunk_id"]) for row in rows)

    def has_document(self, document_id: int) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT 1 FROM rag_chunks WHERE document_id = ? LIMIT 1", (document_id,))
            return cur.fetchone() is not None

    def index_document(self, document_id: int, *, permitted_chunk_ids: Collection[int] | None = None) -> None:
        context = self._context(operation="index_document", document_id=document_id)

        with self._rw_lock:
            try:
                chunks = self._fetch_chunks_for_document(document_id)
                if permitted_chunk_ids is not None:
                    allow = frozenset(int(value) for value in permitted_chunk_ids)
                    chunks = [chunk for chunk in chunks if chunk.chunk_id is not None and int(chunk.chunk_id) in allow]
                if not chunks:
                    logger.info("No chunks found for document indexing", extra={"context": context})
                    return

                self.remove_document(document_id)

                texts_to_embed = [c.text for c in chunks]
                vectors = self.embed(texts_to_embed)
                now = time.time()

                with self._get_connection() as conn:
                    cur = conn.cursor()
                    inserted_ids: list[int] = []
                    for c in chunks:
                        cur.execute(
                            """
                            INSERT INTO rag_chunks (chunk_id, document_id, text, source_ref, text_hash, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (c.chunk_id, c.document_id, c.text, c.source_ref, self._hash_text(c.text), now),
                        )
                        inserted_ids.append(int(cur.lastrowid))

                index = self._require_index(operation="index_document")
                ids_array = np.array(inserted_ids, dtype=np.int64)
                index.add_with_ids(vectors, ids_array)
                self.save()
                self._invalidate_corpus_cache()

                logger.info(
                    "Document indexed incrementally",
                    extra={"context": self._context(operation="index_document_success", chunk_count=len(chunks))},
                )
            except RAGError:
                raise
            except Exception as exc:
                logger.exception("Document indexing failed", extra={"context": context})
                raise RAGError("Document indexing failed.", context=context) from exc

    def remove_document(self, document_id: int) -> None:
        context = self._context(operation="remove_document", document_id=document_id)

        with self._rw_lock:
            try:
                with self._get_connection() as conn:
                    cur = conn.execute("SELECT faiss_id FROM rag_chunks WHERE document_id = ?", (document_id,))
                    rows = cur.fetchall()
                    if not rows:
                        return
                    ids_to_remove = [int(r["faiss_id"]) for r in rows]
                    conn.execute("DELETE FROM rag_chunks WHERE document_id = ?", (document_id,))

                if self.index is not None and ids_to_remove:
                    ids_array = np.array(ids_to_remove, dtype=np.int64)
                    self.index.remove_ids(ids_array)
                    self.save()
                self._invalidate_corpus_cache()

                logger.info(
                    "Document removed from index and metadata store",
                    extra={"context": self._context(operation="remove_document_success", removed_count=len(ids_to_remove))},
                )
            except RAGError:
                raise
            except Exception as exc:
                logger.exception("Document removal failed", extra={"context": context})
                raise RAGError("Document removal failed.", context=context) from exc

    def rebuild_from_source_documents(
        self,
        *,
        policy: IndexRebuildPolicy | None = None,
    ) -> IndexRebuildResult:
        context = self._context(operation="rebuild_from_source_documents")

        with self._rw_lock:
            try:
                document_ids = tuple(sorted(self._list_document_ids()))
                missing_document_ids = (
                    policy.missing_documents(document_ids)
                    if policy is not None
                    else ()
                )
                if (
                    policy is not None
                    and policy.require_complete_allowlists
                    and missing_document_ids
                ):
                    raise RAGError(
                        "Governed index rebuild refused: document allowlists are incomplete.",
                        context={
                            **context,
                            "missing_document_ids": list(missing_document_ids),
                        },
                    )

                included_records: list[_ChunkRecord] = []
                excluded_chunk_ids: list[int] = []
                for document_id in document_ids:
                    chunks = self._fetch_chunks_for_document(document_id)
                    permitted = (
                        policy.permitted_for(document_id)
                        if policy is not None
                        else None
                    )
                    if permitted is None:
                        included_records.extend(chunks)
                        continue
                    for chunk in chunks:
                        if chunk.chunk_id is None:
                            continue
                        chunk_id = int(chunk.chunk_id)
                        if chunk_id in permitted:
                            effective_text = policy.effective_text_for(chunk_id, chunk.text)
                            included_records.append(
                                _ChunkRecord(
                                    chunk_id=chunk.chunk_id,
                                    document_id=chunk.document_id,
                                    text=effective_text,
                                    source_ref=chunk.source_ref,
                                )
                            )
                        else:
                            excluded_chunk_ids.append(chunk_id)

                new_index = self._create_base_index()
                new_rows: list[tuple[_ChunkRecord, int]] = []
                indexed_chunk_ids: list[int] = []
                vectors = (
                    self.embed([record.text for record in included_records])
                    if included_records
                    else np.empty((0, self.embedding_dim), dtype="float32")
                )
                now = time.time()

                with self._get_connection() as conn:
                    conn.execute("DELETE FROM rag_chunks")
                    cursor = conn.cursor()
                    faiss_ids: list[int] = []
                    for record in included_records:
                        cursor.execute(
                            """
                            INSERT INTO rag_chunks
                                (chunk_id, document_id, text, source_ref, text_hash, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                record.chunk_id,
                                record.document_id,
                                record.text,
                                record.source_ref,
                                self._hash_text(record.text),
                                now,
                            ),
                        )
                        faiss_id = int(cursor.lastrowid)
                        faiss_ids.append(faiss_id)
                        new_rows.append((record, faiss_id))
                        if record.chunk_id is not None:
                            indexed_chunk_ids.append(int(record.chunk_id))

                if new_rows:
                    new_index.add_with_ids(
                        vectors,
                        np.array([row_id for _record, row_id in new_rows], dtype=np.int64),
                    )
                self.index = new_index
                self.save()
                self._invalidate_corpus_cache()

                result = IndexRebuildResult(
                    operation=(policy.operation if policy is not None else "legacy_rebuild"),
                    document_ids=document_ids,
                    indexed_chunk_ids=tuple(sorted(indexed_chunk_ids)),
                    excluded_chunk_ids=tuple(sorted(set(excluded_chunk_ids))),
                    missing_document_ids=missing_document_ids,
                )
                logger.info(
                    "RAG engine fully rebuilt from governed source documents",
                    extra={
                        "context": self._context(
                            operation="rebuild_success",
                            document_count=len(document_ids),
                            indexed_chunk_count=result.indexed_count,
                            excluded_chunk_count=result.excluded_count,
                            governed=policy is not None,
                        )
                    },
                )
                return result
            except RAGError:
                raise
            except Exception as exc:
                logger.exception(
                    "Rebuilding RAG engine from sources failed",
                    extra={"context": context},
                )
                raise RAGError(
                    "Rebuilding RAG engine from sources failed.",
                    context=context,
                ) from exc

    @staticmethod
    def normalize_query(query: str) -> str:
        cleaned = query.strip().lower()
        cleaned = re.sub(r"\bconfidential\b", "", cleaned, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _normalize_score(self, raw_score: float) -> float:
        if self.similarity_metric == "cosine":
            return max(0.0, min(1.0, (float(raw_score) + 1.0) / 2.0))
        return 1.0 / (1.0 + math.exp(-float(raw_score)))

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> list[RetrievedChunk]:
        normalized_query = self.normalize_query(query)
        context = self._context(
            operation="search",
            query=normalized_query,
            top_k=top_k,
            min_similarity=min_similarity,
        )

        if not normalized_query:
            raise RAGError("Search query must be non-empty.", context={**context, "error_type": "validation_error"})

        if top_k <= 0:
            raise RAGError("top_k must be greater than zero.", context={**context, "error_type": "validation_error"})

        try:
            q_vec = self.embed([normalized_query])

            with self._rw_lock:
                index = self._require_index(operation="search")
                if index.ntotal == 0:
                    return []

                scores, idxs = index.search(q_vec, min(top_k, index.ntotal))

            valid_hits: list[tuple[int, float]] = []
            for raw_score, fid in zip(scores[0], idxs[0]):
                if fid == -1:
                    continue
                score = self._normalize_score(raw_score)
                if score >= min_similarity:
                    valid_hits.append((int(fid), round(score, 4)))

            if not valid_hits:
                return []

            id_order = {fid: (idx, score) for idx, (fid, score) in enumerate(valid_hits)}
            placeholders = ",".join("?" for _ in valid_hits)
            fid_params = [fid for fid, _ in valid_hits]

            with self._get_connection() as conn:
                cur = conn.execute(
                    f"""
                    SELECT faiss_id, chunk_id, document_id, text, source_ref
                    FROM rag_chunks
                    WHERE faiss_id IN ({placeholders})
                    """,
                    fid_params,
                )
                rows = cur.fetchall()

            matched_chunks: list[tuple[int, RetrievedChunk]] = []
            for row in rows:
                order_idx, score = id_order[row["faiss_id"]]
                chunk_dict = {
                    "chunk_id": row["chunk_id"],
                    "document_id": int(row["document_id"]),
                    "doc_id": int(row["document_id"]),
                    "text": row["text"],
                    "source_ref": row["source_ref"],
                    "score": score,
                }
                matched_chunks.append(
                    (
                        order_idx,
                        self._build_dto(RetrievedChunk, chunk_dict),
                    )
                )

            matched_chunks.sort(key=lambda x: x[0])
            results = [chunk for _, chunk in matched_chunks]

            logger.info(
                "RAG search completed",
                extra={"context": {**context, "hits_returned": len(results)}},
            )
            return results

        except RAGError:
            raise
        except Exception as exc:
            logger.exception("RAG search failed", extra={"context": context})
            raise RAGError("RAG search failed.", context=context) from exc
