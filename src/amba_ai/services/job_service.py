from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Iterator

from amba_ai.compute.edge_slm import OllamaClient
from amba_ai.config import (
    OLLAMA_SUMMARY_MODEL,
    WHISPER_MODEL,
    get_model_for_task,
)
from amba_ai.core.context_tracker import ContextTracker
from amba_ai.core.ingest import ingest_path
from amba_ai.core.memory_manager import VectorInfiniteMemory
from amba_ai.core.pedagogy import PedagogicalFormatter
from amba_ai.core.preprocessing import chunk_text
from amba_ai.core.study_tools import generate_flashcards, generate_mcqs
from amba_ai.core.summarizer import summarize_document_text
from amba_ai.db.database import Database
from amba_ai.exceptions import (
    DatabaseError,
    IngestionError,
    JobServiceError,
    ModelUnavailableError,
    RAGError,
)
from amba_ai.logger import logger
from amba_ai.models.schemas import (
    AnswerResult,
    Flashcard,
    IngestedDocument,
    IngestedDocumentResult,
    MCQ,
    StudyAssetsResult,
    SummaryResult,
    TextChunk,
)
from amba_ai.rag.engine import FaissRAGEngine
from amba_ai.rag.index_policy import IndexRebuildPolicy, IndexRebuildResult
from amba_ai.governance.learning_operations import runtime_learning_operation
from amba_ai.governance.models import EnforcementAction
from amba_ai.services.content_delivery_service import ContentDeliveryService
from amba_ai.services.model_service import ModelService
from amba_ai.services.governed_ingestion_service import GovernedIngestionService
from amba_ai.services.governed_retrieval_service import GovernedRetrievalService
from amba_ai.services.grounded_answer_service import GroundedAnswerService
from amba_ai.services.governed_result_delivery import GovernedResultDeliveryService
from amba_ai.services.document_lifecycle_service import DocumentLifecycleService, DocumentDeletionReceipt
from amba_ai.governance.runtime import RuntimeEducationGovernanceService, RuntimeGovernanceGateError, RuntimeGovernanceReviewRequired
from amba_ai.services.job_governance import (
    JobGovernanceContext,
    JobGovernanceCoordinator,
    JobGovernanceDeliveryError,
    JobGovernanceGateError,
)


