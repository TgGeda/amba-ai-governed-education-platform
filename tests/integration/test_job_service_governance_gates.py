from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from amba_ai.models.schemas import AnswerResult, IngestedDocument
from amba_ai.services.job_governance import (
    JobGovernanceCoordinator,
    JobGovernanceGateError,
)
from amba_ai.services.job_service import JobService
from amba_ai.services.governed_result_delivery import GovernedResultDeliveryService
from amba_ai.governance.runtime.output_guardrails import OutputDisposition, digest_material


class Completion:
    def __init__(self, *, acknowledged: bool = True) -> None:
        self.acknowledged = acknowledged

    def require_delivery_acknowledged(self) -> None:
        if not self.acknowledged:
            raise RuntimeError("not acknowledged")


class Coordinator(JobGovernanceCoordinator):
    def __init__(self, *, block: bool = False, acknowledged: bool = True) -> None:
        self.block = block
        self.acknowledged = acknowledged
        self.events: list[tuple[str, str]] = []

    def begin(self, *, method_name: str, input_metadata: Any, context: Any) -> Any:
        self.events.append(("begin", method_name))
        if self.block:
            raise JobGovernanceGateError(
                method_name=method_name,
                operation_id="classroom_instruction_delivery",
                event_id="event-1",
                action=__import__(
                    "amba_ai.governance.models", fromlist=["EnforcementAction"]
                ).EnforcementAction.BLOCK,
            )
        return object()

    def complete(self, *, invocation: Any, result_material: Any, result_metadata: Any) -> Completion:
        self.events.append(("complete", str(result_metadata["output_type"])))
        return Completion(acknowledged=self.acknowledged)


class ModelService:
    def __init__(self) -> None:
        self.stream_started = False

    def get_client_for_task(self, task: str) -> Any:
        return SimpleNamespace()

    def generate_stream(self, **kwargs: Any):
        self.stream_started = True
        yield "first"
        yield " second"


class Memory:
    def get_relevant_history_text(self, *args: Any, **kwargs: Any) -> str:
        return ""

    def save_exchange(self, **kwargs: Any) -> None:
        return None


class ContextTracker:
    def set_active_tab(self, value: str) -> None: pass
    def set_active_document(self, **kwargs: Any) -> None: pass
    def set_due_flashcards(self, value: int) -> None: pass
    def generate_system_prompt(self) -> str: return ""


class DB:
    def get_document_typed(self, document_id: int) -> IngestedDocument | None:
        if document_id != 1:
            return None
        return IngestedDocument(
            title="Governed test lesson",
            source_path="test_lesson.txt",
            kind="text",
            raw_text="Fractions are equal parts of a whole.",
            metadata={"source_sha256": "test-source-sha256"},
        )

    def log_chat(self, *args: Any, **kwargs: Any) -> None: pass


class RAG:
    index = SimpleNamespace(ntotal=1)
    def search(self, question: str, top_k: int): return []


class GovernedRetrieval:
    def __init__(self) -> None:
        self.called = False

    def retrieve(self, question: str, *, document_id: int, operation: str, top_k: int):
        self.called = True
        return SimpleNamespace(
            document_id=document_id,
            operation=operation,
            hits=(SimpleNamespace(chunk_id=1, text="evidence", source_ref="lesson"),),
            retrieved_chunk_ids=(1,),
            excluded_chunk_ids=(),
            receipt_id="EDU-GOV-RETRIEVE",
            corpus_revision_id="REV-1",
        )


class GroundedAnswer:
    def generate(self, question: str, retrieval: Any, *, max_tokens: int, relevant_memory: str):
        return AnswerResult(
            answer_text="first second",
            sources=["lesson"],
            model_name="test-model",
            metadata={"candidate": True, "delivery_authorized": False},
        )


class OutputValidation:
    def __init__(self, material: dict[str, Any]) -> None:
        self.output_id = "EDU-OUT-GATE"
        self.document_id = 1
        self.operation = "tutor_answer"
        self.disposition = OutputDisposition.DISPLAY
        self.sanitized_material = dict(material)
        self.sanitized_output_sha256 = digest_material(self.sanitized_material)
        self.trace_id = "EDU-TRACE-GATE"
        self.audit_receipt = "EDU-AUDIT-GATE"

    def evidence(self) -> dict[str, Any]:
        return {"decision": self.disposition.value}


class RuntimeGovernance:
    def authorize_generation(
        self,
        document_id: int,
        operation: str,
        source_path: str | None = None,
    ) -> None:
        assert document_id == 1
        assert operation == "tutor_answer"
        assert source_path == "test_lesson.txt"

    def validate_output(self, document_id: int, operation: str, material: dict[str, Any], **kwargs: Any) -> OutputValidation:
        assert document_id == 1
        return OutputValidation(material)


def service(coordinator: Coordinator) -> JobService:
    model = ModelService()
    result = JobService(
        db=DB(),
        rag_engine=RAG(),
        memory_manager=Memory(),
        context_tracker=ContextTracker(),
        model_service=model,
        llm_client=SimpleNamespace(),
        governance_coordinator=coordinator,
        governed_retrieval_service=GovernedRetrieval(),
        grounded_answer_service=GroundedAnswer(),
        governed_result_delivery=GovernedResultDeliveryService(),
        runtime_governance=RuntimeGovernance(),
    )
    return result


def test_blocked_pre_gate_prevents_model_and_rag_work() -> None:
    coordinator = Coordinator(block=True)
    value = service(coordinator)

    with pytest.raises(JobGovernanceGateError):
        list(
            value.tutor_answer_stream(
                "question",
                document_id=1,
                governance_context=object(),  # fake coordinator accepts it
            )
        )

    assert value.model_service.stream_started is False
    assert coordinator.events == [("begin", "tutor_answer")]


def test_governed_stream_is_buffered_until_post_gate_completes() -> None:
    coordinator = Coordinator()
    value = service(coordinator)
    iterator = value.tutor_answer_stream(
        "question",
        document_id=1,
        governance_context=object(),
    )

    first = next(iterator)

    assert first == "first second"
    assert coordinator.events == [
        ("begin", "tutor_answer"),
        ("complete", "answer_result"),
    ]
    assert list(iterator) == []


def test_unacknowledged_stream_releases_no_tokens() -> None:
    coordinator = Coordinator(acknowledged=False)
    value = service(coordinator)

    with pytest.raises(RuntimeError, match="not acknowledged"):
        next(
            value.tutor_answer_stream(
                "question",
                document_id=1,
                governance_context=object(),
            )
        )

    assert coordinator.events[-1] == ("complete", "answer_result")


def test_legacy_construction_without_coordinator_remains_available() -> None:
    value = JobService(
        db=DB(),
        rag_engine=RAG(),
        memory_manager=Memory(),
        context_tracker=ContextTracker(),
        model_service=ModelService(),
        llm_client=SimpleNamespace(),
    )
    assert value.governance_coordinator is None
