from __future__ import annotations

import inspect

from amba_ai.services.policy_agent_service import PolicyAgentRequest, PolicyAgentResponse, PolicyAgentService


def test_service_exposes_only_orchestration_entrypoint():
    public={name for name,value in inspect.getmembers(PolicyAgentService) if callable(value) and not name.startswith("_")}
    assert public == {"run"}


def test_request_does_not_accept_caller_selected_recommendation():
    assert "recommendation" not in PolicyAgentRequest.__dataclass_fields__
    assert "recommended_action" not in PolicyAgentRequest.__dataclass_fields__


def test_response_contains_existing_artifacts_not_authorization_flags():
    fields=PolicyAgentResponse.__dataclass_fields__
    assert "governance_bundle" in fields
    assert "execution_result" in fields
    assert "distribution_effect" in fields
    assert "y3172_trace" in fields
    assert "authorized" not in fields
    assert "approved" not in fields


def test_request_rejects_invalid_query_parameters():
    fields = PolicyAgentRequest.__dataclass_fields__
    assert fields["query_limit"].default == 10
    assert fields["min_similarity"].default == 0.40


def test_response_exposes_non_atomic_boundary_as_limitation_contract():
    source = inspect.getsource(PolicyAgentService.run)
    assert "distribution_and_audit_not_transactionally_atomic" in source


def test_query_digest_is_not_labeled_model_artifact():
    source = inspect.getsource(PolicyAgentService.run)
    assert "model_artifact_ids=()," in source
