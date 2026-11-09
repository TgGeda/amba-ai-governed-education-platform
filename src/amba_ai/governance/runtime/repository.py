from __future__ import annotations
import json,sqlite3,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

_SCHEMA='''
CREATE TABLE IF NOT EXISTS runtime_document_governance(id INTEGER PRIMARY KEY,document_id INTEGER UNIQUE,source_sha256 TEXT NOT NULL,decision TEXT NOT NULL,permitted_json TEXT NOT NULL,restricted_json TEXT NOT NULL,controls_json TEXT NOT NULL,findings_json TEXT NOT NULL,receipt_id TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime_generation_governance(id INTEGER PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,document_id INTEGER NOT NULL,operation TEXT NOT NULL,decision TEXT NOT NULL,source_sha256 TEXT NOT NULL,details_json TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime_governance_receipts(id INTEGER PRIMARY KEY,receipt_id TEXT UNIQUE NOT NULL,event_type TEXT NOT NULL,document_id INTEGER,operation TEXT,payload_json TEXT NOT NULL,created_at TEXT NOT NULL);
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
