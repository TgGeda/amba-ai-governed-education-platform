from __future__ import annotations
from pathlib import Path
import json, subprocess, sys
from PySide6.QtCore import Qt, QProcess
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QTextBrowser,QSplitter,QTreeWidget,QTreeWidgetItem,QFrame,QGridLayout,QMessageBox)
from .governance_manager import GovernanceManager

def _table(headers):
 t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers);t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);t.setEditTriggers(QTableWidget.NoEditTriggers);t.setSelectionBehavior(QTableWidget.SelectRows);return t
def _fill(t,rows):
 t.setRowCount(len(rows))
 for r,row in enumerate(rows):
  for c,value in enumerate(row):t.setItem(r,c,QTableWidgetItem(str(value)))
def _card(title,value):
 f=QFrame();f.setProperty('card',True);l=QVBoxLayout(f);l.addWidget(QLabel(title));v=QLabel(str(value));v.setProperty('metric',True);l.addWidget(v);return f
class GovernanceWidget(QWidget):
 def __init__(self,root:Path,parent=None):
  super().__init__(parent);self.root=root;self.setObjectName('SubmissionDashboard');self.manager=GovernanceManager(root,self);self.manager.snapshot_loaded.connect(self._populate);self.manager.load_failed.connect(self._error);self._build();qss=Path(__file__).with_name('governance.qss');self.setStyleSheet(qss.read_text(encoding='utf-8') if qss.is_file() else '');self.manager.refresh()
 def _build(self):
  layout=QVBoxLayout(self);head=QHBoxLayout();title=QLabel('AMBA-GOV · Submission Governance');title.setStyleSheet('font-size:22px;font-weight:700;');head.addWidget(title);head.addStretch();refresh=QPushButton('Refresh artifacts');refresh.clicked.connect(self.manager.refresh);head.addWidget(refresh);run=QPushButton('Run four scenarios');run.clicked.connect(self._run_demo);head.addWidget(run);verify=QPushButton('Verify manifest');verify.clicked.connect(self._verify);head.addWidget(verify);layout.addLayout(head)
  boundary=QLabel('SYNTHETIC DEMONSTRATION · NO LEGAL EFFECT · INTERPRETED Y.3172 MAPPING · NO ITU CERTIFICATION');boundary.setProperty('boundary',True);boundary.setWordWrap(True);layout.addWidget(boundary)
  self.tabs=QTabWidget();layout.addWidget(self.tabs)
  self.overview=QWidget();self.overview_grid=QGridLayout(self.overview);self.tabs.addTab(self.overview,'Overview')
  self.scenarios=_table(['Stage','Purpose','Recommendation','Approval','Execution','Distribution','Invariant']);self.tabs.addTab(self.scenarios,'Four Scenarios')
  self.agents=_table(['Agent','Responsibility','Fail-closed behavior','Reusable core']);self.tabs.addTab(self.agents,'Agents')
  evidence=QSplitter();self.evidence_tree=QTreeWidget();self.evidence_tree.setHeaderLabels(['Evidence / gap','Type']);self.evidence_detail=QTextBrowser();self.evidence_tree.currentItemChanged.connect(self._evidence_selected);evidence.addWidget(self.evidence_tree);evidence.addWidget(self.evidence_detail);self.tabs.addTab(evidence,'Evidence and Gaps')
  self.y3172=_table(['ID','AMBA-GOV component','Y.3172 interpretation','Records','Runtime evidence']);self.tabs.addTab(self.y3172,'ITU-T Y.3172')
  self.integrity=_table(['Path','Type','SHA-256','Bytes','Status']);self.tabs.addTab(self.integrity,'Audit and Integrity')
 def _populate(self,s):
  self.snapshot=s
  while self.overview_grid.count():
   item=self.overview_grid.takeAt(0);item.widget().deleteLater() if item.widget() else None
  readiness=s.readiness;coverage=readiness.get('evidence_coverage',readiness.get('scoring',{}).get('overall',{}).get('coverage',{}));cards=[('Approved passages',len(s.passages)),('Scenarios',len(s.stages)),('Bounded agents',s.agents.get('agent_count')),('Y.3172 mappings',s.y3172.get('entry_count')),('Evidence coverage',f"{100*float(coverage.get('coverage_ratio',0)):.2f}%"),('Overall project score',readiness.get('overall_project_score') if readiness.get('overall_project_score') is not None else 'WITHHELD'),('Final audit','VALID' if s.evidence_chain.get('final_audit_verification',{}).get('valid') else 'INVALID'),('Pending gates',len(s.pending_gates))]
  for i,(k,v) in enumerate(cards):self.overview_grid.addWidget(_card(k,v),i//4,i%4)
  rows=[]
  for stage in s.stages:
   results=stage.get('policy_agent_results',[]);g=(results[0].get('deterministic_governance',{}) if results else {});rows.append([stage.get('stage_id'),stage.get('purpose',stage.get('stage_name','')),g.get('recommendation',''),g.get('approval_state',''),g.get('execution_state',''),json.dumps(g.get('distribution_effect'),ensure_ascii=False),stage.get('invariant_verification',{}).get('valid')])
  _fill(self.scenarios,rows)
  _fill(self.agents,[[a['name'],a['responsibility'],'; '.join(a['fail_closed_behavior']),', '.join(a['reusable_core'])] for a in s.agents['agents']])
  self.evidence_tree.clear()
  for stage in s.stages:
   parent=QTreeWidgetItem([str(stage.get('stage_id')),'stage']);self.evidence_tree.addTopLevelItem(parent)
   for response in stage.get('policy_agent_results',[]):
    for pid in response.get('verified_evidence',{}).get('passage_ids',[]):QTreeWidgetItem(parent,[pid,'approved passage'])
    for gap in response.get('evidence_gaps',[]):
     gid=gap.get('gap_id',str(gap)) if isinstance(gap,dict) else str(gap);item=QTreeWidgetItem(parent,[gid,'evidence gap']);item.setData(0,Qt.UserRole,gap)
  _fill(self.y3172,[[x['mapping_id'],x['project_component'],x['y3172_interpretation'],', '.join(x['y3172_record_ids']),', '.join(x['runtime_evidence_pointers'])] for x in s.y3172['entries']])
  _fill(self.integrity,[[x['path'],x['artifact_type'],x['sha256'],x['size_bytes'],x['validation_status']] for x in s.manifest['entries']])
 def _evidence_selected(self,current,previous):
  if current is None:return
  ident=current.text(0);payload=self.snapshot.passages.get(ident,current.data(0,Qt.UserRole) or {'id':ident,'type':current.text(1)});self.evidence_detail.setPlainText(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True))
 def _error(self,message):QMessageBox.critical(self,'Artifact load failed',message)
 def _command(self,args,title):
  result=subprocess.run(args,cwd=self.root,text=True,capture_output=True);QMessageBox.information(self,title,(result.stdout+'\n'+result.stderr)[-5000:]);self.manager.refresh()
 def _run_demo(self):self._command([sys.executable,'-m','amba_ai.cli.evidence_chain_demo'],'Four-scenario demonstration')
 def _verify(self):self._command([sys.executable,'tools/submission/verify_submission_manifest.py'],'Submission manifest verification')
