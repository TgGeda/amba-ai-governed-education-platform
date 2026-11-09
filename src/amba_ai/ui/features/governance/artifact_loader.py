from __future__ import annotations
from pathlib import Path
from typing import Any
import json
from amba_ai.submission.manifest_verifier import verify_manifest
from .data_classes import DashboardSnapshot
class DashboardArtifactError(ValueError): pass
_REQUIRED={'evidence_chain':'submission/artifacts/four_stage_evidence_chain.json','agents':'submission/artifacts/agent_architecture.json','y3172':'submission/artifacts/y3172_architecture_mapping.json','readiness':'submission/artifacts/readiness_reflection.json','evidence_plan':'submission/artifacts/readiness_evidence_plan.json','closure_registry':'submission/artifacts/readiness_closure_evidence_registry.json','manifest':'submission/artifacts/submission_manifest.json','passages':'kb/passages/verified_passage_catalog.json'}
def _load(root:Path,relative:str)->dict[str,Any]:
 path=root/relative
 if not path.is_file():raise DashboardArtifactError(f'required dashboard artifact missing: {relative}')
 try:value=json.loads(path.read_text(encoding='utf-8'))
 except Exception as exc:raise DashboardArtifactError(f'invalid JSON dashboard artifact: {relative}') from exc
 if not isinstance(value,dict):raise DashboardArtifactError(f'dashboard artifact must be an object: {relative}')
 return value
def load_dashboard_snapshot(root:Path)->DashboardSnapshot:
 data={k:_load(root,v) for k,v in _REQUIRED.items()};chain=data['evidence_chain'];y=data['y3172'];a=data['agents'];r=data['readiness']
 if len(chain.get('stages',()))!=4:raise DashboardArtifactError('four verified scenarios are required')
 if not chain.get('final_audit_verification',{}).get('valid'):raise DashboardArtifactError('final audit verification is invalid')
 if a.get('agent_count')!=8:raise DashboardArtifactError('eight bounded agents are required')
 if y.get('entry_count')!=13:raise DashboardArtifactError('thirteen Y.3172 mappings are required')
 if y.get('formal_conformance') is not False or y.get('itu_certification') is not False:raise DashboardArtifactError('unsafe Y.3172 claim boundary')
 if r.get('assessment_subject',{}).get('national_assessment') is not False:raise DashboardArtifactError('unsafe national-assessment boundary')
 passages={str(x['passage_id']):x for x in data['passages'].get('passages',())}
 verification=verify_manifest(root,root/_REQUIRED['manifest'])
 return DashboardSnapshot(chain,a,y,r,data['evidence_plan'],data['closure_registry'],data['manifest'],verification,passages)
