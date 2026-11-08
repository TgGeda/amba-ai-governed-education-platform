from __future__ import annotations
from pathlib import Path
from typing import Any
import hashlib,json,yaml
from .models import AssessmentStatus,ReadinessFinding
class ReadinessMappingError(ValueError): pass
def load_artifact(path:Path)->tuple[dict[str,Any],str]:
 raw=path.read_bytes(); data=json.loads(raw.decode('utf-8'))
 if len(data.get('stages',[]))!=4 or not data.get('final_audit_verification',{}).get('valid'): raise ReadinessMappingError('evidence artifact is not a verified four-stage run')
 if not all(s.get('invariant_verification',{}).get('valid') for s in data['stages']): raise ReadinessMappingError('stage invariant verification failed')
 return data,hashlib.sha256(raw).hexdigest()
def load_mappings(path:Path)->tuple[ReadinessFinding,...]:
 raw=yaml.safe_load(path.read_text(encoding='utf-8')); out=[]
 for row in raw['mappings']:
  if len(row)==8: row=(*row,[])
  mid,typ,name,status,rationale,pointers,passages,y3172,limitations=row
  out.append(ReadinessFinding(mid,typ,mid,name,AssessmentStatus(status),rationale,tuple(pointers),tuple(passages),tuple(y3172),tuple(limitations)))
 if len([x for x in out if x.framework_element_type=='factor'])!=6 or len([x for x in out if x.framework_element_type=='dimension'])!=13: raise ReadinessMappingError('mapping must preserve all 6 factors and 13 dimensions')
 return tuple(out)
def validate_references(findings,passage_catalog:Path,y3172_records:Path)->None:
 passages={x['passage_id'] for x in json.loads(passage_catalog.read_text(encoding='utf-8'))['passages']}
 yids={x['record_id'] for x in yaml.safe_load(y3172_records.read_text(encoding='utf-8'))['records']}
 missing_p=sorted({p for f in findings for p in f.passage_ids if p not in passages}); missing_y=sorted({p for f in findings for p in f.y3172_record_ids if p not in yids})
 if missing_p or missing_y: raise ReadinessMappingError(f'unresolved evidence references: passages={missing_p}, y3172={missing_y}')
