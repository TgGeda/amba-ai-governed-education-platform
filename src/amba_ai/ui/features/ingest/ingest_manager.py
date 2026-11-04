from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from amba_ai.logger import logger
from amba_ai.models.schemas import IngestedDocumentResult
from amba_ai.services.job_service import JobService
from amba_ai.ui.workers import FunctionWorker, WorkerResult, unwrap_worker_result
from .data_classes import IngestRequest, IngestViewModel


class IngestManager(QObject):
    ingestionStarted = Signal(str)
    ingestionFinished = Signal(dict)
    ingestionFailed = Signal(dict)
    documentIngested = Signal(int)
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
        self.statusMessage.emit("Ingest profile updated from Equity Switch.", "INFO")

    @Slot(str)
    def ingest_file(self, path: str) -> None:
        if self._is_operation_active:
            self.statusMessage.emit("Ingestion already in progress.", "WARNING")
            return

        request = IngestRequest.from_path(path)

        if not request.exists:
            context = {
                "task_name": "Ingest File",
                "error_type": "FileNotFound",
                "error_message": f"File does not exist: {request.path}",
                "path": request.path,
            }
            self.ingestionFailed.emit(context)
            self.statusMessage.emit(context["error_message"], "ERROR")
            return

        self._is_operation_active = True
        self.ingestionStarted.emit(request.path)
        self.operationStarted.emit("Ingesting learning material...")

        worker = FunctionWorker(
            self.jobs.ingest_file,
            request.path,
            task_name="Ingest File",
            max_retries=0,
        )
        worker.signals.finished.connect(self._on_ingest_finished)
        worker.signals.error.connect(self._on_worker_error)
        worker.signals.status.connect(self._on_worker_status)

        self.thread_pool.start(worker)

    @Slot(dict)
    def _on_worker_status(self, payload: dict[str, Any]) -> None:
        message = str(payload.get("message") or payload.get("stage") or "Ingesting document...")
        self.statusMessage.emit(message, "INFO")

    @Slot(dict)
    def _on_worker_error(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        logger.warning("Ingest worker emitted error", extra={"context": error_context})
        message = str(error_context.get("error_message") or "Ingestion error.")
        self.ingestionFailed.emit(error_context)
        self.statusMessage.emit(message, "ERROR")
        self.operationFinished.emit("Ingestion failed.")

    @Slot(object)
    def _on_ingest_finished(self, raw_result: Any) -> None:
        self._is_operation_active = False
        result = unwrap_worker_result(raw_result, default_task_name="Ingest File")

        if not result.success:
            context = {
                "task_name": result.task_name,
                "error_message": result.error_message or "File ingestion failed.",
                **(result.metadata or {}),
            }
            self.ingestionFailed.emit(context)
            self.statusMessage.emit(context["error_message"], "ERROR")
            self.operationFinished.emit("Ingestion failed.")
            return

        if not isinstance(result.result, IngestedDocumentResult):
            context = {
                "task_name": result.task_name,
                "error_type": "InvalidResult",
                "error_message": "Ingestion returned an invalid result.",
            }
            self.ingestionFailed.emit(context)
            self.statusMessage.emit(context["error_message"], "ERROR")
            self.operationFinished.emit("Ingestion failed.")
            return

        view_model = IngestViewModel.from_ingested_result(result.result)
        payload = view_model.to_dict()

        self.ingestionFinished.emit(payload)
        if view_model.document_id > 0:
            self.documentIngested.emit(view_model.document_id)

        self.statusMessage.emit("Document ingested successfully.", "INFO")
        self.operationFinished.emit("Document ingested successfully.")

    def cleanup_before_close(self) -> None:
        self._equity_profile = {}
        self.statusMessage.emit("Ingest state cleared before close.", "INFO")