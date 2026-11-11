from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class LearningOperation:
    operation_id: str
    required_roles: frozenset[str]
    requires_document: bool
    uses_retrieval: bool
    produces_output: bool
    may_require_review: bool
    allowed_destinations: frozenset[str]

    def __post_init__(self) -> None:
        operation_id = str(self.operation_id).strip()
        if not operation_id.startswith("learning."):
            raise ValueError("Learning operation IDs must use the learning. namespace.")
        roles = frozenset(str(role).strip() for role in self.required_roles if str(role).strip())
        destinations = frozenset(str(value).strip() for value in self.allowed_destinations if str(value).strip())
        if not roles:
            raise ValueError("Learning operations require at least one role.")
        if not destinations:
            raise ValueError("Learning operations require at least one destination.")
        for name in ("requires_document", "uses_retrieval", "produces_output", "may_require_review"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be a strict Boolean.")
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "required_roles", roles)
        object.__setattr__(self, "allowed_destinations", destinations)


def _operation(
    operation_id: str,
    roles: tuple[str, ...],
    *,
    document: bool,
    retrieval: bool = False,
    output: bool = False,
    review: bool = False,
    destinations: tuple[str, ...],
) -> LearningOperation:
    return LearningOperation(
        operation_id,
        frozenset(roles),
        document,
        retrieval,
        output,
        review,
        frozenset(destinations),
    )


LEARNING_OPERATIONS: Mapping[str, LearningOperation] = MappingProxyType({
    "learning.document.ingest": _operation("learning.document.ingest", ("teacher", "school_administrator"), document=False, review=True, destinations=("desktop.library", "review.queue")),
    "learning.document.index": _operation("learning.document.index", ("teacher", "school_administrator"), document=True, review=True, destinations=("internal.retrieval", "review.queue")),
    "learning.document.replace": _operation("learning.document.replace", ("teacher", "school_administrator"), document=True, review=True, destinations=("desktop.library", "review.queue")),
    "learning.document.delete": _operation("learning.document.delete", ("teacher", "school_administrator"), document=True, review=True, destinations=("desktop.library", "audit.ledger")),
    "learning.tutor.retrieve": _operation("learning.tutor.retrieve", ("learner", "teacher"), document=True, retrieval=True, destinations=("internal.retrieval",)),
    "learning.tutor.answer": _operation("learning.tutor.answer", ("learner", "teacher"), document=True, retrieval=True, output=True, review=True, destinations=("desktop.tutor", "review.queue")),
    "learning.summary.generate": _operation("learning.summary.generate", ("learner", "teacher"), document=True, output=True, review=True, destinations=("desktop.summary", "review.queue")),
    "learning.notes.generate": _operation("learning.notes.generate", ("learner", "teacher"), document=True, output=True, review=True, destinations=("desktop.notes", "review.queue")),
    "learning.flashcards.generate": _operation("learning.flashcards.generate", ("learner", "teacher"), document=True, output=True, review=True, destinations=("desktop.study", "review.queue")),
    "learning.quiz.generate": _operation("learning.quiz.generate", ("learner", "teacher"), document=True, output=True, review=True, destinations=("desktop.study", "review.queue")),
    "learning.content.export": _operation("learning.content.export", ("learner", "teacher"), document=True, output=True, review=True, destinations=("local.export", "review.queue")),
    "learning.content.copy": _operation("learning.content.copy", ("learner", "teacher"), document=False, output=True, review=True, destinations=("local.clipboard", "review.queue")),
    "learning.review.decide": _operation("learning.review.decide", ("teacher", "school_administrator"), document=True, review=False, destinations=("review.queue", "audit.ledger")),
    "learning.output.revoke": _operation("learning.output.revoke", ("teacher", "school_administrator"), document=True, review=False, destinations=("audit.ledger",)),
})

LEARNING_METHOD_OPERATION_MAP: Mapping[str, str] = MappingProxyType({
    "ingest_file": "learning.document.ingest",
    "index_document": "learning.document.index",
    "replace_document": "learning.document.replace",
    "delete_document": "learning.document.delete",
    "tutor_retrieve": "learning.tutor.retrieve",
    "tutor_answer": "learning.tutor.answer",
    "tutor_answer_stream": "learning.tutor.answer",
    "tutor_chat": "learning.tutor.answer",
    "tutor_chat_stream": "learning.tutor.answer",
    "summarize_document": "learning.summary.generate",
    "generate_summary": "learning.summary.generate",
    "generate_notes": "learning.notes.generate",
    "generate_notes_markdown": "learning.notes.generate",
    "generate_study_assets": "learning.flashcards.generate",
    "generate_flashcards": "learning.flashcards.generate",
    "generate_mcqs": "learning.quiz.generate",
    "generate_quiz": "learning.quiz.generate",
    "export_notes": "learning.content.export",
    "export_summary": "learning.content.export",
    "copy_content": "learning.content.copy",
    "copy_summary": "learning.content.copy",
    "review_decide": "learning.review.decide",
    "revoke_output": "learning.output.revoke",
    "record_feedback_event": "classroom_exercise_telemetry",
})

_RUNTIME_OPERATION_MAP: Mapping[str, str] = MappingProxyType({
    "learning.document.ingest": "ingest_file",
    "learning.document.index": "index_document",
    "learning.document.replace": "replace_document",
    "learning.document.delete": "delete_document",
    "learning.tutor.retrieve": "tutor_retrieve",
    "learning.tutor.answer": "tutor_answer",
    "learning.summary.generate": "summarize_document",
    "learning.notes.generate": "generate_notes",
    "learning.flashcards.generate": "generate_flashcards",
    "learning.quiz.generate": "generate_quiz",
    "learning.content.export": "export_notes",
    "learning.content.copy": "copy_content",
    "learning.review.decide": "review_decide",
    "learning.output.revoke": "revoke_output",
})


def canonical_learning_operation(operation: str) -> str:
    normalized = str(operation).strip()
    if not normalized:
        raise ValueError("Learning operation must be non-empty.")
    canonical = LEARNING_METHOD_OPERATION_MAP.get(normalized, normalized)
    if canonical not in LEARNING_OPERATIONS and canonical != "classroom_exercise_telemetry":
        raise KeyError(f"Unknown learning operation: {normalized}")
    return canonical


def runtime_learning_operation(operation: str) -> str:
    canonical = canonical_learning_operation(operation)
    return _RUNTIME_OPERATION_MAP.get(canonical, canonical)


def require_learning_operation(operation: str) -> LearningOperation:
    canonical = canonical_learning_operation(operation)
    try:
        return LEARNING_OPERATIONS[canonical]
    except KeyError as error:
        raise KeyError(f"Operation is not an educational operation: {canonical}") from error