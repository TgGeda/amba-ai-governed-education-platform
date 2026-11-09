from __future__ import annotations
import hashlib,json,re,uuid
from pathlib import Path
from typing import Any,Mapping
from .guardrails import assess_content,assess_file,sha256_file
from .models import Decision,GenerationDecision,IngestionDecision,RiskFinding,RuntimeGovernanceGateError,RuntimeGovernanceReviewRequired
from .repository import RuntimeGovernanceRepository

class RuntimeEducationGovernanceService:
 def __init__(self,database_path:str|Path):self.repository=RuntimeGovernanceRepository(database_path)
 def preflight_file(self,path:str|Path)->tuple[str,tuple[RiskFinding,...]]:
  digest,findings=assess_file(Path(path))
  if any(x.severity=='critical' for x in findings):raise RuntimeGovernanceGateError('; '.join(x.message for x in findings))
  return digest,findings
 def assess_ingestion(self,path:str|Path,text:str)->IngestionDecision:
  digest,findings=self.preflight_file(path); decision=assess_content(text,digest)
  payload=decision.to_dict(); payload['file_findings']=[x.__dict__ for x in findings]
  rid=self.repository.receipt('ingestion_assessed',payload)
  return IngestionDecision(decision.decision,decision.source_sha256,decision.findings,decision.permitted_operations,decision.restricted_operations,decision.controls,decision.permits_persistence,decision.permits_indexing,rid)
 def record_document(self,document_id:int,decision:IngestionDecision):self.repository.save_document(document_id,decision.to_dict())
 def authorize_generation(self,document_id:int,operation:str,source_path:str|None=None)->GenerationDecision:
  record=self.repository.get_document(document_id)
  if not record:raise RuntimeGovernanceGateError(f'Document {document_id} has no runtime governance record.')
  if operation in set(record['restricted']):raise RuntimeGovernanceGateError(f'{operation} is restricted for document {document_id}.')
  if operation not in set(record['permitted']):raise RuntimeGovernanceReviewRequired(f'{operation} requires authorized review for document {document_id}.')
  digest_ok=True
  if source_path and Path(source_path).is_file():digest_ok=sha256_file(Path(source_path))==record['source_sha256']
  if not digest_ok:raise RuntimeGovernanceGateError(f'Source digest changed for document {document_id}.')
  request_id='EDU-REQ-'+uuid.uuid4().hex[:20].upper(); rid=self.repository.receipt('generation_authorized',{'request_id':request_id,'document_id':document_id,'operation':operation,'controls':record['controls']},document_id,operation)
  decision=GenerationDecision(Decision.RESTRICTED,document_id,operation,record['source_sha256'],True,tuple(record['controls']),(),rid)
  self.repository.record_generation(request_id,document_id,operation,decision.decision.value,decision.source_sha256,decision.to_dict())
  return decision
 def validate_output(self,document_id:int,operation:str,result_material:Mapping[str,Any])->str:
  text=json.dumps(result_material,sort_keys=True,default=str)
  findings=[]
  if re.search(r'(?i)(system prompt|developer message|ignore previous instructions)',text):findings.append('prompt_leakage')
  if re.search(r'(?i)targeted advertis|send learner profile|buy now',text):findings.append('commercial_manipulation')
  if findings:raise RuntimeGovernanceGateError('Output guardrail blocked: '+', '.join(findings))
  digest=hashlib.sha256(text.encode()).hexdigest();return self.repository.receipt('output_validated',{'document_id':document_id,'operation':operation,'output_sha256':digest,'status':'passed'},document_id,operation)
