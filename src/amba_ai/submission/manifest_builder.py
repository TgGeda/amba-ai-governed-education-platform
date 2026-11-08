from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from typing import Any
import json,subprocess,yaml
from .json_pointer import resolve_json_pointer
from .models import ManifestEntry,SubmissionManifest
class ManifestBuildError(ValueError):pass

def _hash(path:Path)->str:return sha256(path.read_bytes()).hexdigest()
def _commit(root:Path)->str:
    result=subprocess.run(["git","rev-parse","HEAD"],cwd=root,text=True,capture_output=True,check=True);return result.stdout.strip()
def _media(path:Path)->str:return {'.json':'application/json','.yaml':'application/yaml','.yml':'application/yaml','.md':'text/markdown'}.get(path.suffix.lower(),'application/octet-stream')
def build_manifest(root:Path,requirements_path:Path)->SubmissionManifest:
    req=yaml.safe_load(requirements_path.read_text(encoding='utf-8'));entries=[];artifact_paths=[]
    for item in req['required_artifacts']:
        rel=item['path'];path=root/rel
        if not path.is_file():raise ManifestBuildError(f"required artifact missing: {rel}")
        try:data=json.loads(path.read_text(encoding='utf-8'))
        except Exception as exc:raise ManifestBuildError(f"invalid JSON artifact: {rel}") from exc
        for assertion in item.get('required_json_assertions',[]):
            actual=resolve_json_pointer(data,assertion['pointer'])
            if actual!=assertion['equals']:raise ManifestBuildError(f"assertion failed for {rel} {assertion['pointer']}: {actual!r}")
        artifact_paths.append(rel);entries.append(ManifestEntry(rel,item['artifact_type'],_hash(path),path.stat().st_size,_media(path),'verified',()))
    for rel in req['required_source_records']:
        path=root/rel
        if not path.is_file():raise ManifestBuildError(f"required source record missing: {rel}")
        entries.append(ManifestEntry(rel,'source_record',_hash(path),path.stat().st_size,_media(path),'verified',tuple(artifact_paths)))
    closure=json.loads((root/'submission/artifacts/readiness_closure_evidence_registry.json').read_text(encoding='utf-8'))
    pending=tuple(f"metric:{x}" for x in closure.get('pending_metric_ids',[]))
    return SubmissionManifest(req['manifest_id'],_commit(root),tuple(sorted(entries,key=lambda x:x.path)),req['claim_boundaries'],pending)
