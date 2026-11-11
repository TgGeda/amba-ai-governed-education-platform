from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class ReviewDisposition(str,Enum):
 APPROVE="approve"
 APPROVE_WITH_REDACTIONS="approve_with_redactions"
 REJECT="reject"
 REVOKE="revoke"
 SUPERSEDE="supersede"

@dataclass(frozen=True,slots=True)
class GovernanceReviewDecision:
 review_id:str
 subject_type:str
 subject_id:str
 document_id:int
 disposition:ReviewDisposition
 reviewer_role:str
 rationale:str
 redactions:tuple[str,...]
 supersedes_review_id:str|None
 decided_at:str
 receipt_id:str
 published_at:str|None=None
 effective_text:str|None=None
 @property
 def is_published(self)->bool:return bool(self.published_at)
