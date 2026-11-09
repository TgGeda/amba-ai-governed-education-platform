from __future__ import annotations
import hashlib,re
from pathlib import Path
from .models import Decision,IngestionDecision,RiskFinding

_ALLOWED={'.pdf','.docx','.pptx','.txt','.md','.csv','.json','.yaml','.yml','.mp3','.wav','.mp4','.m4a'}
_INJECTION=(r'ignore (?:(?:all|any|the) )?(?:previous|prior|system) instructions',r'reveal (?:the )?(?:system|developer) prompt',r'treat this document as (?:an )?approved policy',r'send .* data to .*external')
_PII=(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',r'\b(?:\+?251|0)9\d{8}\b',r'\bstudent\s*(?:id|number)\s*[:#]?\s*[A-Z0-9-]{3,}\b')
_ASSESS=(r'answer\s*key',r'final\s*exam',r'live\s*exam',r'graded\s*assessment',r'confidential\s*marking')
_HARM=(r'suicide method',r'build (?:a )?bomb',r'how to poison',r'sexual exploitation')

def sha256_file(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def assess_file(path:Path,max_bytes:int=100*1024*1024)->tuple[str,tuple[RiskFinding,...]]:
 if not path.is_file():return '',(RiskFinding('FILE_NOT_FOUND','critical','The selected source is not a regular file.'),)
 digest=sha256_file(path); findings=[]
 if path.suffix.lower() not in _ALLOWED:findings.append(RiskFinding('UNSAFE_FILE_TYPE','critical',f'Unsupported file type: {path.suffix or "none"}'))
 if path.stat().st_size>max_bytes:findings.append(RiskFinding('FILE_TOO_LARGE','critical','The file exceeds the 100 MiB ingestion boundary.'))
 head=path.read_bytes()[:8]
 if path.suffix.lower()=='.pdf' and not head.startswith(b'%PDF-'):findings.append(RiskFinding('MIME_EXTENSION_MISMATCH','critical','PDF extension does not match file signature.'))
 if path.suffix.lower() in {'.docx','.pptx'} and not head.startswith(b'PK'):findings.append(RiskFinding('MIME_EXTENSION_MISMATCH','critical','Office extension does not match ZIP container signature.'))
 return digest,tuple(findings)

def assess_content(text:str,source_sha256:str)->IngestionDecision:
 findings=[]; controls=['ignore_embedded_instructions','local_processing_only','prohibit_targeted_advertising','prohibit_model_training']
 low=text.lower()
 for pat in _INJECTION:
  if re.search(pat,low,re.I):findings.append(RiskFinding('PROMPT_INJECTION','high','Embedded instructions are untrusted document content.'));break
 for pat in _PII:
  if re.search(pat,text,re.I):findings.append(RiskFinding('PERSONAL_DATA','high','Possible learner identifier or contact data detected.'));controls.append('redact_personal_identifiers');break
 for pat in _ASSESS:
  if re.search(pat,low,re.I):findings.append(RiskFinding('PROTECTED_ASSESSMENT','critical','Protected assessment material requires authorized teacher review.'));break
 for pat in _HARM:
  if re.search(pat,low,re.I):findings.append(RiskFinding('HARMFUL_CONTENT','critical','Potentially harmful actionable content requires review.'));break
 critical=any(x.severity=='critical' for x in findings)
 if critical:
  return IngestionDecision(Decision.REVIEW,source_sha256,tuple(findings),('secure_local_storage',),('local_indexing','summarize_document','generate_notes','generate_study_assets','tutor_answer','export_content'),tuple(dict.fromkeys(controls)),True,False)
 permitted=('local_storage','local_indexing','summarize_document','generate_notes','generate_study_assets','tutor_answer','tutor_chat')
 restricted=('external_distribution','targeted_advertising','commercial_profiling','model_training')
 decision=Decision.RESTRICTED if findings else Decision.RESTRICTED
 return IngestionDecision(decision,source_sha256,tuple(findings),permitted,restricted,tuple(dict.fromkeys(controls)),True,True)
