from __future__ import annotations

import pytest

from amba_ai.governance.models import SequentialIdentifierProvider
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.evidence_release import EvidenceReleaseService
from amba_ai.scenarios.models import ScenarioAccessError, ScenarioFact, ScenarioStage


def setup_service():
    clock=DeterministicScenarioClock(initial_time="2026-01-01T00:00:00Z")
    service=EvidenceReleaseService(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    service.register_facts((
        ScenarioFact("F1","S1",ScenarioStage.STAGE_1,("education",),"baseline",{"value":1}),
        ScenarioFact("F2","S1",ScenarioStage.STAGE_2,("education","consumer"),"commerce",{"value":2}),
        ScenarioFact("F3","S1",ScenarioStage.STAGE_3,("consumer",),"sdk",{"value":3}),
    ))
    return service,clock


def test_release_contains_only_visible_current_facts():
    service,_=setup_service(); envelope=service.release(scenario_id="S1",recipient_id="education",stage=ScenarioStage.STAGE_1)
    assert envelope.fact_ids == ("F1",)


def test_release_is_explicit_and_time_does_not_release_facts():
    service,clock=setup_service(); first=service.release(scenario_id="S1",recipient_id="education",stage=ScenarioStage.STAGE_1)
    from datetime import timedelta
    clock.advance_time(timedelta(days=365))
    second=service.release(scenario_id="S1",recipient_id="education",stage=ScenarioStage.STAGE_1)
    assert first.fact_ids == ("F1",)
    assert second.fact_ids == ()


def test_future_release_is_rejected():
    service,_=setup_service()
    with pytest.raises(ScenarioAccessError): service.release(scenario_id="S1",recipient_id="education",stage=ScenarioStage.STAGE_2)


def test_release_chain_and_no_duplicate_release():
    service,clock=setup_service(); first=service.release(scenario_id="S1",recipient_id="education",stage=ScenarioStage.STAGE_1)
    clock.advance_stage(ScenarioStage.STAGE_2)
    second=service.release(scenario_id="S1",recipient_id="education",stage=ScenarioStage.STAGE_2)
    assert second.fact_ids == ("F2",)
    assert second.previous_release_digest == first.release_digest
    assert service.verify_chain(scenario_id="S1",recipient_id="education")


def test_recipient_projection_is_isolated():
    service,clock=setup_service(); clock.advance_stage(ScenarioStage.STAGE_2)
    education=service.release(scenario_id="S1",recipient_id="education",stage=ScenarioStage.STAGE_2)
    consumer=service.release(scenario_id="S1",recipient_id="consumer",stage=ScenarioStage.STAGE_2)
    assert education.fact_ids == ("F1","F2")
    assert consumer.fact_ids == ("F2",)
