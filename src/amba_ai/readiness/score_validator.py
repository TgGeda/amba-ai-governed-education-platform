from __future__ import annotations
from .metric_models import MetricEvaluation, ScoreResult
class ScoreValidationError(ValueError): pass

def validate_score(result: ScoreResult, evaluations: tuple[MetricEvaluation, ...], methodology: dict) -> None:
    minimum=float(methodology["score_scale"]["minimum"]); maximum=float(methodology["score_scale"]["maximum"])
    if any(x.score is not None and not minimum <= x.score <= maximum for x in evaluations): raise ScoreValidationError("metric score outside configured scale")
    if result.score is not None and not minimum <= result.score <= maximum: raise ScoreValidationError("aggregate score outside configured scale")
    if result.score is not None and not result.coverage.sufficient: raise ScoreValidationError("aggregate score cannot be published below coverage threshold")
    if result.score is None and result.status == "calculated_with_sufficient_project_evidence": raise ScoreValidationError("calculated status requires a numeric score")
