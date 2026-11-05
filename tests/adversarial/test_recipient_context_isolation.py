from __future__ import annotations

from dataclasses import replace
import pytest

from amba_ai.governance.models import SequentialIdentifierProvider
from amba_ai.institutional.context_projection import InstitutionalContextProjectionService
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.evidence_release import EvidenceReleaseService
from amba_ai.scenarios.models import ScenarioFact, ScenarioStage


def setup():
    clock=DeterministicScenarioClock(initial_time="2026-01-01T00:00:00Z")
    releases=EvidenceReleaseService(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    releases.register_facts((ScenarioFact("EDU","S",ScenarioStage.STAGE_1,("education",),"education",{"secret":"edu"}),ScenarioFact("DPA","S",ScenarioStage.STAGE_1,("data_protection",),"privacy",{"secret":"dpa"}),ScenarioFact("FUTURE","S",ScenarioStage.STAGE_4,("education",),"advertising",{"secret":"future"})))
    projector=InstitutionalContextProjectionService(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    return releases,projector


def test_projection_cannot_see_other_recipient_fact():
    releases,projector=setup(); envelope=releases.release(scenario_id="S",recipient_id="education",stage=ScenarioStage.STAGE_1); value=projector.project(envelope)
    assert value.fact_ids == ("EDU",)
    assert "dpa" not in value.to_canonical_json()


def test_projection_cannot_see_future_fact():
    releases,projector=setup(); envelope=releases.release(scenario_id="S",recipient_id="education",stage=ScenarioStage.STAGE_1); value=projector.project(envelope)
    assert "FUTURE" not in value.fact_ids
    assert "future" not in value.to_canonical_json()


def test_tampered_release_is_rejected():
    releases,projector=setup(); envelope=releases.release(scenario_id="S",recipient_id="education",stage=ScenarioStage.STAGE_1)
    tampered=object.__new__(type(envelope))
    for field in envelope.__dataclass_fields__: object.__setattr__(tampered,field,getattr(envelope,field))
    object.__setattr__(tampered,"release_digest","0"*64)
    with pytest.raises(Exception,match="digest"): projector.project(tampered)


def test_projector_has_no_fact_registry_surface():
    _,projector=setup()
    assert not hasattr(projector,"register_fact")
    assert not hasattr(projector,"release")
    assert not hasattr(projector,"evaluate")
    assert not hasattr(projector,"recommend")
