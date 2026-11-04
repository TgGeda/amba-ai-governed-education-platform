from __future__ import annotations

import csv
import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
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

from amba_ai.logger import logger
from amba_ai.ui.workers import FunctionWorker, WorkerResult
from amba_ai.core.rlhf_service import RLHFService


# ---------------------------------------------------------------------
# Typed DTOs
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class FeedbackResult:
    event_id: int
    feature: str
    rating: int
    prompt_length: int
    response_length: int
    created_at: float


# ---------------------------------------------------------------------
# FeedbackView
# ---------------------------------------------------------------------

class FeedbackView(QWidget):
    """
    UI for collecting RLHF feedback.

    Responsibilities:
    - Validate input
    - Submit feedback in background thread
    - Emit typed feedback events
    - Export feedback safely (atomic writes)
    - Display lightweight analytics
    """

    feedback_submitted = Signal(FeedbackResult)

    def __init__(
        self,
        rlhf_service: RLHFService | None = None,
        job_service: Any | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.rlhf_service = rlhf_service or RLHFService()
        self.job_service = job_service
        self.thread_pool = QThreadPool.globalInstance()

        # ------------------------------------------------------------------
        # UI widgets
        # ------------------------------------------------------------------

        self.header = QLabel("Feedback")
        self.header.setAlignment(Qt.AlignCenter)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)

        self.status = QLabel("")
        self.status.setStyleSheet("color: gray")

        self.feature = QComboBox()
        self.feature.addItems(
            ["summary", "flashcards", "quiz", "tutor", "translation", "export"]
        )

        self.rating = QComboBox()
        self.rating.addItem("Good (+1)", 1)
        self.rating.addItem("Neutral (0)", 0)
        self.rating.addItem("Bad (-1)", -1)

        self.prompt = QTextEdit()
        self.response = QTextEdit()
        self.comment = QTextEdit()
        self.comment.setPlaceholderText("Optional comment")

        self.btn_submit = QPushButton("Submit Feedback")
        self.btn_export = QPushButton("Export Feedback")
        self.btn_refresh_stats = QPushButton("Refresh Stats")

        self.btn_submit.clicked.connect(self.submit)
        self.btn_export.clicked.connect(self.export_feedback)
        self.btn_refresh_stats.clicked.connect(self.refresh_stats)

        controls = QHBoxLayout()
        controls.addWidget(self.btn_submit)
        controls.addWidget(self.btn_export)
        controls.addWidget(self.btn_refresh_stats)

        layout = QVBoxLayout()
        layout.addWidget(self.header)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(QLabel("Feature"))
        layout.addWidget(self.feature)
        layout.addWidget(QLabel("Rating"))
        layout.addWidget(self.rating)
        layout.addWidget(QLabel("Prompt / Input"))
        layout.addWidget(self.prompt)
        layout.addWidget(QLabel("Response / Output"))
        layout.addWidget(self.response)
        layout.addWidget(QLabel("Comment"))
        layout.addWidget(self.comment)
        layout.addLayout(controls)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> bool:
        if not self.prompt.toPlainText().strip():
            QMessageBox.warning(self, "Feedback", "Prompt cannot be empty.")
            return False

        if not self.response.toPlainText().strip():
            QMessageBox.warning(self, "Feedback", "Response cannot be empty.")
            return False

        return True

    # ------------------------------------------------------------------
    # Submission (background)
    # ------------------------------------------------------------------

    @Slot()
    def submit(self) -> None:
        if not self._validate():
            return

        feature = self.feature.currentText()
        rating = int(self.rating.currentData())
        prompt_text = self.prompt.toPlainText()
        response_text = self.response.toPlainText()
        comment_text = self.comment.toPlainText()

        logger.info(
            "Feedback submission started",
            extra={"context": {"feature": feature, "rating": rating}},
        )

        self._set_busy(True, "Submitting feedback...")

        worker = FunctionWorker(
            self._record_feedback,
            feature,
            rating,
            prompt_text,
            response_text,
            comment_text,
            task_name="Submit Feedback",
            max_retries=1,
        )

        worker.signals.finished.connect(self._on_submitted)
        worker.signals.error.connect(self._on_worker_error)

        self.thread_pool.start(worker)

    def _record_feedback(
        self,
        feature: str,
        rating: int,
        prompt: str,
        response: str,
        comment: str,
    ) -> FeedbackResult:
        event_id = self.rlhf_service.record_feedback(
            feature=feature,
            rating=rating,
            prompt=prompt,
            response=response,
            comment=comment,
        )

        if self.job_service is not None and hasattr(
            self.job_service, "record_feedback_event"
        ):
            try:
                self.job_service.record_feedback_event(event_id)
            except Exception:
                logger.warning("Failed to forward feedback event to JobService", exc_info=True)

        return FeedbackResult(
            event_id=int(event_id),
            feature=feature,
            rating=rating,
            prompt_length=len(prompt),
            response_length=len(response),
            created_at=time.time(),
        )

    @Slot(object)
    def _on_submitted(self, raw: Any) -> None:
        self._set_busy(False)

        result = raw if isinstance(raw, WorkerResult) else None
        if result is None or not result.success:
            self._handle_failure(result)
            return

        feedback: FeedbackResult = result.result
        self.feedback_submitted.emit(feedback)

        logger.info(
            "Feedback submission completed",
            extra={
                "context": {
                    "event_id": feedback.event_id,
                    "feature": feedback.feature,
                    "rating": feedback.rating,
                }
            },
        )

        QMessageBox.information(self, "Feedback", "Feedback saved.")

        self.prompt.clear()
        self.response.clear()
        self.comment.clear()

        self.status.setText(
            f"Last feedback: {feedback.feature} | Rating {feedback.rating} | "
            f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(feedback.created_at))}"
        )

    @Slot(dict)
    def _on_worker_error(self, context: dict[str, Any]) -> None:
        self._set_busy(False)

        logger.error("Feedback submission failed", extra={"context": context})

        retry = QMessageBox.question(
            self,
            "Feedback Error",
            self._format_error(context) + "\n\nRetry?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if retry == QMessageBox.StandardButton.Yes:
            self.submit()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_feedback(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export feedback",
            "feedback.json",
            "JSON (*.json);;CSV (*.csv);;All Files (*)",
        )

        if not path:
            return

        try:
            records = self.rlhf_service.recent_feedback(limit=1000)

            output_path = Path(path).expanduser().resolve()
            if output_path.suffix.lower() == ".csv":
                self._export_csv_atomic(output_path, records)
            else:
                self._export_json_atomic(output_path.with_suffix(".json"), records)

            QMessageBox.information(self, "Export", f"Saved to:\n{output_path}")

            logger.info(
                "Feedback exported",
                extra={
                    "context": {
                        "path": str(output_path),
                        "count": len(records),
                    }
                },
            )

        except Exception as exc:
            logger.exception("Feedback export failed")
            QMessageBox.critical(self, "Export Error", str(exc))

    def _export_json_atomic(self, path: Path, records: list[Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.stem}.",
            suffix=".json.tmp",
            dir=str(path.parent),
            text=True,
        )
        tmp_path = Path(tmp_name)

        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
                f.write("\n")
            tmp_path.replace(path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        finally:
            try:
                import os
                os.close(fd)
            except Exception:
                pass

    def _export_csv_atomic(self, path: Path, records: list[dict[str, Any]]) -> None:
        if not records:
            return

        path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.stem}.",
            suffix=".csv.tmp",
            dir=str(path.parent),
        )
        tmp_path = Path(tmp_name)

        try:
            with tmp_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=records[0].keys())
                writer.writeheader()
                writer.writerows(records)
            tmp_path.replace(path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        finally:
            try:
                import os
                os.close(fd)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Analytics (lightweight)
    # ------------------------------------------------------------------

    def refresh_stats(self) -> None:
        try:
            aggregates = self.rlhf_service.aggregate_feedback()
            lines = [
                f"{a['feature']} | Doc {a['document_id']} | "
                f"Avg {a['avg_rating']} ({a['count']} samples)"
                for a in aggregates
            ]

            QMessageBox.information(
                self,
                "Feedback Stats",
                "\n".join(lines) if lines else "No feedback yet.",
            )

        except Exception as exc:
            QMessageBox.critical(self, "Stats Error", str(exc))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self.progress.setVisible(busy)
        self.btn_submit.setEnabled(not busy)
        self.btn_export.setEnabled(not busy)

        if busy:
            self.progress.setRange(0, 0)
            if message:
                self.status.setText(message)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)

    @staticmethod
    def _format_error(context: dict[str, Any]) -> str:
        lines = [
            f"Feature: {context.get('feature', 'unknown')}",
            f"Error: {context.get('error_message', context.get('error', ''))}",
        ]
        if context.get("traceback"):
            lines.append("\nTraceback:")
            lines.append(str(context["traceback"])[-4000:])
        return "\n".join(lines)

    def _handle_failure(self, result: WorkerResult | None) -> None:
        QMessageBox.critical(
            self,
            "Feedback Error",
            "Feedback submission failed.",
        )