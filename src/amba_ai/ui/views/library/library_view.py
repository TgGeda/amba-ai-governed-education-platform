from PySide6.QtWidgets import QWidget, QVBoxLayout, QMessageBox
from document_store import DocumentStore
from recycle_bin_view import RecycleBinView
from smart_views import TagSmartViewsPanel, SmartView
from heatmap_widgets import UsageHeatmapWidget
from sync_service import LibrarySyncService
from permissions_context import UserContext, DEFAULT_ROLES


class LibraryView(QWidget):
    def __init__(self, job_service, base_path: str):
        super().__init__()

        self.user = UserContext("user1", "teacher", DEFAULT_ROLES["teacher"])
        self.store = DocumentStore()
        self.recycle = RecycleBinView()
        self.smart_views = TagSmartViewsPanel()
        self.heatmap = UsageHeatmapWidget()
        self.sync = LibrarySyncService(base_path, self.refresh)

        layout = QVBoxLayout(self)
        layout.addWidget(self.smart_views)
        layout.addWidget(self.recycle)
        layout.addWidget(self.heatmap)

        self.smart_views.set_views([
            SmartView("AI Docs", {"ai"}),
            SmartView("Math", {"math"}),
        ])

        self.sync.start()

    def refresh(self):
        docs = self.job_service.list_documents()
        for d in docs:
            self.store.upsert(d)
        self.heatmap.update(self.store.list_active())