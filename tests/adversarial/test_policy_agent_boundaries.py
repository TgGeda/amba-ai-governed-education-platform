from __future__ import annotations

import inspect

from amba_ai.services.policy_agent_service import PolicyAgentRequest, PolicyAgentService


def test_agent_has_no_approval_creation_surface():
    assert not hasattr(PolicyAgentService,"approve")
    assert not hasattr(PolicyAgentService,"create_approval")


def test_agent_has_no_policy_engine_surface():
    assert not hasattr(PolicyAgentService,"evaluate_policy")
    assert not hasattr(PolicyAgentService,"recommend")


def test_request_cannot_override_distribution_disposition():
    fields=PolicyAgentRequest.__dataclass_fields__
    assert "distribution_disposition" not in fields
    assert "distribution_executor" not in fields
    assert "enforcement_action" not in fields


def test_agent_does_not_define_receipt_constructors():
    source=inspect.getsource(PolicyAgentService)
    assert "ExecutionReceipt(" not in source
    assert "ReviewQueueReceipt(" not in source
    assert "DistributionAcknowledgment(" not in source
