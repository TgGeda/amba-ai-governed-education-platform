from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import QWidget,QVBoxLayout,QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QLabel,QProgressBar
class ReadinessWidget(QWidget):
 def __init__(self,snapshot,parent=None):
  super().__init__(parent);layout=QVBoxLayout(self);title=QLabel('Evidence-Bounded Project Readiness');title.setStyleSheet('font-size:20px;font-weight:700;');layout.addWidget(title);self.tabs=QTabWidget();layout.addWidget(self.tabs);self._populate(snapshot)
 def _table(self,headers,rows):
  t=QTableWidget(len(rows),len(headers));t.setHorizontalHeaderLabels(headers);t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);t.setEditTriggers(QTableWidget.NoEditTriggers)
  for r,row in enumerate(rows):
   for c,value in enumerate(row):t.setItem(r,c,QTableWidgetItem(str(value)))
  return t
 def _populate(self,s):
  findings=s.readiness.get('findings',[]);self.tabs.addTab(self._table(['ID','Type','Name','Status','Rationale'],[[x['framework_element_id'],x['framework_element_type'],x['framework_element_name'],x['status'],x['rationale']] for x in findings]),'Factors and Dimensions')
  metrics=s.readiness.get('scoring',{}).get('metric_evaluations',[]);self.tabs.addTab(self._table(['Metric','Finding','Status','Score','Weight','Scored'],[[x['metric_id'],x['finding_id'],x['status'],x['score'],x['weight'],x['scored']] for x in metrics]),'Project Proxy Metrics')
  coverage=s.readiness.get('evidence_coverage',{});w=QWidget();l=QVBoxLayout(w);label=QLabel(f"Coverage: {coverage.get('scored_metric_count',0)}/{coverage.get('applicable_metric_count',0)} · Required: {100*float(coverage.get('minimum_required_ratio',0)):.0f}%");l.addWidget(label);bar=QProgressBar();bar.setRange(0,10000);bar.setValue(round(10000*float(coverage.get('coverage_ratio',0))));bar.setFormat('%p% evidence coverage');l.addWidget(bar);l.addWidget(QLabel(f"Overall project score: {s.readiness.get('overall_project_score')}\nStatus: {s.readiness.get('score_status')}"));l.addStretch();self.tabs.addTab(w,'Evidence Coverage')
  gaps=s.evidence_plan.get('metric_gaps',[]);self.tabs.addTab(self._table(['Metric','Current status','Missing evidence','Actions','Impact'],[[x['metric_id'],x['current_status'],'; '.join(x['missing_evidence']),'; '.join(x['recommended_actions']),x['score_impact_if_resolved']['new_coverage_ratio']] for x in gaps]),'Closure Plan')
  pending=s.closure_registry.get('pending_metric_ids',[]);self.tabs.addTab(self._table(['Pending metric','Reason'],[[x,'Acceptance evidence incomplete; see closure registry'] for x in pending]),'Pending Gates')
