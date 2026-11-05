from __future__ import annotations

import pytest

from amba_ai.scenarios.models import ScenarioConfigurationError, ScenarioFact, ScenarioStage


def fact(**overrides):
    values={"fact_id":"FACT-1","scenario_id":"SCENARIO-1","release_stage":ScenarioStage.STAGE_2,"recipient_ids":("education",),"fact_type":"commercial_signal","payload":{"enabled":True}}
    values.update(overrides)
    return ScenarioFact(**values)


def test_fact_is_immutable_and_digest_is_deterministic():
    first=fact(payload={"a":1,"b":2}); second=fact(payload={"b":2,"a":1})
    assert first.fact_digest == second.fact_digest
    with pytest.raises(TypeError): first.payload["a"]=3


def test_fact_visibility_requires_stage_and_recipient():
    item=fact()
    assert not item.visible_to("education",ScenarioStage.STAGE_1)
    assert item.visible_to("education",ScenarioStage.STAGE_2)
    assert not item.visible_to("consumer",ScenarioStage.STAGE_4)


def test_fact_requires_synthetic_without_legal_effect():
    with pytest.raises(ScenarioConfigurationError): fact(synthetic=False)
    with pytest.raises(ScenarioConfigurationError): fact(legal_effect=True)


def test_fact_rejects_duplicate_recipients():
    with pytest.raises(ScenarioConfigurationError): fact(recipient_ids=("education","education"))
