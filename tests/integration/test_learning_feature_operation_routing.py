from __future__ import annotations

from typing import Any
import pytest

from amba_ai.models.schemas import (
    AnswerResult,
    Flashcard,
    MCQ,
    StudyAssetsResult,
    SummaryResult,
)
from amba_ai.ui.features.notes.data_classes import NotesGenerationRequest
from amba_ai.ui.features.notes.notes_manager import NotesManager
from amba_ai.ui.features.study.data_classes import StudyGenerationRequest
from amba_ai.ui.features.study.study_manager import StudyManager
from amba_ai.ui.features.summarizer.data_classes import SummarizerMode, SummarizerRequest
from amba_ai.ui.features.summarizer.summarizer_manager import SummarizerManager
from amba_ai.ui.features.tutor.data_classes import TutorPersona, TutorRequest
from amba_ai.ui.features.tutor.tutor_manager import TutorManager


class FakeJobService:
    def __init__(self) -> None:
        self.called_method: str | None = None
        self.governance_context: Any = None
        self.call_args: dict[str, Any] = {}

    def require_governed_result(self, result: Any) -> Any:
        return result

    def summarize_document(
        self,
        document_id: int,
        *,
        force: bool = False,
        model_name: str | None = None,
        governance_context: Any = None,
    ) -> SummaryResult:
        self.called_method = "summarize_document"
        self.governance_context = governance_context
        self.call_args = {
            "document_id": document_id,
            "force": force,
            "model_name": model_name,
        }
        return SummaryResult(
            markdown_notes=(
                "# Test Document\n\n"
                "## Executive Summary\nSummary content for lesson.\n\n"
                "## Core Concepts\nCore conceptual structure.\n\n"
                "## Structured Study Notes\nDetailed notes content.\n\n"
                "## Sources\n- Test Document, local document ID 1"
            ),
            model_name=model_name or "test-summary-model",
            tokens_used=120,
            metadata={"document_id": document_id},
        )

    def generate_notes(
        self,
        document_id: int,
        *,
        force: bool = False,
        model_name: str | None = None,
        governance_context: Any = None,
    ) -> SummaryResult:
        self.called_method = "generate_notes"
        self.governance_context = governance_context
        self.call_args = {
            "document_id": document_id,
            "force": force,
            "model_name": model_name,
        }
        return SummaryResult(
            markdown_notes=(
                "# Test Document\n\n"
                "## Executive Summary\nNotes summary.\n\n"
                "## Core Concepts\nKey conceptual ideas.\n\n"
                "## Structured Study Notes\nComprehensive study material.\n\n"
                "## Sources\n- Test Document, local document ID 1"
            ),
            model_name=model_name or "test-notes-model",
            tokens_used=150,
            metadata={"document_id": document_id},
        )

    def generate_study_assets(
        self,
        document_id: int,
        *,
        force: bool = False,
        flashcard_count: int | None = None,
        mcq_count: int = 10,
        governance_context: Any = None,
    ) -> StudyAssetsResult:
        self.called_method = "generate_study_assets"
        self.governance_context = governance_context
        self.call_args = {
            "document_id": document_id,
            "force": force,
            "flashcard_count": flashcard_count,
            "mcq_count": mcq_count,
        }
        return StudyAssetsResult(
            flashcards=[
                Flashcard(
                    question="What is the primary thesis of the unit?",
                    answer="The curriculum provides grounded analytical methods.",
                    source_ref="Test Document",
                )
            ],
            mcqs=[
                MCQ(
                    question="Which proposition represents the primary finding?",
                    choices=[
                        "The curriculum provides grounded analytical methods.",
                        "No systematic principles apply.",
                        "The system operates without curriculum constraints.",
                        "Data is processed without pedagogical alignment.",
                    ],
                    correct_answer="The curriculum provides grounded analytical methods.",
                    explanation="The text directly establishes the primary pedagogical basis.",
                    source_ref="Test Document",
                )
            ],
            metadata={"document_id": document_id},
        )

    def tutor_answer(
        self,
        question: str,
        *,
        top_k: int = 5,
        max_tokens: int = 1200,
        document_id: int | None = None,
        active_tab: str = "Student Tutor",
        active_document_title: str | None = None,
        due_flashcards: int | None = None,
        session_id: str | None = None,
        governance_context: Any = None,
    ) -> AnswerResult:
        self.called_method = "tutor_answer"
        self.governance_context = governance_context
        self.call_args = {
            "question": question,
            "top_k": top_k,
            "max_tokens": max_tokens,
            "document_id": document_id,
            "active_tab": active_tab,
        }
        return AnswerResult(
            answer_text="The concept is defined according to Section 3 of the syllabus.",
            model_name="test-tutor-model",
            sources=["Test Document"],
            metadata={"document_id": document_id},
        )


