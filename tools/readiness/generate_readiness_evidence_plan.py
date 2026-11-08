from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json, sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from amba_ai.readiness.evidence_requirement_validator import load_requirements, validate_against_scoring
from amba_ai.readiness.gap_planner import build_evidence_plan

def _write_markdown(plan: dict, path: Path) -> None:
    current = plan["current_state"]["coverage"]
    closure = plan["minimum_threshold_closure_plan"]
    lines = [
        "# AMBA-GOV Readiness Evidence-Coverage Closure Plan", "",
        "> This plan identifies evidence needed to increase defensible project-level coverage. It does not change statuses, lower thresholds, guarantee a score, claim an official ITU score, or establish national AI readiness.", "",
        "## Current state", "",
        f"- Scored applicable metrics: `{current['scored_metric_count']}/{current['applicable_metric_count']}`",
        f"- Coverage ratio: `{current['coverage_ratio']}`",
        f"- Required ratio: `{current['minimum_required_ratio']}`",
        f"- Overall project score: `{plan['current_state']['score']}`",
        f"- Score status: `{plan['current_state']['status']}`", "",
        "## Minimum threshold-closure plan", "",
        f"- Selected metrics: `{', '.join(closure['selected_metrics'])}`",
        f"- Projected scored metrics: `{closure['new_scored_metric_count']}`",
        f"- Projected coverage: `{closure['new_coverage_ratio']}`",
        f"- Threshold reached: `{str(closure['threshold_reached']).lower()}`",
        f"- Selection basis: {closure['selection_basis']}", "",
        "## Metric evidence gaps", "",
    ]
    for item in plan["metric_gaps"]:
        impact = item["score_impact_if_resolved"]
        lines += [
            f"### {item['metric_id']} · {item['title']}",
            f"- Current status: `{item['current_status']}`",
            f"- Delivery risk: `{item['delivery_risk']}`",
            f"- External dependency: `{item['external_dependency']}`",
            f"- Projected coverage if resolved alone: `{impact['new_coverage_ratio']}`",
            f"- Threshold reached alone: `{str(impact['threshold_reached']).lower()}`",
            "- Missing evidence:",
            *[f"  - {value}" for value in item["missing_evidence"]],
            "- Recommended actions:",
            *[f"  - {value}" for value in item["recommended_actions"]],
            "- Acceptance criteria:",
            *[f"  - {value}" for value in item["acceptance_criteria"]],
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")

def main() -> None:
    readiness_path = ROOT / "submission" / "artifacts" / "readiness_reflection.json"
    requirements_path = ROOT / "config" / "readiness_evidence_requirements.yaml"
    readiness_bytes = readiness_path.read_bytes()
    readiness = json.loads(readiness_bytes.decode("utf-8"))
    requirements = load_requirements(requirements_path)
    validate_against_scoring(requirements, readiness["scoring"])
    plan = build_evidence_plan(readiness, requirements)
    plan["readiness_reflection_path"] = readiness_path.relative_to(ROOT).as_posix()
    plan["readiness_reflection_sha256"] = sha256(readiness_bytes).hexdigest()
    output = ROOT / "submission" / "artifacts" / "readiness_evidence_plan.json"
    markdown = ROOT / "submission" / "artifacts" / "readiness_evidence_plan.md"
    text = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    output.write_text(text, encoding="utf-8", newline="\n")
    _write_markdown(plan, markdown)
    closure = plan["minimum_threshold_closure_plan"]
    print(f"unscored_metric_count={plan['unscored_metric_count']}")
    print(f"selected_metrics={','.join(closure['selected_metrics'])}")
    print(f"projected_scored_metric_count={closure['new_scored_metric_count']}")
    print(f"projected_coverage_ratio={closure['new_coverage_ratio']}")
    print(f"threshold_reached={closure['threshold_reached']}")
    print(f"sha256={sha256(text.encode('utf-8')).hexdigest()}")
if __name__ == "__main__": main()
