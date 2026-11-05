from __future__ import annotations

import pytest

from amba_ai.governance.models import SequentialIdentifierProvider
from amba_ai.institutional.assessors.consumer_protection_assessor import ConsumerProtectionAssessor
from amba_ai.institutional.assessors.data_protection_assessor import DataProtectionAssessor
from amba_ai.institutional.assessors.education_assessor import EducationAssessor
from amba_ai.institutional.context_projection import InstitutionalContextProjectionService
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.evidence_release import EvidenceReleaseService
from amba_ai.scenarios.models import ScenarioFact, ScenarioStage


def projection(recipient, fact_type, payload):
    clock=DeterministicScenarioClock(initial_time="2026-01-01T00:00:00Z")
    releases=EvidenceReleaseService(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    releases.register_fact(ScenarioFact("FACT-1","SCENARIO",ScenarioStage.STAGE_1,(recipient,),fact_type,payload))
    envelope=releases.release(scenario_id="SCENARIO",recipient_id=recipient,stage=ScenarioStage.STAGE_1)
    projector=InstitutionalContextProjectionService(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    return projector.project(envelope),clock


def assessor(cls, clock):
    return cls(identifier_provider=SequentialIdentifierProvider(),clock=clock)


def test_education_assessor_preserves_projection_binding():
    value,clock=projection("education","classroom_use",{"teacher_supervised":True})
    result=assessor(EducationAssessor,clock).assess(value)
    assert result.projection_id == value.projection_id
    assert result.assessed_fact_ids == value.fact_ids
    assert result.observations[0].fact_ids == ("FACT-1",)


def test_data_protection_assessor_preserves_unresolved_basis():
    value,clock=projection("data_protection","targeted_advertising",{"learner_profile_used":True})
    result=assessor(DataProtectionAssessor,clock).assess(value)
    assert result.unresolved_questions
    assert any(item.category == "profiling_and_targeting" for item in result.observations)


def test_consumer_assessor_identifies_commercial_interface():
    value,clock=projection("consumer_protection","purchase_interface",{"payment_enabled":True})
    result=assessor(ConsumerProtectionAssessor,clock).assess(value)
    assert any(item.category == "commercial_interface" for item in result.observations)
    assert result.legal_effect is False


@pytest.mark.parametrize("cls",[EducationAssessor,DataProtectionAssessor,ConsumerProtectionAssessor])
def test_assessors_create_no_governance_side_effects(cls):
    recipient=cls.recipient_id
    relevant=next(iter(cls.relevant_fact_types))
    value,clock=projection(recipient,relevant,{"synthetic":True})
    metadata=assessor(cls,clock).assess(value).metadata
    assert metadata["governance_recommendation_created"] is False
    assert metadata["approval_created"] is False
    assert metadata["execution_requested"] is False
    assert metadata["distribution_attempted"] is False
