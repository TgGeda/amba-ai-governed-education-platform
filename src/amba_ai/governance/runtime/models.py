from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

class Decision(str, Enum):
    ACCEPTED='accepted'; RESTRICTED='accepted_with_restrictions'; REVIEW='review_required'; REJECTED='rejected'; QUARANTINED='quarantined'

class RuntimeGovernanceError(RuntimeError): pass
class RuntimeGovernanceGateError(RuntimeGovernanceError): pass
class RuntimeGovernanceReviewRequired(RuntimeGovernanceGateError): pass

@dataclass(frozen=True)
class RiskFinding:
    code:str; severity:str; message:str

@dataclass(frozen=True)
class IngestionDecision:
    decision:Decision; source_sha256:str; findings:tuple[RiskFinding,...]=(); permitted_operations:tuple[str,...]=(); restricted_operations:tuple[str,...]=(); controls:tuple[str,...]=(); permits_persistence:bool=False; permits_indexing:bool=False; receipt_id:str=''
    def to_dict(self)->dict[str,Any]:
        d=asdict(self); d['decision']=self.decision.value; return d

@dataclass(frozen=True)
class GenerationDecision:
    decision:Decision; document_id:int; operation:str; source_sha256:str; source_digest_verified:bool; controls:tuple[str,...]=(); findings:tuple[RiskFinding,...]=(); receipt_id:str=''
    @property
    def allows_generation(self)->bool:return self.decision in {Decision.ACCEPTED,Decision.RESTRICTED}
    @property
    def requires_review(self)->bool:return self.decision is Decision.REVIEW
    def to_dict(self)->dict[str,Any]:
        d=asdict(self); d['decision']=self.decision.value; return d
