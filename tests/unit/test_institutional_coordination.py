from __future__ import annotations

from amba_ai.governance.models import SequentialIdentifierProvider
from amba_ai.institutional.assessors.consumer_protection_assessor import ConsumerProtectionAssessor
from amba_ai.institutional.assessors.education_assessor import EducationAssessor
from amba_ai.institutional.conflict_resolution import InstitutionalConflictDetector
from amba_ai.institutional.context_projection import InstitutionalContextProjectionService
from amba_ai.institutional.coordination import InstitutionalCoordinationService
from amba_ai.institutional.registry import InstitutionalAssessorRegistry
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.evidence_release import EvidenceReleaseService
from amba_ai.scenarios.models import ScenarioFact, ScenarioStage


def setup():
    clock=DeterministicScenarioClock(initial_time="2026-01-01T00:00:00Z")
    releases=EvidenceReleaseService(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    releases.register_facts((
        ScenarioFact("EDU","S",ScenarioStage.STAGE_1,("education",),"classroom_use",{"teacher_supervised":True}),
        ScenarioFact("BUY","S",ScenarioStage.STAGE_1,("consumer_protection",),"purchase_interface",{"payment_enabled":True}),
        ScenarioFact("UNCOVERED","S",ScenarioStage.STAGE_1,("education",),"personal_data",{"learner_data":True}),
    ))
    projector=InstitutionalContextProjectionService(identifier_provider=SequentialIdentifierProvider(),clock=clock)
    projections=tuple(projector.project(releases.release(scenario_id="S",recipient_id=recipient,stage=ScenarioStage.STAGE_1)) for recipient in ("consumer_protection","education"))
    registry=InstitutionalAssessorRegistry()
    registry.register(EducationAssessor(identifier_provider=SequentialIdentifierProvider(),clock=clock))
    registry.register(ConsumerProtectionAssessor(identifier_provider=SequentialIdentifierProvider(),clock=clock))
    coordinator=InstitutionalCoordinationService(registry=registry,conflict_detector=InstitutionalConflictDetector(),identifier_provider=SequentialIdentifierProvider(),clock=clock)
    return coordinator,projections


def test_coordination_preserves_every_assessment():
    coordinator,projections=setup(); result=coordinator.coordinate(projections)
    assert len(result.assessments) == len(projections)
    assert set(result.projection_ids) == {item.projection_id for item in projections}


def test_coordination_preserves_sourced_questions():
    coordinator,projections=setup(); result=coordinator.coordinate(projections)
    for question in result.unresolved_questions:
        assert question.institution_id
        assert question.assessment_id


def test_coordination_reports_uncovered_facts():
    coordinator,projections=setup(); result=coordinator.coordinate(projections)
    assert "UNCOVERED" in result.uncovered_fact_ids


def test_coordination_is_idempotent_for_same_projection_scope():
    coordinator,projections=setup()
    assert coordinator.coordinate(projections) is coordinator.coordinate(tuple(reversed(projections)))


def test_coordination_creates_no_operational_side_effects():
    coordinator,projections=setup(); metadata=coordinator.coordinate(projections).metadata
    assert metadata["governance_recommendation_created"] is False
    assert metadata["approval_created"] is False
    assert metadata["execution_requested"] is False
    assert metadata["distribution_attempted"] is False
