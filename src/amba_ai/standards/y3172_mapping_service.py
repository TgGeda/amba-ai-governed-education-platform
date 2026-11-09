from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib,json,yaml
class Y3172MappingError(ValueError):pass
@dataclass(frozen=True,slots=True)
class Y3172MappingResult:
 payload:dict[str,Any]
 source_artifact_sha256:str

def _ids(root:Path)->tuple[set[str],set[str]]:
 records=yaml.safe_load((root/'kb/records/itu_y3172_verified_records.yaml').read_text(encoding='utf-8'))['records'];catalog=json.loads((root/'kb/passages/verified_passage_catalog.json').read_text(encoding='utf-8'))['passages'];return {x['record_id'] for x in records},{x['passage_id'] for x in catalog}
def build_y3172_mapping(root:Path,config_path:Path)->Y3172MappingResult:
 cfg=yaml.safe_load(config_path.read_text(encoding='utf-8'));source=root/cfg['source_artifact']
 if not source.is_file():raise Y3172MappingError(f'missing source artifact: {cfg["source_artifact"]}')
 runtime=json.loads(source.read_text(encoding='utf-8'))
 if len(runtime.get('stages',[]))!=4 or not runtime.get('final_audit_verification',{}).get('valid'):raise Y3172MappingError('source artifact is not a verified four-stage run')
 records,passages=_ids(root);entries=cfg['entries'];mapping_ids=[x['mapping_id'] for x in entries]
 if len(entries)!=13 or len(mapping_ids)!=len(set(mapping_ids)):raise Y3172MappingError('mapping requires 13 unique entries')
 for entry in entries:
  missing_records=sorted(set(entry['y3172_record_ids'])-records);missing_passages=sorted(set(entry['approved_passage_ids'])-passages);missing_files=sorted(p for p in entry['implementation_files'] if not (root/p).exists())
  if missing_records or missing_passages or missing_files:raise Y3172MappingError(f"{entry['mapping_id']} unresolved references: records={missing_records}, passages={missing_passages}, files={missing_files}")
  if not entry['runtime_evidence_pointers'] or not entry['limitations']:raise Y3172MappingError(f"{entry['mapping_id']} requires evidence pointers and limitations")
 payload={'schema_version':cfg['schema_version'],'artifact_type':'y3172_architecture_mapping','mapping_id':cfg['mapping_id'],'standard_reference':cfg['standard_reference'],'mapping_type':cfg['mapping_type'],'formal_conformance':False,'itu_certification':False,'source_artifact':cfg['source_artifact'],'source_artifact_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'entry_count':len(entries),'entries':entries,'claim_boundary':'Interpreted project-architecture mapping; not formal ITU-T Y.3172 conformance testing or ITU certification.'}
 return Y3172MappingResult(payload,payload['source_artifact_sha256'])
