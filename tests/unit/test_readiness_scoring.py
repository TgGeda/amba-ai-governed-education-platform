from pathlib import Path
import json
from amba_ai.readiness.metric_evaluator import load_methodology,load_metric_definitions,evaluate_metrics
from amba_ai.readiness.score_aggregator import aggregate_score
from amba_ai.readiness.score_validator import validate_score
ROOT=Path(__file__).resolve().parents[2]
def inputs():
 p=json.loads((ROOT/'submission/artifacts/readiness_reflection.json').read_text(encoding='utf-8'));m=load_methodology(ROOT/'config/readiness_scoring_methodology.yaml');d=load_metric_definitions(ROOT/'config/readiness_metric_definitions.yaml');return p,m,d
def test_metric_catalog_is_complete_for_19_findings():
 p,m,d=inputs(); e=evaluate_metrics(p['findings'],d,m);assert len(e)==19;assert {x.finding_id for x in e}=={x['framework_element_id'] for x in p['findings']}
def test_current_coverage_withholds_score():
 p,m,d=inputs();e=evaluate_metrics(p['findings'],d,m);r=aggregate_score(e,0.80,6);validate_score(r,e,m);assert r.score is None;assert r.status=='withheld_insufficient_evidence_coverage';assert r.coverage.coverage_ratio==0.736842;assert r.coverage.scored_metric_count==14;assert r.coverage.applicable_metric_count==19
def test_sufficient_coverage_calculates_numeric_score():
 p,m,d=inputs();findings=[dict(x,status='demonstrated',evidence_pointers=x['evidence_pointers'] or ['/synthetic']) for x in p['findings']];e=evaluate_metrics(findings,d,m);r=aggregate_score(e,0.80,6);validate_score(r,e,m);assert r.score==1.0;assert r.status=='calculated_with_sufficient_project_evidence'
