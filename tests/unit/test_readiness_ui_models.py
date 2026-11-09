from pathlib import Path
from amba_ai.ui.features.governance.artifact_loader import load_dashboard_snapshot
from amba_ai.ui.features.readiness.readiness_models import build_finding_rows,build_metric_rows,build_coverage_summary,build_gap_rows,build_pending_gate_rows
ROOT=Path(__file__).resolve().parents[2]
def test_readiness_presentation_models_are_complete():
 s=load_dashboard_snapshot(ROOT);assert len(build_finding_rows(s))==19;assert len(build_metric_rows(s))==19;summary=build_coverage_summary(s);assert summary.scored_count==14;assert summary.applicable_count==19;assert summary.coverage_ratio==0.736842;assert summary.minimum_ratio==0.8;assert summary.additional_equal_weight_metrics_required==2;assert len(build_gap_rows(s))==5;assert {x.metric_id for x in build_pending_gate_rows(s)}=={'D11-M01','F5-M01'}
