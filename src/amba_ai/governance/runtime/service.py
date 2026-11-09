from __future__ import annotations
import hashlib,json,re,uuid
from pathlib import Path
from typing import Any,Mapping
from .guardrails import assess_content,assess_file,sha256_file
from .models import ChunkGovernanceDecision,Decision,GenerationDecision,GovernedRetrievalResult,IngestionDecision,RiskFinding,RuntimeGovernanceGateError,RuntimeGovernanceReviewRequired
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
 def assess_chunks(self,document_id:int,chunks:list[Any])->tuple[ChunkGovernanceDecision,...]:
  decisions=[]
  default_ops=('summarize_document','generate_notes','generate_study_assets','tutor_answer','tutor_chat','generate_flashcards','generate_quiz')
  for chunk in chunks:
   data=dict(chunk) if isinstance(chunk,dict) or hasattr(chunk,'keys') else {'id':getattr(chunk,'id',None),'text':getattr(chunk,'text','')}
   chunk_id=int(data.get('id') or data.get('chunk_id')); text=str(data.get('text') or '')
   if not text.strip():raise RuntimeGovernanceGateError(f'Chunk {chunk_id} has no text.')
   digest=hashlib.sha256(text.encode('utf-8')).hexdigest(); findings=[];controls=['ignore_embedded_instructions']
   low=text.lower()
   if re.search(r'ignore (?:(?:all|any|the) )?(?:previous|prior|system) instructions|reveal (?:the )?(?:system|developer) prompt',low,re.I):findings.append(RiskFinding('PROMPT_INJECTION','high','Embedded instructions are non-authoritative.'))
   if re.search(r'answer\s*key|final\s*exam|live\s*exam|graded\s*assessment|confidential\s*marking',low,re.I):findings.append(RiskFinding('PROTECTED_ASSESSMENT','critical','Protected assessment chunk requires teacher review.'))
   if re.search(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|\bstudent\s*(?:id|number)\s*[:#]?\s*[A-Z0-9-]{3,}\b',text,re.I):findings.append(RiskFinding('PERSONAL_DATA','high','Possible learner identifier detected.'));controls.append('redact_personal_identifiers')
   blocked=any(x.code in {'PROMPT_INJECTION','PROTECTED_ASSESSMENT'} or x.severity=='critical' for x in findings)
   decision=Decision.REVIEW if blocked else Decision.RESTRICTED
   decisions.append(ChunkGovernanceDecision(chunk_id,document_id,digest,decision,'untrusted_source',not blocked,not blocked,default_ops if not blocked else (),tuple(findings),tuple(dict.fromkeys(controls)),'pending_review' if blocked else 'approved'))
  self.repository.save_chunk_decisions([d.to_dict() for d in decisions])
  self.repository.receipt('chunks_assessed',{'document_id':document_id,'chunk_count':len(decisions),'indexed_count':sum(d.indexing_permitted for d in decisions),'excluded_chunk_ids':[d.chunk_id for d in decisions if not d.indexing_permitted]},document_id)
  return tuple(decisions)
 def permitted_chunk_ids(self,document_id:int,operation:str)->frozenset[int]:
  decisions=self.repository.get_chunk_decisions(document_id)
  if not decisions:raise RuntimeGovernanceGateError(f'Document {document_id} has no chunk governance decisions.')
  return self.repository.permitted_chunk_ids(document_id,operation)
 def filter_retrieval(self,document_id:int,operation:str,hits:list[Any])->GovernedRetrievalResult:
  allowed=self.permitted_chunk_ids(document_id,operation); kept=[];excluded=[]
  for hit in hits:
   chunk_id=hit.get('chunk_id') if isinstance(hit,dict) else getattr(hit,'chunk_id',None)
   if chunk_id is not None and int(chunk_id) in allowed:kept.append(hit)
   elif chunk_id is not None:excluded.append(int(chunk_id))
  returned_ids=[int(item.get('chunk_id') if isinstance(item,dict) else getattr(item,'chunk_id')) for item in kept]
  rid=self.repository.receipt('retrieval_filtered',{'document_id':document_id,'operation':operation,'returned_chunk_ids':returned_ids,'excluded_chunk_ids':excluded},document_id,operation)
  return GovernedRetrievalResult(tuple(kept),tuple(excluded),('chunk_allowlist','operation_filter'),(),(),rid)

