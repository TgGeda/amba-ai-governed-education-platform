from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml

class EvidenceRequirementValidationError(ValueError):
    pass

_REQUIRED_FIELDS = {
    "title", "eligible_target_statuses", "missing_evidence", "recommended_actions",
    "acceptance_criteria", "delivery_risk", "external_dependency",
}
_ALLOWED_TARGETS = {"partially_demonstrated", "demonstrated"}
_ALLOWED_RISK = {"low", "medium", "high"}


def load_requirements(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload.get("selection_policy", {}).get("prohibit_threshold_reduction") is not True:
        raise EvidenceRequirementValidationError("coverage threshold reduction must be prohibited")
    if payload.get("selection_policy", {}).get("prohibit_status_change_without_verified_evidence") is not True:
        raise EvidenceRequirementValidationError("status changes without verified evidence must be prohibited")
    requirements = payload.get("requirements")
    if not isinstance(requirements, dict) or not requirements:
        raise EvidenceRequirementValidationError("requirements must be a non-empty mapping")
    for metric_id, item in requirements.items():
        missing = _REQUIRED_FIELDS - set(item)
        if missing:
            raise EvidenceRequirementValidationError(f"{metric_id} missing fields: {sorted(missing)}")
        if not item["missing_evidence"] or not item["recommended_actions"] or not item["acceptance_criteria"]:
            raise EvidenceRequirementValidationError(f"{metric_id} requirements must be non-empty")
        targets = set(item["eligible_target_statuses"])
        if not targets or not targets <= _ALLOWED_TARGETS:
            raise EvidenceRequirementValidationError(f"{metric_id} has invalid target statuses: {sorted(targets)}")
        if item["delivery_risk"] not in _ALLOWED_RISK or item["external_dependency"] not in _ALLOWED_RISK:
            raise EvidenceRequirementValidationError(f"{metric_id} has invalid risk classification")
    preferred = payload.get("preferred_closure_metrics", [])
    if len(preferred) != len(set(preferred)) or any(metric_id not in requirements for metric_id in preferred):
        raise EvidenceRequirementValidationError("preferred closure metrics must be unique requirement IDs")
    return payload


def validate_against_scoring(requirements: dict[str, Any], scoring: dict[str, Any]) -> tuple[str, ...]:
    unscored = tuple(sorted(item["metric_id"] for item in scoring["metric_evaluations"] if item["applicable"] and not item["scored"]))
    configured = tuple(sorted(requirements["requirements"]))
    if configured != unscored:
        raise EvidenceRequirementValidationError(
            f"requirements must exactly cover applicable unscored metrics: configured={configured}, unscored={unscored}"
        )
    return unscored
