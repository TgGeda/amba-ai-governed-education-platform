from pathlib import Path
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from amba_ai.ui.features.governance.artifact_loader import load_dashboard_snapshot
from amba_ai.ui.features.governance.governance_widget import GovernanceWidget
from amba_ai.ui.features.readiness.readiness_widget import ReadinessWidget
ROOT=Path(__file__).resolve().parents[2]
def test_governance_and_readiness_widgets_construct_offscreen():
 app=QApplication.instance() or QApplication([]);s=load_dashboard_snapshot(ROOT);g=GovernanceWidget(ROOT);r=ReadinessWidget(s);assert g.tabs.count()==6;assert r.tabs.count()==6;assert g.scenarios.rowCount()==4;assert g.agents.rowCount()==8;assert g.y3172.rowCount()==13;g.close();r.close()
