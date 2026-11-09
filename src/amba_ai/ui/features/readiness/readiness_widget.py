from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QTextBrowser,QSplitter,QProgressBar,QComboBox,QLineEdit,QFrame,QGridLayout
from .readiness_manager import ReadinessManager
from .readiness_models import build_finding_rows,build_metric_rows,build_coverage_summary,build_gap_rows,build_pending_gate_rows

def table(headers):
 t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers);t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);t.setEditTriggers(QTableWidget.NoEditTriggers);t.setSelectionBehavior(QTableWidget.SelectRows);t.setSortingEnabled(True);return t
def fill(t,rows):
 t.setSortingEnabled(False);t.setRowCount(len(rows))
 for r,row in enumerate(rows):
  for c,value in enumerate(row):t.setItem(r,c,QTableWidgetItem('WITHHELD' if value is None else str(value)))
 t.setSortingEnabled(True)
class ReadinessWidget(QWidget):
 refresh_requested=Signal()
 def __init__(self,snapshot,root:Path|None=None,parent=None):
  super().__init__(parent);self.setObjectName('ReadinessWorkspace');self.root=root or Path.cwd();self.snapshot=snapshot;self.manager=ReadinessManager(self.root,self);self._build();qss=Path(__file__).with_name('readiness.qss');self.setStyleSheet(qss.read_text(encoding='utf-8') if qss.is_file() else '');self.populate(snapshot)
 def _build(self):
  layout=QVBoxLayout(self);header=QHBoxLayout();title=QLabel('Evidence-Bounded Project Readiness');title.setStyleSheet('font-size:22px;font-weight:700;');header.addWidget(title);header.addStretch();self.generate=QPushButton('Regenerate reflection');self.generate.clicked.connect(self.manager.generate_reflection);header.addWidget(self.generate);layout.addLayout(header)
  boundary=QLabel('PROJECT SELF-EVALUATION · NOT A NATIONAL SCORE · NO OFFICIAL ITU SCORE OR CERTIFICATION · NO RUNTIME AUTHORITY');boundary.setWordWrap(True);boundary.setStyleSheet('background:#fff4d6;color:#674c00;padding:8px;border:1px solid #e8c86a;border-radius:6px;');layout.addWidget(boundary);self.tabs=QTabWidget();layout.addWidget(self.tabs)
  fw=QSplitter();left=QWidget();ll=QVBoxLayout(left);filters=QHBoxLayout();self.framework_search=QLineEdit();self.framework_search.setPlaceholderText('Filter factors and dimensions…');self.framework_search.textChanged.connect(self._filter_framework);filters.addWidget(self.framework_search);ll.addLayout(filters);self.framework=table(['ID','Name','Type','Status','Evidence','Limitations']);self.framework.itemSelectionChanged.connect(self._framework_detail);ll.addWidget(self.framework);self.framework_detail=QTextBrowser();fw.addWidget(left);fw.addWidget(self.framework_detail);fw.setSizes([900,500]);self.tabs.addTab(fw,'Framework')
  metric=QWidget();ml=QVBoxLayout(metric);mfilters=QHBoxLayout();self.metric_filter=QComboBox();self.metric_filter.addItems(['All','Scored','Unscored','Factors','Dimensions']);self.metric_filter.currentTextChanged.connect(self._filter_metrics);mfilters.addWidget(QLabel('Show:'));mfilters.addWidget(self.metric_filter);mfilters.addStretch();ml.addLayout(mfilters);self.metrics=table(['Metric','Finding','Type','Status','Score','Weight','Applicable','Scored']);ml.addWidget(self.metrics);self.tabs.addTab(metric,'Project Proxy Metrics')
  self.coverage=QWidget();self.tabs.addTab(self.coverage,'Evidence Coverage')
  closure=QSplitter();self.gaps=table(['Metric','Status','Risk','Dependency','Projected coverage','Threshold alone','Minimum set']);self.gaps.itemSelectionChanged.connect(self._gap_detail);self.gap_detail=QTextBrowser();closure.addWidget(self.gaps);closure.addWidget(self.gap_detail);self.tabs.addTab(closure,'Closure Plan')
  self.gates=table(['Metric','Failed acceptance checks','Limitations']);self.tabs.addTab(self.gates,'Pending Gates')
  self.boundaries=table(['Claim','Value','Interpretation']);self.tabs.addTab(self.boundaries,'Claim Boundaries')
  self.manager.operation_output.connect(lambda text:self.framework_detail.append(text));self.manager.operation_completed.connect(lambda n,c:self.refresh_requested.emit());self.manager.busy_changed.connect(self.generate.setDisabled)
 def populate(self,s):
  self.snapshot=s;self.findings=build_finding_rows(s);self.metric_rows=build_metric_rows(s);self.gap_rows=build_gap_rows(s);self.gate_rows=build_pending_gate_rows(s);self.summary=build_coverage_summary(s);self._show_findings(self.findings);self._show_metrics(self.metric_rows);self._show_coverage();fill(self.gaps,[[x.metric_id,x.current_status,x.delivery_risk,x.external_dependency,f'{100*x.projected_coverage:.4f}%',x.threshold_reached,'YES' if x.selected_for_minimum_closure else ''] for x in self.gap_rows]);fill(self.gates,[[x.metric_id,'; '.join(x.failed_checks),'; '.join(x.limitations)] for x in self.gate_rows]);r=s.readiness;claims=[('project_assessment',True,'Project-level evidence reflection only'),('national_assessment',r.get('assessment_subject',{}).get('national_assessment'),'No national inference'),('official_itu_score',False,'Project proxy score is not an ITU score'),('official_itu_certification',r.get('assessment_subject',{}).get('official_itu_certification'),'No ITU certification'),('formal_y3172_conformance',s.y3172.get('formal_conformance'),'Interpreted mapping only'),('runtime_authority',False,'Readiness cannot authorize or block runtime'),('legal_effect',s.evidence_chain.get('legal_effect'),'Synthetic and legally non-effective')];fill(self.boundaries,claims)
 def _show_findings(self,rows):fill(self.framework,[[x.element_id,x.name,x.element_type,x.status,len(x.evidence_pointers),len(x.limitations)] for x in rows])
 def _show_metrics(self,rows):fill(self.metrics,[[x.metric_id,x.finding_id,x.element_type,x.status,x.score,x.weight,x.applicable,x.scored] for x in rows])
 def _filter_framework(self,text):q=text.lower();self._show_findings(tuple(x for x in self.findings if q in f'{x.element_id} {x.name} {x.status} {x.element_type}'.lower()))
 def _filter_metrics(self,value):
  rows=self.metric_rows
  if value=='Scored':rows=tuple(x for x in rows if x.scored)
  elif value=='Unscored':rows=tuple(x for x in rows if not x.scored)
  elif value=='Factors':rows=tuple(x for x in rows if x.element_type=='factor')
  elif value=='Dimensions':rows=tuple(x for x in rows if x.element_type=='dimension')
  self._show_metrics(rows)
 def _framework_detail(self):
  row=self.framework.currentRow()
  if row<0:return
  ident=self.framework.item(row,0).text();x=next((f for f in self.findings if f.element_id==ident),None)
  if x:self.framework_detail.setMarkdown(f'# {x.element_id} · {x.name}\n\n**Status:** `{x.status}`\n\n{x.rationale}\n\n**Evidence pointers**\n'+'\n'.join(f'- `{p}`' for p in x.evidence_pointers)+'\n\n**Approved passages**\n'+'\n'.join(f'- `{p}`' for p in x.passage_ids)+'\n\n**Y.3172 records**\n'+'\n'.join(f'- `{p}`' for p in x.y3172_record_ids)+'\n\n**Limitations**\n'+'\n'.join(f'- {p}' for p in x.limitations))
 def _gap_detail(self):
  row=self.gaps.currentRow()
  if row<0:return
  ident=self.gaps.item(row,0).text();x=next((g for g in self.gap_rows if g.metric_id==ident),None)
  if x:self.gap_detail.setMarkdown(f'# {x.metric_id}\n\n**Current status:** `{x.current_status}`\n\n**Missing evidence**\n'+'\n'.join(f'- {p}' for p in x.missing_evidence)+'\n\n**Recommended actions**\n'+'\n'.join(f'- {p}' for p in x.recommended_actions)+f'\n\n**Projected coverage:** `{100*x.projected_coverage:.4f}%`')
 def _show_coverage(self):
  old=self.coverage.layout()
  if old:
   while old.count():
    item=old.takeAt(0);item.widget().deleteLater() if item.widget() else None
  else:old=QVBoxLayout(self.coverage)
  current=QProgressBar();current.setRange(0,10000);current.setValue(round(10000*self.summary.coverage_ratio));current.setFormat('Current evidence coverage: %p%');threshold=QProgressBar();threshold.setRange(0,10000);threshold.setValue(round(10000*self.summary.minimum_ratio));threshold.setFormat('Publication threshold: %p%');old.addWidget(QLabel(f'<h2>{self.summary.scored_count} of {self.summary.applicable_count} applicable proxy metrics scored</h2>'));old.addWidget(current);old.addWidget(threshold);old.addWidget(QLabel(f'<b>Overall project score:</b> {self.summary.overall_score if self.summary.overall_score is not None else "WITHHELD"}<br><b>Status:</b> {self.summary.score_status}<br><b>Equal-weight metrics still required:</b> {self.summary.additional_equal_weight_metrics_required}'));old.addStretch()
