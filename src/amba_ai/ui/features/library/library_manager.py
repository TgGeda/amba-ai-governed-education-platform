from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from .data_classes import LibraryDocument
from amba_ai.ui.workers import FunctionWorker, unwrap_worker_result


class LibraryManager(QObject):
    libraryRefreshStarted = Signal()
    libraryRefreshFinished = Signal(list)
    libraryRefreshFailed = Signal(dict)
    statusMessage = Signal(str, str)
    operationStarted = Signal(str)
    operationFinished = Signal(str)
    documentDeletionFinished = Signal(dict)
    documentDeletionFailed = Signal(dict)

    def __init__(self, job_service: JobService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.jobs = job_service
        self.thread_pool = QThreadPool.globalInstance()
        self._is_operation_active = False
        self.documents: list[LibraryDocument] = []

    @Slot()
    def refresh_documents(self) -> None:
        if self._is_operation_active:
            self.statusMessage.emit("Library refresh already in progress.", "WARNING")
            return

        self._is_operation_active = True
        self.libraryRefreshStarted.emit()
        self.operationStarted.emit("Refreshing local document library...")

        worker = FunctionWorker(
            self.jobs.list_documents,
            task_name="List Documents",
            max_retries=0,
        )
        worker.signals.finished.connect(self._on_refresh_finished)
        worker.signals.error.connect(self._on_refresh_error)
        worker.signals.status.connect(self._on_worker_status)

        self.thread_pool.start(worker)

    @Slot(dict)
    def _on_worker_status(self, payload: dict[str, Any]) -> None:
        message = str(payload.get("message") or payload.get("stage") or "Refreshing library...")
        self.statusMessage.emit(message, "INFO")

    @Slot(dict)
    def _on_refresh_error(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        logger.warning("Library worker emitted error", extra={"context": error_context})
        message = str(error_context.get("error_message") or "Library refresh error.")
        self.documents = []
        self.libraryRefreshFailed.emit(error_context)
        self.statusMessage.emit(message, "ERROR")
        self.operationFinished.emit("Library refresh failed.")

    @Slot(object)
    def _on_refresh_finished(self, raw_result: Any) -> None:
        self._is_operation_active = False
        result = unwrap_worker_result(raw_result, default_task_name="List Documents")

        if not result.success:
            context = {
                "task_name": result.task_name,
                "error_message": result.error_message or "Library refresh failed.",
                **(result.metadata or {}),
            }
            self.documents = []
            self.libraryRefreshFailed.emit(context)
            self.statusMessage.emit(context["error_message"], "ERROR")
            self.operationFinished.emit("Library refresh failed.")
            return

        normalized = [doc for item in list(result.result or []) if (doc := LibraryDocument.from_any(item))]
        self.documents = normalized
        self.libraryRefreshFinished.emit([doc.to_dict() for doc in self.documents])
        self.statusMessage.emit(f"Library refreshed: {len(self.documents)} document(s).", "INFO")
        self.operationFinished.emit("Library refreshed.")

    def delete_document(self, document_id: int, *, reviewer_role: str) -> None:
        if self._is_operation_active:
            self.statusMessage.emit("A library operation is already in progress.", "WARNING")
            return
        self._is_operation_active = True
        self.operationStarted.emit("Deleting governed document...")
        worker = FunctionWorker(
            self.jobs.delete_document,
            document_id,
            reviewer_role=reviewer_role,
            task_name="Governed Document Deletion",
            max_retries=0,
        )
        worker.signals.finished.connect(self._on_delete_finished)
        worker.signals.error.connect(self._on_delete_error)
        self.thread_pool.start(worker)

    @Slot(object)
    def _on_delete_finished(self, raw_result: Any) -> None:
        self._is_operation_active = False
        result = unwrap_worker_result(raw_result, default_task_name="Governed Document Deletion")
        if not result.success:
            self._on_delete_error({"error_message": result.error_message or "Document deletion failed."})
            return
        receipt = result.result
        payload = receipt.to_dict() if hasattr(receipt, "to_dict") else dict(receipt or {})
        document_id = int(payload.get("document_id", 0))
        self.documents = [item for item in self.documents if item.document_id != document_id]
        self.documentDeletionFinished.emit(payload)
        self.statusMessage.emit("Document deleted under governance controls.", "INFO")
        self.operationFinished.emit("Governed document deletion completed.")

    @Slot(dict)
    def _on_delete_error(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        self.documentDeletionFailed.emit(error_context)
        self.statusMessage.emit(str(error_context.get("error_message") or "Document deletion failed."), "ERROR")
        self.operationFinished.emit("Governed document deletion failed.")

    def document_by_id(self, document_id: int) -> LibraryDocument | None:
        return next((doc for doc in self.documents if doc.document_id == document_id), None)

    def cleanup_before_close(self) -> None:
        self.documents = []
        self.statusMessage.emit("Library cleared before close.", "INFO")