from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from amba_ai.logger import logger
from amba_ai.models.schemas import SummaryResult
from amba_ai.services.job_service import JobService
from amba_ai.ui.governance_context import desktop_governance_context
from .data_classes import SummarizerRequest, SummaryViewModel
from amba_ai.ui.workers import FunctionWorker, unwrap_worker_result


class SummarizerManager(QObject):
    summaryStarted = Signal(str)
    summaryFinished = Signal(dict)
    summaryFailed = Signal(dict)
    summaryHeld = Signal(dict)
    summaryGenerated = Signal(int)
    statusMessage = Signal(str, str)
    operationStarted = Signal(str)
    operationFinished = Signal(str)

    def __init__(self, job_service: JobService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.jobs = job_service
        self.thread_pool = QThreadPool.globalInstance()
        self._is_operation_active = False
        self._equity_profile: dict[str, Any] = {}

    @Slot(dict)
    def apply_equity_profile(self, profile: dict[str, Any]) -> None:
        self._equity_profile = dict(profile or {})
        self.statusMessage.emit("Summarizer profile synchronized with Equity Engine.", "INFO")

    @Slot(dict)
    def generate_summary(self, request_payload: dict[str, Any]) -> None:
        if self._is_operation_active:
            self.statusMessage.emit("Curriculum synthesis already in progress.", "WARNING")
            return

        request = SummarizerRequest.from_dict(request_payload)

        if request.document_id <= 0:
            context = {
                "task_name": "Synthesize Lesson",
                "error_type": "InvalidDocument",
                "error_message": "A valid document must be selected before lesson generation.",
            }
            self.summaryFailed.emit(context)
            self.statusMessage.emit(context["error_message"], "ERROR")
            return

        self._is_operation_active = True
        self.summaryStarted.emit(request.mode.value)
        self.operationStarted.emit("Synthesizing structured lesson modules...")

        worker = FunctionWorker(
            self._run_summary,
            request,
            task_name="Synthesize Lesson",
            max_retries=0,
        )
        worker.signals.finished.connect(self._on_summary_finished)
        worker.signals.error.connect(self._on_worker_error)
        worker.signals.held.connect(self._on_worker_held)
        worker.signals.status.connect(self._on_worker_status)

        self.thread_pool.start(worker)

    def _run_summary(self, request: SummarizerRequest) -> SummaryViewModel:
        result = self.jobs.summarize_document(
            request.document_id,
            force=request.force,
            model_name=request.preferred_model,
            governance_context=desktop_governance_context(
                "summarize_document",
                document_id=request.document_id,
            ),
        )

        result = self.jobs.require_governed_result(result)
        if not isinstance(result, SummaryResult):
            raise TypeError("Summarizer backend returned an invalid result.")

        return SummaryViewModel.from_summary_result(result, mode=request.mode.value)

    @Slot(dict)
    def _on_worker_status(self, payload: dict[str, Any]) -> None:
        message = str(payload.get("message") or payload.get("stage") or "Processing lesson context...")
        self.statusMessage.emit(message, "INFO")

    @Slot(dict)
    def _on_worker_held(self, hold_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        logger.info("Summarizer operation held for governance review", extra={"context": hold_context})
        receipt = hold_context.get("review_queue_receipt") or hold_context.get("event_id") or "pending"
        message = f"Lesson synthesis held for governance review (receipt: {receipt})."
        self.summaryHeld.emit(hold_context)
        self.statusMessage.emit(message, "WARNING")
        self.operationFinished.emit("Lesson synthesis held for review.")

    @Slot(dict)
    def _on_worker_error(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        logger.warning("Summarizer worker emitted error", extra={"context": error_context})
        message = str(error_context.get("error_message") or "Lesson generation failed.")
        self.summaryFailed.emit(error_context)
        self.statusMessage.emit(message, "ERROR")
        self.operationFinished.emit("Lesson generation failed.")

    @Slot(object)
    def _on_summary_finished(self, raw_result: Any) -> None:
        self._is_operation_active = False
        result = unwrap_worker_result(raw_result, default_task_name="Synthesize Lesson")

        if not result.success:
            context = {
                "task_name": result.task_name,
                "error_message": result.error_message or "Lesson synthesis failed.",
                **(result.metadata or {}),
            }
            self.summaryFailed.emit(context)
            self.statusMessage.emit(context["error_message"], "ERROR")
            self.operationFinished.emit("Lesson synthesis failed.")
            return

        if not isinstance(result.result, SummaryViewModel):
            context = {
                "task_name": result.task_name,
                "error_type": "InvalidResult",
                "error_message": "Synthesis returned an unexpected structure.",
            }
            self.summaryFailed.emit(context)
            self.statusMessage.emit(context["error_message"], "ERROR")
            self.operationFinished.emit("Lesson synthesis failed.")
            return

        payload = result.result.to_dict()
        document_id = int(payload.get("document_id") or 0)

        self.summaryFinished.emit(payload)
        if document_id > 0:
            self.summaryGenerated.emit(document_id)

        self.statusMessage.emit("Interactive lesson modules generated.", "INFO")
        self.operationFinished.emit("Lesson generated.")

    def cleanup_before_close(self) -> None:
        self._equity_profile = {}
        self.statusMessage.emit("Summarizer manager state reset.", "INFO")