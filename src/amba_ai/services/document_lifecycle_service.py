from __future__ import annotations
import hashlib,json,uuid
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from typing import Any

class DocumentLifecycleError(RuntimeError):pass
@dataclass(frozen=True,slots=True)
class DocumentDeletionReceipt:
 document_id:int;subject_id:str;source_sha256:str;chunk_set_sha256:str;decision:str;status:str;trace_id:str;receipt_id:str;deleted_at:str;corpus_revision_id:str
 def to_dict(self)->dict[str,Any]:return asdict(self)
class DocumentLifecycleService:
 ALLOWED_ROLES=frozenset({'teacher','school_administrator'})
 def __init__(self,*,db:Any,runtime_governance:Any,corpus_builder:Any,rag_engine:Any,governance_coordinator:Any=None)->None:
  self.db=db;self.runtime_governance=runtime_governance;self.corpus_builder=corpus_builder;self.rag_engine=rag_engine;self.governance_coordinator=governance_coordinator
 @staticmethod
 def _now()->str:return datetime.now(timezone.utc).isoformat()
 @staticmethod
 def _digest(values:Any)->str:return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
 def delete_document(self,*,document_id:int,reviewer_role:str,governance_context:Any=None)->DocumentDeletionReceipt:
  document_id=int(document_id);role=str(reviewer_role).strip()
  if document_id<=0:raise ValueError('document_id must be positive.')
  if role not in self.ALLOWED_ROLES:raise DocumentLifecycleError('Role is not authorized for learning.document.delete.')
  row=self.db.get_document(document_id)
  if row is None:raise DocumentLifecycleError(f'Document {document_id} does not exist.')
  document=dict(row);chunks=list(self.db.get_chunks(document_id));governance=self.runtime_governance.repository.get_document(document_id)
  if not governance:raise DocumentLifecycleError('Document has no runtime governance record.')
  source_sha=str(governance['source_sha256']);chunk_entries=[(int(x['id']),hashlib.sha256(str(x['text']).encode()).hexdigest()) for x in chunks];chunk_set_sha=self._digest(chunk_entries)
  trace_id='EDU-TRACE-'+uuid.uuid4().hex[:20].upper();subject_id='DOC-'+hashlib.sha256(f'{document_id}:{source_sha}'.encode()).hexdigest()[:20].upper();requested=self._now()
  # Runtime operation authorization happens before any mutation.
  self.runtime_governance.authorize_generation(document_id,'delete_document',str(document.get('source_path') or '') or None)
  invocation=None
  if self.governance_coordinator is not None:
   invocation=self.governance_coordinator.begin(method_name='delete_document',input_metadata={'document_id':document_id,'reviewer_role':role,'source_sha256':source_sha},context=governance_context)
  self.runtime_governance.repository.begin_document_deletion(document_id=document_id,subject_id=subject_id,source_sha256=source_sha,chunk_set_sha256=chunk_set_sha,trace_id=trace_id,requested_at=requested)
  self.runtime_governance.repository.revoke_document_chunks(document_id);self.rag_engine.corpus_cache.invalidate()
  try:
   self.rag_engine.remove_document(document_id)
   counts=self.db.delete_governed_document_data(document_id)
   self.runtime_governance.repository.privacy_purge_document_records(document_id)
   self.rag_engine.corpus_cache.invalidate();corpus=self.corpus_builder.build(operation='learning.tutor.retrieve');corpus.require_aligned()
   if set(x for x,_ in chunk_entries).intersection(corpus.eligible_chunk_ids):raise DocumentLifecycleError('Deleted chunks remain eligible.')
   deleted_at=self._now();safe={'document_id':document_id,'subject_id':subject_id,'source_sha256':source_sha,'chunk_set_sha256':chunk_set_sha,'event_type':'document_deleted','decision':'authorized','status':'complete','trace_id':trace_id,'deleted_counts':counts,'corpus_revision_id':corpus.revision.revision_id}
   receipt=self.runtime_governance.repository.receipt('governed_document_deletion_completed',safe,document_id,'learning.document.delete')
   self.runtime_governance.repository.set_document_deletion_status(document_id,'complete',receipt_id=receipt,completed_at=deleted_at)
   if invocation is not None:
    completion=self.governance_coordinator.complete(invocation=invocation,result_material=safe,result_metadata={'document_id':document_id,'output_type':'document_deletion_receipt'});completion.require_delivery_acknowledged()
   return DocumentDeletionReceipt(document_id,subject_id,source_sha,chunk_set_sha,'authorized','complete',trace_id,receipt,deleted_at,corpus.revision.revision_id)
  except Exception as error:
   self.rag_engine.corpus_cache.invalidate();self.runtime_governance.repository.set_document_deletion_status(document_id,'failed')
   self.runtime_governance.repository.receipt('governed_document_deletion_failed',{'document_id':document_id,'subject_id':subject_id,'source_sha256':source_sha,'chunk_set_sha256':chunk_set_sha,'event_type':'document_deletion_failed','decision':'authorized','status':'failed','trace_id':trace_id,'error_type':type(error).__name__},document_id,'learning.document.delete')
   raise DocumentLifecycleError('Governed document deletion failed closed.') from error
