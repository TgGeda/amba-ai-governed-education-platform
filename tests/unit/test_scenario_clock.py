from __future__ import annotations

from datetime import timedelta
import pytest

from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.models import ScenarioConfigurationError, ScenarioStage


def test_clock_advances_time_without_advancing_stage():
    clock=DeterministicScenarioClock(initial_time="2026-01-01T00:00:00Z")
    clock.advance_time(timedelta(days=180))
    assert clock.stage is ScenarioStage.STAGE_1


def test_clock_advances_stages_sequentially():
    clock=DeterministicScenarioClock(initial_time="2026-01-01T00:00:00Z")
    assert clock.advance_stage(ScenarioStage.STAGE_2) is ScenarioStage.STAGE_2
    with pytest.raises(ScenarioConfigurationError): clock.advance_stage(ScenarioStage.STAGE_4)


def test_clock_rejects_backward_time():
    clock=DeterministicScenarioClock(initial_time="2026-01-02T00:00:00Z")
    with pytest.raises(ScenarioConfigurationError): clock.advance_stage(ScenarioStage.STAGE_2,at_time="2026-01-01T00:00:00Z")


def test_clock_requires_timezone():
    with pytest.raises(ScenarioConfigurationError): DeterministicScenarioClock(initial_time="2026-01-01T00:00:00")
