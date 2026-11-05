from __future__ import annotations

from datetime import timedelta
import pytest

from amba_ai.governance.models import SequentialIdentifierProvider
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.evidence_release import EvidenceReleaseService
from amba_ai.scenarios.models import ScenarioAccessError, ScenarioFact, ScenarioStage


def service():
    clock=DeterministicScenarioClock(initial_time="2026-01-01T00:00:00Z")
    releases=EvidenceReleaseService(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    releases.register_facts((
        ScenarioFact("NOW","SCENARIO",ScenarioStage.STAGE_1,("education",),"baseline",{"secret":False}),
        ScenarioFact("FUTURE","SCENARIO",ScenarioStage.STAGE_4,("education",),"targeted_advertising",{"secret":True}),
        ScenarioFact("OTHER","SCENARIO",ScenarioStage.STAGE_1,("consumer",),"consumer_only",{"secret":True}),
    ))
    return releases,clock


def test_future_fact_cannot_leak_into_early_release():
    releases,_=service(); envelope=releases.release(scenario_id="SCENARIO",recipient_id="education",stage=ScenarioStage.STAGE_1)
    assert envelope.fact_ids == ("NOW",)
    assert "FUTURE" not in envelope.to_canonical_json()


def test_advancing_wall_clock_does_not_unlock_future_stage():
    releases,clock=service(); clock.advance_time(timedelta(days=3650))
    envelope=releases.release(scenario_id="SCENARIO",recipient_id="education",stage=ScenarioStage.STAGE_1)
    assert envelope.fact_ids == ("NOW",)


def test_requesting_future_stage_fails_closed():
    releases,_=service()
    with pytest.raises(ScenarioAccessError): releases.release(scenario_id="SCENARIO",recipient_id="education",stage=ScenarioStage.STAGE_4)


def test_recipient_cannot_receive_other_context():
    releases,_=service(); envelope=releases.release(scenario_id="SCENARIO",recipient_id="education",stage=ScenarioStage.STAGE_1)
    assert "OTHER" not in envelope.fact_ids
    assert "consumer_only" not in envelope.to_canonical_json()