def test_summarizer_manager_uses_summary_operation() -> None:
    jobs = FakeJobService()
    manager = SummarizerManager(jobs)

    request = SummarizerRequest(
        document_id=1,
        mode=SummarizerMode.DETAILED,
        force=False,
        preferred_model="test-summary-model",
    )

    view_model = manager._run_summary(request)

    assert jobs.called_method == "summarize_document"
    assert view_model is not None
    assert jobs.governance_context is not None
    assert jobs.governance_context.destination_id == "desktop.summary"
    assert jobs.governance_context.authorization_basis.purposes == ("learning.summary.generate",)
    assert jobs.governance_context.authorization_basis.processing_operations == (
        "learning.summary.generate",
    )


def test_notes_manager_uses_notes_operation() -> None:
    jobs = FakeJobService()
    manager = NotesManager(jobs)

    request = NotesGenerationRequest(
        document_id=2,
        note_style="structured",
        force=True,
        preferred_model="test-notes-model",
    )

    view_model = manager._run_notes(request)

    assert jobs.called_method == "generate_notes"
    assert view_model is not None
    assert jobs.governance_context is not None
    assert jobs.governance_context.destination_id == "desktop.notes"
    assert jobs.governance_context.authorization_basis.purposes == ("learning.notes.generate",)
    assert jobs.governance_context.authorization_basis.processing_operations == (
        "learning.notes.generate",
    )


def test_study_manager_uses_study_operation() -> None:
    jobs = FakeJobService()
    manager = StudyManager(jobs)

    request = StudyGenerationRequest(
        document_id=3,
        flashcard_count=5,
        mcq_count=5,
        force=False,
    )

    view_model = manager._run_study_assets(request)

    assert jobs.called_method == "generate_study_assets"
    assert view_model is not None
    assert jobs.governance_context is not None
    assert jobs.governance_context.destination_id == "desktop.study"
    assert jobs.governance_context.authorization_basis.purposes == ("learning.flashcards.generate",)
    assert jobs.governance_context.authorization_basis.processing_operations == (
        "learning.flashcards.generate",
    )


def test_tutor_manager_uses_tutor_operation() -> None:
    jobs = FakeJobService()
    manager = TutorManager(jobs)

    request = TutorRequest(
        question="Explain packet routing in networks.",
        document_id=4,
        persona=TutorPersona.ACADEMIC,
        top_k=4,
        max_tokens=600,
    )

    view_model = manager._run_tutor_answer(request)

    assert jobs.called_method == "tutor_answer"
    assert view_model is not None
    assert jobs.governance_context is not None
    assert jobs.governance_context.destination_id == "desktop.tutor"
    assert jobs.governance_context.authorization_basis.purposes == ("learning.tutor.answer",)
    assert jobs.governance_context.authorization_basis.processing_operations == (
        "learning.tutor.answer",
    )


@pytest.mark.parametrize(
    ("manager_class", "runner_method", "request_obj", "expected_method", "expected_op", "expected_dest"),
    [
        (
            SummarizerManager,
            "_run_summary",
            SummarizerRequest(document_id=1, mode=SummarizerMode.DETAILED, force=False),
            "summarize_document",
            "learning.summary.generate",
            "desktop.summary",
        ),
        (
            NotesManager,
            "_run_notes",
            NotesGenerationRequest(document_id=1, note_style="structured", force=False),
            "generate_notes",
            "learning.notes.generate",
            "desktop.notes",
        ),
        (
            StudyManager,
            "_run_study_assets",
            StudyGenerationRequest(document_id=1, flashcard_count=5, mcq_count=5, force=False),
            "generate_study_assets",
            "learning.flashcards.generate",
            "desktop.study",
        ),
        (
            TutorManager,
            "_run_tutor_answer",
            TutorRequest(question="Test question", document_id=1),
            "tutor_answer",
            "learning.tutor.answer",
            "desktop.tutor",
        ),
    ],
)
def test_all_learning_managers_route_to_distinct_operations(
    manager_class: type,
    runner_method: str,
    request_obj: Any,
    expected_method: str,
    expected_op: str,
    expected_dest: str,
) -> None:
    jobs = FakeJobService()
    manager = manager_class(jobs)
    runner = getattr(manager, runner_method)
    runner(request_obj)

    assert jobs.called_method == expected_method
    assert jobs.governance_context.destination_id == expected_dest
    assert jobs.governance_context.authorization_basis.processing_operations == (expected_op,)