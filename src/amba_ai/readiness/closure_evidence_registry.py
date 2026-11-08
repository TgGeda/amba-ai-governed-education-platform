from __future__ import annotations
from pathlib import Path
from typing import Any
import json
from .evidence_artifact_models import canonical_json,sha256_file
class ClosureEvidenceRegistryError(ValueError):pass

def build_registry(root:Path,records:list[dict[str,Any]])->dict[str,Any]:
 ids=[x['evidence_id'] for x in records]
 if len(ids)!=len(set(ids)):raise ClosureEvidenceRegistryError('duplicate evidence_id')
 return {'schema_version':'1.0.0','registry_id':'AMBA-GOV-READINESS-CLOSURE-EVIDENCE-REGISTRY-001','records':sorted(records,key=lambda x:x['evidence_id']),'accepted_metric_ids':sorted(x['metric_id'] for x in records if x['acceptance_passed']),'pending_metric_ids':sorted(x['metric_id'] for x in records if not x['acceptance_passed'])}

def write_registry(path:Path,registry:dict[str,Any])->str:
 text=canonical_json(registry);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n');return sha256_file(path)
