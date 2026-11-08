from pathlib import Path
import json
from amba_ai.application.composition import create_demo
from amba_ai.application.evidence_chain_report import build_evidence_chain_report
from amba_ai.cli.evidence_chain_demo import execute, install_evidence_chain_providers, main
ROOT=Path(__file__).resolve().parents[2]
def test_complete_four_stage_evidence_chain(tmp_path: Path):
    app=create_demo(project_root=ROOT,settings_overrides={"database_path":tmp_path/"complete.db"},configure=install_evidence_chain_providers)
    try:
        app.start(); payload=build_evidence_chain_report(execute(app.providers,'EVIDENCE-CHAIN-INTEGRATION-001'))
    finally: app.stop()
    assert [x['stage_id'] for x in payload['stages']]==['STAGE-1','STAGE-2','STAGE-3','STAGE-4']
    assert payload['final_audit_verification']['valid'] is True
    assert all(x['invariant_verification']['valid'] for x in payload['stages'])
    assert any('GAP-COMMERCIAL-EXPLOITATION' in x['thematic_evidence_references']['gap_ids'] for x in payload['stages'])
    assert all(not r['deterministic_governance'].get('binding_finding_eligible',False) for x in payload['stages'] for r in x['policy_agent_results'])


def test_targeted_advertising_uses_unregistered_synthetic_sink(tmp_path: Path):
    app=create_demo(project_root=ROOT,settings_overrides={"database_path":tmp_path/"destination.db"},configure=install_evidence_chain_providers)
    try:
        app.start()
        result=execute(app.providers,'EVIDENCE-CHAIN-DESTINATION-001')
    finally:
        app.stop()
    stage_four=result.stages[-1]
    requests=[r.execution_result.request for r in stage_four.policy_agent_responses]
    assert requests
    assert all(r.destination_id == "SYNTHETIC-AD-SINK" for r in requests)
    assert all(r.operation_id == "targeted_ad_dispatch" for r in requests)


def test_report_contract_fields_are_populated(tmp_path: Path):
    app=create_demo(project_root=ROOT,settings_overrides={"database_path":tmp_path/"contracts.db"},configure=install_evidence_chain_providers)
    try:
        app.start(); payload=build_evidence_chain_report(execute(app.providers,'EVIDENCE-CHAIN-CONTRACTS-001'))
    finally:
        app.stop()
    responses=[r for stage in payload["stages"] for r in stage["policy_agent_results"]]
    assert responses
    assert all(r["deterministic_governance"]["execution_state"] for r in responses)
    assert all(r["audit"]["block_id"] and r["audit"]["payload_hash"] and r["audit"]["block_hash"] for r in responses)
    conflicts=[c for stage in payload["stages"] for c in stage["preserved_conflicts"]]
    assert all(c["resolution_status"] == "unresolved" for c in conflicts)


def test_command_artifact_is_byte_deterministic(tmp_path: Path):
    first = tmp_path / "first.json"
    first_pretty = tmp_path / "first_pretty.json"
    second = tmp_path / "second.json"
    second_pretty = tmp_path / "second_pretty.json"
    database = tmp_path / "command.db"

    common = [
        "--project-root", str(ROOT),
        "--run-id", "EVIDENCE-CHAIN-DETERMINISTIC-001",
        "--database", str(database),
    ]
    assert main(common + ["--output", str(first), "--pretty-output", str(first_pretty)]) == 0
    assert main(common + ["--output", str(second), "--pretty-output", str(second_pretty)]) == 0

    assert first.read_bytes() == second.read_bytes()
    assert first_pretty.read_bytes() == second_pretty.read_bytes()
