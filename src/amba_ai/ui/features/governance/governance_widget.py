from __future__ import annotations
from pathlib import Path
import json
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QTextBrowser,QSplitter,QTreeWidget,QTreeWidgetItem,QFrame,QGridLayout,QLineEdit,QPlainTextEdit,QProgressBar
from .governance_manager import GovernanceManager

def table(headers):
 t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers);t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);t.setEditTriggers(QTableWidget.NoEditTriggers);t.setSelectionBehavior(QTableWidget.SelectRows);t.setSortingEnabled(True);return t
def fill(t,rows):
 t.setSortingEnabled(False);t.setRowCount(len(rows))
 for r,row in enumerate(rows):
  for c,value in enumerate(row):t.setItem(r,c,QTableWidgetItem(str(value)))
 t.setSortingEnabled(True)
def card(title,value,subtitle=''):
 f=QFrame();f.setProperty('card',True);l=QVBoxLayout(f);l.addWidget(QLabel(title));v=QLabel(str(value));v.setProperty('metric',True);l.addWidget(v)
 if subtitle:l.addWidget(QLabel(subtitle))
 return f
class GovernanceWidget(QWidget):
 snapshot_changed=Signal(object)
 def __init__(self,root:Path,parent=None):
  super().__init__(parent);self.root=root;self.setObjectName('SubmissionDashboard');self.manager=GovernanceManager(root,self);self.manager.snapshot_loaded.connect(self.populate);self.manager.load_failed.connect(self._load_error);self._build();qss=Path(__file__).with_name('governance.qss');self.setStyleSheet(qss.read_text(encoding='utf-8') if qss.is_file() else '');self.manager.refresh()
 def _build(self):
  layout=QVBoxLayout(self);head=QHBoxLayout();title=QLabel('AMBA-GOV · Evidence-Grounded Governance');title.setStyleSheet('font-size:22px;font-weight:700;');head.addWidget(title);head.addStretch();self.buttons=[]
  for label,slot in [('Refresh',self.manager.refresh),('Run four scenarios',self.manager.run_four_scenarios),('Verify manifest',self.manager.verify_manifest),('Regenerate Y.3172',self.manager.generate_y3172_mapping),('Regenerate agents',self.manager.generate_agent_architecture)]:
   b=QPushButton(label);b.clicked.connect(slot);head.addWidget(b);self.buttons.append(b)
  layout.addLayout(head);boundary=QLabel('SYNTHETIC DEMONSTRATION · NO LEGAL EFFECT · INTERPRETED Y.3172 MAPPING · NO ITU CERTIFICATION');boundary.setProperty('boundary',True);boundary.setWordWrap(True);layout.addWidget(boundary);self.tabs=QTabWidget();layout.addWidget(self.tabs)
  self.overview=QWidget();self.overview_grid=QGridLayout(self.overview);self.tabs.addTab(self.overview,'Overview')
  scenario=QSplitter();left=QWidget();ll=QVBoxLayout(left);self.scenario_search=QLineEdit();self.scenario_search.setPlaceholderText('Filter scenarios…');self.scenario_search.textChanged.connect(self._filter_scenarios);ll.addWidget(self.scenario_search);self.scenarios=table(['Stage','Purpose','Approval','Execution','Distribution','Invariant']);self.scenarios.itemSelectionChanged.connect(self._scenario_detail);ll.addWidget(self.scenarios);self.scenario_detail=QTextBrowser();scenario.addWidget(left);scenario.addWidget(self.scenario_detail);scenario.setSizes([850,650]);self.tabs.addTab(scenario,'Four Scenarios')
  agent=QSplitter();self.agents=table(['Agent','Responsibility','Fail-closed behavior','Reusable core']);self.agents.itemSelectionChanged.connect(self._agent_detail);self.agent_detail=QTextBrowser();agent.addWidget(self.agents);agent.addWidget(self.agent_detail);self.tabs.addTab(agent,'Agents')
  evidence=QSplitter();self.evidence_tree=QTreeWidget();self.evidence_tree.setHeaderLabels(['Evidence / gap','Type']);self.evidence_tree.currentItemChanged.connect(self._evidence_detail);self.evidence_detail=QTextBrowser();evidence.addWidget(self.evidence_tree);evidence.addWidget(self.evidence_detail);self.tabs.addTab(evidence,'Evidence and Gaps')
  y=QSplitter();self.y3172=table(['ID','AMBA-GOV component','Y.3172 interpretation','Records','Runtime evidence']);self.y3172.itemSelectionChanged.connect(self._y3172_detail);self.y3172_detail=QTextBrowser();y.addWidget(self.y3172);y.addWidget(self.y3172_detail);self.tabs.addTab(y,'ITU-T Y.3172')
  audit=QWidget();al=QVBoxLayout(audit);self.manifest_banner=QLabel();self.manifest_banner.setProperty('boundary',True);al.addWidget(self.manifest_banner);self.integrity=table(['Path','Type','SHA-256','Bytes','Recorded status']);al.addWidget(self.integrity);self.activity=QPlainTextEdit();self.activity.setReadOnly(True);self.activity.setMaximumBlockCount(1000);self.activity.setPlaceholderText('Operations and verification output appear here.');al.addWidget(self.activity);self.tabs.addTab(audit,'Audit and Integrity')
  self.manager.operation_started.connect(lambda n:self.activity.appendPlainText(f'▶ {n}'))
  self.manager.operation_output.connect(self.activity.appendPlainText)
  self.manager.operation_completed.connect(lambda n,c:self.activity.appendPlainText(f'■ {n}: exit {c}'))
  self.manager.operation_failed.connect(lambda n,m:self.activity.appendPlainText(f'✖ {n}: {m}'))
  self.manager.busy_changed.connect(lambda busy:[b.setDisabled(busy) for b in self.buttons])
 def populate(self,s):
  self.snapshot=s;self.snapshot_changed.emit(s)
  while self.overview_grid.count():
   item=self.overview_grid.takeAt(0)
   if item.widget():item.widget().deleteLater()
  coverage=s.readiness.get('evidence_coverage',{});cards=[('Approved passages',len(s.passages),'Academically approved'),('Verified scenarios',len(s.stages),'All invariants valid'),('Bounded agents',s.agents.get('agent_count'),'Reusable building blocks'),('Y.3172 mappings',s.y3172.get('entry_count'),'Interpreted, non-certifying'),('Evidence coverage',f"{100*float(coverage.get('coverage_ratio',0)):.4f}%",'80% publication threshold'),('Project score','WITHHELD' if s.readiness.get('overall_project_score') is None else s.readiness.get('overall_project_score'),s.readiness.get('score_status','')),('Final audit','VALID' if s.evidence_chain.get('final_audit_verification',{}).get('valid') else 'INVALID','Hash-linked chain'),('Manifest',s.manifest_state,f"{len(s.manifest_verification.get('failures',()))} verification failures")]
  for i,(a,b,c) in enumerate(cards):self.overview_grid.addWidget(card(a,b,c),i//4,i%4)
  self.stage_rows=list(s.stages);self._show_scenarios(self.stage_rows)
  fill(self.agents,[[x['name'],x['responsibility'],'; '.join(x['fail_closed_behavior']),', '.join(x['reusable_core'])] for x in s.agents['agents']])
  self.evidence_tree.clear()
  for stage in s.stages:
   parent=QTreeWidgetItem([str(stage.get('stage_id')),'stage']);self.evidence_tree.addTopLevelItem(parent)
   for response in stage.get('policy_agent_results',()):
    evidence=response.get('verified_evidence',{})
    for pid in evidence.get('passage_ids',()):item=QTreeWidgetItem(parent,[str(pid),'approved passage']);item.setData(0,Qt.UserRole,{'kind':'passage','id':pid})
    for gap in response.get('evidence_gaps',()):
     gid=gap.get('gap_id',str(gap)) if isinstance(gap,dict) else str(gap);item=QTreeWidgetItem(parent,[gid,'evidence gap']);item.setData(0,Qt.UserRole,{'kind':'gap','value':gap})
  self.y_rows=list(s.y3172['entries']);fill(self.y3172,[[x['mapping_id'],x['project_component'],x['y3172_interpretation'],', '.join(x['y3172_record_ids']),', '.join(x['runtime_evidence_pointers'])] for x in self.y_rows]);fill(self.integrity,[[x['path'],x['artifact_type'],x['sha256'],x['size_bytes'],x['validation_status']] for x in s.manifest['entries']]);failures=s.manifest_verification.get('failures',());self.manifest_banner.setText(f"Manifest state: {s.manifest_state} · SHA-256: {s.manifest_verification.get('manifest_sha256','')}"+(f" · Failures: {'; '.join(failures)}" if failures else ''))
 def _show_scenarios(self,stages):
  rows=[]
  for stage in stages:
   response=(stage.get('policy_agent_results') or [{}])[0];g=response.get('deterministic_governance',{});rows.append([stage.get('stage_id'),stage.get('purpose',stage.get('stage_name','')),g.get('approval_state',''),g.get('execution_state',''),json.dumps(g.get('distribution_effect'),ensure_ascii=False),stage.get('invariant_verification',{}).get('valid')])
  fill(self.scenarios,rows)
 def _filter_scenarios(self,text):q=text.lower();self._show_scenarios([s for s in self.stage_rows if q in json.dumps(s,ensure_ascii=False).lower()])
 def _scenario_detail(self):
  row=self.scenarios.currentRow()
  if row<0:return
  ident=self.scenarios.item(row,0).text();stage=next((x for x in self.stage_rows if str(x.get('stage_id'))==ident),None)
  if stage:self.scenario_detail.setMarkdown(self._stage_markdown(stage))
 def _stage_markdown(self,s):
  response=(s.get('policy_agent_results') or [{}])[0];g=response.get('deterministic_governance',{});sections=[f"# {s.get('stage_id')} · {s.get('purpose',s.get('stage_name',''))}",f"**Invariant valid:** `{s.get('invariant_verification',{}).get('valid')}`","## Released facts",*['- `'+str(x)+'`' for x in s.get('released_fact_ids',())],"## Recipient projections",'```json',json.dumps(s.get('recipient_projections',{}),ensure_ascii=False,indent=2),'```',"## Institutional observations",'```json',json.dumps(s.get('institutional_observations',{}),ensure_ascii=False,indent=2),'```',"## Preserved conflicts",'```json',json.dumps(s.get('preserved_conflicts',()),ensure_ascii=False,indent=2),'```',"## Governance",f"- Recommendation: `{g.get('recommendation')}`",f"- Approval: `{g.get('approval_state')}`",f"- Execution: `{g.get('execution_state')}`",f"- Distribution: `{g.get('distribution_effect')}`","## Evidence gaps",'```json',json.dumps(response.get('evidence_gaps',()),ensure_ascii=False,indent=2),'```',"## Y.3172 trace",'```json',json.dumps(response.get('y3172_trace',{}),ensure_ascii=False,indent=2),'```',"## Audit",'```json',json.dumps(response.get('audit',{}),ensure_ascii=False,indent=2),'```',"## Limitations",*['- '+str(x) for x in response.get('limitations',())]];return '\n\n'.join(sections)
 def _agent_detail(self):
  row=self.agents.currentRow()
  if row<0:return
  name=self.agents.item(row,0).text();x=next((a for a in self.snapshot.agents['agents'] if a['name']==name),None)
  if x:self.agent_detail.setMarkdown(f"# {x['name']}\n\n{x['responsibility']}\n\n**Inputs**\n"+'\n'.join('- '+v for v in x['inputs'])+'\n\n**Outputs**\n'+'\n'.join('- '+v for v in x['outputs'])+'\n\n**Consumes from**\n'+'\n'.join('- '+v for v in x['interactions']['consumes_from'])+'\n\n**Produces for**\n'+'\n'.join('- '+v for v in x['interactions']['produces_for'])+f"\n\n**Education:** {x['education_example']}\n\n**Agriculture:** {x['agriculture_example']}\n\n**Finance:** {x['finance_example']}")
 def _evidence_detail(self,current,previous):
  if current is None:return
  data=current.data(0,Qt.UserRole) or {};payload=self.snapshot.passages.get(str(data.get('id')),data.get('value',{'id':current.text(0),'type':current.text(1)}));self.evidence_detail.setPlainText(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True))
 def _y3172_detail(self):
  row=self.y3172.currentRow()
  if row<0:return
  ident=self.y3172.item(row,0).text();x=next((v for v in self.y_rows if v['mapping_id']==ident),None)
  if x:self.y3172_detail.setMarkdown(f"# {x['mapping_id']} · {x['project_component']}\n\n**Interpretation:** {x['y3172_interpretation']}\n\n{x['runtime_responsibility']}\n\n**Implementation**\n"+'\n'.join('- `'+v+'`' for v in x['implementation_files'])+'\n\n**Approved passages**\n'+'\n'.join('- `'+v+'`' for v in x['approved_passage_ids'])+'\n\n**Limitations**\n'+'\n'.join('- '+v for v in x['limitations'])+'\n\n**Formal conformance:** `false`\n\n**ITU certification:** `false`')
 def _load_error(self,message):self.activity.appendPlainText('ARTIFACT LOAD FAILED: '+message);self.manifest_banner.setText('Dashboard artifact load failed: '+message)
