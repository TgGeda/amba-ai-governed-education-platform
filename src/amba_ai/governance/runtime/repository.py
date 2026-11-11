from __future__ import annotations
import json,sqlite3,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

_SCHEMA='''
CREATE TABLE IF NOT EXISTS runtime_document_governance(id INTEGER PRIMARY KEY,document_id INTEGER UNIQUE,source_sha256 TEXT NOT NULL,decision TEXT NOT NULL,permitted_json TEXT NOT NULL,restricted_json TEXT NOT NULL,controls_json TEXT NOT NULL,findings_json TEXT NOT NULL,receipt_id TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime_chunk_governance(id INTEGER PRIMARY KEY,chunk_id INTEGER UNIQUE NOT NULL,document_id INTEGER NOT NULL,chunk_sha256 TEXT NOT NULL,decision TEXT NOT NULL,trust_level TEXT NOT NULL,indexing_permitted INTEGER NOT NULL,generation_eligible INTEGER NOT NULL,operations_json TEXT NOT NULL,findings_json TEXT NOT NULL,controls_json TEXT NOT NULL,review_status TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_runtime_chunk_document ON runtime_chunk_governance(document_id);
CREATE TABLE IF NOT EXISTS runtime_generation_governance(id INTEGER PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,document_id INTEGER NOT NULL,operation TEXT NOT NULL,decision TEXT NOT NULL,source_sha256 TEXT NOT NULL,details_json TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime_output_governance(id INTEGER PRIMARY KEY,output_id TEXT UNIQUE NOT NULL,request_id TEXT,document_id INTEGER NOT NULL,operation TEXT NOT NULL,decision TEXT NOT NULL,raw_output_sha256 TEXT NOT NULL,sanitized_output_sha256 TEXT NOT NULL,evidence_json TEXT NOT NULL,trace_id TEXT NOT NULL,receipt_id TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_runtime_output_document ON runtime_output_governance(document_id);
CREATE TABLE IF NOT EXISTS runtime_governance_receipts(id INTEGER PRIMARY KEY,receipt_id TEXT UNIQUE NOT NULL,event_type TEXT NOT NULL,document_id INTEGER,operation TEXT,payload_json TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime_governance_reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,review_id TEXT UNIQUE NOT NULL,subject_type TEXT NOT NULL,subject_id TEXT NOT NULL,document_id INTEGER NOT NULL,disposition TEXT NOT NULL,reviewer_role TEXT NOT NULL,rationale TEXT NOT NULL,redactions_json TEXT NOT NULL,supersedes_review_id TEXT,decided_at TEXT NOT NULL,receipt_id TEXT NOT NULL,published_at TEXT,effective_text TEXT,FOREIGN KEY(supersedes_review_id) REFERENCES runtime_governance_reviews(review_id));
CREATE INDEX IF NOT EXISTS idx_runtime_reviews_subject ON runtime_governance_reviews(subject_type,subject_id,id);
CREATE INDEX IF NOT EXISTS idx_runtime_reviews_document ON runtime_governance_reviews(document_id,id);
CREATE TABLE IF NOT EXISTS runtime_document_tombstones(id INTEGER PRIMARY KEY AUTOINCREMENT,document_id INTEGER UNIQUE NOT NULL,subject_id TEXT NOT NULL,source_sha256 TEXT NOT NULL,chunk_set_sha256 TEXT NOT NULL,event_type TEXT NOT NULL,decision TEXT NOT NULL,status TEXT NOT NULL,trace_id TEXT NOT NULL,receipt_id TEXT,requested_at TEXT NOT NULL,completed_at TEXT);
'''
class RuntimeGovernanceRepository:
 def __init__(self,path:str|Path):self.path=Path(path);self.ensure_schema()
 def _connect(self):c=sqlite3.connect(str(self.path));c.row_factory=sqlite3.Row;return c
 def ensure_schema(self):
  with self._connect() as c:c.executescript(_SCHEMA)
 def receipt(self,event_type:str,payload:dict[str,Any],document_id:int|None=None,operation:str|None=None)->str:
  rid='EDU-GOV-'+uuid.uuid4().hex[:20].upper();now=datetime.now(timezone.utc).isoformat()
  with self._connect() as c:c.execute('INSERT INTO runtime_governance_receipts(receipt_id,event_type,document_id,operation,payload_json,created_at) VALUES(?,?,?,?,?,?)',(rid,event_type,document_id,operation,json.dumps(payload,sort_keys=True,default=str),now))
  return rid
 def save_document(self,document_id:int,decision:dict[str,Any]):
  now=datetime.now(timezone.utc).isoformat()
  with self._connect() as c:c.execute('INSERT OR REPLACE INTO runtime_document_governance(document_id,source_sha256,decision,permitted_json,restricted_json,controls_json,findings_json,receipt_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(document_id,decision['source_sha256'],decision['decision'],json.dumps(decision['permitted_operations']),json.dumps(decision['restricted_operations']),json.dumps(decision['controls']),json.dumps(decision['findings']),decision['receipt_id'],now))
 def get_document(self,document_id:int)->dict[str,Any]|None:
  with self._connect() as c:r=c.execute('SELECT * FROM runtime_document_governance WHERE document_id=?',(document_id,)).fetchone()
  if not r:return None
  d=dict(r)
  for k in ('permitted_json','restricted_json','controls_json','findings_json'):d[k[:-5]]=json.loads(d.pop(k))
  return d
 def record_generation(self,request_id:str,document_id:int,operation:str,decision:str,source_sha256:str,details:dict[str,Any]):
  with self._connect() as c:c.execute('INSERT INTO runtime_generation_governance(request_id,document_id,operation,decision,source_sha256,details_json,created_at) VALUES(?,?,?,?,?,?,?)',(request_id,document_id,operation,decision,source_sha256,json.dumps(details,sort_keys=True,default=str),datetime.now(timezone.utc).isoformat()))
 def save_chunk_decisions(self,decisions:list[dict[str,Any]]):
  now=datetime.now(timezone.utc).isoformat()
  rows=[(int(d['chunk_id']),int(d['document_id']),d['chunk_sha256'],d['decision'],d['trust_level'],int(bool(d['indexing_permitted'])),int(bool(d['generation_eligible'])),json.dumps(d['operations_permitted']),json.dumps(d['findings']),json.dumps(d['controls']),d['review_status'],now) for d in decisions]
  with self._connect() as c:c.executemany('INSERT OR REPLACE INTO runtime_chunk_governance(chunk_id,document_id,chunk_sha256,decision,trust_level,indexing_permitted,generation_eligible,operations_json,findings_json,controls_json,review_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',rows)
 def get_chunk_decisions(self,document_id:int)->list[dict[str,Any]]:
  with self._connect() as c:rows=c.execute('SELECT * FROM runtime_chunk_governance WHERE document_id=? ORDER BY chunk_id',(document_id,)).fetchall()
  out=[]
  for row in rows:
   d=dict(row);d['operations_permitted']=json.loads(d.pop('operations_json'));d['findings']=json.loads(d.pop('findings_json'));d['controls']=json.loads(d.pop('controls_json'));d['indexing_permitted']=bool(d['indexing_permitted']);d['generation_eligible']=bool(d['generation_eligible']);out.append(d)
  return out
 def permitted_chunk_ids(self,document_id:int,operation:str)->frozenset[int]:
  return frozenset(int(d['chunk_id']) for d in self.get_chunk_decisions(document_id) if d['indexing_permitted'] and d['generation_eligible'] and d['review_status']=='approved' and operation in set(d['operations_permitted']))
 def chunk_allowed(self,chunk_id:int,operation:str)->bool:
  with self._connect() as c:r=c.execute('SELECT indexing_permitted,generation_eligible,operations_json,review_status FROM runtime_chunk_governance WHERE chunk_id=?',(chunk_id,)).fetchone()
  return bool(r and r['indexing_permitted'] and r['generation_eligible'] and r['review_status']=='approved' and operation in set(json.loads(r['operations_json'])))
 def save_output_validation(self,record:dict[str,Any]):
  with self._connect() as c:c.execute('INSERT INTO runtime_output_governance(output_id,request_id,document_id,operation,decision,raw_output_sha256,sanitized_output_sha256,evidence_json,trace_id,receipt_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(record['output_id'],record.get('request_id'),record['document_id'],record['operation'],record['decision'],record['raw_output_sha256'],record['sanitized_output_sha256'],json.dumps(record['evidence'],sort_keys=True,default=str),record['trace_id'],record['receipt_id'],datetime.now(timezone.utc).isoformat()))
 def excluded_chunk_ids(self,document_id:int)->frozenset[int]:
  return frozenset(int(d['chunk_id']) for d in self.get_chunk_decisions(document_id) if not d['indexing_permitted'] or not d['generation_eligible'] or d['review_status']!='approved')
 def delete_document_records(self,document_id:int):
  with self._connect() as c:
   c.execute('DELETE FROM runtime_chunk_governance WHERE document_id=?',(document_id,))
   c.execute('DELETE FROM runtime_generation_governance WHERE document_id=?',(document_id,))
   c.execute('DELETE FROM runtime_output_governance WHERE document_id=?',(document_id,))
   c.execute('DELETE FROM runtime_document_governance WHERE document_id=?',(document_id,))
 def append_review(self,decision:Any):
  with self._connect() as c:c.execute('INSERT INTO runtime_governance_reviews(review_id,subject_type,subject_id,document_id,disposition,reviewer_role,rationale,redactions_json,supersedes_review_id,decided_at,receipt_id,published_at,effective_text) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(decision.review_id,decision.subject_type,decision.subject_id,decision.document_id,decision.disposition.value,decision.reviewer_role,decision.rationale,json.dumps(decision.redactions),decision.supersedes_review_id,decision.decided_at,decision.receipt_id,decision.published_at,decision.effective_text))
 def publish_review(self,review_id:str,published_at:str):
  with self._connect() as c:
   row=c.execute('SELECT published_at FROM runtime_governance_reviews WHERE review_id=?',(review_id,)).fetchone()
   if not row:raise LookupError(f'Review {review_id} does not exist.')
   if row['published_at']:raise ValueError(f'Review {review_id} is already published.')
   c.execute('UPDATE runtime_governance_reviews SET published_at=? WHERE review_id=?',(published_at,review_id))
 def unpublish_review(self,review_id:str):
  with self._connect() as c:c.execute('UPDATE runtime_governance_reviews SET published_at=NULL WHERE review_id=?',(review_id,))
 def get_review(self,review_id:str):
  with self._connect() as c:r=c.execute('SELECT * FROM runtime_governance_reviews WHERE review_id=?',(review_id,)).fetchone()
  return self._review_from_row(r)
 def list_reviews(self,subject_type:str,subject_id:str):
  with self._connect() as c:rows=c.execute('SELECT * FROM runtime_governance_reviews WHERE subject_type=? AND subject_id=? ORDER BY id',(subject_type,subject_id)).fetchall()
  return [self._review_from_row(r) for r in rows]
 def effective_review(self,subject_type:str,subject_id:str):
  with self._connect() as c:r=c.execute('SELECT * FROM runtime_governance_reviews WHERE subject_type=? AND subject_id=? AND published_at IS NOT NULL ORDER BY id DESC LIMIT 1',(subject_type,subject_id)).fetchone()
  return self._review_from_row(r)
 def _review_from_row(self,row):
  if not row:return None
  from .review_models import GovernanceReviewDecision,ReviewDisposition
  d=dict(row);return GovernanceReviewDecision(d['review_id'],d['subject_type'],d['subject_id'],int(d['document_id']),ReviewDisposition(d['disposition']),d['reviewer_role'],d['rationale'],tuple(json.loads(d['redactions_json'])),d['supersedes_review_id'],d['decided_at'],d['receipt_id'],d['published_at'],d['effective_text'])
 def effective_chunk_text(self,chunk_id:int,original_text:str)->str:
  review=self.effective_review('chunk',str(chunk_id))
  return review.effective_text if review and review.effective_text is not None else original_text
 def _base_chunk_decisions(self,document_id:int):
  with self._connect() as c:rows=c.execute('SELECT * FROM runtime_chunk_governance WHERE document_id=? ORDER BY chunk_id',(document_id,)).fetchall()
  out=[]
  for row in rows:
   d=dict(row);d['operations_permitted']=json.loads(d.pop('operations_json'));d['findings']=json.loads(d.pop('findings_json'));d['controls']=json.loads(d.pop('controls_json'));d['indexing_permitted']=bool(d['indexing_permitted']);d['generation_eligible']=bool(d['generation_eligible']);out.append(d)
  return out
 def get_chunk_decisions(self,document_id:int)->list[dict[str,Any]]:
  out=self._base_chunk_decisions(document_id)
  for d in out:
   review=self.effective_review('chunk',str(d['chunk_id']))
   if not review:continue
   d['effective_review_id']=review.review_id
   if review.disposition.value in {'approve','approve_with_redactions','supersede'}:
    d['indexing_permitted']=True;d['generation_eligible']=True;d['review_status']='approved'
    if not d['operations_permitted']:d['operations_permitted']=['tutor_answer','tutor_chat','generate_notes','summarize_document','generate_study_assets','generate_flashcards','generate_quiz','learning.tutor.retrieve','learning.tutor.answer','learning.summary.generate','learning.notes.generate','learning.flashcards.generate','learning.quiz.generate']
   elif review.disposition.value=='reject':d['indexing_permitted']=False;d['generation_eligible']=False;d['review_status']='rejected'
   elif review.disposition.value=='revoke':d['indexing_permitted']=False;d['generation_eligible']=False;d['review_status']='revoked'
  return out
 def begin_document_deletion(self,*,document_id:int,subject_id:str,source_sha256:str,chunk_set_sha256:str,trace_id:str,requested_at:str)->None:
  with self._connect() as c:c.execute('INSERT INTO runtime_document_tombstones(document_id,subject_id,source_sha256,chunk_set_sha256,event_type,decision,status,trace_id,requested_at) VALUES(?,?,?,?,?,?,?,?,?)',(document_id,subject_id,source_sha256,chunk_set_sha256,'document_deleted','authorized','pending',trace_id,requested_at))
 def set_document_deletion_status(self,document_id:int,status:str,*,receipt_id:str|None=None,completed_at:str|None=None)->None:
  with self._connect() as c:c.execute('UPDATE runtime_document_tombstones SET status=?,receipt_id=COALESCE(?,receipt_id),completed_at=COALESCE(?,completed_at) WHERE document_id=?',(status,receipt_id,completed_at,document_id))
 def get_document_tombstone(self,document_id:int)->dict[str,Any]|None:
  with self._connect() as c:r=c.execute('SELECT document_id,subject_id,source_sha256,chunk_set_sha256,event_type,decision,status,trace_id,receipt_id,requested_at,completed_at FROM runtime_document_tombstones WHERE document_id=?',(document_id,)).fetchone()
  return dict(r) if r else None
 def revoke_document_chunks(self,document_id:int)->None:
  with self._connect() as c:c.execute("UPDATE runtime_chunk_governance SET indexing_permitted=0,generation_eligible=0,operations_json='[]',review_status='revoked' WHERE document_id=?",(document_id,))
 def privacy_purge_document_records(self,document_id:int)->None:
  with self._connect() as c:
   c.execute('DELETE FROM runtime_governance_reviews WHERE document_id=?',(document_id,))
   c.execute('DELETE FROM runtime_generation_governance WHERE document_id=?',(document_id,))
   c.execute('DELETE FROM runtime_output_governance WHERE document_id=?',(document_id,))
   c.execute('DELETE FROM runtime_chunk_governance WHERE document_id=?',(document_id,))
   c.execute('DELETE FROM runtime_document_governance WHERE document_id=?',(document_id,))