class JobService:
    DEFAULT_SESSION_ID = "default"

    def __init__(
        self,
        db: Database | None = None,
        rag_engine: FaissRAGEngine | None = None,
        rag_pipeline_factory: Callable[..., Any] | None = None,
        memory_manager: VectorInfiniteMemory | None = None,
        context_tracker: ContextTracker | None = None,
        llm_client: OllamaClient | None = None,
        model_service: ModelService | None = None,
        content_delivery_service: ContentDeliveryService | None = None,
        governance_coordinator: JobGovernanceCoordinator | None = None,
        runtime_governance: RuntimeEducationGovernanceService | None = None,
        governed_ingestion_service: GovernedIngestionService | None = None,
        governed_retrieval_service: GovernedRetrievalService | None = None,
        grounded_answer_service: GroundedAnswerService | None = None,
        governed_result_delivery: GovernedResultDeliveryService | None = None,
        document_lifecycle_service: DocumentLifecycleService | None = None,
    ) -> None:
        self.db = db or Database()
        database_path = getattr(self.db, "path", None)
        self.runtime_governance = runtime_governance
        if self.runtime_governance is None and database_path is not None:
            self.runtime_governance = RuntimeEducationGovernanceService(database_path)
        self._rag_engine = rag_engine
        self._rag_pipeline_factory = rag_pipeline_factory
        self.memory = memory_manager or VectorInfiniteMemory()
        self.context_tracker = context_tracker or ContextTracker()
        self.model_service = model_service or ModelService.get_instance()
        self.llm = llm_client or self.model_service.get_client_for_task("tutor_chat")
        self.pedagogy = PedagogicalFormatter()
        self.content_delivery = content_delivery_service or ContentDeliveryService()
        if governance_coordinator is not None and not isinstance(
            governance_coordinator, JobGovernanceCoordinator
        ):
            raise TypeError(
                "governance_coordinator must be a JobGovernanceCoordinator or None"
            )
        self.governance_coordinator = governance_coordinator
        self.governed_ingestion = governed_ingestion_service
        self.governed_retrieval = governed_retrieval_service
        self.grounded_answer = grounded_answer_service
        self.result_delivery = governed_result_delivery
        self.document_lifecycle = document_lifecycle_service

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _context(
        self,
        *,
        operation: str,
        document_id: int | None = None,
        path: str | Path | None = None,
        model_name: str | None = None,
        question: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "operation": operation,
            "timestamp": self._now_iso(),
        }

        if document_id is not None:
            context["document_id"] = document_id

        if path is not None:
            context["path"] = str(path)

        if model_name is not None:
            context["model_name"] = model_name

        if question is not None:
            context["question_length"] = len(question)

        context.update(extra)
        return context

    @property
    def rag(self) -> FaissRAGEngine:
        if self._rag_engine is None:
            provider = (
                lambda: self._build_index_rebuild_policy("tutor_answer")
                if self.runtime_governance is not None
                else None
            )
            self._rag_engine = FaissRAGEngine(
                self.db,
                rebuild_policy_provider=provider,
            )
        return self._rag_engine

    def _get_rag_pipeline(self, document_id: int | None = None) -> Any | None:
        if self._rag_pipeline_factory is not None:
            return self._rag_pipeline_factory(
                db=self.db,
                rag_engine=self.rag,
                llm=self.llm,
                document_id=document_id,
                runtime_governance=self.runtime_governance,
                operation="learning.tutor.retrieve",
            )

        try:
            from amba_ai.rag.ambaai_integration import build_production_rag_pipeline
            return build_production_rag_pipeline(
                db=self.db,
                rag_engine=self.rag,
                llm=self.llm,
                document_id=document_id,
                runtime_governance=self.runtime_governance,
                operation="learning.tutor.retrieve",
            )
        except (ImportError, AttributeError):
            return None

    @contextmanager
    def _db_connect(
        self,
        *,
        operation: str,
        context: dict[str, Any],
    ) -> Iterator[sqlite3.Connection]:
        try:
            with self.db.connect(operation=operation, context=context) as conn:
                yield conn
        except TypeError:
            with self.db.connect() as conn:
                yield conn

    def _get_document_or_raise(self, document_id: int) -> IngestedDocument:
        context = self._context(
            operation="get_document_or_raise",
            document_id=document_id,
        )

        if not isinstance(document_id, int) or document_id <= 0:
            raise ValueError(f"Invalid document_id: {document_id}")

        try:
            if hasattr(self.db, "get_document_typed"):
                doc = self.db.get_document_typed(document_id)
            else:
                row = self.db.get_document(document_id)
                doc = None

                if row is not None:
                    data = dict(row)
                    metadata = self._decode_metadata(data)

                    doc = IngestedDocument(
                        title=str(data["title"]),
                        source_path=str(data["source_path"]),
                        kind=str(data["kind"]),
                        raw_text=str(data["raw_text"]),
                        metadata=metadata,
                    )

            if doc is None:
                raise JobServiceError(
                    "Document not found.",
                    context={
                        **context,
                        "error_type": "document_not_found",
                    },
                )

            return doc

        except JobServiceError:
            raise

        except Exception as exc:
            logger.exception("Failed to load document", extra={"context": context})
            raise JobServiceError("Failed to load document.", context=context) from exc

    @staticmethod
    def _decode_metadata(data: dict[str, Any]) -> dict[str, Any]:
        raw_metadata = (
            data.get("metadata")
            or data.get("metadata_json")
            or data.get("metadata_dict")
            or {}
        )

        if isinstance(raw_metadata, dict):
            return raw_metadata

        if isinstance(raw_metadata, str):
            try:
                parsed = json.loads(raw_metadata)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}

        return {}

    def _insert_document(self, doc: IngestedDocument) -> int:
        try:
            return self.db.insert_document(doc)
        except TypeError:
            return self.db.insert_document(
                title=doc.title,
                source_path=doc.source_path,
                kind=doc.kind,
                raw_text=doc.raw_text,
                metadata=doc.metadata,
            )

    def _insert_chunks(
        self,
        *,
        document_id: int,
        chunks: list[TextChunk],
    ) -> None:
        try:
            self.db.insert_chunks(chunks)
        except TypeError:
            raw_chunks = [
                {
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "source_ref": chunk.source_ref,
                }
                for chunk in chunks
            ]
            self.db.insert_chunks(document_id, raw_chunks)

    def _get_existing_flashcards(self, document_id: int) -> list[Flashcard]:
        if hasattr(self.db, "get_flashcards_typed"):
            return list(self.db.get_flashcards_typed(document_id))

        if hasattr(self.db, "get_flashcards"):
            rows = self.db.get_flashcards(document_id)
            return [
                Flashcard(
                    question=str(row["question"]),
                    answer=str(row["answer"]),
                    source_ref=row["source_ref"],
                )
                for row in rows
            ]

        return []

    def _get_existing_mcqs(self, document_id: int) -> list[MCQ]:
        if hasattr(self.db, "get_mcqs_typed"):
            return list(self.db.get_mcqs_typed(document_id))

        if hasattr(self.db, "get_mcqs_dicts"):
            items = self.db.get_mcqs_dicts(document_id)
            return [
                MCQ(
                    question=str(item["question"]),
                    choices=[str(choice) for choice in item["choices"]],
                    correct_answer=str(item["correct_answer"]),
                    explanation=str(item["explanation"]),
                    source_ref=item.get("source_ref"),
                )
                for item in items
            ]

        return []

    def _delete_existing_study_assets(self, document_id: int) -> None:
        context = self._context(
            operation="delete_existing_study_assets",
            document_id=document_id,
        )

        try:
            with self._db_connect(
                operation="delete_existing_study_assets",
                context=context,
            ) as conn:
                conn.execute("DELETE FROM flashcards WHERE document_id = ?", (document_id,))
                conn.execute("DELETE FROM mcqs WHERE document_id = ?", (document_id,))

            logger.info("Deleted existing study assets", extra={"context": context})

        except Exception as exc:
            logger.exception("Failed to delete existing study assets", extra={"context": context})
            raise JobServiceError(
                "Failed to delete existing study assets.",
                context=context,
            ) from exc

    def _delete_existing_summaries(self, document_id: int) -> None:
        context = self._context(
            operation="delete_existing_summaries",
            document_id=document_id,
        )

        try:
            with self._db_connect(
                operation="delete_existing_summaries",
                context=context,
            ) as conn:
                conn.execute("DELETE FROM summaries WHERE document_id = ?", (document_id,))

            logger.info("Deleted existing summaries", extra={"context": context})

        except Exception as exc:
            logger.exception("Failed to delete existing summaries", extra={"context": context})
            raise JobServiceError(
                "Failed to delete existing summaries.",
                context=context,
            ) from exc

    @staticmethod
    def _plain_excerpt(text: str, *, limit: int = 3000) -> str:
        clean = " ".join((text or "").split())
        if not clean:
            return "No readable text was extracted."
        return clean[:limit].strip()

    @staticmethod
    def _split_sentences(text: str, *, limit: int = 8) -> list[str]:
        clean = " ".join((text or "").split())
        if not clean:
            return []

        parts = re.split(r"(?<=[.!?])\s+", clean)
        sentences = [part.strip() for part in parts if len(part.strip()) > 30]
        return sentences[:limit]

    def _fallback_summary(
        self,
        *,
        document_id: int,
        doc: IngestedDocument,
        reason: str,
    ) -> SummaryResult:
        sentences = self._split_sentences(doc.raw_text, limit=6)

        bullet_text = "\n".join(
            f"- {sentence}" for sentence in sentences
        ) or "- Review the uploaded material and identify the main concepts."

        markdown = (
            f"# {doc.title}\n\n"
            "## Executive Summary\n\n"
            "AmbaAI created these offline study notes from the uploaded learning material.\n\n"
            "## Core Concepts\n\n"
            f"{bullet_text}\n\n"
            "## Structured Study Notes\n\n"
            "- Review the key points carefully.\n"
            "- Ask AmbaAI focused questions about unclear concepts.\n"
            "- Generate flashcards and quizzes for exam practice.\n\n"
            f"## Sources\n- {doc.title}, local document ID {document_id}"
        )

        return SummaryResult(
            markdown_notes=markdown,
            model_name="fallback-extractive",
            tokens_used=None,
            metadata={
                "document_id": document_id,
                "source_document_ids": [document_id],
                "citations": [
                    {
                        "source_id": f"local-document:{document_id}",
                        "locator": f"document:{document_id}",
                    }
                ],
                "fallback": True,
                "fallback_reason": reason,
                "text_length": len(doc.raw_text or ""),
                "created_at": self._now_iso(),
            },
        )

    def _fallback_study_assets(
        self,
        *,
        document_id: int,
        doc: IngestedDocument,
        flashcard_count: int,
        mcq_count: int,
        reason: str,
    ) -> StudyAssetsResult:
        sentences = self._split_sentences(doc.raw_text, limit=max(flashcard_count, mcq_count, 10))

        if not sentences:
            sentences = [
                "The uploaded document should be reviewed by the learner and teacher.",
                "AmbaAI can create offline learning activities from local curriculum materials.",
            ]

        flashcards: list[Flashcard] = []
        for index, sentence in enumerate(sentences[:flashcard_count], start=1):
            flashcards.append(
                Flashcard(
                    question=f"What is the key idea in point {index}?",
                    answer=sentence,
                    source_ref=doc.title,
                )
            )

        mcqs: list[MCQ] = []
        for index, sentence in enumerate(sentences[:mcq_count], start=1):
            mcqs.append(
                MCQ(
                    question=f"Which statement best matches key point {index} from the uploaded material?",
                    choices=[
                        sentence,
                        "This point is unrelated to the uploaded material.",
                        "The uploaded material does not contain educational content.",
                        "This statement contradicts the source material.",
                    ],
                    correct_answer=sentence,
                    explanation="This option is based directly on the uploaded source text.",
                    source_ref=doc.title,
                )
            )

        return StudyAssetsResult(
            flashcards=flashcards,
            mcqs=mcqs,
            metadata={
                "document_id": document_id,
                "cached": False,
                "fallback": True,
                "fallback_reason": reason,
                "flashcard_count": len(flashcards),
                "mcq_count": len(mcqs),
                "created_at": self._now_iso(),
                "model_name": "fallback-extractive",
            },
        )

    def _fallback_answer(
        self,
        *,
        question: str,
        document_id: int | None,
        retrieved_hits: list[Any],
        reason: str,
        model_name: str,
    ) -> AnswerResult:
        source_text = self._format_rag_hits(retrieved_hits)

        if source_text:
            answer_text = (
                "AmbaAI could not use the local language model, so it is showing "
                "the most relevant retrieved study material instead.\n\n"
                f"Question: {question}\n\n"
                "Relevant uploaded material:\n\n"
                f"{source_text[:2500]}"
            )
        else:
            answer_text = (
                "AmbaAI could not use the local language model, and no relevant "
                "uploaded study material was retrieved for this question."
            )

        return self._make_answer_result(
            answer_text=answer_text,
            raw_answer=answer_text,
            model_name=f"{model_name}-fallback",
            sources=self._sources_from_hits(retrieved_hits),
            metadata={
                "document_id": document_id,
                "fallback": True,
                "fallback_reason": reason,
                "hits_count": len(retrieved_hits),
                "created_at": self._now_iso(),
            },
        )

    def ingest_file(self, path: str | Path) -> IngestedDocumentResult:
        if self.governed_ingestion is None:
            raise IngestionError(
                "Governed ingestion service is not configured.",
                context=self._context(operation="ingest_file", path=path),
            )
        return self.governed_ingestion.ingest(path)

    def _begin_job_governance(
        self,
        *,
        method_name: str,
        input_metadata: dict[str, Any],
        governance_context: JobGovernanceContext | None,
    ) -> Any | None:
        document_id = input_metadata.get("document_id")
        if document_id is not None and self.runtime_governance is not None:
            doc = self._get_document_or_raise(int(document_id))
            source_path = str(doc.get("source_path") or "") if isinstance(doc, dict) else str(getattr(doc, "source_path", ""))
            self.runtime_governance.authorize_generation(int(document_id), method_name, source_path or None)
        if self.governance_coordinator is None:
            return None
        return self.governance_coordinator.begin(
            method_name=method_name,
            input_metadata=input_metadata,
            context=governance_context,
        )

    def _complete_job_governance(
        self,
        *,
        invocation: Any | None,
        result_material: dict[str, Any],
        result_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        document_id = result_metadata.get("document_id")
        operation = getattr(invocation, "method_name", None) if invocation is not None else str(result_metadata.get("operation") or "runtime_output")
        governed_material = dict(result_material)
        if document_id is not None and self.runtime_governance is not None:
            validation = self.runtime_governance.validate_output(
                int(document_id),
                str(operation),
                governed_material,
                source_digest_verified=True,
                retrieved_chunk_ids=tuple(result_metadata.get("retrieved_chunk_ids") or ()),
                excluded_chunk_ids=tuple(result_metadata.get("excluded_chunk_ids") or ()),
            )
            governed_material = dict(validation.sanitized_material)
            result_metadata["runtime_output_governance"] = validation.evidence()
            if self.result_delivery is None:
                raise JobServiceError("Governed result delivery is not configured.")
            envelope = self.result_delivery.envelope_from_validation(
                validation,
                operation_id=str(getattr(invocation, "operation_id", operation)),
            )
            governed_metadata = dict(governed_material.get("metadata") or {})
            governed_metadata["governed_result_envelope"] = envelope.to_dict()
            governed_material["metadata"] = governed_metadata
        if invocation is None:
            return governed_material

        completion = self.governance_coordinator.complete(
            invocation=invocation,
            result_material=governed_material,
            result_metadata=result_metadata,
        )

        post_evaluation = getattr(completion, "post_evaluation", None)
        execution_result = getattr(completion, "execution_result", None)

        if post_evaluation is None or execution_result is None:
            require_acknowledgment = getattr(
                completion,
                "require_delivery_acknowledged",
                None,
            )
            if not callable(require_acknowledgment):
                raise JobServiceError(
                    "Governance completion does not provide a post-gate "
                    "evaluation or delivery acknowledgment invariant."
                )
            require_acknowledgment()
            return governed_material

        recommendation = post_evaluation.recommendation
        recommended_action = recommendation.recommended_action
        findings = tuple(getattr(post_evaluation, "findings", ()))

        review_receipt = execution_result.review_queue_receipt
        execution_receipt = execution_result.execution_receipt

        review_receipt_id = (
            getattr(review_receipt, "receipt_id", str(review_receipt))
            if review_receipt is not None
            else None
        )

        logger.info(
            "Job governance delivery disposition",
            extra={
                "context": {
                    "method_name": completion.invocation.method_name,
                    "operation_id": completion.invocation.operation_id,
                    "event_id": completion.post_event.event_id,
                    "recommended_action": recommended_action.value,
                    "delivery_acknowledged": completion.delivery_acknowledged,
                    "queued_for_review": completion.queued_for_review,
                    "execution_recorded": completion.execution_recorded,
                    "execution_action": (
                        execution_receipt.action_executed.value
                        if execution_receipt is not None
                        else None
                    ),
                    "execution_status": (
                        execution_receipt.status.value
                        if execution_receipt is not None
                        else None
                    ),
                    "finding_codes": [
                        getattr(
                            finding,
                            "code",
                            getattr(finding, "finding_id", "UNKNOWN"),
                        )
                        for finding in findings
                    ],
                    "review_queue_receipt_id": review_receipt_id,
                    "has_distribution_acknowledgment": (
                        completion.execution_result.distribution_acknowledgment
                        is not None
                    ),
                }
            },
        )

        if recommended_action is not EnforcementAction.PROCEED:
            raise JobGovernanceGateError(
                method_name=completion.invocation.method_name,
                operation_id=completion.invocation.operation_id,
                event_id=completion.post_event.event_id,
                action=recommended_action,
                recommendation_id=getattr(recommendation, "recommendation_id", None),
                findings=findings,
                review_queue_receipt=review_receipt_id,
            )

        completion.require_delivery_acknowledged()
        return governed_material

    def require_governed_result(self, result: Any) -> Any:
        if self.result_delivery is None:
            raise JobServiceError("Governed result delivery is not configured.")
        metadata = dict(getattr(result, "metadata", {}) or {})
        envelope_data = metadata.get("governed_result_envelope")
        if not isinstance(envelope_data, dict):
            raise JobServiceError("Result has no governed delivery envelope.")
        envelope = self.result_delivery.envelope_from_dict(envelope_data)
        self.result_delivery.verify(envelope)
        return result

    @staticmethod
    def _summary_from_material(original: SummaryResult, material: Mapping[str, Any]) -> SummaryResult:
        governed_metadata = dict(material.get("metadata") or {})
        original_metadata = dict(original.metadata or {})
        merged_metadata = {**original_metadata, **governed_metadata}
        return SummaryResult(
            markdown_notes=str(material.get("markdown_notes", original.markdown_notes)),
            model_name=str(material.get("model_name", original.model_name)),
            tokens_used=material.get("tokens_used", original.tokens_used),
            metadata=merged_metadata,
        )

    @staticmethod
    def _answer_from_material(original: AnswerResult, material: Mapping[str, Any]) -> AnswerResult:
        governed_metadata = dict(material.get("metadata") or {})
        original_metadata = dict(original.metadata or {})
        merged_metadata = {**original_metadata, **governed_metadata}
        return AnswerResult(
            answer_text=str(material.get("answer_text", original.answer_text)),
            sources=list(material.get("sources", original.sources)),
            model_name=str(material.get("model_name", original.model_name)),
            metadata=merged_metadata,
        )

    @staticmethod
    def _assets_from_material(original: StudyAssetsResult, material: Mapping[str, Any]) -> StudyAssetsResult:
        cards = [Flashcard(**item) if isinstance(item, dict) else item for item in material.get("flashcards", [])]
        mcqs = [MCQ(**item) if isinstance(item, dict) else item for item in material.get("mcqs", [])]
        governed_metadata = dict(material.get("metadata") or {})
        original_metadata = dict(original.metadata or {})
        merged_metadata = {**original_metadata, **governed_metadata}
        return StudyAssetsResult(flashcards=cards, mcqs=mcqs, metadata=merged_metadata)

    @staticmethod
    def _answer_material(answer: AnswerResult) -> dict[str, Any]:
        return {
            "answer_text": answer.answer_text,
            "sources": list(answer.sources),
            "model_name": answer.model_name,
            "metadata": dict(answer.metadata),
        }

    @staticmethod
    def _summary_material(summary: SummaryResult) -> dict[str, Any]:
        return {
            "markdown_notes": summary.markdown_notes,
            "model_name": summary.model_name,
            "tokens_used": summary.tokens_used,
            "metadata": dict(summary.metadata),
        }

    @staticmethod
    def _assets_material(result: StudyAssetsResult) -> dict[str, Any]:
        return {
            "flashcards": [asdict(card) for card in result.flashcards],
            "mcqs": [asdict(item) for item in result.mcqs],
            "metadata": dict(result.metadata),
        }

    def generate_notes(
        self,
        document_id: int,
        *,
        force: bool = False,
        model_name: str | None = None,
        governance_context: JobGovernanceContext | None = None,
    ) -> SummaryResult:
        resolved_model = model_name or get_model_for_task("summary")
        context = self._context(
            operation="generate_notes",
            document_id=document_id,
            model_name=resolved_model,
        )
        invocation = self._begin_job_governance(
            method_name="generate_notes",
            input_metadata={"document_id": document_id, "force": force},
            governance_context=governance_context,
        )
        try:
            doc = self._get_document_or_raise(document_id)
            if not force:
                cached = self.db.latest_summary(document_id)
                if cached is not None:
                    data = dict(cached)
                    result = SummaryResult(
                        markdown_notes=str(data["summary_markdown"]),
                        model_name=str(data["model_name"]),
                        tokens_used=None,
                        metadata={
                            "document_id": document_id,
                            "source_document_ids": [document_id],
                            "citations": [
                                {
                                    "source_id": f"local-document:{document_id}",
                                    "locator": f"document:{document_id}",
                                }
                            ],
                            "cached": True,
                            "summary_id": data.get("id"),
                            "created_at": data.get("created_at"),
                            "text_length": len(doc.raw_text or ""),
                        },
                    )
                    governed_material = self._complete_job_governance(
                        invocation=invocation,
                        result_material=self._summary_material(result),
                        result_metadata={
                            "output_type": "summary_result",
                            "markdown_length": len(result.markdown_notes),
                            "model_name": result.model_name,
                            "tokens_used": result.tokens_used,
                            "document_id": document_id,
                            "citations": list(result.metadata.get("citations", ())),
                            "source_document_ids": [document_id],
                        },
                    )
                    candidate = self._summary_from_material(result, governed_material)
                    envelope = candidate.metadata.get("governed_result_envelope")
                    if not isinstance(envelope, dict):
                        raise JobGovernanceDeliveryError(
                            method_name="generate_notes",
                            operation_id="learning.notes.generate",
                            event_id=getattr(invocation.event, "event_id", "cached"),
                            queued_for_review=False,
                            reason="Governed result envelope was lost during SummaryResult reconstruction.",
                        )
                    return candidate
            try:
                summary = self.content_delivery.generate_study_notes(
                    raw_text=doc.raw_text,
                    title=doc.title,
                    document_id=document_id,
                    source_name=doc.title,
                )
            except Exception as service_exc:
                logger.warning(
                    "ContentDeliveryService note generation failed; using deterministic fallback",
                    extra={"context": {**context, "cause_type": type(service_exc).__name__, "cause_message": str(service_exc)}},
                    exc_info=True,
                )
                summary = self._fallback_summary(
                    document_id=document_id,
                    doc=doc,
                    reason=f"{type(service_exc).__name__}: {service_exc}",
                )
            candidate = SummaryResult(
                markdown_notes=summary.markdown_notes,
                model_name=summary.model_name,
                tokens_used=summary.tokens_used,
                metadata={
                    **(summary.metadata or {}),
                    "document_id": document_id,
                    "source_document_ids": [document_id],
                    "citations": list(
                        summary.metadata.get("citations")
                        or [
                            {
                                "source_id": f"local-document:{document_id}",
                                "locator": f"document:{document_id}",
                            }
                        ]
                    ),
                    "cached": False,
                    "created_at": self._now_iso(),
                },
            )
            governed_material = self._complete_job_governance(
                invocation=invocation,
                result_material=self._summary_material(candidate),
                result_metadata={
                    "output_type": "summary_result",
                    "markdown_length": len(candidate.markdown_notes),
                    "model_name": candidate.model_name,
                    "tokens_used": candidate.tokens_used,
                    "document_id": document_id,
                    "citations": list(candidate.metadata.get("citations", ())),
                    "source_document_ids": [document_id],
                    "fallback": bool(candidate.metadata.get("fallback", False)),
                },
            )
            candidate = self._summary_from_material(candidate, governed_material)
            envelope_data = candidate.metadata.get("governed_result_envelope")
            if not isinstance(envelope_data, dict):
                raise JobGovernanceDeliveryError(
                    method_name="generate_notes",
                    operation_id="learning.notes.generate",
                    event_id=getattr(invocation.event, "event_id", "generate_notes"),
                    queued_for_review=False,
                    reason="Governed result envelope was lost during SummaryResult reconstruction.",
                )
            if force:
                self._delete_existing_summaries(document_id)
            envelope = self.result_delivery.envelope_from_result(candidate)
            summary_id = self.result_delivery.deliver(
                envelope, "notes_persistence", db=self.db
            ).value
            result = SummaryResult(
                markdown_notes=candidate.markdown_notes,
                model_name=candidate.model_name,
                tokens_used=candidate.tokens_used,
                metadata={**candidate.metadata, "summary_id": summary_id},
            )
            logger.info("Notes generation completed", extra={"context": context})
            return result
        except (JobGovernanceGateError, JobGovernanceDeliveryError):
            raise
        except Exception as exc:
            failure_context = {
                **context,
                "cause_type": type(exc).__name__,
                "cause_message": str(exc),
                "failure_stage": "notes_governed_delivery",
            }
            logger.exception("Notes generation failed", extra={"context": failure_context})
            raise JobServiceError(f"Notes generation failed: {type(exc).__name__}: {exc}", context=failure_context) from exc

    def summarize_document(
        self,
        document_id: int,
        *,
        force: bool = False,
        model_name: str | None = None,
        governance_context: JobGovernanceContext | None = None,
    ) -> SummaryResult:
        resolved_model = model_name or get_model_for_task("summary")
        context = self._context(
            operation="summarize_document",
            document_id=document_id,
            model_name=resolved_model,
        )
        invocation = self._begin_job_governance(
            method_name="summarize_document",
            input_metadata={"document_id": document_id, "force": force},
            governance_context=governance_context,
        )
        try:
            doc = self._get_document_or_raise(document_id)
            if not force:
                cached = self.db.latest_summary(document_id)
                if cached is not None:
                    data = dict(cached)
                    result = SummaryResult(
                        markdown_notes=str(data["summary_markdown"]),
                        model_name=str(data["model_name"]),
                        tokens_used=None,
                        metadata={
                            "document_id": document_id,
                            "source_document_ids": [document_id],
                            "citations": [
                                {
                                    "source_id": f"local-document:{document_id}",
                                    "locator": f"document:{document_id}",
                                }
                            ],
                            "cached": True,
                            "summary_id": data.get("id"),
                            "created_at": data.get("created_at"),
                            "text_length": len(doc.raw_text or ""),
                        },
                    )
                    governed_material = self._complete_job_governance(
                        invocation=invocation,
                        result_material=self._summary_material(result),
                        result_metadata={
                            "output_type": "summary_result",
                            "markdown_length": len(result.markdown_notes),
                            "model_name": result.model_name,
                            "tokens_used": result.tokens_used,
                            "document_id": document_id,
                            "citations": list(result.metadata.get("citations", ())),
                            "source_document_ids": [document_id],
                        },
                    )
                    candidate = self._summary_from_material(result, governed_material)
                    envelope = candidate.metadata.get("governed_result_envelope")
                    if not isinstance(envelope, dict):
                        raise JobGovernanceDeliveryError(
                            method_name="summarize_document",
                            operation_id="learning.summary.generate",
                            event_id=getattr(invocation.event, "event_id", "cached"),
                            queued_for_review=False,
                            reason="Governed result envelope was lost during SummaryResult reconstruction.",
                        )
                    return candidate

            try:
                summary = self.content_delivery.summarize_document(
                    raw_text=doc.raw_text,
                    title=doc.title,
                    document_id=document_id,
                    source_name=doc.title,
                )
            except Exception as service_exc:
                logger.warning(
                    "ContentDeliveryService summarize_document failed; using deterministic fallback",
                    extra={"context": {**context, "cause_type": type(service_exc).__name__, "cause_message": str(service_exc)}},
                    exc_info=True,
                )
                summary = self._fallback_summary(
                    document_id=document_id,
                    doc=doc,
                    reason=f"{type(service_exc).__name__}: {service_exc}",
                )

            candidate = SummaryResult(
                markdown_notes=summary.markdown_notes,
                model_name=summary.model_name,
                tokens_used=summary.tokens_used,
                metadata={
                    **(summary.metadata or {}),
                    "document_id": document_id,
                    "source_document_ids": [document_id],
                    "citations": list(
                        summary.metadata.get("citations")
                        or [
                            {
                                "source_id": f"local-document:{document_id}",
                                "locator": f"document:{document_id}",
                            }
                        ]
                    ),
                    "cached": False,
                    "created_at": self._now_iso(),
                },
            )

            governed_material = self._complete_job_governance(
                invocation=invocation,
                result_material=self._summary_material(candidate),
                result_metadata={
                    "output_type": "summary_result",
                    "markdown_length": len(candidate.markdown_notes),
                    "model_name": candidate.model_name,
                    "tokens_used": candidate.tokens_used,
                    "document_id": document_id,
                    "citations": list(candidate.metadata.get("citations", ())),
                    "source_document_ids": [document_id],
                    "fallback": bool(candidate.metadata.get("fallback", False)),
                },
            )
            candidate = self._summary_from_material(candidate, governed_material)
            envelope_data = candidate.metadata.get("governed_result_envelope")
            if not isinstance(envelope_data, dict):
                raise JobGovernanceDeliveryError(
                    method_name="summarize_document",
                    operation_id="learning.summary.generate",
                    event_id=getattr(invocation.event, "event_id", "summarize_document"),
                    queued_for_review=False,
                    reason="Governed result envelope was lost during SummaryResult reconstruction.",
                )

            if force:
                self._delete_existing_summaries(document_id)
            envelope = self.result_delivery.envelope_from_result(candidate)
            summary_id = self.result_delivery.deliver(
                envelope, "summary_persistence", db=self.db
            ).value
            result = SummaryResult(
                markdown_notes=candidate.markdown_notes,
                model_name=candidate.model_name,
                tokens_used=candidate.tokens_used,
                metadata={**candidate.metadata, "summary_id": summary_id},
            )
            logger.info("Summarize document completed", extra={"context": context})
            return result
        except (JobGovernanceGateError, JobGovernanceDeliveryError):
            raise
        except Exception as exc:
            failure_context = {
                **context,
                "cause_type": type(exc).__name__,
                "cause_message": str(exc),
                "failure_stage": "summary_governance_completion",
            }
            logger.exception("Summarize document failed", extra={"context": failure_context})
            raise JobServiceError(f"Summarize document failed: {type(exc).__name__}: {exc}", context=failure_context) from exc

    def generate_study_assets(
        self,
        document_id: int,
        *,
        force: bool = False,
        flashcard_count: int | None = None,
        mcq_count: int = 10,
        governance_context: JobGovernanceContext | None = None,
    ) -> StudyAssetsResult:
        structured_model = get_model_for_task("flashcards")
        target_flashcards = flashcard_count if flashcard_count is not None else 10
        context = self._context(
            operation="generate_study_assets",
            document_id=document_id,
            model_name=structured_model,
            force=force,
            flashcard_count=target_flashcards,
            mcq_count=mcq_count,
        )
        invocation = self._begin_job_governance(
            method_name="generate_study_assets",
            input_metadata={
                "document_id": document_id,
                "force": force,
                "requested_flashcard_count": target_flashcards,
                "mcq_count": mcq_count,
            },
            governance_context=governance_context,
        )
        try:
            doc = self._get_document_or_raise(document_id)
            existing_cards = self._get_existing_flashcards(document_id)
            existing_mcqs = self._get_existing_mcqs(document_id)
            if not force and existing_cards and existing_mcqs:
                result = StudyAssetsResult(
                    flashcards=existing_cards,
                    mcqs=existing_mcqs,
                    metadata={
                        "document_id": document_id,
                        "cached": True,
                        "flashcard_count": len(existing_cards),
                        "mcq_count": len(existing_mcqs),
                        "created_at": self._now_iso(),
                    },
                )
                governed_material = self._complete_job_governance(
                    invocation=invocation,
                    result_material=self._assets_material(result),
                    result_metadata={
                        "output_type": "study_assets_result",
                        "flashcard_count": len(result.flashcards),
                        "mcq_count": len(result.mcqs),
                        "document_id": document_id,
                    },
                )
                candidate = self._assets_from_material(result, governed_material)
                envelope = candidate.metadata.get("governed_result_envelope")
                if not isinstance(envelope, dict):
                    raise JobGovernanceDeliveryError(
                        method_name="generate_study_assets",
                        operation_id="learning.flashcards.generate",
                        event_id=getattr(invocation.event, "event_id", "cached"),
                        queued_for_review=False,
                        reason="Governed result envelope was lost during StudyAssetsResult reconstruction.",
                    )
                return candidate
            try:
                result = self.content_delivery.generate_study_assets(
                    raw_text=doc.raw_text,
                    title=doc.title,
                    flashcard_count=target_flashcards,
                    mcq_count=mcq_count,
                )
            except Exception as service_exc:
                logger.warning(
                    "ContentDeliveryService asset generation failed; using deterministic fallback",
                    extra={"context": {**context, "cause_type": type(service_exc).__name__, "cause_message": str(service_exc)}},
                    exc_info=True,
                )
                result = self._fallback_study_assets(
                    document_id=document_id,
                    doc=doc,
                    flashcard_count=target_flashcards,
                    mcq_count=mcq_count,
                    reason=f"{type(service_exc).__name__}: {service_exc}",
                )
            governed_material = self._complete_job_governance(
                invocation=invocation,
                result_material=self._assets_material(result),
                result_metadata={
                    "output_type": "study_assets_result",
                    "flashcard_count": len(result.flashcards),
                    "mcq_count": len(result.mcqs),
                    "document_id": document_id,
                    "model_name": result.metadata.get("model_name", structured_model),
                },
            )
            result = self._assets_from_material(result, governed_material)
            envelope_data = result.metadata.get("governed_result_envelope")
            if not isinstance(envelope_data, dict):
                raise JobGovernanceDeliveryError(
                    method_name="generate_study_assets",
                    operation_id="learning.flashcards.generate",
                    event_id=getattr(invocation.event, "event_id", "generate_study_assets"),
                    queued_for_review=False,
                    reason="Governed result envelope was lost during StudyAssetsResult reconstruction.",
                )
            if force:
                self._delete_existing_study_assets(document_id)
            envelope = self.result_delivery.envelope_from_result(result)
            self.result_delivery.deliver(envelope, "study_assets_persistence", db=self.db)
            logger.info("Study asset generation completed", extra={"context": context})
            return result
        except (JobGovernanceGateError, JobGovernanceDeliveryError):
            raise
        except Exception as exc:
            failure_context = {
                **context,
                "cause_type": type(exc).__name__,
                "cause_message": str(exc),
                "failure_stage": "study_assets_governed_delivery",
            }
            logger.exception("Study asset generation failed", extra={"context": failure_context})
            raise JobServiceError(f"Study asset generation failed: {type(exc).__name__}: {exc}", context=failure_context) from exc

    def _authorize_answer_delivery(
        self,
        *,
        invocation: Any | None,
        answer: AnswerResult,
        document_id: int | None,
    ) -> AnswerResult:
        governed_material = self._complete_job_governance(
            invocation=invocation,
            result_material=self._answer_material(answer),
            result_metadata={
                "output_type": "answer_result",
                "answer_length": len(answer.answer_text),
                "citation_count": len(answer.sources),
                "document_id": document_id,
                "model_name": answer.model_name,
            },
        )
        return self._answer_from_material(answer, governed_material)

    def tutor_answer(
        self, question: str, *, top_k: int = 5, max_tokens: int = 1200,
        document_id: int | None = None, active_tab: str = "Student Tutor",
        active_document_title: str | None = None, due_flashcards: int | None = None,
        session_id: str | None = None, remember: bool = True,
        governance_context: JobGovernanceContext | None = None,
    ) -> AnswerResult:
        clean = str(question).strip()
        if not clean:
            raise ValueError("Question must be a non-empty string.")
        if document_id is None:
            raise RuntimeGovernanceGateError("Governed tutor answers require an explicit document_id.")
        if self.governed_retrieval is None or self.grounded_answer is None:
            raise JobServiceError("Governed retrieval and grounded answer services are required.")
        invocation = self._begin_job_governance(
            method_name="tutor_answer",
            input_metadata={
                "document_id": document_id,
                "question_length": len(clean),
                "top_k": top_k,
                "max_tokens": max_tokens,
                "active_tab": active_tab,
                "remember": remember,
            },
            governance_context=governance_context,
        )
        session = session_id or self._session_id_for(document_id)
        retrieval = self.governed_retrieval.retrieve(clean, document_id=document_id, operation="learning.tutor.retrieve", top_k=top_k)
        memory = self.memory.get_relevant_history_text(clean, k=3, session_id=session)
        candidate = self.grounded_answer.generate(clean, retrieval, max_tokens=max_tokens, relevant_memory=memory)
        metadata = {
            "output_type": "answer_result",
            "answer_length": len(candidate.answer_text),
            "citation_count": len(candidate.sources),
            "document_id": document_id,
            "model_name": candidate.model_name,
            "retrieved_chunk_ids": retrieval.retrieved_chunk_ids,
            "excluded_chunk_ids": retrieval.excluded_chunk_ids,
        }
        governed = self._complete_job_governance(invocation=invocation, result_material=self._answer_material(candidate), result_metadata=metadata)
        answer = self._answer_from_material(candidate, governed)
        envelope_data = answer.metadata.get("governed_result_envelope")
        if not isinstance(envelope_data, dict):
            raise JobGovernanceDeliveryError(
                method_name="tutor_answer",
                operation_id="learning.tutor.answer",
                event_id=getattr(invocation.event, "event_id", "tutor_answer"),
                queued_for_review=False,
                reason="Governed result envelope was lost during AnswerResult reconstruction.",
            )
        answer.metadata["candidate"] = False
        answer.metadata["delivery_authorized"] = True
        self._persist_and_log_answer(clean, answer, session, document_id, active_tab, remember, active_document_title)
        return answer

    def _persist_and_log_answer(
        self,
        user_text: str,
        answer: AnswerResult,
        session_id: str,
        document_id: int | None,
        active_tab: str,
        remember: bool,
        active_document_title: str | None = None,
    ) -> None:
        if self.result_delivery is None:
            raise JobServiceError("Governed result delivery is not configured.")
        envelope = self.result_delivery.envelope_from_result(answer)
        self.result_delivery.deliver(
            envelope,
            "chat_log",
            db=self.db,
            user_text=user_text,
        )
        if remember:
            self.result_delivery.deliver(
                envelope,
                "learning_memory",
                memory=self.memory,
                user_text=user_text,
                session_id=session_id,
                metadata={
                    "operation": "tutor_answer",
                    "document_id": document_id,
                    "active_tab": active_tab,
                    "active_document_title": active_document_title,
                    "model_name": answer.model_name,
                    "sources_count": len(answer.sources),
                },
            )

    def tutor_answer_stream(
        self, question: str, *, top_k: int = 5, max_tokens: int = 1200,
        document_id: int | None = None, active_tab: str = "Student Tutor",
        active_document_title: str | None = None, due_flashcards: int | None = None,
        session_id: str | None = None, remember: bool = True,
        governance_context: JobGovernanceContext | None = None,
    ) -> Iterator[str]:
        answer = self.tutor_answer(
            question,
            top_k=top_k,
            max_tokens=max_tokens,
            document_id=document_id,
            active_tab=active_tab,
            active_document_title=active_document_title,
            due_flashcards=due_flashcards,
            session_id=session_id,
            remember=remember,
            governance_context=governance_context,
        )
        yield answer.answer_text

    def _source_document_ids(self) -> tuple[int, ...]:
        rows = (
            self.db.list_documents_typed(limit=100_000, offset=0)
            if hasattr(self.db, "list_documents_typed")
            else self.db.list_documents()
        )
        identifiers: list[int] = []
        for row in rows:
            value = (
                row.get("id")
                if isinstance(row, dict) or hasattr(row, "keys")
                else getattr(row, "id", None)
            )
            if value is not None:
                identifiers.append(int(value))
        return tuple(sorted(set(identifiers)))

    def _build_index_rebuild_policy(self, operation: str) -> IndexRebuildPolicy:
        if self.runtime_governance is None:
            raise RuntimeGovernanceGateError(
                "Governed index rebuild requires runtime education governance."
            )
        canonical_operation = runtime_learning_operation(operation)
        allowlists = {
            document_id: self.runtime_governance.permitted_chunk_ids(
                document_id,
                canonical_operation,
            )
            for document_id in self._source_document_ids()
        }
        return IndexRebuildPolicy.from_allowlists(
            operation=canonical_operation,
            allowlists=allowlists,
            require_complete_allowlists=True,
        )

    def _rebuild_rag_index(self, operation: str) -> IndexRebuildResult | None:
        if not hasattr(self.rag, "rebuild_from_source_documents"):
            if self.runtime_governance is not None:
                raise RAGError(
                    "Governed RAG engine does not expose governed reconstruction.",
                    context={"operation": operation},
                )
            if hasattr(self.rag, "rebuild_from_database"):
                self.rag.rebuild_from_database()
                return None
            raise RAGError(
                "RAG engine does not expose a rebuild operation.",
                context={"operation": operation},
            )
        policy = (
            self._build_index_rebuild_policy(operation)
            if self.runtime_governance is not None
            else None
        )
        return self.rag.rebuild_from_source_documents(policy=policy)

    def _index_document_governed(self, document_id: int, operation: str) -> None:
        canonical_operation = runtime_learning_operation(operation)
        permitted = (
            self.runtime_governance.permitted_chunk_ids(
                int(document_id),
                canonical_operation,
            )
            if self.runtime_governance is not None
            else None
        )
        self.rag.index_document(
            int(document_id),
            permitted_chunk_ids=permitted,
        )

    def _prepare_rag_index(self, context: dict[str, Any]) -> None:
        rag_index = getattr(self.rag, "index", None)
        index_size = int(rag_index.ntotal) if rag_index is not None else 0

        if index_size > 0:
            return

        logger.warning(
            "RAG index is empty before tutor answer; attempting rebuild",
            extra={"context": {**context, "index_size": index_size}},
        )

        operation = runtime_learning_operation(
            str(context.get("operation") or "tutor_answer")
        )
        self._rebuild_rag_index(operation)

    def _rag_search(
        self,
        question: str,
        *,
        top_k: int,
        document_id: int | None = None,
        operation: str = "tutor_answer",
    ) -> list[Any]:
        if hasattr(self.rag, "search"):
            hits = list(self.rag.search(question, top_k=top_k))
        elif hasattr(self.rag, "retrieve"):
            hits = list(self.rag.retrieve(question, top_k=top_k))
        else:
            raise RAGError(
                "RAG engine does not expose search or retrieve.",
                context={"operation": "rag_search"},
            )
        if self.runtime_governance is None:
            return hits
        if document_id is None:
            raise RuntimeGovernanceGateError("Governed retrieval requires an explicit document_id.")
        governed = self.runtime_governance.filter_retrieval(
            int(document_id),
            runtime_learning_operation(operation),
            hits,
        )
        return list(governed.hits)

    def _format_rag_hits(self, hits: list[Any]) -> str:
        if not hits:
            return ""

        parts: list[str] = []
        for index, hit in enumerate(hits, start=1):
            text = self._hit_text(hit)
            source = self._hit_source(hit)
            if text:
                parts.append(f"[Source {index}: {source}]\n{text}")

        return "\n\n".join(parts).strip()

    @staticmethod
    def _hit_text(hit: Any) -> str:
        if isinstance(hit, dict):
            return str(hit.get("text") or hit.get("page_content") or "")

        if hasattr(hit, "page_content"):
            return str(hit.page_content)

        if hasattr(hit, "text"):
            return str(hit.text)

        return str(hit)

    @staticmethod
    def _hit_source(hit: Any) -> str:
        if isinstance(hit, dict):
            return str(
                hit.get("source_ref")
                or hit.get("source")
                or hit.get("document_id")
                or "Local Study Material"
            )

        metadata = getattr(hit, "metadata", None)
        if isinstance(metadata, dict):
            return str(
                metadata.get("source_ref")
                or metadata.get("source")
                or metadata.get("document_id")
                or "Local Study Material"
            )

        return "Local Study Material"

    def _documents_for_pedagogy(self, hits: list[Any]) -> list[Any]:
        return hits

    def _sources_from_hits(self, hits: list[Any]) -> list[str]:
        sources: list[str] = []
        seen: set[str] = set()

        for hit in hits:
            source = self._hit_source(hit)
            if source and source not in seen:
                seen.add(source)
                sources.append(source)

        return sources

    def _build_tutor_system_prompt(self) -> str:
        runtime_context = self.context_tracker.generate_system_prompt()

        return f"""
You are AmbaAI, an offline-first educational tutor.

Rules:
- Use the retrieved study material first.
- Use relevant long-term memory only to personalize support, not as a factual source.
- If the answer is not supported by the retrieved material, say that the uploaded material does not contain enough information.
- Keep answers clear, student-friendly, and exam-useful.
- Avoid hallucination.
- Cite available sources.

{runtime_context}
""".strip()

    @staticmethod
    def _build_tutor_prompt(
        *,
        question: str,
        retrieved_context: str,
        relevant_memory: str,
    ) -> str:
        sections = [
            "Student question:",
            question,
            "",
            "Retrieved study material:",
            retrieved_context if retrieved_context else "No relevant uploaded study material was retrieved.",
        ]

        if relevant_memory:
            sections.extend(
                [
                    "",
                    "Relevant past learning memory:",
                    relevant_memory,
                ]
            )

        sections.extend(
            [
                "",
                "Answer the student using the instructions. Be concise but complete.",
            ]
        )

        return "\n".join(sections).strip()

    def _update_context_tracker(
        self,
        *,
        active_tab: str,
        document_id: int | None,
        active_document_title: str | None,
        due_flashcards: int | None,
    ) -> None:
        self.context_tracker.set_active_tab(active_tab)

        if document_id is not None or active_document_title:
            self.context_tracker.set_active_document(
                document_id=document_id,
                title=active_document_title,
            )

        if due_flashcards is not None:
            self.context_tracker.set_due_flashcards(due_flashcards)

    @staticmethod
    def _session_id_for(document_id: int | None) -> str:
        if document_id is None:
            return "student:global"
        return f"student:document:{document_id}"

    def _log_chat_to_database(
        self,
        *,
        user_text: str,
        assistant_text: str,
        context_payload: dict[str, Any],
    ) -> None:
        try:
            self.db.log_chat("user", user_text)
            self.db.log_chat("assistant", assistant_text, context=[context_payload])
        except Exception:
            logger.warning("Failed to write chat log to database", exc_info=True)

    @staticmethod
    def _make_answer_result(
        *,
        answer_text: str,
        raw_answer: str,
        model_name: str,
        sources: list[str],
        metadata: dict[str, Any],
    ) -> AnswerResult:
        try:
            return AnswerResult(
                answer_text=answer_text,
                model_name=model_name,
                sources=sources,
                metadata=metadata,
            )
        except TypeError:
            try:
                return AnswerResult(
                    answer_text=answer_text,
                    raw_answer=raw_answer,
                    model_name=model_name,
                    sources=sources,
                    metadata=metadata,
                )
            except TypeError:
                return AnswerResult(
                    answer_text=answer_text,
                    sources=sources,
                    model_name=model_name,
                    metadata=metadata,
                )

    def list_documents(self) -> list[dict[str, Any]]:
        context = self._context(operation="list_documents")
        failures: list[dict[str, str]] = []
        rows: list[Any] = []

        if hasattr(self.db, "list_documents_typed"):
            try:
                rows = list(self.db.list_documents_typed(limit=10_000, offset=0))
            except TypeError as exc:
                failures.append(
                    {
                        "source": "db.list_documents_typed(limit, offset)",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )
                try:
                    rows = list(self.db.list_documents_typed())
                except Exception as fallback_exc:
                    failures.append(
                        {
                            "source": "db.list_documents_typed()",
                            "error_type": type(fallback_exc).__name__,
                            "error_message": str(fallback_exc),
                        }
                    )
            except Exception as exc:
                failures.append(
                    {
                        "source": "db.list_documents_typed",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )

        if not rows and hasattr(self.db, "list_documents"):
            try:
                rows = list(self.db.list_documents(limit=10_000, offset=0))
            except TypeError as exc:
                failures.append(
                    {
                        "source": "db.list_documents(limit, offset)",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )
                try:
                    rows = list(self.db.list_documents())
                except Exception as fallback_exc:
                    failures.append(
                        {
                            "source": "db.list_documents()",
                            "error_type": type(fallback_exc).__name__,
                            "error_message": str(fallback_exc),
                        }
                    )
            except Exception as exc:
                failures.append(
                    {
                        "source": "db.list_documents",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )

        if not rows:
            try:
                with self._db_connect(
                    operation="list_documents_sql",
                    context=context,
                ) as conn:
                    rows = self._query_documents_fallback(conn)
            except Exception as exc:
                failures.append(
                    {
                        "source": "direct_sql_fallback",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )

        documents: list[dict[str, Any]] = []

        for row in rows:
            normalized = self._normalize_document_listing(row)
            if normalized is not None:
                documents.append(normalized)

        if failures:
            logger.warning(
                "Document listing completed with fallback failures",
                extra={
                    "context": {
                        **context,
                        "document_count": len(documents),
                        "raw_row_count": len(rows),
                        "fallback_failures": failures,
                    }
                },
            )
        else:
            logger.info(
                "Documents listed",
                extra={
                    "context": {
                        **context,
                        "document_count": len(documents),
                        "raw_row_count": len(rows),
                    }
                },
            )

        return documents

    def _query_documents_fallback(self, conn: sqlite3.Connection) -> list[Any]:
        try:
            conn.row_factory = sqlite3.Row
        except Exception:
            pass

        table_exists = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'documents'
            """
        ).fetchone()

        if table_exists is None:
            return []

        columns = [
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(documents)").fetchall()
        ]

        if not columns:
            return []

        order_column = "created_at" if "created_at" in columns else "id" if "id" in columns else columns[0]

        return list(
            conn.execute(
                f"""
                SELECT *
                FROM documents
                ORDER BY {order_column} DESC
                LIMIT 10000
                """
            ).fetchall()
        )

    def _normalize_document_listing(self, row: Any) -> dict[str, Any] | None:
        try:
            if row is None:
                return None

            if is_dataclass(row):
                data = asdict(row)
            elif isinstance(row, dict):
                data = dict(row)
            else:
                try:
                    data = dict(row)
                except Exception:
                    data = dict(getattr(row, "__dict__", {}))

            document_id = data.get("id") or data.get("document_id") or data.get("doc_id")

            if document_id is None:
                logger.warning(
                    "Document listing skipped because id is missing",
                    extra={"context": {"row": str(row)[:500]}},
                )
                return None

            metadata = self._decode_metadata(data)

            return {
                "id": int(document_id),
                "document_id": int(document_id),
                "title": str(data.get("title") or f"Document {document_id}"),
                "source_path": str(data.get("source_path") or data.get("path") or ""),
                "kind": str(data.get("kind") or data.get("type") or "unknown"),
                "metadata": metadata,
                "created_at": str(data.get("created_at") or ""),
            }

        except Exception as exc:
            logger.warning(
                "Failed to normalize document listing row",
                extra={
                    "context": {
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "row": str(row)[:500],
                    }
                },
                exc_info=True,
            )
            return None

    def delete_document(
        self,
        document_id: int,
        *,
        reviewer_role: str,
        governance_context: JobGovernanceContext | None = None,
    ) -> DocumentDeletionReceipt:
        if self.document_lifecycle is None:
            raise JobServiceError("Governed document lifecycle service is not configured.")
        return self.document_lifecycle.delete_document(
            document_id=document_id,
            reviewer_role=reviewer_role,
            governance_context=governance_context,
        )

    def get_notes(self, document_id: int) -> str:
        context = self._context(operation="get_notes", document_id=document_id)

        try:
            row = self.db.latest_summary(document_id)
            if row is None:
                return ""
            return str(dict(row)["summary_markdown"])
        except Exception as exc:
            logger.exception("Failed to get notes", extra={"context": context})
            raise JobServiceError("Failed to get notes.", context=context) from exc

    def generate_notes_markdown(
        self,
        document_id: int,
        *,
        force: bool = False,
        model_name: str = OLLAMA_SUMMARY_MODEL,
        governance_context: JobGovernanceContext | None = None,
    ) -> str:
        result = self.generate_notes(
            document_id=document_id,
            force=force,
            model_name=model_name,
            governance_context=governance_context,
        )
        return result.markdown_notes

    def generate_flashcards(
        self,
        document_id: int,
        *,
        limit: int = 20,
        force: bool = False,
        governance_context: JobGovernanceContext | None = None,
    ) -> list[Flashcard]:
        assets = self.generate_study_assets(
            document_id=document_id,
            force=force,
            flashcard_count=limit,
            governance_context=governance_context,
        )
        return assets.flashcards[:limit]

    def generate_quiz(
        self,
        document_id: int,
        *,
        count: int = 10,
        force: bool = False,
        governance_context: JobGovernanceContext | None = None,
    ) -> list[MCQ]:
        assets = self.generate_study_assets(
            document_id=document_id,
            force=force,
            mcq_count=count,
            governance_context=governance_context,
        )
        return assets.mcqs[:count]

    def tutor_chat(
        self,
        document_id: int | None,
        question: str,
        *,
        top_k: int = 5,
        max_tokens: int = 1200,
        active_tab: str = "Student Tutor",
        active_document_title: str | None = None,
        due_flashcards: int | None = None,
        session_id: str | None = None,
        governance_context: JobGovernanceContext | None = None,
    ) -> AnswerResult:
        context = self._context(
            operation="tutor_chat",
            document_id=document_id,
            question=question,
        )

        if self.governance_coordinator is not None:
            return self.tutor_answer(
                question=question,
                top_k=top_k,
                max_tokens=max_tokens,
                document_id=document_id,
                active_tab=active_tab,
                active_document_title=active_document_title,
                due_flashcards=due_flashcards,
                session_id=session_id,
                remember=True,
                governance_context=governance_context,
            )
        try:
            if document_id is not None:
                document = self._get_document_or_raise(document_id)
                active_document_title = active_document_title or document.title

                if hasattr(self.rag, "has_document"):
                    if not self.rag.has_document(document_id):
                        self._index_document_governed(document_id, "tutor_answer")
                elif hasattr(self.rag, "meta"):
                    is_indexed = any(
                        int(m.get("document_id", -1)) == document_id
                        for m in getattr(self.rag, "meta", [])
                    )
                    if not is_indexed:
                        self._index_document_governed(document_id, "tutor_answer")

            return self.tutor_answer(
                question=question,
                top_k=top_k,
                max_tokens=max_tokens,
                document_id=document_id,
                active_tab=active_tab,
                active_document_title=active_document_title,
                due_flashcards=due_flashcards,
                session_id=session_id,
                remember=True,
            )

        except Exception as exc:
            logger.exception("Tutor chat failed", extra={"context": context})
            raise JobServiceError("Tutor chat failed.", context=context) from exc

    def tutor_chat_stream(
        self,
        document_id: int | None,
        question: str,
        *,
        top_k: int = 5,
        max_tokens: int = 1200,
        active_tab: str = "Student Tutor",
        active_document_title: str | None = None,
        due_flashcards: int | None = None,
        session_id: str | None = None,
        governance_context: JobGovernanceContext | None = None,
    ) -> Iterator[str]:
        if self.governance_coordinator is not None:
            yield from self.tutor_answer_stream(
                question=question,
                top_k=top_k,
                max_tokens=max_tokens,
                document_id=document_id,
                active_tab=active_tab,
                active_document_title=active_document_title,
                due_flashcards=due_flashcards,
                session_id=session_id,
                remember=True,
                governance_context=governance_context,
            )
            return
        if document_id is not None:
            try:
                document = self._get_document_or_raise(document_id)
                active_document_title = active_document_title or document.title

                if hasattr(self.rag, "has_document"):
                    if not self.rag.has_document(document_id):
                        self._index_document_governed(document_id, "tutor_answer")
                elif hasattr(self.rag, "meta"):
                    is_indexed = any(
                        int(m.get("document_id", -1)) == document_id
                        for m in getattr(self.rag, "meta", [])
                    )
                    if not is_indexed:
                        self._index_document_governed(document_id, "tutor_answer")
            except Exception:
                pass

        yield from self.tutor_answer_stream(
            question=question,
            top_k=top_k,
            max_tokens=max_tokens,
            document_id=document_id,
            active_tab=active_tab,
            active_document_title=active_document_title,
            due_flashcards=due_flashcards,
            session_id=session_id,
            remember=True,
        )

    def export_notes(self, document_id: int, path: str | Path, fmt: str = "md") -> None:
        if self.result_delivery is None:
            raise JobServiceError("Governed result delivery is not configured.")
        row = self.db.latest_summary(document_id)
        if row is None:
            result = self.generate_notes(document_id)
        else:
            data = dict(row)
            result = SummaryResult(
                markdown_notes=str(data["summary_markdown"]),
                model_name=str(data["model_name"]),
                tokens_used=None,
                metadata={"document_id": document_id},
            )
            raise JobServiceError(
                "Existing summaries require a governed delivery envelope before export."
            )
        envelope = self.result_delivery.envelope_from_result(result)
        self.result_delivery.deliver(
            envelope,
            "export",
            path=Path(path).expanduser().resolve(),
            fmt=fmt,
        )

    def record_feedback_event(
        self,
        event_id: int,
        *,
        governance_context: JobGovernanceContext | None = None,
    ) -> None:
        invocation = self._begin_job_governance(
            method_name="record_feedback_event",
            input_metadata={},
            governance_context=governance_context,
        )
        self._complete_job_governance(
            invocation=invocation,
            result_material={"event_id": event_id, "recorded": True},
            result_metadata={"output_type": "feedback_event", "recorded": True},
        )
        logger.info(
            "UI recorded feedback event",
            extra={"context": {"event_id": event_id}},
        )