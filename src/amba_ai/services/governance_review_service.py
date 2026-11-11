from __future__ import annotations
import uuid
from datetime import datetime,timezone
from typing import Any
from amba_ai.governance.runtime.review_models import GovernanceReviewDecision,ReviewDisposition

class GovernanceReviewError(RuntimeError):pass
class GovernanceReviewService:
 ALLOWED_ROLES=frozenset({'teacher','school_administrator'})
 def __init__(self,*,runtime_governance:Any,corpus_builder:Any,rag_engine:Any)->None:
  self.runtime_governance=runtime_governance;self.corpus_builder=corpus_builder;self.rag_engine=rag_engine
 @staticmethod
 def _now()->str:return datetime.now(timezone.utc).isoformat()
 @staticmethod
 def _redact(text:str,redactions:tuple[str,...])->str:
  value=text
  for item in redactions:
   if not item.strip():raise GovernanceReviewError('Redactions must be non-empty.')
   value=value.replace(item,'[REDACTED]')
  return value
 def decide(self,*,subject_type:str,subject_id:str,document_id:int,disposition:ReviewDisposition|str,reviewer_role:str,rationale:str,redactions:tuple[str,...]=(),supersedes_review_id:str|None=None,operation:str='learning.tutor.answer')->GovernanceReviewDecision:
  if subject_type!='chunk':raise GovernanceReviewError('Only chunk review subjects are currently supported.')
  role=str(reviewer_role).strip()
  if role not in self.ALLOWED_ROLES:raise GovernanceReviewError('Reviewer role is not authorized for learning.review.decide.')
  if not str(rationale).strip():raise GovernanceReviewError('Review rationale is required.')
  disp=ReviewDisposition(disposition)
  reds=tuple(str(x) for x in redactions)
  if disp is ReviewDisposition.APPROVE_WITH_REDACTIONS and not reds:raise GovernanceReviewError('Redaction approval requires redactions.')
  if disp is not ReviewDisposition.APPROVE_WITH_REDACTIONS and reds:raise GovernanceReviewError('Redactions are permitted only with approve_with_redactions.')
  decisions={int(d['chunk_id']):d for d in self.runtime_governance.repository._base_chunk_decisions(document_id)}
  try:chunk_id=int(subject_id)
  except ValueError as e:raise GovernanceReviewError('Chunk subject_id must be an integer.') from e
  if chunk_id not in decisions:raise GovernanceReviewError('Review subject does not exist in the document.')
  prior=self.runtime_governance.repository.effective_review(subject_type,subject_id)
  if disp in {ReviewDisposition.REVOKE,ReviewDisposition.SUPERSEDE}:
   if not supersedes_review_id:raise GovernanceReviewError(f'{disp.value} requires supersedes_review_id.')
   superseded=self.runtime_governance.repository.get_review(supersedes_review_id)
   if not superseded:raise GovernanceReviewError('Superseded review does not exist.')
   if superseded.subject_type!=subject_type or superseded.subject_id!=subject_id or superseded.document_id!=document_id:raise GovernanceReviewError('Cross-subject or cross-document supersession is prohibited.')
   if prior and prior.review_id!=supersedes_review_id:raise GovernanceReviewError('Only the current effective review may be superseded or revoked.')
  elif supersedes_review_id:raise GovernanceReviewError('supersedes_review_id is valid only for revoke or supersede.')
  if disp in {ReviewDisposition.APPROVE,ReviewDisposition.APPROVE_WITH_REDACTIONS,ReviewDisposition.REJECT} and prior:raise GovernanceReviewError('An effective review already exists; append a supersede or revoke decision.')
  effective_text=None
  if disp is ReviewDisposition.APPROVE_WITH_REDACTIONS:
   rows=[r for r in self.corpus_builder.db.get_chunks(document_id) if int(r['id'])==chunk_id]
   if not rows:raise GovernanceReviewError('Chunk source text is unavailable.')
   effective_text=self._redact(str(rows[0]['text']),reds)
  rid=self.runtime_governance.repository.receipt('governance_review_recorded',{'subject_type':subject_type,'subject_id':subject_id,'document_id':document_id,'disposition':disp.value,'reviewer_role':role,'supersedes_review_id':supersedes_review_id},document_id,'learning.review.decide')
  decision=GovernanceReviewDecision('EDU-REVIEW-'+uuid.uuid4().hex[:20].upper(),subject_type,subject_id,document_id,disp,role,str(rationale).strip(),reds,supersedes_review_id,self._now(),rid,None,effective_text)
  self.runtime_governance.repository.append_review(decision)
  published=self._now()
  self.runtime_governance.repository.publish_review(decision.review_id,published)
  self.rag_engine.corpus_cache.invalidate()
  try:
   result=self.corpus_builder.build(operation=operation);result.require_aligned()
  except Exception as error:
   self.runtime_governance.repository.unpublish_review(decision.review_id)
   self.rag_engine.corpus_cache.invalidate()
   self.runtime_governance.repository.receipt('governance_review_publication_failed',{'review_id':decision.review_id,'error_type':type(error).__name__},document_id,'learning.review.decide')
   raise GovernanceReviewError('Review was recorded but not published because corpus refresh failed.') from error
  audit=self.runtime_governance.repository.receipt('governance_review_published',{'review_id':decision.review_id,'revision_id':result.revision.revision_id,'eligible_chunk_ids':sorted(result.eligible_chunk_ids),'excluded_chunk_ids':sorted(result.excluded_chunk_ids)},document_id,'learning.review.decide')
  return GovernanceReviewDecision(decision.review_id,decision.subject_type,decision.subject_id,decision.document_id,decision.disposition,decision.reviewer_role,decision.rationale,decision.redactions,decision.supersedes_review_id,decision.decided_at,audit,published,decision.effective_text)
