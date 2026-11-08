from __future__ import annotations
from .metric_models import CoverageResult, MetricEvaluation

def analyze_coverage(evaluations: tuple[MetricEvaluation, ...], minimum_ratio: float) -> CoverageResult:
    applicable = tuple(x for x in evaluations if x.applicable); scored = tuple(x for x in applicable if x.scored)
    applicable_weight = sum(x.weight for x in applicable); scored_weight = sum(x.weight for x in scored)
    ratio = 0.0 if applicable_weight == 0 else scored_weight / applicable_weight
    return CoverageResult(len(evaluations), len(applicable), len(scored), len(evaluations)-len(applicable), len(applicable)-len(scored), round(applicable_weight, 6), round(scored_weight, 6), round(ratio, 6), float(minimum_ratio), ratio >= minimum_ratio)
