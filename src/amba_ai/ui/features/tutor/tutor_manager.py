from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from amba_ai.logger import logger
from amba_ai.models.schemas import AnswerResult
from amba_ai.services.job_service import JobService
from .data_classes import TutorAnswerViewModel, TutorPersona, TutorRequest
from amba_ai.ui.workers import FunctionWorker, unwrap_worker_result


class TutorManager(QObject):
    tutorStarted = Signal(str)
    tutorFinished = Signal(dict)
    tutorFailed = Signal(dict)
    tutorAnswerReady = Signal(str)
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
        self.statusMessage.emit("Tutor cognitive parameters aligned with Equity Switch.", "INFO")

    @Slot(dict)
    def ask(self, request_payload: dict[str, Any]) -> None:
        if self._is_operation_active:
            self.statusMessage.emit("Tutor is currently generating an explanation.", "WARNING")
            return

        request = TutorRequest.from_dict(request_payload)

        if not request.question:
            context = {
                "task_name": "Tutor Explanation",
                "error_type": "InvalidQuestion",
                "error_message": "Please enter a valid study question or concept.",
            }
            self.tutorFailed.emit(context)
            self.statusMessage.emit(context["error_message"], "ERROR")
            return

        self._is_operation_active = True
        self.tutorStarted.emit(request.question)
        self.operationStarted.emit("Consulting grounded curriculum material...")

        worker = FunctionWorker(
            self._run_tutor_answer,
            request,
            task_name="Tutor Explanation",
            max_retries=0,
        )
        worker.signals.finished.connect(self._on_tutor_finished)
        worker.signals.error.connect(self._on_worker_error)
        worker.signals.status.connect(self._on_worker_status)

        self.thread_pool.start(worker)

    def _run_tutor_answer(self, request: TutorRequest) -> TutorAnswerViewModel:
        if hasattr(self.jobs, "tutor_chat"):
            result = self.jobs.tutor_chat(
                request.document_id, request.question, top_k=request.top_k, max_tokens=request.max_tokens,
                active_tab=request.active_tab, active_document_title=request.active_document_title,
                due_flashcards=request.due_flashcards, session_id=request.session_id,
            )
        elif hasattr(self.jobs, "tutor_answer"):
            result = self.jobs.tutor_answer(
                request.question, top_k=request.top_k, max_tokens=request.max_tokens, document_id=request.document_id,
                active_tab=request.active_tab, active_document_title=request.active_document_title,
                due_flashcards=request.due_flashcards, session_id=request.session_id,
            )
        else:
            raise AttributeError("JobService does not support governed tutor answers.")
        if not isinstance(result, AnswerResult) or not getattr(result, "answer_text", None):
            raise TypeError("Governed tutor backend returned an invalid result.")
        return TutorAnswerViewModel.from_answer_result(result,question=request.question,document_id=request.document_id,persona=request.persona)

    @Slot(dict)
    def _on_worker_status(self, payload: dict[str, Any]) -> None:
        message = str(payload.get("message") or payload.get("stage") or "Synthesizing tutor answer...")
        self.statusMessage.emit(message, "INFO")

    @Slot(dict)
    def _on_worker_error(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        logger.warning("Tutor worker failed; fail-closed response emitted.")
        self.tutorFailed.emit(dict(error_context))
        self.statusMessage.emit(str(error_context.get("error_message") or "Tutor request was not performed."), "ERROR")
        self.operationFinished.emit("Tutor request refused or failed.")

    @Slot(object)
    def _on_tutor_finished(self, raw_result: Any) -> None:
        self._is_operation_active = False
        result = unwrap_worker_result(raw_result, default_task_name="Tutor Explanation")

        if not result.success or not isinstance(result.result, TutorAnswerViewModel):
            context = {"task_name": "Tutor Explanation", "error_type": "GovernedTutorFailure", "error_message": result.error_message or "Tutor request was not performed."}
            self.tutorFailed.emit(context)
            self.statusMessage.emit(context["error_message"], "ERROR")
            self.operationFinished.emit("Tutor request refused or failed.")
            return

        payload = result.result.to_dict()
        self.tutorFinished.emit(payload)
        self.tutorAnswerReady.emit(result.result.answer_text)
        self.statusMessage.emit("Tutor answer generated.", "INFO")
        self.operationFinished.emit("Tutor answer ready.")

    def cleanup_before_close(self) -> None:
        self._equity_profile = {}
        self.statusMessage.emit("Tutor session synchronized before close.", "INFO")