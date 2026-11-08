from __future__ import annotations
from collections import defaultdict
from pathlib import Path
from typing import Any
from .metric_evaluator import evaluate_metrics, load_methodology, load_metric_definitions
from .score_aggregator import aggregate_score
from .score_validator import validate_score

class ReadinessScoringService:
    def score(self, *, findings: list[dict[str, Any]], metric_definitions_path: Path, methodology_path: Path) -> dict[str, Any]:
        definitions = load_metric_definitions(metric_definitions_path)
        methodology = load_methodology(methodology_path)
        evaluations = evaluate_metrics(findings, definitions, methodology)
        minimum = float(methodology["coverage"]["minimum_for_overall_project_score"])
        rounding = int(methodology["aggregation"]["rounding_decimal_places"])
        overall = aggregate_score(evaluations, minimum, rounding)
        validate_score(overall, evaluations, methodology)
        grouped: dict[str, list] = defaultdict(list)
        for item in evaluations:
            grouped[item.element_type].append(item)
        element_scores: dict[str, list[dict[str, Any]]] = {"factor": [], "dimension": []}
        for element_type in ("factor", "dimension"):
            threshold = float(methodology["coverage"][f"minimum_for_{element_type}_score"])
            for item in grouped[element_type]:
                result = aggregate_score((item,), threshold, rounding)
                validate_score(result, (item,), methodology)
                element_scores[element_type].append({"element_id": item.element_id, "metric_ids": [item.metric_id], **result.to_dict()})
        return {
            "methodology_id": methodology["methodology_id"],
            "metric_set_id": "AMBA-GOV-READINESS-PROXY-METRICS-1.0",
            "metric_scope": "19 evidence-mapped project proxy metrics; not the complete 111-metric ITU instrument",
            "framework_metric_reference_count": int(methodology["framework_metric_reference_count"]),
            "implemented_project_proxy_metric_count": len(evaluations),
            "status_values": methodology["status_values"],
            "non_scoring_statuses": methodology["non_scoring_statuses"],
            "metric_evaluations": [x.to_dict() for x in evaluations],
            "factor_scores": sorted(element_scores["factor"], key=lambda x: x["element_id"]),
            "dimension_scores": sorted(element_scores["dimension"], key=lambda x: x["element_id"]),
            "overall": overall.to_dict(),
            "claim_boundaries": methodology["claim_boundaries"],
        }
