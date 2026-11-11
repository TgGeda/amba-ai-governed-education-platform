from __future__ import annotations
import hashlib,json
from types import SimpleNamespace
import pytest
from amba_ai.db.database import Database
from amba_ai.governance.runtime import RuntimeEducationGovernanceService
from amba_ai.models.schemas import IngestedDocument
from amba_ai.rag.corpus_revision import GovernedCorpusBuilder,RetrievalCorpusCache
from amba_ai.services.document_lifecycle_service import DocumentLifecycleError,DocumentLifecycleService

RAW=('learner@example.com','Student ID: ABC-123',r'F:\Private\student_record.txt')
class Engine:
 def __init__(self):self.ids=frozenset();self.docs=set();self.corpus_cache=RetrievalCorpusCache();self.fail=False
 def indexed_chunk_ids(self):return self.ids
 def has_document(self,d):return d in self.docs
 def remove_document(self,d):
  if self.fail:raise RuntimeError('remove failed')
  self.docs.discard(d);self.ids=frozenset()
 def rebuild_from_source_documents(self,*,policy):self.ids=frozenset(x for v in policy.permitted_chunk_ids_by_document.values() for x in v)
class Coordinator:
 def begin(self,**k):return SimpleNamespace(method_name='delete_document')
 def complete(self,**k):return SimpleNamespace(require_delivery_acknowledged=lambda:None)
def fixture(tmp_path):
 db=Database(tmp_path/'app.db');doc=IngestedDocument('Private lesson',RAW[2],'text',' '.join(RAW),{});document_id,chunks=db.insert_governed_document(doc,[SimpleNamespace(text=' '.join(RAW),chunk_index=0,source_ref='lesson')]);runtime=RuntimeEducationGovernanceService(db.path);source=hashlib.sha256(b'source').hexdigest();runtime.repository.save_document(document_id,{'source_sha256':source,'decision':'accepted_with_restrictions','permitted_operations':['delete_document'],'restricted_operations':[],'controls':[],'findings':[],'receipt_id':'DOC'});runtime.assess_chunks(document_id,db.get_chunks(document_id));engine=Engine();engine.ids=frozenset(chunks);engine.docs.add(document_id);builder=GovernedCorpusBuilder(db=db,rag_engine=engine,runtime_governance=runtime,cache=engine.corpus_cache);svc=DocumentLifecycleService(db=db,runtime_governance=runtime,corpus_builder=builder,rag_engine=engine,governance_coordinator=Coordinator());return db,runtime,engine,svc,document_id,chunks
def test_governed_deletion_removes_content_and_retains_safe_tombstone(tmp_path):
 db,runtime,engine,svc,document_id,chunks=fixture(tmp_path);receipt=svc.delete_document(document_id=document_id,reviewer_role='teacher',governance_context=object());assert db.get_document(document_id) is None;assert not engine.ids;assert runtime.repository.get_document(document_id) is None;tomb=runtime.repository.get_document_tombstone(document_id);assert tomb and tomb['status']=='complete';retained=json.dumps(tomb)+json.dumps(receipt.to_dict());assert all(value not in retained for value in RAW)
def test_unauthorized_deletion_has_no_effect(tmp_path):
 db,runtime,engine,svc,document_id,chunks=fixture(tmp_path)
 with pytest.raises(DocumentLifecycleError,match='not authorized'):svc.delete_document(document_id=document_id,reviewer_role='learner')
 assert db.get_document(document_id) is not None;assert engine.ids;assert runtime.repository.get_document_tombstone(document_id) is None
def test_index_removal_failure_fails_closed_without_completion(tmp_path):
 db,runtime,engine,svc,document_id,chunks=fixture(tmp_path);engine.fail=True
 with pytest.raises(DocumentLifecycleError,match='failed closed'):svc.delete_document(document_id=document_id,reviewer_role='school_administrator')
 tomb=runtime.repository.get_document_tombstone(document_id);assert tomb and tomb['status']=='failed';assert tomb['receipt_id'] is None;assert runtime.repository.permitted_chunk_ids(document_id,'learning.tutor.answer')==frozenset()
