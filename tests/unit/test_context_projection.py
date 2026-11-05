from __future__ import annotations

from amba_ai.governance.models import SequentialIdentifierProvider
from amba_ai.institutional.context_projection import InstitutionalContextProjectionService
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.evidence_release import EvidenceReleaseService
from amba_ai.scenarios.models import ScenarioFact, ScenarioStage


def setup_projection():
    clock=DeterministicScenarioClock(initial_time="2026-01-01T00:00:00Z")
    releases=EvidenceReleaseService(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    releases.register_facts((ScenarioFact("F1","S1",ScenarioStage.STAGE_1,("education",),"baseline",{"v":1}),ScenarioFact("F2","S1",ScenarioStage.STAGE_1,("consumer",),"consumer",{"v":2})))
    projector=InstitutionalContextProjectionService(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    return releases,projector


def test_projection_exactly_preserves_release_scope():
    releases,projector=setup_projection()
    envelope=releases.release(scenario_id="S1",recipient_id="education",stage=ScenarioStage.STAGE_1)
    value=projector.project(envelope)
    assert value.fact_ids == envelope.fact_ids == ("F1",)
    assert value.recipient_id == envelope.recipient_id
    assert value.stage is envelope.stage
    assert value.source_release_digest == envelope.release_digest


def test_projection_is_idempotent_per_release():
    releases,projector=setup_projection()
    envelope=releases.release(scenario_id="S1",recipient_id="education",stage=ScenarioStage.STAGE_1)
    assert projector.project(envelope) is projector.project(envelope)


def test_projection_is_retrievable_by_release_digest():
    releases,projector=setup_projection()
    envelope=releases.release(scenario_id="S1",recipient_id="education",stage=ScenarioStage.STAGE_1)
    value=projector.project(envelope)
    assert projector.get_by_release_digest(envelope.release_digest) is value


def test_projection_creates_no_governance_side_effects():
    releases,projector=setup_projection()
    envelope=releases.release(scenario_id="S1",recipient_id="education",stage=ScenarioStage.STAGE_1)
    metadata=projector.project(envelope).metadata
    assert metadata["governance_decision_created"] is False
    assert metadata["approval_created"] is False
    assert metadata["execution_requested"] is False
    assert metadata["distribution_attempted"] is False
