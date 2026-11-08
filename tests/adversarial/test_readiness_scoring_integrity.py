from pathlib import Path
import json,pytest
from amba_ai.readiness.metric_evaluator import MetricEvaluationError,evaluate_metrics,load_methodology,load_metric_definitions
from amba_ai.readiness.metric_models import ScoreResult
from amba_ai.readiness.score_aggregator import aggregate_score
from amba_ai.readiness.score_validator import ScoreValidationError,validate_score
ROOT=Path(__file__).resolve().parents[2]
def prepared():
 p=json.loads((ROOT/'submission/artifacts/readiness_reflection.json').read_text(encoding='utf-8'));m=load_methodology(ROOT/'config/readiness_scoring_methodology.yaml');d=load_metric_definitions(ROOT/'config/readiness_metric_definitions.yaml');e=evaluate_metrics(p['findings'],d,m);return m,e
def test_numeric_score_cannot_be_published_below_coverage_threshold():
 m,e=prepared();valid=aggregate_score(e,0.80,6);forged=ScoreResult(0.99,'calculated_with_sufficient_project_evidence',valid.coverage,valid.weighted_score_sum,valid.scored_weight)
 with pytest.raises(ScoreValidationError,match='below coverage threshold'):validate_score(forged,e,m)
def test_unknown_status_fails_closed():
 p=json.loads((ROOT/'submission/artifacts/readiness_reflection.json').read_text(encoding='utf-8'));p['findings'][0]['status']='optimistic';m=load_methodology(ROOT/'config/readiness_scoring_methodology.yaml');d=load_metric_definitions(ROOT/'config/readiness_metric_definitions.yaml')
 with pytest.raises(MetricEvaluationError,match='unknown assessment status'):evaluate_metrics(p['findings'],d,m)
