from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True,slots=True)
class ReadinessFindingRow:
 element_id:str;element_type:str;name:str;status:str;rationale:str;evidence_pointers:tuple[str,...];passage_ids:tuple[str,...];y3172_record_ids:tuple[str,...];limitations:tuple[str,...]
@dataclass(frozen=True,slots=True)
class MetricRow:
 metric_id:str;finding_id:str;element_type:str;status:str;score:float|None;weight:float;applicable:bool;scored:bool;evidence_pointers:tuple[str,...]
@dataclass(frozen=True,slots=True)
class CoverageSummary:
 scored_count:int;applicable_count:int;coverage_ratio:float;minimum_ratio:float;sufficient:bool;overall_score:float|None;score_status:str
 @property
 def additional_equal_weight_metrics_required(self)->int:
  required=0
  while self.applicable_count and (self.scored_count+required)/self.applicable_count<self.minimum_ratio:required+=1
  return required
@dataclass(frozen=True,slots=True)
class GapRow:
 metric_id:str;current_status:str;missing_evidence:tuple[str,...];recommended_actions:tuple[str,...];delivery_risk:str;external_dependency:str;projected_coverage:float;threshold_reached:bool;selected_for_minimum_closure:bool
@dataclass(frozen=True,slots=True)
class PendingGateRow:
 metric_id:str;failed_checks:tuple[str,...];limitations:tuple[str,...]
