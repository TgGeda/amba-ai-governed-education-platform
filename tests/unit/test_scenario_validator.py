from __future__ import annotations

import pytest

from amba_ai.governance.models import SequentialIdentifierProvider
from amba_ai.institutional.assessors.education_assessor import EducationAssessor
from amba_ai.institutional.registry import InstitutionalAssessorRegistry
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.models import ScenarioFact, ScenarioStage
from amba_ai.scenarios.repository import ScenarioDefinition, ScenarioDestination, ScenarioEventDefinition
from amba_ai.scenarios.validator import ScenarioValidator


def registry():
    value=InstitutionalAssessorRegistry(); value.register(EducationAssessor(identifier_provider=SequentialIdentifierProvider(),clock=DeterministicScenarioClock(initial_time="2026-01-01T00:00:00Z"))); return value


def valid_definition():
    facts=(ScenarioFact("F1","S",ScenarioStage.STAGE_1,("education",),"baseline",{}),ScenarioFact("F2","S",ScenarioStage.STAGE_2,("education",),"classroom_use",{}))
    destinations=(ScenarioDestination("D1","teacher_ui","education"),)
    events=(ScenarioEventDefinition("E1","O1",ScenarioStage.STAGE_1,"D1",("F1",)),ScenarioEventDefinition("E2","O2",ScenarioStage.STAGE_2,"D1",("F1","F2")))
    return ScenarioDefinition("S","Scenario",(ScenarioStage.STAGE_1,ScenarioStage.STAGE_2),facts,destinations,events)


def test_validator_accepts_complete_definition():
    result=ScenarioValidator(institutional_registry=registry()).validate(valid_definition())
    assert result.valid is True
    assert result.checked_fact_count == 2


def test_validator_rejects_stage_gap():
    base=valid_definition()
    with pytest.raises(Exception,match="gap"):
        ScenarioValidator(institutional_registry=registry()).validate(ScenarioDefinition("S","Gap",(ScenarioStage.STAGE_1,ScenarioStage.STAGE_3),base.facts,base.destinations,base.events))


def test_validator_rejects_unregistered_recipient():
    fact=ScenarioFact("F1","S",ScenarioStage.STAGE_1,("unknown",),"baseline",{})
    definition=ScenarioDefinition("S","Unknown",(ScenarioStage.STAGE_1,),(fact,),(ScenarioDestination("D1","sink","education"),),(ScenarioEventDefinition("E1","O1",ScenarioStage.STAGE_1,"D1",("F1",)),))
    with pytest.raises(Exception,match="unregistered"):
        ScenarioValidator(institutional_registry=registry()).validate(definition)


def test_validator_rejects_future_fact_reference():
    base=valid_definition()
    bad=(ScenarioEventDefinition("E1","O1",ScenarioStage.STAGE_1,"D1",("F2",)),)
    definition=ScenarioDefinition("S","Future",base.configured_stages,base.facts,base.destinations,bad)
    with pytest.raises(Exception,match="future-stage"):
        ScenarioValidator(institutional_registry=registry()).validate(definition)
