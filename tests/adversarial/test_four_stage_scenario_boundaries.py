from __future__ import annotations

import inspect

from amba_ai.scenarios.runner import FourStageScenarioRunner, ScenarioRunResult


def test_runner_enforces_exact_four_stage_sequence():
    source=inspect.getsource(FourStageScenarioRunner.run)
    assert "STAGE_1" in source
    assert "STAGE_4" in source
    assert "four-stage runner requires exactly" in source


def test_runner_fails_closed_on_future_evidence():
    source=inspect.getsource(FourStageScenarioRunner._pipeline_event)
    assert "future-stage evidence" in source


def test_runner_verifies_invariants_before_stage_result():
    source=inspect.getsource(FourStageScenarioRunner._execute_stage)
    assert source.index("self._invariants.verify(") < source.index("return ScenarioStageResult(")


def test_runner_verifies_audit_before_run_result():
    source=inspect.getsource(FourStageScenarioRunner.run)
    assert source.index("self._audit.verify(run_key)") < source.index("result = ScenarioRunResult(")


def test_run_result_has_no_mutable_or_authorizing_surface():
    for name in ("approve","authorize","execute","deliver","distribute","recommend"):
        assert not hasattr(ScenarioRunResult,name)
