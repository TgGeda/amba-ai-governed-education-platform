from __future__ import annotations

from dataclasses import replace
import pytest

from amba_ai.scenarios.models import ScenarioFact, ScenarioStage
from amba_ai.scenarios.repository import ScenarioDefinition, ScenarioDestination, ScenarioEventDefinition


def test_event_cannot_reference_future_fact_in_validated_scenario():
    assert ScenarioStage.STAGE_4 > ScenarioStage.STAGE_1


def test_definition_rejects_duplicate_operation_identities():
    facts=(ScenarioFact("F1","S",ScenarioStage.STAGE_1,("education",),"baseline",{}),)
    destinations=(ScenarioDestination("D1","sink","education"),)
    events=(ScenarioEventDefinition("E1","O1",ScenarioStage.STAGE_1,"D1",("F1",)),ScenarioEventDefinition("E2","O1",ScenarioStage.STAGE_1,"D1",("F1",)))
    with pytest.raises(Exception,match="operation_id"):
        ScenarioDefinition("S","Duplicate",(ScenarioStage.STAGE_1,),facts,destinations,events)


def test_definition_rejects_non_synthetic_destination():
    with pytest.raises(Exception,match="synthetic"):
        ScenarioDestination("D1","sink","education",synthetic=False)
