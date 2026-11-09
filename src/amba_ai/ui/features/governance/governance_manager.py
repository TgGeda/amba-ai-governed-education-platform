from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from .artifact_loader import load_dashboard_snapshot
class GovernanceManager(QObject):
    snapshot_loaded = Signal(object)
    load_failed = Signal(str)
    def __init__(self, root: Path, parent: QObject | None = None):
        super().__init__(parent); self.root = root
    def refresh(self) -> None:
        try:self.snapshot_loaded.emit(load_dashboard_snapshot(self.root))
        except Exception as exc:self.load_failed.emit(str(exc))
