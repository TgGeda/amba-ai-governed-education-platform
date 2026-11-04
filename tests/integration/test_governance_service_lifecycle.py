from __future__ import annotations

from dataclasses import dataclass

from amba_ai.governance.distribution import DistributionBlockExecutor, DistributionPermitExecutor, ReviewQueueExecutor


def test_lifecycle_object_types_remain_distinct() -> None:
    from amba_ai.governance.models import PolicyFinding, PolicyRecommendation
    from amba_ai.governance.approvals import ApprovalDecision
    from amba_ai.governance.execution import ExecutionResult
    assert PolicyFinding is not PolicyRecommendation
    assert PolicyRecommendation is not ApprovalDecision
    assert ApprovalDecision is not ExecutionResult


def test_distribution_lifecycle_separates_delivery_prevention_and_review() -> None:
    delivered = DistributionPermitExecutor().execute("destination", {"event_id": "event"})
    prevented = DistributionBlockExecutor().execute("destination", {"event_id": "event"})
    review = ReviewQueueExecutor().execute("review", {"event_id": "event"})
    assert delivered.delivered and not delivered.prevented and not delivered.queued_for_review
    assert prevented.prevented and not prevented.delivered and not prevented.queued_for_review
    assert review.queued_for_review and not review.delivered and not review.prevented


def test_service_boundaries_do_not_duplicate_domain_engines() -> None:
    from amba_ai.services.governance_service import GovernanceService
    from amba_ai.services.approval_service import ApprovalService
    from amba_ai.services.execution_service import ExecutionService
    from amba_ai.services.audit_service import AuditService
    assert not hasattr(GovernanceService, "approve")
    assert not hasattr(GovernanceService, "execute")
    assert not hasattr(ApprovalService, "execute")
    assert not hasattr(ExecutionService, "approve")
    assert not hasattr(AuditService, "execute")
