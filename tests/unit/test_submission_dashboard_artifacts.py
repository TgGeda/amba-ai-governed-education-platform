from pathlib import Path
from amba_ai.ui.features.governance.artifact_loader import load_dashboard_snapshot
ROOT=Path(__file__).resolve().parents[2]
def test_dashboard_snapshot_preserves_verified_boundaries():
 s=load_dashboard_snapshot(ROOT);assert len(s.stages)==4;assert s.agents['agent_count']==8;assert s.y3172['entry_count']==13;assert s.y3172['formal_conformance'] is False;assert s.y3172['itu_certification'] is False;assert s.evidence_chain['final_audit_verification']['valid'];assert 'metric:D11-M01' in s.pending_gates;assert 'metric:F5-M01' in s.pending_gates
