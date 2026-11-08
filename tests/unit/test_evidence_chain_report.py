from pathlib import Path
from amba_ai.application.evidence_chain_report import canonical_json,write_evidence_chain_report

def test_canonical_output_is_deterministic(tmp_path:Path):
    payload={'z':2,'a':{'b':1}}
    one=tmp_path/'one.json'; two=tmp_path/'two.json'
    h1=write_evidence_chain_report(payload,one); h2=write_evidence_chain_report(payload,two)
    assert h1==h2 and one.read_bytes()==two.read_bytes()
    assert one.read_text(encoding='utf-8')=='{"a":{"b":1},"z":2}\n'


def test_approval_state_uses_execution_request_decision_id() -> None:
    from types import SimpleNamespace
    from amba_ai.application.evidence_chain_report import _approval_state

    response = SimpleNamespace(
        governance_bundle=SimpleNamespace(
            recommendation=SimpleNamespace(requires_approval=True)
        ),
        execution_result=SimpleNamespace(
            request=SimpleNamespace(approval_decision_id="DECISION-001")
        ),
    )
    assert _approval_state(response) == "decision_recorded"

    response.execution_result.request.approval_decision_id = None
    assert _approval_state(response) == "required_not_supplied"

    response.governance_bundle.recommendation.requires_approval = False
    assert _approval_state(response) == "not_required"


def test_demo_database_is_explicitly_isolated() -> None:
    import inspect
    from amba_ai.cli import evidence_chain_demo
    source = inspect.getsource(evidence_chain_demo.main)
    assert "evidence_chain_demo.db" in source
    assert "settings_overrides={'database_path':database}" in source


def test_report_uses_policy_recommendation_public_contract() -> None:
    from dataclasses import fields
    from amba_ai.governance.models import PolicyRecommendation

    names = {field.name for field in fields(PolicyRecommendation)}
    assert "requires_approval" in names
    assert "requires_human_approval" not in names


def test_execution_state_uses_receipt_contract() -> None:
    from types import SimpleNamespace
    from amba_ai.application.evidence_chain_report import _execution_state

    executed = SimpleNamespace(to_dict=lambda: {
        "execution_receipt": {"status": "succeeded"},
        "review_queue_receipt": None,
    })
    queued = SimpleNamespace(to_dict=lambda: {
        "execution_receipt": None,
        "review_queue_receipt": {"reason_code": "approval_required"},
    })
    assert _execution_state(executed) == "succeeded"
    assert _execution_state(queued) == "review_queued"


def test_execution_result_public_contract_has_receipts_not_state() -> None:
    from dataclasses import fields
    from amba_ai.governance.execution import ExecutionResult

    names = {field.name for field in fields(ExecutionResult)}
    assert {"execution_receipt", "review_queue_receipt"} <= names
    assert "state" not in names


def test_runtime_container_types_are_json_serializable() -> None:
    from enum import Enum
    from pathlib import Path
    from types import MappingProxyType
    from amba_ai.application.evidence_chain_report import canonical_json

    class State(str, Enum):
        READY = "ready"

    payload = MappingProxyType({
        "state": State.READY,
        "path": Path("submission") / "artifacts",
        "tuple": ("b", "a"),
        "set": frozenset({"z", "x"}),
        "nested": MappingProxyType({"enabled": True}),
    })
    serialized = canonical_json(payload)
    assert serialized == (
        '{"nested":{"enabled":true},"path":"submission/artifacts",'
        '"set":["x","z"],"state":"ready","tuple":["b","a"]}'
    )


def test_unsupported_runtime_type_fails_closed() -> None:
    import pytest
    from amba_ai.application.evidence_chain_report import canonical_json

    with pytest.raises(TypeError, match="Unsupported evidence-chain value"):
        canonical_json({"unsupported": object()})


def test_evidence_chain_provider_configuration_is_deterministic() -> None:
    from amba_ai.cli.evidence_chain_demo import (
        EVIDENCE_CHAIN_TIME,
        EvidenceChainClock,
        EvidenceChainIdentifierProvider,
    )
    from amba_ai.governance.models import UUIDIdentifierProvider
    from amba_ai.governance.principals import SystemClock

    identifiers = EvidenceChainIdentifierProvider()
    clock = EvidenceChainClock()

    assert isinstance(identifiers, UUIDIdentifierProvider)
    assert isinstance(clock, SystemClock)
    assert identifiers.new_id("test") == "test_000000000001"
    assert identifiers.new_id("test") == "test_000000000002"
    assert clock.now_iso() == EVIDENCE_CHAIN_TIME
