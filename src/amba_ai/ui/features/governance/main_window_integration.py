from __future__ import annotations
from pathlib import Path
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow,QTabWidget,QLabel
from .artifact_loader import load_dashboard_snapshot
from .governance_widget import GovernanceWidget
from amba_ai.ui.features.readiness import ReadinessWidget

def _project_root()->Path:return Path(__file__).resolve().parents[5]
def install_submission_workspaces(window:QMainWindow,root:Path|None=None)->None:
 if getattr(window,'_amba_submission_integrated',False):return
 root=root or _project_root();tabs=[x for x in window.findChildren(QTabWidget) if x.parent() is window.centralWidget() or x.parent() is window]
 if not tabs:tabs=window.findChildren(QTabWidget)
 if not tabs:raise RuntimeError('AMBA-GOV main window has no QTabWidget integration point')
 tab=max(tabs,key=lambda x:x.count());snapshot=load_dashboard_snapshot(root);governance=GovernanceWidget(root,window);readiness=ReadinessWidget(snapshot,root,window);governance.snapshot_changed.connect(readiness.populate);readiness.refresh_requested.connect(governance.manager.refresh);governance_index=tab.addTab(governance,'Governance');readiness_index=tab.addTab(readiness,'Readiness')
 menu=window.menuBar().addMenu('&Governance');open_governance=QAction('Open Governance',window);open_governance.triggered.connect(lambda:tab.setCurrentIndex(governance_index));menu.addAction(open_governance);open_readiness=QAction('Open Readiness',window);open_readiness.triggered.connect(lambda:tab.setCurrentIndex(readiness_index));menu.addAction(open_readiness)
 status=QLabel('SYNTHETIC · NO LEGAL EFFECT · Y.3172 INTERPRETATION · SCORE WITHHELD');status.setStyleSheet('color:#674c00;font-weight:700;padding:3px 8px;');window.statusBar().addPermanentWidget(status);window.governance_widget=governance;window.readiness_widget=readiness;window._amba_submission_integrated=True
