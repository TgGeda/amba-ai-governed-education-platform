from __future__ import annotations

from dataclasses import replace
import inspect
import pytest

from amba_ai.institutional.assessment import AssessmentConfidence, InstitutionalAssessment
from amba_ai.institutional.conflict_resolution import InstitutionalConflictDetector
from amba_ai.institutional.coordination import InstitutionalCoordinationResult, InstitutionalCoordinationService
from amba_ai.institutional.registry import InstitutionalAssessorRegistry
from amba_ai.scenarios.models import ScenarioConfigurationError


def test_conflict_detector_preserves_confidence_divergence():
    assert hasattr(InstitutionalConflictDetector,"detect")


def test_coordination_result_rejects_consensus_metadata():
    fields=InstitutionalCoordinationResult.__dataclass_fields__
    assert "recommended_action" not in fields
    assert "approval_decision" not in fields
    assert "consensus" not in fields


def test_coordination_exposes_no_decision_surface():
    for name in ("recommend","approve","execute","deliver","distribute","authorize","resolve_winner"):
        assert not hasattr(InstitutionalCoordinationService,name)


def test_registry_exposes_no_operational_surface():
    for name in ("recommend","approve","execute","deliver","distribute","authorize"):
        assert not hasattr(InstitutionalAssessorRegistry,name)


def test_coordination_source_does_not_construct_governance_artifacts():
    source=inspect.getsource(InstitutionalCoordinationService)
    for prohibited in ("PolicyRecommendation(","ApprovalDecision(","ExecutionReceipt(","DistributionEffect(","EnforcementAction."):
        assert prohibited not in source


def test_conflicts_are_not_marked_resolved_by_default():
    source=inspect.getsource(InstitutionalConflictDetector)
    assert "resolved=True" not in source
