from __future__ import annotations

import os
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal, Slot, QThreadPool
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from amba_ai.ui.common.ui_icons_utils import icon
from amba_ai.ui.workers import FunctionWorker, unwrap_worker_result


class RecycleBinWidget(QWidget):
    documentDeleted = Signal(int)
    statusMessage = Signal(str, str)

    def __init__(self, job_service: JobService, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.jobs = job_service
        self.thread_pool = QThreadPool.globalInstance()
        self.setObjectName("AmbaRecycleBinWidgetUI")

        self._setup_ui()
        self.load_documents()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QLabel(self.tr("Knowledge Base Management & Pruning"))
        header.setStyleSheet("font-size: 13pt; font-weight: bold; color: #F8FAFC;")
        layout.addWidget(header)

        sub = QLabel(self.tr("Safely prune or purge outdated learning materials and vector embeddings."))
        sub.setStyleSheet("color: #94A3B8; font-size: 9pt;")
        layout.addWidget(sub)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            self.tr("ID"),
            self.tr("Title"),
            self.tr("Kind"),
            self.tr("Origin Source"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(14)
        layout.addWidget(self.progress_bar)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton(icon("refresh"), self.tr("Refresh Store"))
        self.delete_btn = QPushButton(icon("delete"), self.tr("Delete Selected Material"))
        self.delete_btn.setObjectName("dangerButton")

        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.delete_btn)
        layout.addLayout(btn_row)

        self.refresh_btn.clicked.connect(self.load_documents)
        self.delete_btn.clicked.connect(self._confirm_delete)

    @Slot()
    def load_documents(self) -> None:
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.refresh_btn.setEnabled(False)

        worker = FunctionWorker(self.jobs.list_documents, task_name="Load Recycle Bin Documents")
        worker.signals.finished.connect(self._on_documents_loaded)
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)

    @Slot(object)
    def _on_documents_loaded(self, raw_result: Any) -> None:
        self.progress_bar.setVisible(False)
        self.refresh_btn.setEnabled(True)
        result = unwrap_worker_result(raw_result)

        if not result.success:
            self.statusMessage.emit("Failed to load documents for management.", "ERROR")
            return

        docs = list(result.result or [])
        self.table.setRowCount(0)
        self.table.setRowCount(len(docs))

        for row, doc in enumerate(docs):
            doc_id = doc.get("id") or doc.get("document_id") or 0
            raw_path = str(doc.get("source_path") or "")
            # Path sanitization: extract file name only
            safe_source = os.path.basename(raw_path.replace("\\", "/")) if raw_path else "Internal Source"

            self.table.setItem(row, 0, QTableWidgetItem(f"#{doc_id}"))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, int(doc_id))
            self.table.setItem(row, 1, QTableWidgetItem(str(doc.get("title", f"Document #{doc_id}"))))
            self.table.setItem(row, 2, QTableWidgetItem(str(doc.get("kind", "unknown")).upper()))
            self.table.setItem(row, 3, QTableWidgetItem(safe_source))

    @Slot(dict)
    def _on_worker_error(self, ctx: dict[str, Any]) -> None:
        self.progress_bar.setVisible(False)
        self.refresh_btn.setEnabled(True)
        err = str(ctx.get("error_message") or "Operation failed")
        self.statusMessage.emit(err, "ERROR")

    def _confirm_delete(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, self.tr("Selection Required"), self.tr("Select a document to delete."))
            return

        item = self.table.item(row, 0)
        doc_id = int(item.data(Qt.ItemDataRole.UserRole))
        title = self.table.item(row, 1).text()

        reply = QMessageBox.question(
            self,
            self.tr("Confirm Resource Deletion"),
            self.tr(
                f"Permanently delete '{title}'?\n\n"
                "This action removes all precomputed embeddings and generated study caches."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.delete_btn.setEnabled(False)

            worker = FunctionWorker(self.jobs.delete_document, doc_id, task_name="Delete Document")
            worker.signals.finished.connect(lambda res, d_id=doc_id: self._on_delete_finished(res, d_id))
            worker.signals.error.connect(self._on_worker_error)
            self.thread_pool.start(worker)

    def _on_delete_finished(self, raw_result: Any, doc_id: int) -> None:
        self.progress_bar.setVisible(False)
        self.delete_btn.setEnabled(True)
        result = unwrap_worker_result(raw_result)

        if result.success:
            self.documentDeleted.emit(doc_id)
            self.statusMessage.emit(f"Purged document #{doc_id} from storage.", "INFO")
            self.load_documents()
        else:
            QMessageBox.critical(self, self.tr("Deletion Error"), result.error_message or "Failed to delete.")