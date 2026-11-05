from __future__ import annotations

import inspect
import pytest

from amba_ai.governance.models import SequentialIdentifierProvider
from amba_ai.institutional.assessors.consumer_protection_assessor import ConsumerProtectionAssessor
from amba_ai.institutional.assessors.data_protection_assessor import DataProtectionAssessor
from amba_ai.institutional.assessors.education_assessor import EducationAssessor
from amba_ai.institutional.context_projection import InstitutionalContextProjectionService
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.evidence_release import EvidenceReleaseService
from amba_ai.scenarios.models import ScenarioFact, ScenarioStage


def projection(recipient, fact_type, secret):
    clock=DeterministicScenarioClock(initial_time="2026-01-01T00:00:00Z")
    releases=EvidenceReleaseService(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    releases.register_fact(ScenarioFact("FACT","S",ScenarioStage.STAGE_1,(recipient,),fact_type,{"secret":secret}))
    envelope=releases.release(scenario_id="S",recipient_id=recipient,stage=ScenarioStage.STAGE_1)
    projector=InstitutionalContextProjectionService(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    return projector.project(envelope),clock


def test_assessor_rejects_another_recipient_projection():
    value,clock=projection("data_protection","personal_data","private")
    education=EducationAssessor(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    with pytest.raises(PermissionError,match="outside the assessor mandate"):
        education.assess(value)


def test_out_of_mandate_fact_is_not_assessed():
    value,clock=projection("education","personal_data","private")
    result=EducationAssessor(identifier_provider=SequentialIdentifierProvider(),clock=clock).assess(value)
    assert result.assessed_fact_ids == ()
    assert result.observations == ()
    assert result.unresolved_questions


@pytest.mark.parametrize("cls",[EducationAssessor,DataProtectionAssessor,ConsumerProtectionAssessor])
def test_assessors_expose_no_decision_or_execution_surface(cls):
    for name in ("recommend","approve","execute","deliver","distribute","authorize"):
        assert not hasattr(cls,name)


def test_assessor_source_does_not_construct_governance_artifacts():
    sources="\n".join(inspect.getsource(cls) for cls in (EducationAssessor,DataProtectionAssessor,ConsumerProtectionAssessor))
    for prohibited in ("PolicyRecommendation(","ApprovalDecision(","ExecutionReceipt(","DistributionEffect("):
        assert prohibited not in sources
