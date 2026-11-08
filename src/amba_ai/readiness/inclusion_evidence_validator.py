from __future__ import annotations
from pathlib import Path
from typing import Any
import json,yaml
from .evidence_artifact_models import sha256_file
class InclusionEvidenceError(ValueError):pass

def validate_inclusion_evidence(root:Path,requirements_path:Path)->dict[str,Any]:
 req=yaml.safe_load(requirements_path.read_text(encoding='utf-8'));checks=[];refs=[]
 for rel in req['required_protocols']:
  p=root/rel;ok=p.is_file() and bool(p.read_text(encoding='utf-8').strip());checks.append({'check_id':f'protocol:{rel}','passed':ok,'detail':'protocol present' if ok else 'protocol missing'});
  if ok:refs.append({'path':rel,'sha256':sha256_file(p)})
 objects={}
 for rel in req['required_artifacts'][:-1]:
  p=root/rel
  try:data=json.loads(p.read_text(encoding='utf-8'));objects[rel]=data;ok=True;refs.append({'path':rel,'sha256':sha256_file(p)})
  except Exception:ok=False
  checks.append({'check_id':f'artifact:{rel}','passed':ok,'detail':'artifact parsed' if ok else 'artifact missing or invalid'})
 acc=objects.get('submission/artifacts/accessibility_evaluation.json',{});checks.append({'check_id':'accessibility:tested-and-untested','passed':bool(acc.get('tested_criteria')) and bool(acc.get('untested_criteria')) and acc.get('formal_certification') is False,'detail':'tested/untested criteria and non-certification boundary'})
 offline=objects.get('submission/artifacts/offline_operation_evaluation.json',{});checks.append({'check_id':'offline:result','passed':offline.get('completed') is True and bool(offline.get('scenarios')),'detail':'offline or constrained-connectivity result'})
 review=objects.get('submission/artifacts/representative_review_record.json',{});review_ok=review.get('completed') is True and review.get('personal_data_included') is False and bool(review.get('scope')) and bool(review.get('limitations')) and bool(review.get('outcome_measures'));checks.append({'check_id':'representative-review:completed','passed':review_ok,'detail':'real representative review completed without personal data' if review_ok else 'representative review incomplete; generator does not fabricate it'})
 source=root/req['acceptance']['source_artifact'];checks.append({'check_id':'source-artifact:verified','passed':source.is_file(),'detail':'verified four-stage artifact linked'});
 if source.is_file():refs.append({'path':req['acceptance']['source_artifact'],'sha256':sha256_file(source)})
 passed=all(x['passed'] for x in checks)
 return {'schema_version':'1.0.0','evidence_id':req['evidence_id'],'metric_id':req['metric_id'],'artifact_type':'inclusion_outcome_evidence','acceptance_passed':passed,'acceptance_checks':checks,'artifact_references':sorted(refs,key=lambda x:x['path']),'target_status':req['acceptance']['target_status_after_acceptance'] if passed else None,'formal_accessibility_certification':False,'limitations':[] if passed else ['D11 remains unaccepted until a real representative review and all required evaluations pass.','No participant, review, or inclusion outcome is fabricated by the generator.']}
