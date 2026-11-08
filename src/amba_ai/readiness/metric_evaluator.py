from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from .metric_models import MetricDefinition, MetricEvaluation
class MetricEvaluationError(ValueError): pass

def load_metric_definitions(path: Path) -> tuple[MetricDefinition, ...]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")); rows = payload["metrics"]
    definitions = tuple(MetricDefinition(metric_id=str(r["metric_id"]), finding_id=str(r["finding_id"]), element_type=str(r["element_type"]), element_id=str(r["element_id"]), name=str(r["name"]), weight=float(r["weight"])) for r in rows)
    ids = [x.metric_id for x in definitions]
    if len(ids) != len(set(ids)): raise MetricEvaluationError("metric_id values must be unique")
    if any(x.weight <= 0 for x in definitions): raise MetricEvaluationError("metric weights must be positive")
    return definitions

def load_methodology(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))

def evaluate_metrics(findings: list[dict[str, Any]], definitions: tuple[MetricDefinition, ...], methodology: dict[str, Any]) -> tuple[MetricEvaluation, ...]:
    by_id = {str(x["framework_element_id"]): x for x in findings}
    if set(by_id) != {x.finding_id for x in definitions}: raise MetricEvaluationError("metric definitions must cover every readiness finding exactly once")
    values = methodology["status_values"]; non_scoring = methodology["non_scoring_statuses"]; out = []
    for definition in definitions:
        finding = by_id[definition.finding_id]; status = str(finding["status"]); pointers = tuple(finding.get("evidence_pointers", ()))
        if status in values:
            if not pointers: raise MetricEvaluationError(f"scored status requires evidence pointers: {definition.metric_id}")
            score = float(values[status]); applicable = True; scored = True
        elif status in non_scoring:
            score = None; applicable = non_scoring[status] != "excluded"; scored = False
        else: raise MetricEvaluationError(f"unknown assessment status: {status}")
        out.append(MetricEvaluation(definition.metric_id, definition.finding_id, definition.element_type, definition.element_id, status, definition.weight, applicable, scored, score, pointers, str(finding["rationale"])))
    return tuple(out)
