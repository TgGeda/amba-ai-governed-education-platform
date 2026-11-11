from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from amba_ai.services.governance_review_service import GovernanceReviewService
from amba_ai.ui.workers import FunctionWorker, unwrap_worker_result
from .data_classes import (
    ReviewActionRequest,
    ReviewDecisionHistoryItem,
    ReviewItemViewModel,
)


class GovernanceReviewManager(QObject):
    itemsLoaded = Signal(list)
    reviewStarted = Signal(str)
    reviewCompleted = Signal(dict)
    reviewFailed = Signal(dict)
    statusMessage = Signal(str, str)
    operationStarted = Signal(str)
    operationFinished = Signal(str)

    def __init__(
        self,
        *,
        review_service: GovernanceReviewService,
        services: Any,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.review_service = review_service
        self.services = services
        self.thread_pool = QThreadPool.globalInstance()
        self._is_operation_active = False

    @Slot(int)
    def load_document_chunks(self, document_id: int) -> None:
        if self._is_operation_active:
            self.statusMessage.emit("A review operation is in progress.", "WARNING")
            return
        doc_id = int(document_id)
        if doc_id <= 0:
            self.itemsLoaded.emit([])
            return
        self._is_operation_active = True
        self.operationStarted.emit(
            "Loading document chunks and governance history..."
        )
        worker = FunctionWorker(
            self._load_chunks_task,
            doc_id,
            task_name="Load Chunks For Review",
            max_retries=0,
        )
        worker.signals.finished.connect(self._on_load_finished)
        worker.signals.error.connect(self._on_load_error)
        self.thread_pool.start(worker)

    def _load_chunks_task(self, document_id: int) -> list[ReviewItemViewModel]:
        db = self.services.database
        runtime_repo = self.services.runtime_governance.repository
        doc_row = db.get_document(document_id)
        if doc_row is None:
            raise LookupError(f"Document {document_id} does not exist.")
        doc_dict = dict(doc_row)
        doc_title = str(doc_dict.get("title") or f"Document #{document_id}")
        doc_gov = runtime_repo.get_document(document_id)
        if not doc_gov:
            raise LookupError("Document governance record is unavailable.")
        source_digest = str(doc_gov.get("source_sha256") or "unknown")
        restricted_ops = tuple(
            str(value)
            for value in (
                doc_gov.get("restricted_operations")
                or doc_gov.get("restricted")
                or ()
            )
        )
        chunk_rows = list(db.get_chunks(document_id))
        chunk_decisions = {
            int(decision["chunk_id"]): decision
            for decision in runtime_repo.get_chunk_decisions(document_id)
        }
        view_models: list[ReviewItemViewModel] = []
        for row in chunk_rows:
            chunk = dict(row)
            chunk_id = int(chunk.get("id") or chunk.get("chunk_id") or 0)
            decision = chunk_decisions.get(chunk_id, {})
            reviews = runtime_repo.list_reviews("chunk", str(chunk_id))
            history = tuple(
                ReviewDecisionHistoryItem(
                    review_id=review.review_id,
                    disposition=review.disposition.value,
                    reviewer_role=review.reviewer_role,
                    rationale=review.rationale,
                    redactions=tuple(review.redactions),
                    supersedes_review_id=review.supersedes_review_id,
                    decided_at=review.decided_at,
                    receipt_id=review.receipt_id,
                    published_at=review.published_at,
                    effective_text=review.effective_text,
                )
                for review in reviews
            )
            effective = runtime_repo.effective_review("chunk", str(chunk_id))
            # Findings are classifications, not exact text spans. Exact redactions
            # must be supplied by the reviewer or a future structured span detector.
            view_models.append(
                ReviewItemViewModel(
                    document_id=document_id,
                    document_title=doc_title,
                    chunk_id=chunk_id,
                    chunk_text=str(chunk.get("text") or ""),
                    source_digest=source_digest,
                    risk_findings=tuple(
                        str(value) for value in decision.get("findings") or ()
                    ),
                    current_status=str(
                        decision.get("review_status")
                        or decision.get("decision")
                        or "pending"
                    ),
                    permitted_operations=tuple(
                        str(value)
                        for value in decision.get("operations_permitted") or ()
                    ),
                    restricted_operations=restricted_ops,
                    proposed_redactions=(),
                    previous_reviews=history,
                    effective_review_id=(effective.review_id if effective else None),
                    effective_text=(effective.effective_text if effective else None),
                )
            )
        return view_models

    @Slot(object)
    def _on_load_finished(self, raw_result: Any) -> None:
        self._is_operation_active = False
        result = unwrap_worker_result(
            raw_result, default_task_name="Load Chunks For Review"
        )
        if not result.success:
            self._emit_failure(result.error_message or "Failed to load chunks.")
            return
        payload = [item.to_dict() for item in (result.result or [])]
        self.itemsLoaded.emit(payload)
        self.statusMessage.emit(
            f"Loaded {len(payload)} chunks for governance review.", "INFO"
        )
        self.operationFinished.emit("Chunks loaded.")

    @Slot(dict)
    def _on_load_error(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        message = str(
            error_context.get("error_message") or "Failed to load chunks."
        )
        self.reviewFailed.emit(dict(error_context))
        self.statusMessage.emit(message, "ERROR")
        self.operationFinished.emit("Failed to load chunks.")

    @Slot(dict)
    def submit_review(self, request_payload: dict[str, Any]) -> None:
        if self._is_operation_active:
            self.statusMessage.emit(
                "Another review decision is currently processing.", "WARNING"
            )
            return
        try:
            request = ReviewActionRequest.from_dict(request_payload)
        except Exception as exc:
            self._emit_failure(f"Invalid review request: {exc}")
            return
        self._is_operation_active = True
        self.reviewStarted.emit(request.subject_id)
        self.operationStarted.emit(
            f"Submitting {request.disposition} for chunk {request.subject_id}..."
        )
        worker = FunctionWorker(
            self._submit_review_task,
            request,
            task_name="Submit Governance Review",
            max_retries=0,
        )
        worker.signals.finished.connect(self._on_submit_finished)
        worker.signals.error.connect(self._on_submit_error)
        self.thread_pool.start(worker)

    def _submit_review_task(self, request: ReviewActionRequest) -> dict[str, Any]:
        decision = self.review_service.decide(
            subject_type="chunk",
            subject_id=request.subject_id,
            document_id=request.document_id,
            disposition=request.disposition,
            reviewer_role=request.reviewer_role,
            rationale=request.rationale,
            redactions=request.redactions,
            supersedes_review_id=request.supersedes_review_id,
            operation=request.operation,
        )
        return {
            "review_id": decision.review_id,
            "subject_id": decision.subject_id,
            "document_id": decision.document_id,
            "disposition": decision.disposition.value,
            "reviewer_role": decision.reviewer_role,
            "rationale": decision.rationale,
            "redactions": list(decision.redactions),
            "supersedes_review_id": decision.supersedes_review_id,
            "decided_at": decision.decided_at,
            "receipt_id": decision.receipt_id,
            "published_at": decision.published_at,
            "effective_text": decision.effective_text,
        }

    @Slot(object)
    def _on_submit_finished(self, raw_result: Any) -> None:
        self._is_operation_active = False
        result = unwrap_worker_result(
            raw_result, default_task_name="Submit Governance Review"
        )
        if not result.success:
            self._emit_failure(result.error_message or "Review submission failed.")
            return
        data = dict(result.result or {})
        self.reviewCompleted.emit(data)
        self.statusMessage.emit(
            f"Review decision published: {data.get('receipt_id')}", "INFO"
        )
        self.operationFinished.emit("Review decision published.")

    @Slot(dict)
    def _on_submit_error(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        message = str(
            error_context.get("error_message") or "Review submission failed."
        )
        self.reviewFailed.emit(dict(error_context))
        self.statusMessage.emit(message, "ERROR")
        self.operationFinished.emit("Review submission failed.")

    def _emit_failure(self, message: str) -> None:
        payload = {"error_message": str(message)}
        self.reviewFailed.emit(payload)
        self.statusMessage.emit(str(message), "ERROR")
        self.operationFinished.emit("Review operation failed.")

    def cleanup_before_close(self) -> None:
        pass
