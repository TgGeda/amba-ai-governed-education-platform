from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from threading import RLock
from typing import Any

from .models import DocumentVersion


class SourceControl:
    def __init__(self, manifest_path: str | Path) -> None:
        self.path = Path(manifest_path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def register(
        self,
        document_id: str,
        title: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> DocumentVersion:
        checksum = hashlib.sha256(content).hexdigest()
        with self._lock:
            manifest = self._load()
            history = manifest.setdefault(str(document_id), [])

            for item in history:
                if item["checksum"] == checksum:
                    return DocumentVersion(**item)
                item["active"] = False

            new_version_num = len(history) + 1
            version = DocumentVersion(
                document_id=str(document_id),
                version_id=f"v{new_version_num}",
                checksum=checksum,
                title=title,
                active=True,
                metadata=dict(metadata or {}),
            )

            history.append(
                {
                    "document_id": version.document_id,
                    "version_id": version.version_id,
                    "checksum": version.checksum,
                    "title": version.title,
                    "active": version.active,
                    "created_at": version.created_at,
                    "metadata": version.metadata,
                }
            )
            self._save(manifest)
            return version

    def active_version(self, document_id: str) -> DocumentVersion | None:
        with self._lock:
            records = self._load().get(str(document_id), [])
            for item in reversed(records):
                if item.get("active"):
                    return DocumentVersion(**item)
            return None

    def list_versions(self, document_id: str) -> list[DocumentVersion]:
        with self._lock:
            records = self._load().get(str(document_id), [])
            return [DocumentVersion(**item) for item in records]

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, manifest: dict[str, Any]) -> None:
        temp_file = self.path.with_suffix(f".tmp_{os.getpid()}_{int(time.time() * 1000)}")
        serialized = json.dumps(manifest, ensure_ascii=False, indent=2)
        temp_file.write_text(serialized, encoding="utf-8")

        for attempt in range(5):
            try:
                temp_file.replace(self.path)
                return
            except PermissionError:
                time.sleep(0.05 * (attempt + 1))

        if temp_file.exists():
            try:
                os.remove(self.path)
                temp_file.replace(self.path)
            except OSError:
                pass