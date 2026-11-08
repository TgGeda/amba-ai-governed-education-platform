from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib, json

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"

@dataclass(frozen=True, slots=True)
class EvidenceArtifactReference:
    evidence_id: str
    path: str
    sha256: str
    artifact_type: str
    source_artifact_links: tuple[str, ...]
    acceptance_passed: bool
    limitations: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]:
        return {"evidence_id":self.evidence_id,"path":self.path,"sha256":self.sha256,"artifact_type":self.artifact_type,"source_artifact_links":list(self.source_artifact_links),"acceptance_passed":self.acceptance_passed,"limitations":list(self.limitations)}
