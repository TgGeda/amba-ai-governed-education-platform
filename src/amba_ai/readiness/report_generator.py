from __future__ import annotations
from pathlib import Path
from typing import Any
import hashlib, json
from .models import ReadinessReflection

def write_reports(reflection: ReadinessReflection, compact: Path, pretty: Path, markdown: Path, scoring: dict[str, Any] | None = None) -> str:
    payload = reflection.to_dict()
    if scoring is not None:
        payload["scoring"] = scoring
        payload["overall_project_score"] = scoring["overall"]["score"]
        payload["score_status"] = scoring["overall"]["status"]
        payload["evidence_coverage"] = scoring["overall"]["coverage"]
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    compact.parent.mkdir(parents=True, exist_ok=True)
    compact.write_text(text, encoding="utf-8", newline="\n")
    pretty.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines = ["# AMBA-GOV Evidence-Bounded Readiness Reflection", "", f"Evidence artifact SHA-256: `{payload['evidence_artifact']['sha256']}`", "", "> Project-level reflection only. This is not a national assessment, official ITU certification, formal Y.3172 conformance claim, or legal determination.", "", "## Score boundary", "", f"- Overall project score: `{payload['overall_project_score']}`", f"- Status: `{payload['score_status']}`"]
    if scoring is not None:
        coverage = scoring["overall"]["coverage"]
        lines += [f"- Evidence coverage: `{coverage['coverage_ratio']}`", f"- Minimum required coverage: `{coverage['minimum_required_ratio']}`", f"- Scored project proxy metrics: `{coverage['scored_metric_count']}/{coverage['applicable_metric_count']}`", "- Scope: 19 project proxy metrics mapped to the verified reflection; the ITU framework's 111 metrics remain a reference count, not a claim of full metric assessment."]
    lines += ["", "## Findings", ""]
    for finding in payload["findings"]:
        lines += [f"### {finding['framework_element_id']} · {finding['framework_element_name']}", f"- Type: `{finding['framework_element_type']}`", f"- Status: `{finding['status']}`", f"- Rationale: {finding['rationale']}", f"- Evidence pointers: {', '.join(finding['evidence_pointers']) or 'none'}", f"- Approved passage IDs: {', '.join(finding['passage_ids']) or 'none'}", f"- Y.3172 records: {', '.join(finding['y3172_record_ids']) or 'none'}", f"- Limitations: {'; '.join(finding['limitations']) or 'none'}", ""]
    markdown.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
