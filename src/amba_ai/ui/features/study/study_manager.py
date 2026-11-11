from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from amba_ai.logger import logger
from amba_ai.models.schemas import StudyAssetsResult
from amba_ai.services.job_service import JobService
from amba_ai.ui.governance_context import desktop_governance_context
from .data_classes import StudyAssetsViewModel, StudyGenerationRequest
from amba_ai.ui.workers import FunctionWorker, unwrap_worker_result


class StudyManager(QObject):
    studyStarted = Signal(str)
    studyFinished = Signal(dict)
    studyFailed = Signal(dict)
    studyHeld = Signal(dict)
    studyAssetsGenerated = Signal(int)
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
        self.statusMessage.emit("Study pedagogy profile synchronized with Equity Switch.", "INFO")

    @Slot(dict)
    def generate_study_assets(self, request_payload: dict[str, Any]) -> None:
        if self._is_operation_active:
            self.statusMessage.emit("Study asset synthesis already in progress.", "WARNING")
            return

        request = StudyGenerationRequest.from_dict(request_payload)

        if request.document_id <= 0:
            context = {
                "task_name": "Synthesize Study Pack",
                "error_type": "InvalidDocument",
                "error_message": "A valid document must be selected before generating study materials.",
            }
            self.studyFailed.emit(context)
            self.statusMessage.emit(context["error_message"], "ERROR")
            return

        self._is_operation_active = True
        self.studyStarted.emit("Synthesizing active recall cards & scenario quiz...")
        self.operationStarted.emit("Synthesizing active recall cards & scenario quiz...")

        worker = FunctionWorker(
            self._run_study_assets,
            request,
            task_name="Synthesize Study Pack",
            max_retries=0,
        )
        worker.signals.finished.connect(self._on_study_finished)
        worker.signals.error.connect(self._on_worker_error)
        worker.signals.held.connect(self._on_worker_held)
        worker.signals.status.connect(self._on_worker_status)

        self.thread_pool.start(worker)

    def _run_study_assets(self, request: StudyGenerationRequest) -> StudyAssetsViewModel:
        result = self.jobs.generate_study_assets(
            document_id=request.document_id,
            force=request.force,
            flashcard_count=request.flashcard_count,
            mcq_count=request.mcq_count,
            governance_context=desktop_governance_context(
                "generate_study_assets",
                document_id=request.document_id,
            ),
        )
        result = self.jobs.require_governed_result(result)
        if not isinstance(result, StudyAssetsResult):
            raise TypeError("Governed study backend returned an invalid result.")
        return StudyAssetsViewModel.from_study_assets_result(result)

    @Slot(dict)
    def _on_worker_status(self, payload: dict[str, Any]) -> None:
        message = str(payload.get("message") or payload.get("stage") or "Synthesizing curriculum assets...")
        self.statusMessage.emit(message, "INFO")

    @Slot(dict)
    def _on_worker_held(self, hold_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        logger.info("Study operation held for governance review", extra={"context": hold_context})
        receipt = hold_context.get("review_queue_receipt") or hold_context.get("event_id") or "pending"
        message = f"Study asset synthesis held for governance review (receipt: {receipt})."
        self.studyHeld.emit(hold_context)
        self.statusMessage.emit(message, "WARNING")
        self.operationFinished.emit("Study asset synthesis held for review.")

    @Slot(dict)
    def _on_worker_error(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        logger.warning("Study manager worker emitted error", extra={"context": error_context})
        message = str(error_context.get("error_message") or "Study asset synthesis error.")
        self.studyFailed.emit(error_context)
        self.statusMessage.emit(message, "ERROR")
        self.operationFinished.emit("Study asset generation failed.")

    @Slot(object)
    def _on_study_finished(self, raw_result: Any) -> None:
        self._is_operation_active = False
        result = unwrap_worker_result(raw_result, default_task_name="Synthesize Study Pack")

        if not result.success:
            context = {
                "task_name": result.task_name,
                "error_message": result.error_message or "Study generation failed.",
                **(result.metadata or {}),
            }
            self.studyFailed.emit(context)
            self.statusMessage.emit(context["error_message"], "ERROR")
            self.operationFinished.emit("Study generation failed.")
            return

        if not isinstance(result.result, StudyAssetsViewModel):
            context = {
                "task_name": result.task_name,
                "error_type": "InvalidResult",
                "error_message": "Study generation returned an unexpected structure.",
            }
            self.studyFailed.emit(context)
            self.statusMessage.emit(context["error_message"], "ERROR")
            self.operationFinished.emit("Study generation failed.")
            return

        payload = result.result.to_dict()
        document_id = int(payload.get("document_id") or 0)

        self.studyFinished.emit(payload)
        if document_id > 0:
            self.studyAssetsGenerated.emit(document_id)

        self.statusMessage.emit("Interactive study pack synthesized.", "INFO")
        self.operationFinished.emit("Study pack ready.")

    def cleanup_before_close(self) -> None:
        self._equity_profile = {}
        self.statusMessage.emit("Study manager state cleared.", "INFO")