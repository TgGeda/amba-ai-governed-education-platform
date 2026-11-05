from __future__ import annotations

import pytest

from amba_ai.institutional.models import InstitutionalContextProjection
from amba_ai.scenarios.models import ScenarioConfigurationError, ScenarioFact, ScenarioStage, sha256_canonical


def fact():
    return ScenarioFact("F1","S1",ScenarioStage.STAGE_1,("education",),"baseline",{"value":1})


def projection(**overrides):
    item=fact()
    values={"projection_id":"P1","scenario_id":"S1","stage":ScenarioStage.STAGE_1,"recipient_id":"education","source_release_id":"R1","source_release_digest":"a"*64,"projected_at":"2026-01-01T00:00:00Z","facts":(item,),"metadata":{"source_release_verified":True},"synthetic":True,"legal_effect":False}
    values.update(overrides)
    payload={"projection_id":values["projection_id"],"scenario_id":values["scenario_id"],"stage":int(values["stage"]),"recipient_id":values["recipient_id"],"source_release_id":values["source_release_id"],"source_release_digest":values["source_release_digest"],"projected_at":"2026-01-01T00:00:00+00:00","facts":[entry.to_dict() for entry in values["facts"]],"metadata":values["metadata"],"synthetic":values["synthetic"],"legal_effect":values["legal_effect"]}
    values["projection_digest"]=sha256_canonical(payload)
    return InstitutionalContextProjection(**values)


def test_projection_is_immutable_and_canonical():
    value=projection()
    assert value.fact_ids == ("F1",)
    assert value.to_canonical_json()
    with pytest.raises(TypeError): value.metadata["x"]=True


def test_projection_rejects_governance_decision_metadata():
    with pytest.raises(ScenarioConfigurationError): projection(metadata={"recommended_action":"block"})


def test_projection_remains_synthetic_without_legal_effect():
    with pytest.raises(ScenarioConfigurationError): projection(synthetic=False)
    with pytest.raises(ScenarioConfigurationError): projection(legal_effect=True)


def test_projection_rejects_wrong_recipient_fact():
    with pytest.raises(Exception): projection(recipient_id="consumer")
