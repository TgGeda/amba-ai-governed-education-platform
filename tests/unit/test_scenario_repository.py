from __future__ import annotations

import pytest

from amba_ai.scenarios.models import ScenarioFact, ScenarioStage
from amba_ai.scenarios.repository import ScenarioDefinition, ScenarioDestination, ScenarioEventDefinition, ScenarioRepository


def definition(scenario_id="S1",fact_id="F1"):
    fact=ScenarioFact(fact_id,scenario_id,ScenarioStage.STAGE_1,("education",),"baseline",{"v":1})
    destination=ScenarioDestination("D1","teacher_ui","education")
    event=ScenarioEventDefinition("E1","O1",ScenarioStage.STAGE_1,"D1",(fact_id,))
    return ScenarioDefinition(scenario_id,"Synthetic scenario",(ScenarioStage.STAGE_1,),(fact,),(destination,),(event,))


def test_repository_is_idempotent_and_deterministic():
    repository=ScenarioRepository(); value=definition(); repository.register(value); repository.register(value)
    assert repository.get("S1") is value
    assert repository.list_definitions() == (value,)


def test_repository_rejects_conflicting_scenario_replacement():
    repository=ScenarioRepository(); repository.register(definition())
    with pytest.raises(Exception,match="scenario_id"):
        repository.register(ScenarioDefinition("S1","Changed",(ScenarioStage.STAGE_1,),definition().facts,definition().destinations,definition().events))


def test_repository_rejects_global_fact_collision():
    repository=ScenarioRepository(); repository.register(definition("S1","F1"))
    with pytest.raises(Exception,match="fact_id"):
        repository.register(definition("S2","F1"))


def test_repository_has_no_operational_surface():
    repository=ScenarioRepository()
    for name in ("recommend","approve","execute","distribute","authorize"):
        assert not hasattr(repository,name)
