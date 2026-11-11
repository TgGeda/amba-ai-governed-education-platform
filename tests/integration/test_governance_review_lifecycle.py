from __future__ import annotations
import hashlib
from types import SimpleNamespace
import pytest
from amba_ai.governance.runtime import RuntimeEducationGovernanceService
from amba_ai.governance.runtime.review_models import ReviewDisposition
from amba_ai.rag.corpus_revision import GovernedCorpusBuilder,RetrievalCorpusCache
from amba_ai.services.governance_review_service import GovernanceReviewError,GovernanceReviewService

class DB:
 def list_documents(self,limit=100000,offset=0):return [{'id':1,'metadata':{'version_id':'v1'},'created_at':'now'}]
 def get_chunks(self,document_id):return [{'id':11,'document_id':1,'text':'FINAL EXAM ANSWER KEY learner@example.com','chunk_index':0}]
class Engine:
 def __init__(self):self.ids=frozenset();self.corpus_cache=RetrievalCorpusCache();self.rebuilds=0;self.fail=False
 def indexed_chunk_ids(self):return self.ids
 def rebuild_from_source_documents(self,*,policy):
  if self.fail:raise RuntimeError('rebuild failed')
  self.ids=frozenset(x for values in policy.permitted_chunk_ids_by_document.values() for x in values);self.rebuilds+=1

def fixture(tmp_path):
 runtime=RuntimeEducationGovernanceService(tmp_path/'db.sqlite3');runtime.repository.save_document(1,{'source_sha256':'source','decision':'accepted_with_restrictions','permitted_operations':['tutor_answer'],'restricted_operations':[],'controls':[],'findings':[],'receipt_id':'DOC'})
 runtime.assess_chunks(1,[{'id':11,'text':'FINAL EXAM ANSWER KEY learner@example.com'}])
 db=DB();engine=Engine();builder=GovernedCorpusBuilder(db=db,rag_engine=engine,runtime_governance=runtime,cache=engine.corpus_cache)
 return runtime,engine,builder,GovernanceReviewService(runtime_governance=runtime,corpus_builder=builder,rag_engine=engine)

def test_approve_revoke_and_supersede_are_append_only(tmp_path):
 runtime,engine,builder,svc=fixture(tmp_path)
 before=builder.build(operation='learning.tutor.answer').revision.revision_id
 approved=svc.decide(subject_type='chunk',subject_id='11',document_id=1,disposition='approve',reviewer_role='teacher',rationale='Authorized teaching use')
 after=builder.build(operation='learning.tutor.answer');assert 11 in after.eligible_chunk_ids;assert before!=after.revision.revision_id
 revoked=svc.decide(subject_type='chunk',subject_id='11',document_id=1,disposition='revoke',reviewer_role='school_administrator',rationale='Authorization withdrawn',supersedes_review_id=approved.review_id)
 final=builder.build(operation='learning.tutor.answer');assert 11 not in final.eligible_chunk_ids
 reviews=runtime.repository.list_reviews('chunk','11');assert [x.review_id for x in reviews]==[approved.review_id,revoked.review_id]

def test_redacted_approval_indexes_effective_text_not_original(tmp_path):
 runtime,engine,builder,svc=fixture(tmp_path)
 decision=svc.decide(subject_type='chunk',subject_id='11',document_id=1,disposition=ReviewDisposition.APPROVE_WITH_REDACTIONS,reviewer_role='teacher',rationale='Release after redaction',redactions=('learner@example.com',))
 result=builder.build(operation='learning.tutor.answer');texts=[c.text for c in result.bm25.chunks]
 assert decision.is_published;assert all('learner@example.com' not in x for x in texts);assert any('[REDACTED]' in x for x in texts)

def test_unauthorized_reviewer_causes_no_mutation(tmp_path):
 runtime,engine,builder,svc=fixture(tmp_path)
 with pytest.raises(GovernanceReviewError,match='not authorized'):svc.decide(subject_type='chunk',subject_id='11',document_id=1,disposition='approve',reviewer_role='learner',rationale='no')
 assert runtime.repository.list_reviews('chunk','11')==[];assert engine.rebuilds==0

def test_refresh_failure_records_unpublished_append_only_review(tmp_path):
 runtime,engine,builder,svc=fixture(tmp_path);engine.fail=True
 with pytest.raises(GovernanceReviewError,match='not published'):svc.decide(subject_type='chunk',subject_id='11',document_id=1,disposition='approve',reviewer_role='teacher',rationale='approve')
 reviews=runtime.repository.list_reviews('chunk','11');assert len(reviews)==1;assert not reviews[0].is_published;assert runtime.repository.effective_review('chunk','11') is None
