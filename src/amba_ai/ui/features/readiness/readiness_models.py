from __future__ import annotations
from amba_ai.ui.features.governance.data_classes import DashboardSnapshot
from .data_classes import ReadinessFindingRow,MetricRow,CoverageSummary,GapRow,PendingGateRow

def build_finding_rows(s:DashboardSnapshot):
 return tuple(ReadinessFindingRow(str(x['framework_element_id']),str(x['framework_element_type']),str(x['framework_element_name']),str(x['status']),str(x['rationale']),tuple(x.get('evidence_pointers',())),tuple(x.get('passage_ids',())),tuple(x.get('y3172_record_ids',())),tuple(x.get('limitations',()))) for x in s.readiness.get('findings',()))
def build_metric_rows(s):
 return tuple(MetricRow(str(x['metric_id']),str(x['finding_id']),str(x['element_type']),str(x['status']),x.get('score'),float(x['weight']),bool(x['applicable']),bool(x['scored']),tuple(x.get('evidence_pointers',()))) for x in s.readiness.get('scoring',{}).get('metric_evaluations',()))
def build_coverage_summary(s):
 x=s.readiness.get('evidence_coverage',s.readiness.get('scoring',{}).get('overall',{}).get('coverage',{}));return CoverageSummary(int(x.get('scored_metric_count',0)),int(x.get('applicable_metric_count',0)),float(x.get('coverage_ratio',0)),float(x.get('minimum_required_ratio',0)),bool(x.get('sufficient')),s.readiness.get('overall_project_score'),str(s.readiness.get('score_status','')))
def build_gap_rows(s):
 selected=set(s.evidence_plan.get('minimum_threshold_closure_plan',{}).get('selected_metrics',()));return tuple(GapRow(str(x['metric_id']),str(x['current_status']),tuple(x.get('missing_evidence',())),tuple(x.get('recommended_actions',())),str(x.get('delivery_risk','')),str(x.get('external_dependency','')),float(x.get('score_impact_if_resolved',{}).get('new_coverage_ratio',0)),bool(x.get('score_impact_if_resolved',{}).get('threshold_reached')),x['metric_id'] in selected) for x in s.evidence_plan.get('metric_gaps',()))
def build_pending_gate_rows(s):
 records={x['metric_id']:x for x in s.closure_registry.get('records',())};rows=[]
 for metric in s.closure_registry.get('pending_metric_ids',()):
  record=records.get(metric,{});failed=tuple(x.get('check_id','') for x in record.get('acceptance_checks',()) if not x.get('passed'));rows.append(PendingGateRow(str(metric),failed,tuple(record.get('limitations',()))))
 return tuple(rows)
