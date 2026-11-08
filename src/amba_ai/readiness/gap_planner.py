from __future__ import annotations
from itertools import combinations
from typing import Any

_RISK = {"low": 0, "medium": 1, "high": 2}


def _project(scoring: dict[str, Any], resolved_count: int) -> dict[str, Any]:
    coverage = scoring["overall"]["coverage"]
    scored = int(coverage["scored_metric_count"]) + resolved_count
    applicable = int(coverage["applicable_metric_count"])
    ratio = round(scored / applicable, 6) if applicable else 0.0
    required = float(coverage["minimum_required_ratio"])
    return {
        "new_scored_metric_count": scored,
        "applicable_metric_count": applicable,
        "new_coverage_ratio": ratio,
        "minimum_required_ratio": required,
        "threshold_reached": ratio >= required,
    }


def build_evidence_plan(readiness: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    scoring = readiness["scoring"]
    by_metric = {item["metric_id"]: item for item in scoring["metric_evaluations"]}
    gaps = []
    for metric_id in sorted(requirements["requirements"]):
        metric = by_metric[metric_id]
        req = requirements["requirements"][metric_id]
        gaps.append({
            "metric_id": metric_id,
            "finding_id": metric["finding_id"],
            "element_type": metric["element_type"],
            "element_id": metric["element_id"],
            "current_status": metric["status"],
            "current_score": metric["score"],
            "weight": metric["weight"],
            "title": req["title"],
            "missing_evidence": list(req["missing_evidence"]),
            "recommended_actions": list(req["recommended_actions"]),
            "acceptance_criteria": list(req["acceptance_criteria"]),
            "eligible_target_statuses": list(req["eligible_target_statuses"]),
            "delivery_risk": req["delivery_risk"],
            "external_dependency": req["external_dependency"],
            "score_impact_if_resolved": _project(scoring, 1),
        })
    unresolved = [item["metric_id"] for item in gaps]
    minimum_set = None
    for size in range(1, len(unresolved) + 1):
        candidates = []
        for combo in combinations(unresolved, size):
            projection = _project(scoring, len(combo))
            if not projection["threshold_reached"]:
                continue
            risk = sum(_RISK[requirements["requirements"][m]["delivery_risk"]] for m in combo)
            external = sum(_RISK[requirements["requirements"][m]["external_dependency"]] for m in combo)
            preferred_penalty = sum(m not in requirements.get("preferred_closure_metrics", []) for m in combo)
            candidates.append((risk, external, preferred_penalty, combo, projection))
        if candidates:
            risk, external, _, combo, projection = min(candidates, key=lambda x: (x[0], x[1], x[2], x[3]))
            minimum_set = {
                "selected_metrics": list(combo),
                "selection_basis": "minimum metric count, then delivery risk, external dependency, preferred closure, and metric ID",
                "combined_delivery_risk_rank": risk,
                "combined_external_dependency_rank": external,
                **projection,
            }
            break
    return {
        "schema_version": "1.0.0",
        "artifact_type": "readiness_evidence_coverage_closure_plan",
        "readiness_artifact_sha256": readiness.get("evidence_artifact", {}).get("sha256"),
        "methodology_id": scoring["methodology_id"],
        "metric_set_id": scoring["metric_set_id"],
        "current_state": scoring["overall"],
        "unscored_metric_count": len(gaps),
        "metric_gaps": gaps,
        "minimum_threshold_closure_plan": minimum_set,
        "claim_boundaries": {
            "status_changes_require_verified_evidence": True,
            "coverage_threshold_reduction_allowed": False,
            "project_score_guaranteed_after_plan": False,
            "national_ai_readiness_score": False,
            "official_itu_score": False,
            "formal_y3172_conformance": False,
        },
    }
