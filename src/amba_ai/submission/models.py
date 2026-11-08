from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True, slots=True)
class ManifestEntry:
    path: str
    artifact_type: str
    sha256: str
    size_bytes: int
    media_type: str
    validation_status: str
    source_links: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]:
        return {"path":self.path,"artifact_type":self.artifact_type,"sha256":self.sha256,"size_bytes":self.size_bytes,"media_type":self.media_type,"validation_status":self.validation_status,"source_links":list(self.source_links)}

@dataclass(frozen=True, slots=True)
class SubmissionManifest:
    manifest_id: str
    repository_commit: str
    entries: tuple[ManifestEntry, ...]
    claim_boundaries: dict[str, bool]
    pending_gates: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]:
        return {"schema_version":"1.0.0","manifest_id":self.manifest_id,"repository_commit":self.repository_commit,"entries":[x.to_dict() for x in self.entries],"claim_boundaries":dict(sorted(self.claim_boundaries.items())),"pending_gates":list(self.pending_gates)}
