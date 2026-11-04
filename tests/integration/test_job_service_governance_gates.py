from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from amba_ai.models.schemas import AnswerResult
from amba_ai.services.job_governance import (
    JobGovernanceCoordinator,
    JobGovernanceGateError,
)
from amba_ai.services.job_service import JobService


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
    def log_chat(self, *args: Any, **kwargs: Any) -> None: pass


class RAG:
    index = SimpleNamespace(ntotal=1)
    def search(self, question: str, top_k: int): return []


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
    )
    return result


def test_blocked_pre_gate_prevents_model_and_rag_work() -> None:
    coordinator = Coordinator(block=True)
    value = service(coordinator)

    with pytest.raises(JobGovernanceGateError):
        list(
            value.tutor_answer_stream(
                "question",
                governance_context=object(),  # fake coordinator accepts it
            )
        )

    assert value.model_service.stream_started is False
    assert coordinator.events == [("begin", "tutor_answer_stream")]


def test_governed_stream_is_buffered_until_post_gate_completes() -> None:
    coordinator = Coordinator()
    value = service(coordinator)
    iterator = value.tutor_answer_stream(
        "question",
        governance_context=object(),
    )

    first = next(iterator)

    assert first == "first"
    assert coordinator.events == [
        ("begin", "tutor_answer_stream"),
        ("complete", "answer_result"),
    ]
    assert list(iterator) == [" second"]


def test_unacknowledged_stream_releases_no_tokens() -> None:
    coordinator = Coordinator(acknowledged=False)
    value = service(coordinator)

    with pytest.raises(RuntimeError, match="not acknowledged"):
        next(
            value.tutor_answer_stream(
                "question",
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
