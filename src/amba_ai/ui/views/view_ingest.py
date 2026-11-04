# src/amba_ai/ui/ingest_view.py
from __future__ import annotations

import os
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from amba_ai.logger import logger
from amba_ai.core.safety_service import SafetyService, SafetyDecision
from amba_ai.ui.workers import FunctionWorker, WorkerResult
from amba_ai.services.job_service import JobService


# ---------------------------------------------------------------------
# Typed DTOs
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class IngestResult:
    document_id: int | None
    file_path: str
    status: str  # "success" | "failure"
    metadata: dict[str, Any]


# ---------------------------------------------------------------------
# View
# ---------------------------------------------------------------------

class IngestView(QWidget):
    """
    UI component responsible for:
    - File selection
    - Safety validation
    - Background ingestion
    - Typed result emission
    """

    document_ingested = Signal(IngestResult)

    def __init__(
        self,
        job_service: JobService,
        safety_service: SafetyService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.job_service = job_service
        self.safety = safety_service or SafetyService()
        self.thread_pool = QThreadPool.globalInstance()
        self._active_worker: FunctionWorker | None = None

        # ------------------------------------------------------------------
        # UI widgets
        # ------------------------------------------------------------------

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SingleSelection)

        self.status = QLabel("Ready")
        self.status.setAlignment(Qt.AlignLeft)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)

        self.btn_add = QPushButton("Add Files")
        self.btn_ingest = QPushButton("Ingest Selected")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)

        self.btn_add.clicked.connect(self.add_files)
        self.btn_ingest.clicked.connect(self.ingest_selected)
        self.btn_cancel.clicked.connect(self.cancel_ingestion)

        # ------------------------------------------------------------------
        # Layout
        # ------------------------------------------------------------------

        top = QHBoxLayout()
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_ingest)
        top.addWidget(self.btn_cancel)

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self.file_list)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # File selection
    # ------------------------------------------------------------------

    @Slot()
    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select study files",
            "",
            (
                "Study Files (*.pdf *.docx *.pptx *.ppt "
                "*.mp3 *.wav *.mp4 *.txt *.md *.markdown);;All Files (*)"
            ),
        )

        if not files:
            return

        logger.info(
            "Files selected for ingestion",
            extra={
                "context": {
                    "operation": "add_files",
                    "count": len(files),
                    "extensions": sorted({Path(f).suffix.lower() for f in files}),
                }
            },
        )

        existing = {
            self.file_list.item(i).text()
            for i in range(self.file_list.count())
        }

        for file_path in files:
            decision = self._validate_file(file_path)
            if not decision.allowed:
                self._show_validation_rejection(file_path, decision)
                continue

            if file_path in existing:
                continue

            item = QListWidgetItem(file_path)
            self._attach_file_metadata(item, Path(file_path))
            self.file_list.addItem(item)
            existing.add(file_path)

    def _attach_file_metadata(self, item: QListWidgetItem, path: Path) -> None:
        try:
            stat = path.stat()
            tooltip = (
                f"File: {path.name}\n"
                f"Type: {path.suffix or 'unknown'}\n"
                f"Size: {stat.st_size / 1024:.1f} KB\n"
                f"Last modified: {datetime.fromtimestamp(stat.st_mtime)}"
            )
            item.setToolTip(tooltip)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    @Slot()
    def ingest_selected(self) -> None:
        item = self.file_list.currentItem()
        if item is None:
            QMessageBox.information(self, "No file selected", "Please select a file.")
            return

        file_path = item.text()
        decision = self._validate_file(file_path)

        if not decision.allowed:
            self._show_validation_rejection(file_path, decision)
            return

        self._start_ingestion(file_path)

    def _start_ingestion(self, file_path: str) -> None:
        self.status.setText(f"Ingesting {Path(file_path).name}...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setValue(0)

        self.btn_ingest.setEnabled(False)
        self.btn_add.setEnabled(False)
        self.btn_cancel.setEnabled(True)

        logger.info(
            "Ingestion started",
            extra={
                "context": {
                    "operation": "ingest_selected",
                    "file_path": file_path,
                }
            },
        )

        self._active_worker = FunctionWorker(
            self.job_service.ingest_file,
            file_path,
            task_name="Ingest File",
            max_retries=1,
        )

        self._active_worker.signals.started.connect(self._on_worker_started)
        self._active_worker.signals.progress.connect(self._on_worker_progress)
        self._active_worker.signals.finished.connect(
            lambda result: self._on_ingested(result, file_path)
        )
        self._active_worker.signals.error.connect(
            lambda err: self._on_ingest_failed(err, file_path)
        )

        self.thread_pool.start(self._active_worker)

    def cancel_ingestion(self) -> None:
        if self._active_worker:
            self.status.setText("Cancelling ingestion...")
            self._active_worker.setAutoDelete(True)
            self._active_worker = None

        self._reset_ui()

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    def _validate_file(self, file_path: str) -> SafetyDecision:
        try:
            return self.safety.validate_file(file_path)
        except Exception as exc:
            logger.exception(
                "Safety validation error",
                extra={
                    "context": {
                        "operation": "validate_file",
                        "file_path": file_path,
                        "error": str(exc),
                    }
                },
            )
            return SafetyDecision(
                allowed=False,
                reason=str(exc),
                error_type="validation_error",
                metadata={"file_path": file_path},
            )

    def _show_validation_rejection(
        self,
        file_path: str,
        decision: SafetyDecision,
    ) -> None:
        message = (
            f"File rejected:\n\n{file_path}\n\n"
            f"Reason: {decision.reason}\n"
            f"Type: {decision.error_type}"
        )

        QMessageBox.warning(self, "Rejected File", message)

    # ------------------------------------------------------------------
    # Worker slots
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_worker_started(self, task_name: str) -> None:
        self.status.setText(f"{task_name} started")

    @Slot(str)
    def _on_worker_progress(self, message: str) -> None:
        safe_message = self.safety.redact_sensitive_text(message).value
        self.status.setText(safe_message)

    def _on_ingested(self, worker_result: WorkerResult, file_path: str) -> None:
        self._reset_ui()

        if not worker_result.success:
            self._handle_worker_failure(worker_result, file_path)
            return

        document_id = int(worker_result.result)

        result = IngestResult(
            document_id=document_id,
            file_path=file_path,
            status="success",
            metadata={
                "size": os.path.getsize(file_path),
                "type": Path(file_path).suffix,
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        logger.info(
            "Ingestion completed",
            extra={
                "context": {
                    "operation": "ingestion_completed",
                    "file_path": file_path,
                    "document_id": document_id,
                }
            },
        )

        self.status.setText("Ingestion completed.")
        self.document_ingested.emit(result)

    def _on_ingest_failed(self, error_context: dict[str, Any], file_path: str) -> None:
        self._reset_ui()

        logger.error(
            "Ingestion failed",
            extra={
                "context": {
                    **error_context,
                    "file_path": file_path,
                }
            },
        )

        QMessageBox.critical(
            self,
            "Ingestion Failed",
            self._format_error_dialog(file_path, error_context),
        )

        self.document_ingested.emit(
            IngestResult(
                document_id=None,
                file_path=file_path,
                status="failure",
                metadata=error_context,
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reset_ui(self) -> None:
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)

        self.btn_ingest.setEnabled(True)
        self.btn_add.setEnabled(True)
        self.btn_cancel.setEnabled(False)

        self._active_worker = None

    @staticmethod
    def _format_error_dialog(file_path: str, context: dict[str, Any]) -> str:
        lines = [
            f"File: {file_path}",
            f"Error: {context.get('error_type', 'unknown')}",
            f"Message: {context.get('error_message', '')}",
        ]

        tb = context.get("traceback")
        if tb:
            lines.append("\nTraceback:")
            lines.append(str(tb)[-4000:])

        return "\n".join(lines)