from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from amba_ai.logger import logger
from amba_ai.ui.workers import FunctionWorker, WorkerResult
from amba_ai.services.job_service import JobService
from amba_ai.core.context_tracker import ContextTracker
from amba_ai.core.export import export_markdown, export_pdf


# ---------------------------------------------------------------------
# Typed DTOs
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class DocumentSummary:
    document_id: int
    title: str
    kind: str
    created_at: str
    size: int | None
    summary_text: str | None = None


# ---------------------------------------------------------------------
# StudentView
# ---------------------------------------------------------------------

class StudentView(QWidget):
    """
    Student dashboard for browsing and opening study documents.

    Phase‑1 responsibilities:
    - Display document list and summaries
    - Emit document_opened events
    - Update ContextTracker with real UI state (NO LLM calls here)
    """

    document_opened = Signal(DocumentSummary)

    def __init__(self, job_service: JobService, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.job_service = job_service
        self.thread_pool = QThreadPool.globalInstance()
        self._documents: list[DocumentSummary] = []

        # Phase‑1 context tracker (shared instance from JobService)
        self.context_tracker: ContextTracker | None = getattr(
            job_service, "context_tracker", None
        )

        # ------------------------------------------------------------------
        # UI widgets
        # ------------------------------------------------------------------

        self.header = QLabel("Student Dashboard")
        self.header.setAlignment(Qt.AlignCenter)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Search by title or kind...")
        self.filter_input.textChanged.connect(self._apply_filter)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)

        self.documents = QListWidget()
        self.documents.itemDoubleClicked.connect(self.open_selected)

        self.summary = QTextEdit()
        self.summary.setReadOnly(True)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_open = QPushButton("Open Selected")
        self.btn_export_md = QPushButton("Export Markdown")
        self.btn_export_pdf = QPushButton("Export PDF")

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_open.clicked.connect(self.open_selected)
        self.btn_export_md.clicked.connect(lambda: self.export_summary("markdown"))
        self.btn_export_pdf.clicked.connect(lambda: self.export_summary("pdf"))

        actions = QHBoxLayout()
        actions.addWidget(self.btn_refresh)
        actions.addWidget(self.btn_open)
        actions.addWidget(self.btn_export_md)
        actions.addWidget(self.btn_export_pdf)

        layout = QVBoxLayout()
        layout.addWidget(self.header)
        layout.addWidget(self.filter_input)
        layout.addLayout(actions)
        layout.addWidget(self.progress)
        layout.addWidget(self.documents)
        layout.addWidget(QLabel("Summary"))
        layout.addWidget(self.summary)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Refresh documents
    # ------------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        logger.info("Student dashboard refresh requested")

        self._set_busy(True, "Refreshing documents...")

        worker = FunctionWorker(
            self.job_service.list_documents,
            task_name="Refresh Documents",
            max_retries=1,
        )

        worker.signals.finished.connect(self._on_refresh_finished)
        worker.signals.error.connect(self._on_worker_error)

        self.thread_pool.start(worker)

    @Slot(object)
    def _on_refresh_finished(self, raw: Any) -> None:
        self._set_busy(False)

        result = self._unwrap(raw)
        if not result.success:
            self._handle_failure(result)
            return

        docs = result.result or []
        self._documents.clear()
        self.documents.clear()

        for doc in docs:
            summary = DocumentSummary(
                document_id=int(getattr(doc, "id", doc["id"])),
                title=str(getattr(doc, "title", doc.get("title", ""))),
                kind=str(getattr(doc, "kind", doc.get("kind", ""))),
                created_at=str(getattr(doc, "created_at", doc.get("created_at", ""))),
                size=(doc.get("size") if isinstance(doc, dict) else None),
            )
            self._documents.append(summary)

        self._populate_list(self._documents)

        logger.info(
            "Student dashboard refresh completed",
            extra={"context": {"document_count": len(self._documents)}},
        )

    # ------------------------------------------------------------------
    # Open document
    # ------------------------------------------------------------------

    @Slot()
    def open_selected(self) -> None:
        item = self.documents.currentItem()
        if item is None:
            return

        doc_id = item.data(Qt.ItemDataRole.UserRole)

        self._set_busy(True, "Opening document...")

        logger.info(
            "Opening document",
            extra={"context": {"document_id": doc_id}},
        )

        worker = FunctionWorker(
            self.job_service.get_notes,
            doc_id,
            task_name="Open Document",
            max_retries=1,
        )

        worker.signals.finished.connect(
            lambda raw, d=doc_id: self._on_open_finished(raw, d)
        )
        worker.signals.error.connect(self._on_worker_error)

        self.thread_pool.start(worker)

    def _on_open_finished(self, raw: Any, document_id: int) -> None:
        self._set_busy(False)

        result = self._unwrap(raw)
        if not result.success:
            self._handle_failure(result, document_id=document_id)
            return

        summary_text = result.result or ""

        doc = next((d for d in self._documents if d.document_id == document_id), None)
        if not doc:
            QMessageBox.warning(self, "Student Dashboard", "Document not found.")
            return

        updated = DocumentSummary(
            **doc.__dict__,
            summary_text=str(summary_text),
        )

        self.summary.setPlainText(updated.summary_text or "")
        self.document_opened.emit(updated)

        # ------------------------------------------------------------
        # ✅ Phase‑1 REAL Context Wiring (NO MOCKS)
        # ------------------------------------------------------------
        if self.context_tracker is not None:
            self.context_tracker.set_active_tab("Student Dashboard")
            self.context_tracker.set_active_document(
                document_id=updated.document_id,
                title=updated.title,
            )

        logger.info(
            "Document opened",
            extra={
                "context": {
                    "document_id": updated.document_id,
                    "title": updated.title,
                }
            },
        )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_summary(self, fmt: str) -> None:
        item = self.documents.currentItem()
        if item is None:
            QMessageBox.information(self, "Student Dashboard", "Select a document first.")
            return

        text = self.summary.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Student Dashboard", "No summary to export.")
            return

        ext = "md" if fmt == "markdown" else "pdf"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export summary",
            f"summary.{ext}",
            f"{ext.upper()} (*.{ext});;All Files (*)",
        )

        if not path:
            return

        try:
            if fmt == "markdown":
                result = export_markdown(path, text)
            else:
                result = export_pdf(path, text)

            QMessageBox.information(self, "Exported", f"Saved to:\n{result.path}")

            logger.info(
                "Summary exported",
                extra={
                    "context": {
                        "format": fmt,
                        "path": str(result.path),
                    }
                },
            )

        except Exception as exc:
            logger.exception(
                "Export failed",
                extra={"context": {"format": fmt}},
            )
            QMessageBox.critical(self, "Export Error", str(exc))

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        query = text.strip().lower()

        if not query:
            self._populate_list(self._documents)
            return

        filtered = [
            d for d in self._documents
            if query in d.title.lower() or query in d.kind.lower()
        ]
        self._populate_list(filtered)

    def _populate_list(self, docs: list[DocumentSummary]) -> None:
        self.documents.clear()

        for doc in docs:
            item = QListWidgetItem(f"{doc.document_id}: {doc.title}")
            item.setData(Qt.ItemDataRole.UserRole, doc.document_id)

            tooltip = (
                f"Title: {doc.title}\n"
                f"Kind: {doc.kind}\n"
                f"Created: {doc.created_at}\n"
                f"Size: {doc.size or 'unknown'}"
            )
            item.setToolTip(tooltip)

            self.documents.addItem(item)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self.progress.setVisible(busy)
        if busy:
            self.progress.setRange(0, 0)
            if message:
                self.header.setText(message)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.header.setText("Student Dashboard")

    @staticmethod
    def _unwrap(raw: Any) -> WorkerResult:
        if isinstance(raw, WorkerResult):
            return raw
        return WorkerResult(
            task_name="unknown",
            result=raw,
            success=True,
        )

    def _handle_failure(self, result: WorkerResult, document_id: int | None = None) -> None:
        context = {
            "task": result.task_name,
            "document_id": document_id,
            **result.metadata,
        }

        logger.error("Student dashboard operation failed", extra={"context": context})

        retry = QMessageBox.question(
            self,
            "Student Dashboard Error",
            self._format_error(context) + "\n\nRetry?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if retry == QMessageBox.StandardButton.Yes:
            self.refresh()

    @staticmethod
    def _format_error(context: dict[str, Any]) -> str:
        lines = [
            f"Task: {context.get('task', 'unknown')}",
            f"Document ID: {context.get('document_id', 'n/a')}",
        ]
        if context:
            lines.append(f"Context: {context}")
        return "\n".join(lines)
