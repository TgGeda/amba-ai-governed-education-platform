from pathlib import Path
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QMainWindow,QTabWidget
from amba_ai.ui.features.governance.artifact_loader import load_dashboard_snapshot
from amba_ai.ui.features.governance.governance_widget import GovernanceWidget
from amba_ai.ui.features.governance.main_window_integration import install_submission_workspaces
from amba_ai.ui.features.readiness.readiness_widget import ReadinessWidget
ROOT=Path(__file__).resolve().parents[2]
def app():return QApplication.instance() or QApplication([])
def test_complete_governance_and_readiness_interactions_construct():
 app();s=load_dashboard_snapshot(ROOT);g=GovernanceWidget(ROOT);r=ReadinessWidget(s,ROOT);assert g.tabs.count()==6;assert r.tabs.count()==6;assert g.scenarios.rowCount()==4;assert g.agents.rowCount()==8;assert g.y3172.rowCount()==13;assert r.framework.rowCount()==19;assert r.metrics.rowCount()==19;assert r.gaps.rowCount()==5;assert r.gates.rowCount()==2;g.scenarios.selectRow(0);g._scenario_detail();assert g.scenario_detail.toPlainText();g.agents.selectRow(0);g._agent_detail();assert g.agent_detail.toPlainText();g.y3172.selectRow(0);g._y3172_detail();assert 'Formal conformance' in g.y3172_detail.toPlainText();r.framework.selectRow(0);r._framework_detail();assert r.framework_detail.toPlainText();r.gaps.selectRow(0);r._gap_detail();assert r.gap_detail.toPlainText();g.close();r.close()
def test_generic_main_window_integration_adds_two_tabs_once():
 app();window=QMainWindow();tabs=QTabWidget(window);window.setCentralWidget(tabs);tabs.addTab(QTabWidget(),'Existing');install_submission_workspaces(window,ROOT);assert [tabs.tabText(i) for i in range(tabs.count())][-2:]==['Governance','Readiness'];install_submission_workspaces(window,ROOT);assert tabs.count()==3;assert window._amba_submission_integrated;window.close()
