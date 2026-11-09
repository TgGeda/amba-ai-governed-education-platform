from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import QMainWindow,QTabWidget
from .artifact_loader import load_dashboard_snapshot
from .governance_widget import GovernanceWidget
from amba_ai.ui.features.readiness import ReadinessWidget
class SubmissionDashboard(QMainWindow):
 def __init__(self,root:Path,parent=None):
  super().__init__(parent);self.root=root;self.setWindowTitle('AMBA-GOV · Governance Demonstration');self.resize(1500,900);snapshot=load_dashboard_snapshot(root);tabs=QTabWidget();self.governance=GovernanceWidget(root);self.readiness=ReadinessWidget(snapshot,root);self.governance.snapshot_changed.connect(self.readiness.populate);self.readiness.refresh_requested.connect(self.governance.manager.refresh);tabs.addTab(self.governance,'Governance');tabs.addTab(self.readiness,'Readiness');self.setCentralWidget(tabs)
