from __future__ import annotations
from pathlib import Path
from typing import Any
import json, yaml
from .evidence_artifact_models import sha256_file

_PLACEHOLDERS=("choose a license","license to be determined","insert license","tbd")
class OpenSourceEvidenceError(ValueError): pass

def validate_open_source_evidence(root:Path,requirements_path:Path)->dict[str,Any]:
 req=yaml.safe_load(requirements_path.read_text(encoding='utf-8')); checks=[]; refs=[]
 for rel in req['required_repository_files']:
  path=root/rel; exists=path.is_file(); nonempty=exists and bool(path.read_text(encoding='utf-8',errors='replace').strip()); valid=exists and nonempty
  if rel=='LICENSE' and valid: valid=not any(x in path.read_text(encoding='utf-8',errors='replace').lower() for x in _PLACEHOLDERS)
  checks.append({'check_id':f'file:{rel}','passed':valid,'detail':'repository file present and acceptable' if valid else 'missing, empty, or placeholder'});
  if valid: refs.append({'path':rel,'sha256':sha256_file(path)})
 sbom=root/'submission/artifacts/sbom.cdx.json'
 if sbom.is_file():
  data=json.loads(sbom.read_text(encoding='utf-8'));ok=data.get('bomFormat')=='CycloneDX' and data.get('specVersion')=='1.5' and isinstance(data.get('components'),list);checks.append({'check_id':'sbom:cyclonedx-1.5','passed':ok,'detail':'CycloneDX 1.5 structure validated' if ok else 'invalid SBOM structure'});refs.append({'path':'submission/artifacts/sbom.cdx.json','sha256':sha256_file(sbom)})
 else: checks.append({'check_id':'sbom:cyclonedx-1.5','passed':False,'detail':'SBOM missing'})
 passed=all(x['passed'] for x in checks)
 return {'schema_version':'1.0.0','evidence_id':req['evidence_id'],'metric_id':req['metric_id'],'artifact_type':'open_source_governance_evidence','acceptance_passed':passed,'acceptance_checks':checks,'artifact_references':sorted(refs,key=lambda x:x['path']),'target_status':req['acceptance']['target_status_after_acceptance'] if passed else None,'limitations':[] if passed else ['Open-source governance remains unaccepted until every required file and deterministic SBOM passes.','No software license was inferred or selected by automation.']}
