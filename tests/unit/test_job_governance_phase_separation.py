from __future__ import annotations

from pathlib import Path


def test_exact_governance_phase_markers() -> None:
    job = Path("src/amba_ai/services/job_governance.py").read_text(encoding="utf-8")
    assert job.count('"governance_phase": "pre_generation"') == 1
    assert job.count('"governance_phase": "post_generation"') == 1


def test_exact_output_evaluator_deferrals() -> None:
    evaluators = Path("src/amba_ai/governance/evaluators.py").read_text(encoding="utf-8")
    assert evaluators.count('event.payload.get("governance_phase") == "pre_generation"') == 2
    assert evaluators.count("CITATION_NOT_YET_AVAILABLE") == 1
    assert evaluators.count("CONTENT_SAFETY_NOT_YET_AVAILABLE") == 1
    assert 'self._begin("find_cit"' in evaluators
    assert 'self._begin("find_safety"' in evaluators
