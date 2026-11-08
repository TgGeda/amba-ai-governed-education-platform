from __future__ import annotations
from .coverage_analyzer import analyze_coverage
from .metric_models import MetricEvaluation, ScoreResult

def aggregate_score(evaluations: tuple[MetricEvaluation, ...], minimum_coverage: float, rounding: int) -> ScoreResult:
    coverage = analyze_coverage(evaluations, minimum_coverage); scored = tuple(x for x in evaluations if x.applicable and x.scored)
    weighted_sum = sum(float(x.score) * x.weight for x in scored); weight = sum(x.weight for x in scored)
    if not coverage.sufficient: return ScoreResult(None, "withheld_insufficient_evidence_coverage", coverage, round(weighted_sum, rounding), round(weight, rounding))
    if weight <= 0: return ScoreResult(None, "withheld_no_scored_applicable_metrics", coverage, 0.0, 0.0)
    return ScoreResult(round(weighted_sum / weight, rounding), "calculated_with_sufficient_project_evidence", coverage, round(weighted_sum, rounding), round(weight, rounding))
