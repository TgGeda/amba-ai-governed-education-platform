from __future__ import annotations

import inspect

from amba_ai.scenarios.runner import FourStageScenarioRunner, ScenarioRunResult, ScenarioStageResult


def test_runner_result_models_are_immutable():
    assert ScenarioStageResult.__dataclass_params__.frozen is True
    assert ScenarioRunResult.__dataclass_params__.frozen is True


def test_runner_exposes_one_execution_entrypoint():
    public={name for name,value in inspect.getmembers(FourStageScenarioRunner) if callable(value) and not name.startswith("_")}
    assert public == {"run"}


def test_runner_does_not_construct_governance_outcomes():
    source=inspect.getsource(FourStageScenarioRunner)
    for prohibited in (
        "PolicyRecommendation(",
        "ApprovalDecision(",
        "ExecutionReceipt(",
        "ReviewQueueReceipt(",
        "DistributionEffect(",
        "DistributionAcknowledgment(",
        "Y3172PipelineTrace(",
        "AuditBlock(",
        "EnforcementAction.PROCEED",
        "EnforcementAction.BLOCK",
    ):
        assert prohibited not in source
