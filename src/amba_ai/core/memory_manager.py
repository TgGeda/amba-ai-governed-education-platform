from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from amba_ai.config import DATA_DIR, EMBEDDING_MODEL_NAME, SQLITE_PATH
from amba_ai.logger import logger

@dataclass(frozen=True)
class MemoryTurn:
    turn_id: str
    session_id: str
    user_text: str
    assistant_text: str
    created_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class MemoryChunk:
    chunk_id: str
    turn_id: str
    session_id: str
    text: str
    role_scope: str
    created_at: str
    faiss_position: int
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class RetrievedMemory:
    chunk_id: str
    turn_id: str
    session_id: str
    text: str
    score: float
    created_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class VectorInfiniteMemory:
    DEFAULT_INDEX_PATH = DATA_DIR / "db" / "chat_history.faiss"
    DEFAULT_METADATA_PATH = DATA_DIR / "db" / "chat_history_meta.json"
    DEFAULT_CHUNK_SIZE_CHARS = 1200
    DEFAULT_CHUNK_OVERLAP_CHARS = 160
    DEFAULT_MAX_SEARCH_MULTIPLIER = 12
    DEFAULT_MAX_SEARCH_LIMIT = 256

    def __init__(
        self,
        sqlite_path: Path = SQLITE_PATH,
        index_path: Path = DEFAULT_INDEX_PATH,
        metadata_path: Path = DEFAULT_METADATA_PATH,
        embedding_model_name: str = EMBEDDING_MODEL_NAME,
        chunk_size_chars: int = DEFAULT_CHUNK_SIZE_CHARS,
        chunk_overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
    ) -> None:
        self.sqlite_path = Path(sqlite_path)
        self.index_path = Path(index_path)
        self.metadata_path = Path(metadata_path)
        self.embedding_model_name = str(embedding_model_name)
        self.chunk_size_chars = max(400, int(chunk_size_chars))
        self.chunk_overlap_chars = max(0, min(int(chunk_overlap_chars), self.chunk_size_chars // 2))

        self._lock = threading.RLock()
        self._embedding_model: Optional[SentenceTransformer] = None
        self._embedding_dim: Optional[int] = None
        self._index: Optional[faiss.Index] = None
        self._metadata: list[dict[str, Any]] =[]
        self._backend_ready = False

        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)

        self._initialize_sqlite()

        logger.info(
            "VectorInfiniteMemory initialized lazily",
            extra={
                "context": {
                    "sqlite_path": str(self.sqlite_path),
                    "index_path": str(self.index_path),
                    "metadata_path": str(self.metadata_path),
                    "embedding_model": self.embedding_model_name,
                }
            },
        )

    def save_exchange(
        self,
        user_text: str,
        assistant_text: str,
        *,
        session_id: str = "default",
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryTurn:
        user_text = (user_text or "").strip()
        assistant_text = (assistant_text or "").strip()

        if not user_text and not assistant_text:
            raise ValueError("Cannot save an empty memory exchange.")

        now = self._now()
        safe_metadata = self._json_safe_dict(metadata or {})

        turn = MemoryTurn(
            turn_id=str(uuid.uuid4()),
            session_id=str(session_id or "default"),
            user_text=user_text,
            assistant_text=assistant_text,
            created_at=now,
            metadata=safe_metadata,
        )

        combined_text = self._format_turn_for_memory(turn)
        chunks = self._chunk_text(combined_text)

        with self._lock:
            self._insert_turn(turn)

            if not chunks:
                logger.info(
                    "Memory turn saved without chunks",
                    extra={"context": {"turn_id": turn.turn_id, "session_id": turn.session_id}},
                )
                return turn

            self._ensure_vector_backend()
            assert self._index is not None

            vectors = self._embed(chunks)
            start_position = int(self._index.ntotal)

            chunk_records =[
                MemoryChunk(
                    chunk_id=str(uuid.uuid4()),
                    turn_id=turn.turn_id,
                    session_id=turn.session_id,
                    text=chunk_text,
                    role_scope="exchange",
                    created_at=now,
                    faiss_position=start_position + offset,
                    metadata=safe_metadata,
                )
                for offset, chunk_text in enumerate(chunks)
            ]

            try:
                self._index.add(vectors)
                self._metadata.extend([self._chunk_to_metadata(chunk) for chunk in chunk_records])
                self._insert_chunks(chunk_records)
                self._save_index_atomic()
                self._save_metadata_atomic()
            except Exception:
                logger.warning(
                    "Memory write failed; rebuilding index from SQLite",
                    extra={"context": {"turn_id": turn.turn_id}},
                    exc_info=True,
                )
                self.rebuild_index_from_sqlite()
                raise

        logger.info(
            "Memory exchange saved and indexed",
            extra={
                "context": {
                    "turn_id": turn.turn_id,
                    "session_id": turn.session_id,
                    "chunks": len(chunks),
                }
            },
        )

        return turn

    def add_turn(
        self,
        user_text: str,
        assistant_text: str,
        *,
        session_id: str = "default",
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryTurn:
        return self.save_exchange(
            user_text=user_text,
            assistant_text=assistant_text,
            session_id=session_id,
            metadata=metadata,
        )

    def get_relevant_history(
        self,
        current_query: str,
        k: int = 3,
        *,
        session_id: Optional[str] = None,
        min_score: float = 0.0,
    ) -> list[RetrievedMemory]:
        query = (current_query or "").strip()

        if not query:
            return[]

        safe_k = max(1, min(int(k), 20))

        with self._lock:
            self._ensure_vector_backend()
            assert self._index is not None

            if self._index.ntotal <= 0 or not self._metadata:
                return[]

            search_k = min(
                max(safe_k * self.DEFAULT_MAX_SEARCH_MULTIPLIER, safe_k),
                int(self._index.ntotal),
                self.DEFAULT_MAX_SEARCH_LIMIT,
            )

            query_vector = self._embed([query])
            scores, indexes = self._index.search(query_vector, search_k)

            results: list[RetrievedMemory] = []
            seen_chunks: set[str] = set()

            for score, faiss_index in zip(scores[0], indexes[0]):
                position = int(faiss_index)

                if position < 0 or position >= len(self._metadata):
                    continue

                item = self._metadata[position]

                if session_id is not None and str(item.get("session_id")) != str(session_id):
                    continue

                chunk_id = str(item.get("chunk_id", ""))

                if not chunk_id or chunk_id in seen_chunks:
                    continue

                score_value = float(score)

                if score_value < float(min_score):
                    continue

                text = str(item.get("text", "")).strip()

                if not text:
                    continue

                seen_chunks.add(chunk_id)

                results.append(
                    RetrievedMemory(
                        chunk_id=chunk_id,
                        turn_id=str(item.get("turn_id", "")),
                        session_id=str(item.get("session_id", "")),
                        text=text,
                        score=score_value,
                        created_at=str(item.get("created_at", "")),
                        metadata=dict(item.get("metadata") or {}),
                    )
                )

                if len(results) >= safe_k:
                    break

        logger.info(
            "Relevant memory retrieved",
            extra={
                "context": {
                    "query_chars": len(query),
                    "requested_k": safe_k,
                    "returned": len(results),
                    "session_id": session_id,
                }
            },
        )

        return results

    def get_relevant_history_text(
        self,
        current_query: str,
        k: int = 3,
        *,
        session_id: Optional[str] = None,
        min_score: float = 0.0,
    ) -> str:
        memories = self.get_relevant_history(
            current_query=current_query,
            k=k,
            session_id=session_id,
            min_score=min_score,
        )

        if not memories:
            return ""

        lines = ["Relevant past conversation memory:"]
        for index, memory in enumerate(memories, start=1):
            lines.append(f"{index}. [{memory.created_at}] {memory.text}")

        return "\n".join(lines).strip()

    def count_turns(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM chat_memory_turns").fetchone()
            return int(row["count"])

    def count_chunks(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM chat_memory_chunks").fetchone()
            return int(row["count"])

    def rebuild_index_from_sqlite(self) -> None:
        with self._lock:
            self._load_embedding_model()
            assert self._embedding_dim is not None

            chunks = self._load_chunks_from_sqlite()
            self._index = faiss.IndexFlatIP(self._embedding_dim)
            self._metadata = []

            if chunks:
                texts = [str(chunk["text"]) for chunk in chunks]
                vectors = self._embed(texts)
                self._index.add(vectors)

                updated_chunks: list[dict[str, Any]] =[]

                for position, row in enumerate(chunks):
                    item = dict(row)
                    item["faiss_position"] = position
                    updated_chunks.append(item)

                    self._metadata.append(
                        {
                            "chunk_id": str(item["chunk_id"]),
                            "turn_id": str(item["turn_id"]),
                            "session_id": str(item["session_id"]),
                            "text": str(item["text"]),
                            "role_scope": str(item["role_scope"]),
                            "created_at": str(item["created_at"]),
                            "faiss_position": position,
                            "metadata": self._loads_json_dict(item.get("metadata_json")),
                        }
                    )

                self._replace_chunk_positions(updated_chunks)

            self._save_index_atomic()
            self._save_metadata_atomic()
            self._backend_ready = True

        logger.warning(
            "Memory FAISS index rebuilt from SQLite",
            extra={"context": {"chunks": len(self._metadata), "index_path": str(self.index_path)}},
        )

    def clear_all(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM chat_memory_chunks")
                conn.execute("DELETE FROM chat_memory_turns")
                conn.commit()

            self._load_embedding_model()
            assert self._embedding_dim is not None

            self._index = faiss.IndexFlatIP(self._embedding_dim)
            self._metadata =[]
            self._save_index_atomic()
            self._save_metadata_atomic()
            self._backend_ready = True

    def _ensure_vector_backend(self) -> None:
        if self._backend_ready:
            return

        self._load_embedding_model()
        assert self._embedding_dim is not None

        self._index = self._load_or_create_index()
        self._metadata = self._load_metadata()
        self._repair_metadata_alignment()
        self._backend_ready = True

    def _load_embedding_model(self) -> None:
        if self._embedding_model is not None:
            return

        try:
            try:
                self._embedding_model = SentenceTransformer(
                    self.embedding_model_name,
                    local_files_only=True,
                )
            except TypeError:
                self._embedding_model = SentenceTransformer(self.embedding_model_name)

            self._embedding_dim = int(self._embedding_model.get_sentence_embedding_dimension())

            logger.info(
                "Memory embedding model loaded",
                extra={
                    "context": {
                        "embedding_model": self.embedding_model_name,
                        "embedding_dim": self._embedding_dim,
                    }
                },
            )
        except Exception as exc:
            logger.error(
                "Failed to load memory embedding model",
                extra={"context": {"embedding_model": self.embedding_model_name}},
                exc_info=True,
            )
            raise RuntimeError(
                f"Failed to load embedding model for memory: {self.embedding_model_name}"
            ) from exc

    def _initialize_sqlite(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;

                CREATE TABLE IF NOT EXISTS chat_memory_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    user_text TEXT NOT NULL,
                    assistant_text TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_memory_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id TEXT NOT NULL UNIQUE,
                    turn_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    role_scope TEXT NOT NULL,
                    faiss_position INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(turn_id) REFERENCES chat_memory_turns(turn_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_chat_memory_turns_session
                    ON chat_memory_turns(session_id);

                CREATE INDEX IF NOT EXISTS idx_chat_memory_turns_created
                    ON chat_memory_turns(created_at);

                CREATE INDEX IF NOT EXISTS idx_chat_memory_chunks_turn
                    ON chat_memory_chunks(turn_id);

                CREATE INDEX IF NOT EXISTS idx_chat_memory_chunks_session
                    ON chat_memory_chunks(session_id);

                CREATE INDEX IF NOT EXISTS idx_chat_memory_chunks_position
                    ON chat_memory_chunks(faiss_position);

                CREATE INDEX IF NOT EXISTS idx_chat_memory_chunks_created
                    ON chat_memory_chunks(created_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.sqlite_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _insert_turn(self, turn: MemoryTurn) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO chat_memory_turns(
                    turn_id,
                    session_id,
                    user_text,
                    assistant_text,
                    metadata_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    turn.turn_id,
                    turn.session_id,
                    turn.user_text,
                    turn.assistant_text,
                    self._dumps_json(turn.metadata),
                    turn.created_at,
                ),
            )
            conn.commit()

    def _insert_chunks(self, chunks: Iterable[MemoryChunk]) -> None:
        rows =[
            (
                chunk.chunk_id,
                chunk.turn_id,
                chunk.session_id,
                chunk.text,
                chunk.role_scope,
                int(chunk.faiss_position),
                self._dumps_json(chunk.metadata),
                chunk.created_at,
            )
            for chunk in chunks
        ]

        if not rows:
            return

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO chat_memory_chunks(
                    chunk_id,
                    turn_id,
                    session_id,
                    text,
                    role_scope,
                    faiss_position,
                    metadata_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()

    def _load_chunks_from_sqlite(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT
                    chunk_id,
                    turn_id,
                    session_id,
                    text,
                    role_scope,
                    faiss_position,
                    metadata_json,
                    created_at
                FROM chat_memory_chunks
                ORDER BY id ASC
                """
            ).fetchall()

    def _replace_chunk_positions(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return

        with self._connect() as conn:
            conn.executemany(
                """
                UPDATE chat_memory_chunks
                SET faiss_position = ?
                WHERE chunk_id = ?
                """,
                [(int(chunk["faiss_position"]), str(chunk["chunk_id"])) for chunk in chunks],
            )
            conn.commit()

    def _load_or_create_index(self) -> faiss.Index:
        assert self._embedding_dim is not None

        if self.index_path.exists():
            try:
                index = faiss.read_index(str(self.index_path))

                if int(index.d) != int(self._embedding_dim):
                    logger.warning(
                        "Memory FAISS dimension mismatch; creating fresh index",
                        extra={
                            "context": {
                                "index_dim": int(index.d),
                                "embedding_dim": int(self._embedding_dim),
                            }
                        },
                    )
                    return faiss.IndexFlatIP(self._embedding_dim)

                return index
            except Exception:
                logger.warning(
                    "Failed to load memory FAISS index; creating fresh index",
                    extra={"context": {"index_path": str(self.index_path)}},
                    exc_info=True,
                )

        return faiss.IndexFlatIP(self._embedding_dim)

    def _load_metadata(self) -> list[dict[str, Any]]:
        if not self.metadata_path.exists():
            return[]

        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning(
                "Failed to load memory metadata",
                extra={"context": {"metadata_path": str(self.metadata_path)}},
                exc_info=True,
            )
            return[]

        if not isinstance(data, list):
            logger.warning(
                "Invalid memory metadata format; expected list",
                extra={"context": {"metadata_path": str(self.metadata_path)}},
            )
            return []

        valid: list[dict[str, Any]] =[]

        for item in data:
            if not isinstance(item, dict):
                continue
            if "chunk_id" not in item or "text" not in item:
                continue
            valid.append(item)

        return valid

    def _repair_metadata_alignment(self) -> None:
        assert self._index is not None

        if int(self._index.ntotal) == len(self._metadata):
            return

        logger.warning(
            "Memory FAISS/metadata mismatch detected; rebuilding from SQLite",
            extra={
                "context": {
                    "faiss_vectors": int(self._index.ntotal),
                    "metadata_entries": len(self._metadata),
                }
            },
        )

        self.rebuild_index_from_sqlite()

    def _save_index_atomic(self) -> None:
        assert self._index is not None

        fd, tmp_name = tempfile.mkstemp(
            prefix=".chat_history.",
            suffix=".faiss.tmp",
            dir=str(self.index_path.parent),
        )
        os.close(fd)

        tmp_path = Path(tmp_name)

        try:
            faiss.write_index(self._index, str(tmp_path))
            tmp_path.replace(self.index_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def _save_metadata_atomic(self) -> None:
        fd, tmp_name = tempfile.mkstemp(
            prefix=".chat_history_meta.",
            suffix=".json.tmp",
            dir=str(self.metadata_path.parent),
            text=True,
        )

        tmp_path = Path(tmp_name)

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(self._metadata, file, ensure_ascii=False, indent=2)
                file.write("\n")

            tmp_path.replace(self.metadata_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def _embed(self, texts: list[str]) -> np.ndarray:
        self._load_embedding_model()
        assert self._embedding_model is not None

        vectors = self._embedding_model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        if not isinstance(vectors, np.ndarray):
            vectors = np.asarray(vectors)

        return vectors.astype("float32")

    def _format_turn_for_memory(self, turn: MemoryTurn) -> str:
        parts =[]

        if turn.user_text:
            parts.append(f"User: {turn.user_text}")
        if turn.assistant_text:
            parts.append(f"AmbaAI: {turn.assistant_text}")

        parts.append(f"Time: {turn.created_at}")

        return "\n".join(parts).strip()

    def _chunk_text(self, text: str) -> list[str]:
        clean = " ".join((text or "").split())
        if not clean:
            return[]

        if len(clean) <= self.chunk_size_chars:
            return [clean]

        chunks: list[str] =[]
        start = 0
        text_length = len(clean)

        while start < text_length:
            end = min(start + self.chunk_size_chars, text_length)
            chunk = clean[start:end].strip()

            if chunk:
                chunks.append(chunk)

            if end >= text_length:
                break

            start = max(0, end - self.chunk_overlap_chars)

        return chunks

    def _chunk_to_metadata(self, chunk: MemoryChunk) -> dict[str, Any]:
        return {
            "chunk_id": chunk.chunk_id,
            "turn_id": chunk.turn_id,
            "session_id": chunk.session_id,
            "text": chunk.text,
            "role_scope": chunk.role_scope,
            "created_at": chunk.created_at,
            "faiss_position": int(chunk.faiss_position),
            "metadata": self._json_safe_dict(chunk.metadata),
        }

    @classmethod
    def _json_safe_dict(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}

        safe: dict[str, Any] = {}

        for key, item in value.items():
            clean_key = str(key)

            if isinstance(item, (str, int, float, bool)) or item is None:
                safe[clean_key] = item
            elif isinstance(item, (list, tuple)):
                safe[clean_key] =[
                    x if isinstance(x, (str, int, float, bool)) or x is None else str(x)
                    for x in item[:32]
                ]
            elif isinstance(item, dict):
                safe[clean_key] = {
                    str(k): v if isinstance(v, (str, int, float, bool)) or v is None else str(v)
                    for k, v in list(item.items())[:32]
                }
            else:
                safe[clean_key] = str(item)

        return safe

    @classmethod
    def _dumps_json(cls, value: dict[str, Any]) -> str:
        return json.dumps(cls._json_safe_dict(value), ensure_ascii=False)

    @staticmethod
    def _loads_json_dict(value: Any) -> dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = json.loads(str(value))
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

MemoryManager = VectorInfiniteMemory