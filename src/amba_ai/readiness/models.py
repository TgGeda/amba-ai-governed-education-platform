from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any
class AssessmentStatus(str,Enum):
 DEMONSTRATED='demonstrated'; PARTIALLY_DEMONSTRATED='partially_demonstrated'; NOT_DEMONSTRATED='not_demonstrated'; NOT_APPLICABLE='not_applicable'; INSUFFICIENT_EVIDENCE='insufficient_evidence'; UNRESOLVED='unresolved'; NOT_ASSESSED='not_assessed'
@dataclass(frozen=True,slots=True)
class ReadinessFinding:
 mapping_id:str; framework_element_type:str; framework_element_id:str; framework_element_name:str; status:AssessmentStatus; rationale:str; evidence_pointers:tuple[str,...]; passage_ids:tuple[str,...]; y3172_record_ids:tuple[str,...]; limitations:tuple[str,...]
 def to_dict(self)->dict[str,Any]: return {'mapping_id':self.mapping_id,'framework_element_type':self.framework_element_type,'framework_element_id':self.framework_element_id,'framework_element_name':self.framework_element_name,'status':self.status.value,'rationale':self.rationale,'evidence_pointers':list(self.evidence_pointers),'passage_ids':list(self.passage_ids),'y3172_record_ids':list(self.y3172_record_ids),'limitations':list(self.limitations)}
@dataclass(frozen=True,slots=True)
class ReadinessReflection:
 evidence_artifact_path:str; evidence_artifact_sha256:str; findings:tuple[ReadinessFinding,...]; coverage:dict[str,int]
 def to_dict(self)->dict[str,Any]: return {'schema_version':'1.0.0','artifact_type':'evidence_bounded_readiness_reflection','assessment_subject':{'type':'project','id':'AMBA-GOV','national_assessment':False,'official_itu_certification':False},'framework':{'framework_id':'ITU-AI-READINESS-2.0','factor_count':6,'dimension_count':13,'metric_count':111},'y3172_mapping':{'source_id':'ITU-T-Y3172-2019','mapping_type':'interpreted_project_architecture_mapping','formal_y3172_conformance':False,'itu_certification':False},'evidence_artifact':{'path':self.evidence_artifact_path,'sha256':self.evidence_artifact_sha256},'findings':[x.to_dict() for x in self.findings],'coverage':self.coverage,'overall_project_score':None,'score_status':'withheld_pending_methodology_and_evidence_coverage','national_ai_readiness_score':None,'limitations':['project reflection, not a national assessment','not an official ITU certification','no unverified metric weights or maturity score applied','readiness cannot authorize or block runtime operations']}
