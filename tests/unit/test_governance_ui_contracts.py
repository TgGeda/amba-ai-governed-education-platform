from pathlib import Path
from amba_ai.ui.features.governance.artifact_loader import load_dashboard_snapshot
ROOT=Path(__file__).resolve().parents[2]
def test_manifest_is_actually_verified_and_boundaries_preserved():
 s=load_dashboard_snapshot(ROOT);assert s.manifest_state in {'VALID','STALE'};assert len(s.stages)==4;assert s.y3172['formal_conformance'] is False;assert s.y3172['itu_certification'] is False;assert s.readiness['assessment_subject']['national_assessment'] is False
