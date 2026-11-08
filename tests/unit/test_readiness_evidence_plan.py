from pathlib import Path
import json
from amba_ai.readiness.evidence_requirement_validator import load_requirements, validate_against_scoring
from amba_ai.readiness.gap_planner import build_evidence_plan
ROOT = Path(__file__).resolve().parents[2]
def inputs():
    readiness=json.loads((ROOT/'submission/artifacts/readiness_reflection.json').read_text(encoding='utf-8')); requirements=load_requirements(ROOT/'config/readiness_evidence_requirements.yaml');validate_against_scoring(requirements,readiness['scoring']);return readiness,requirements
def test_every_unscored_metric_has_complete_requirements():
    readiness,requirements=inputs();plan=build_evidence_plan(readiness,requirements);assert plan['unscored_metric_count']==5;assert {x['metric_id'] for x in plan['metric_gaps']}=={'F2-M01','F5-M01','D1-M01','D2-M01','D11-M01'};assert all(x['missing_evidence'] and x['recommended_actions'] and x['acceptance_criteria'] for x in plan['metric_gaps'])
def test_single_metric_impact_and_minimum_closure_plan():
    readiness,requirements=inputs();plan=build_evidence_plan(readiness,requirements);d11=next(x for x in plan['metric_gaps'] if x['metric_id']=='D11-M01');assert d11['score_impact_if_resolved']=={'new_scored_metric_count':15,'applicable_metric_count':19,'new_coverage_ratio':0.789474,'minimum_required_ratio':0.8,'threshold_reached':False};closure=plan['minimum_threshold_closure_plan'];assert closure['selected_metrics']==['D11-M01','F5-M01'];assert closure['new_scored_metric_count']==16;assert closure['new_coverage_ratio']==0.842105;assert closure['threshold_reached'] is True
def test_plan_never_changes_status_or_threshold():
    readiness,requirements=inputs();plan=build_evidence_plan(readiness,requirements);assert plan['claim_boundaries']['status_changes_require_verified_evidence'] is True;assert plan['claim_boundaries']['coverage_threshold_reduction_allowed'] is False;assert plan['claim_boundaries']['project_score_guaranteed_after_plan'] is False
