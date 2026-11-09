from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import QMainWindow,QTabWidget
from .artifact_loader import load_dashboard_snapshot
from .governance_widget import GovernanceWidget
from amba_ai.ui.features.readiness import ReadinessWidget
class SubmissionDashboard(QMainWindow):
 def __init__(self,root:Path,parent=None):
  super().__init__(parent);self.root=root;self.setWindowTitle('AMBA-GOV · Governance Demonstration');self.resize(1500,900);snapshot=load_dashboard_snapshot(root);tabs=QTabWidget();tabs.addTab(GovernanceWidget(root),'Governance');tabs.addTab(ReadinessWidget(snapshot),'Readiness');self.setCentralWidget(tabs)
