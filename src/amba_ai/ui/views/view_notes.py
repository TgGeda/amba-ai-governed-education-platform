# src/amba_ai/ui/notes_view.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from amba_ai.core.safety_service import SafetyService
from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from amba_ai.ui.workers import FunctionWorker, WorkerResult


# ---------------------------------------------------------------------
# UI helper DTO
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class NotesMetadata:
    document_id: int
    title: str
    created_at: str
    text_length: int
    model_name: str | None = None
    cached: bool | None = None


# ---------------------------------------------------------------------
# NotesView
# ---------------------------------------------------------------------

class NotesView(QWidget):
    """
    Notes editor and viewer with:
    - Background generation
    - Cached refresh
    - Metadata display
    - Autosave-ready dirty tracking
    - Safe export through JobService
    """

    status_message = Signal(str)

    AUTOSAVE_INTERVAL_MS = 5_000

    def __init__(
        self,
        job_service: JobService,
        safety_service: SafetyService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.job_service = job_service
        self.safety = safety_service or SafetyService()

        self.document_id: int | None = None
        self._dirty = False
        self._last_loaded_text = ""

        # ------------------------------------------------------------------
        # UI widgets
        # ------------------------------------------------------------------

        self.meta_label = QLabel("No document selected")
        self.meta_label.setStyleSheet("color: gray")

        self.editor = QTextEdit()
        self.editor.setReadOnly(False)
        self.editor.textChanged.connect(self._on_text_changed)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)

        self.btn_generate = QPushButton("Generate Notes")
        self.btn_refresh = QPushButton("Refresh")
        self.btn_export_md = QPushButton("Export Markdown")
        self.btn_export_txt = QPushButton("Export Text")
        self.btn_export_pdf = QPushButton("Export PDF")

        self.btn_generate.clicked.connect(self.generate_notes)
        self.btn_refresh.clicked.connect(self.refresh_notes)
        self.btn_export_md.clicked.connect(lambda: self.export_notes("md"))
        self.btn_export_txt.clicked.connect(lambda: self.export_notes("txt"))
        self.btn_export_pdf.clicked.connect(lambda: self.export_notes("pdf"))

        actions = QHBoxLayout()
        actions.addWidget(self.btn_generate)
        actions.addWidget(self.btn_refresh)
        actions.addWidget(self.btn_export_md)
        actions.addWidget(self.btn_export_txt)
        actions.addWidget(self.btn_export_pdf)

        layout = QVBoxLayout()
        layout.addWidget(self.meta_label)
        layout.addLayout(actions)
        layout.addWidget(self.progress)
        layout.addWidget(self.editor)
        self.setLayout(layout)

        # ------------------------------------------------------------------
        # Autosave timer
        # ------------------------------------------------------------------

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(self.AUTOSAVE_INTERVAL_MS)
        self.autosave_timer.timeout.connect(self._autosave)
        self.autosave_timer.start()

    # ------------------------------------------------------------------
    # Document handling
    # ------------------------------------------------------------------

    def set_document(self, document_id: int) -> None:
        if self._dirty and not self._confirm_discard():
            return

        self.document_id = document_id
        self._dirty = False
        self._last_loaded_text = ""

        self.editor.blockSignals(True)
        self.editor.clear()
        self.editor.blockSignals(False)

        self._update_metadata(
            NotesMetadata(
                document_id=document_id,
                title="Document",
                created_at="",
                text_length=0,
                model_name=None,
                cached=None,
            )
        )

        self.refresh_notes()

    # ------------------------------------------------------------------
    # Generation / refresh
    # ------------------------------------------------------------------

    @Slot()
    def generate_notes(self) -> None:
        if self.document_id is None:
            self._info("Select a document first.")
            return

        logger.info(
            "Notes generation requested",
            extra={"context": {"document_id": self.document_id}},
        )

        self._start_progress("Generating notes...")

        worker = FunctionWorker(
            self.job_service.generate_notes_markdown,
            self.document_id,
            task_name="Generate Notes",
            max_retries=1,
        )
        worker.signals.finished.connect(self._on_notes_loaded)
        worker.signals.error.connect(self._on_worker_error)

        self._start_worker(worker)

    @Slot()
    def refresh_notes(self) -> None:
        if self.document_id is None:
            return

        logger.info(
            "Notes refresh requested",
            extra={"context": {"document_id": self.document_id}},
        )

        self._start_progress("Refreshing notes...")

        worker = FunctionWorker(
            self.job_service.get_notes,
            self.document_id,
            task_name="Refresh Notes",
            max_retries=0,
        )
        worker.signals.finished.connect(self._on_notes_loaded)
        worker.signals.error.connect(self._on_worker_error)

        self._start_worker(worker)

    # ------------------------------------------------------------------
    # Worker callbacks
    # ------------------------------------------------------------------

    @Slot(object)
    def _on_notes_loaded(self, raw: Any) -> None:
        self._stop_progress()

        result = self._unwrap(raw)

        if not result.success:
            self._handle_failure(result)
            return

        notes = "" if result.result is None else str(result.result)

        self.editor.blockSignals(True)
        self.editor.setPlainText(notes)
        self.editor.blockSignals(False)

        self._last_loaded_text = notes
        self._dirty = False

        meta = NotesMetadata(
            document_id=self.document_id or 0,
            title="Document",
            created_at="",
            text_length=len(notes),
            model_name=None,
            cached=None,
        )
        self._update_metadata(meta)

        logger.info(
            "Notes loaded",
            extra={
                "context": {
                    "document_id": meta.document_id,
                    "text_length": meta.text_length,
                }
            },
        )

        if not notes:
            self.status_message.emit("No cached notes found. Generate notes to create them.")
        else:
            self.status_message.emit("Notes ready.")

    @Slot(dict)
    def _on_worker_error(self, context: dict[str, Any]) -> None:
        self._stop_progress()

        logger.error(
            "Notes worker error",
            extra={"context": context},
        )

        retry = QMessageBox.question(
            self,
            "Notes Error",
            self._format_error(context) + "\n\nRetry generation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if retry == QMessageBox.StandardButton.Yes:
            self.generate_notes()

    def _handle_failure(self, result: WorkerResult) -> None:
        context = getattr(result, "context", None) or {
            "operation": getattr(result, "task_name", "unknown"),
            "error_message": getattr(result, "error", "Unknown error"),
        }

        self._on_worker_error(context)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_notes(self, fmt: str) -> None:
        if self.document_id is None:
            self._info("Select a document first.")
            return

        current_text = self.editor.toPlainText().strip()

        if not current_text:
            self._info("Generate notes first.")
            return

        if self._dirty:
            proceed = QMessageBox.question(
                self,
                "Unsaved Changes",
                "The editor contains unsaved changes. Export will use the persisted notes from JobService.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if proceed != QMessageBox.StandardButton.Yes:
                return

        export_fmt = self._normalize_export_format(fmt)
        extension = self._extension_for_format(export_fmt)
        filename = f"{self._safe_filename(f'notes_{self.document_id}')}.{extension}"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export notes",
            filename,
            self._filter_for_format(export_fmt),
        )

        if not path:
            return

        try:
            self.job_service.export_notes(
                self.document_id,
                Path(path),
                export_fmt,
            )

            QMessageBox.information(
                self,
                "Exported",
                f"Saved to:\n{path}",
            )

            logger.info(
                "Notes exported",
                extra={
                    "context": {
                        "document_id": self.document_id,
                        "format": export_fmt,
                        "path": path,
                    }
                },
            )

        except Exception as exc:
            logger.exception(
                "Notes export failed",
                extra={
                    "context": {
                        "document_id": self.document_id,
                        "format": export_fmt,
                        "path": path,
                    }
                },
            )
            self._error(str(exc))

    # ------------------------------------------------------------------
    # Autosave
    # ------------------------------------------------------------------

    def _on_text_changed(self) -> None:
        self._dirty = self.editor.toPlainText() != self._last_loaded_text

    def _autosave(self) -> None:
        if not self._dirty or self.document_id is None:
            return

        logger.info(
            "Autosave skipped because persistence for edited notes is not exposed by JobService",
            extra={"context": {"document_id": self.document_id}},
        )

    def _confirm_discard(self) -> bool:
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Discard unsaved changes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _start_worker(self, worker: FunctionWorker) -> None:
        worker.signals.started.connect(lambda _: self._set_busy(True))
        worker.signals.finished.connect(lambda _: self._set_busy(False))
        worker.signals.error.connect(lambda _: self._set_busy(False))
        QThreadPool.globalInstance().start(worker)

    def _start_progress(self, message: str) -> None:
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status_message.emit(message)

    def _stop_progress(self) -> None:
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)

    def _set_busy(self, busy: bool) -> None:
        self.btn_generate.setEnabled(not busy)
        self.btn_refresh.setEnabled(not busy)
        self.btn_export_md.setEnabled(not busy)
        self.btn_export_txt.setEnabled(not busy)
        self.btn_export_pdf.setEnabled(not busy)

    def _update_metadata(self, meta: NotesMetadata) -> None:
        cached_text = ""
        if meta.cached is True:
            cached_text = " | Cached"
        elif meta.cached is False:
            cached_text = " | Fresh"

        self.meta_label.setText(
            f"Document {meta.document_id} | "
            f"Length: {meta.text_length} chars | "
            f"Model: {meta.model_name or 'n/a'} | "
            f"Created: {meta.created_at or 'n/a'}"
            f"{cached_text}"
        )

    @staticmethod
    def _unwrap(raw: Any) -> WorkerResult:
        if isinstance(raw, WorkerResult):
            return raw

        return WorkerResult(
            task_name="unknown",
            result=raw,
            success=True,
        )

    @staticmethod
    def _format_error(context: dict[str, Any]) -> str:
        lines = [
            f"Operation: {context.get('operation', context.get('task_name', 'unknown'))}",
            f"Error: {context.get('error_message', context.get('error', ''))}",
        ]

        if context.get("document_id"):
            lines.append(f"Document ID: {context['document_id']}")

        if context.get("traceback"):
            lines.append("\nTraceback:")
            lines.append(str(context["traceback"])[-4000:])

        return "\n".join(lines)

    def _safe_filename(self, value: str) -> str:
        result = self.safety.safe_filename(value)

        if isinstance(result, str):
            return result

        if hasattr(result, "value"):
            return str(result.value)

        return str(result)

    @staticmethod
    def _normalize_export_format(fmt: str) -> str:
        normalized = (fmt or "md").strip().lower()

        if normalized in {"markdown", "md"}:
            return "md"

        if normalized in {"text", "txt"}:
            return "txt"

        if normalized == "pdf":
            return "pdf"

        return normalized

    @staticmethod
    def _extension_for_format(fmt: str) -> str:
        if fmt == "md":
            return "md"
        if fmt == "txt":
            return "txt"
        return fmt

    @staticmethod
    def _filter_for_format(fmt: str) -> str:
        if fmt == "md":
            return "Markdown (*.md);;All Files (*)"

        if fmt == "txt":
            return "Text (*.txt);;All Files (*)"

        if fmt == "pdf":
            return "PDF (*.pdf);;All Files (*)"

        return f"{fmt.upper()} (*.{fmt});;All Files (*)"

    def _info(self, message: str) -> None:
        QMessageBox.information(self, "Notes", message)

    def _error(self, message: str) -> None:
        QMessageBox.critical(self, "Notes Error", message)