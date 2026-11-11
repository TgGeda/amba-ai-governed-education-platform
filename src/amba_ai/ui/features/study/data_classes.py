from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import html
import re
from typing import Any


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _clean_study_text(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"\[Page\s*\d+\]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:Question|Answer|Prompt|Explanation):\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


@dataclass(frozen=True)
class StudyGenerationRequest:
    document_id: int
    force: bool = False
    flashcard_count: int = 10
    mcq_count: int = 10
    target_language: str = "English"
    simple_language: bool = True
    teacher_review_required: bool = True
    preferred_model: str = "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> StudyGenerationRequest:
        source = dict(data or {})
        return cls(
            document_id=int(source.get("document_id") or 0),
            force=_coerce_bool(source.get("force"), False),
            flashcard_count=int(source.get("flashcard_count") or 10),
            mcq_count=int(source.get("mcq_count") or 10),
            target_language=str(source.get("target_language") or "English"),
            simple_language=_coerce_bool(source.get("simple_language"), True),
            teacher_review_required=_coerce_bool(source.get("teacher_review_required"), True),
            preferred_model=str(source.get("preferred_model") or "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"),
        )


@dataclass(frozen=True)
class FlashcardViewModel:
    question: str
    answer: str
    source_ref: str = "Verified Grounded Material"
    concept: str = "Core Concept"
    code_snippet: str = ""
    language: str = "text"
    difficulty: str = "Medium"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def card_id(self) -> str:
        raw = f"{self.question}::{self.answer}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def from_any(cls, value: Any, fallback_index: int = 1) -> FlashcardViewModel:
        if isinstance(value, dict):
            raw_q = str(value.get("question") or "")
            raw_a = str(value.get("answer") or "")
            source = str(value.get("source_ref") or "Verified Grounded Material")
            concept = str(value.get("concept") or value.get("category") or "Curriculum Concept")
            code = str(value.get("code_snippet") or value.get("code") or "")
            diff = str(value.get("difficulty") or "Medium")
        else:
            raw_q = str(getattr(value, "question", "") or "")
            raw_a = str(getattr(value, "answer", "") or "")
            source = str(getattr(value, "source_ref", None) or "Verified Grounded Material")
            concept = str(getattr(value, "concept", None) or getattr(value, "category", "") or "Curriculum Concept")
            code = str(getattr(value, "code_snippet", "") or getattr(value, "code", "") or "")
            diff = str(getattr(value, "difficulty", "") or "Medium")

        q = _clean_study_text(raw_q)
        a = _clean_study_text(raw_a)

        detected_lang = "text"
        if not code:
            code_match = re.search(r"```([a-zA-Z0-9_-]*)\n(.*?)```", a, flags=re.DOTALL)
            if code_match:
                detected_lang = code_match.group(1).strip() or "text"
                code = code_match.group(2).strip()
            else:
                code_match_q = re.search(r"```([a-zA-Z0-9_-]*)\n(.*?)```", q, flags=re.DOTALL)
                if code_match_q:
                    detected_lang = code_match_q.group(1).strip() or "text"
                    code = code_match_q.group(2).strip()

        if not q:
            q = f"What core principle is established in section {fallback_index} of {source}?"
        if not a:
            a = f"Consult {source} for detailed examination and active recall guidance."

        return cls(
            question=q,
            answer=a,
            source_ref=_clean_study_text(source),
            concept=concept.strip() or "Core Learning Concept",
            code_snippet=code.strip(),
            language=detected_lang,
            difficulty=diff,
        )


@dataclass(frozen=True)
class MCQViewModel:
    question: str
    choices: list[str]
    correct_answer: str
    explanation: str
    source_ref: str = "Verified Grounded Material"
    concept: str = "Knowledge Assessment"
    code_snippet: str = ""
    language: str = "text"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def question_id(self) -> str:
        raw = f"{self.question}::{self.correct_answer}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def from_any(cls, value: Any, fallback_index: int = 1) -> MCQViewModel:
        if isinstance(value, dict):
            raw_q = str(value.get("question") or "")
            raw_choices = list(value.get("choices") or [])
            correct = str(value.get("correct_answer") or "")
            exp = str(value.get("explanation") or "")
            source = str(value.get("source_ref") or "Verified Grounded Material")
            concept = str(value.get("concept") or value.get("category") or "Knowledge Check")
            code = str(value.get("code_snippet") or value.get("code") or "")
        else:
            raw_q = str(getattr(value, "question", "") or "")
            raw_choices = list(getattr(value, "choices", []) or [])
            correct = str(getattr(value, "correct_answer", "") or "")
            exp = str(getattr(value, "explanation", "") or "")
            source = str(getattr(value, "source_ref", None) or "Verified Grounded Material")
            concept = str(getattr(value, "concept", None) or getattr(value, "category", "") or "Knowledge Check")
            code = str(getattr(value, "code_snippet", "") or getattr(value, "code", "") or "")

        q = _clean_study_text(raw_q)
        clean_choices = [_clean_study_text(c) for c in raw_choices if str(c).strip()]
        correct = _clean_study_text(correct)
        exp = _clean_study_text(exp)

        detected_lang = "text"
        if not code:
            code_match = re.search(r"```([a-zA-Z0-9_-]*)\n(.*?)```", q, flags=re.DOTALL)
            if code_match:
                detected_lang = code_match.group(1).strip() or "text"
                code = code_match.group(2).strip()

        if not q:
            q = f"Which proposition represents the primary conclusion for lesson topic {fallback_index}?"
        if not correct:
            correct = clean_choices[0] if clean_choices else "Verified principle documented in source curriculum."

        if correct not in clean_choices:
            clean_choices.insert(0, correct)

        while len(clean_choices) < 4:
            clean_choices.append(f"Alternative curriculum interpretation {len(clean_choices) + 1}")

        if not exp:
            exp = f"Based directly on verified learning objectives in {source}."

        return cls(
            question=q,
            choices=clean_choices[:4],
            correct_answer=correct,
            explanation=exp,
            source_ref=_clean_study_text(source),
            concept=concept.strip() or "Curriculum Assessment",
            code_snippet=code.strip(),
            language=detected_lang,
        )


@dataclass(frozen=True)
class StudyAssetsViewModel:
    document_id: int
    flashcards: list[FlashcardViewModel] = field(default_factory=list)
    mcqs: list[MCQViewModel] = field(default_factory=list)
    cached: bool = False
    fallback: bool = False
    metadata: dict[str, Any] | None = None

    @property
    def flashcard_count(self) -> int:
        return len(self.flashcards)

    @property
    def mcq_count(self) -> int:
        return len(self.mcqs)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["flashcards"] = [card.to_dict() for card in self.flashcards]
        data["mcqs"] = [mcq.to_dict() for mcq in self.mcqs]
        return data

    @classmethod
    def from_study_assets_result(cls, result: Any) -> StudyAssetsViewModel:
        metadata = dict(getattr(result, "metadata", {}) or {})
        document_id = int(metadata.get("document_id") or 0)
        raw_flashcards = list(getattr(result, "flashcards", []) or [])
        raw_mcqs = list(getattr(result, "mcqs", []) or [])

        flashcards = [
            FlashcardViewModel.from_any(card, fallback_index=idx)
            for idx, card in enumerate(raw_flashcards, start=1)
        ]
        mcqs = [
            MCQViewModel.from_any(mcq, fallback_index=idx)
            for idx, mcq in enumerate(raw_mcqs, start=1)
        ]

        if not flashcards:
            flashcards = cls._build_default_flashcards(document_id)
        if not mcqs:
            mcqs = cls._build_default_mcqs(document_id)

        return cls(
            document_id=document_id,
            flashcards=flashcards,
            mcqs=mcqs,
            cached=bool(metadata.get("cached") or False),
            fallback=bool(metadata.get("fallback") or False),
            metadata=metadata,
        )

    @staticmethod
    def _build_default_flashcards(document_id: int = 0) -> list[FlashcardViewModel]:
        source_name = f"Curriculum Document #{document_id}" if document_id else "Verified Curriculum Material"
        return [
            FlashcardViewModel(
                question=f"What is the foundational objective established in {source_name}?",
                answer="Understanding and applying the core concepts defined in the primary lesson.",
                source_ref=source_name,
                concept="Curriculum Foundation",
                difficulty="Easy",
            ),
            FlashcardViewModel(
                question=f"How should key principles from {source_name} be systematically reviewed?",
                answer="Through spaced repetition, active recall cards, and interactive scenario questions.",
                source_ref=source_name,
                concept="Pedagogical Method",
                difficulty="Medium",
            ),
            FlashcardViewModel(
                question=f"What constitutes verified evidence when answering examination questions on this unit?",
                answer="Direct factual citations grounded in the authorized syllabus text.",
                source_ref=source_name,
                concept="Evidence & Grounding",
                difficulty="Hard",
            ),
        ]

    @staticmethod
    def _build_default_mcqs(document_id: int = 0) -> list[MCQViewModel]:
        source_name = f"Curriculum Document #{document_id}" if document_id else "Verified Curriculum Material"
        return [
            MCQViewModel(
                question=f"Which proposition represents the primary verified finding in {source_name}?",
                choices=[
                    "The curriculum establishes validated analytical principles for active learning.",
                    "No structured framework is provided for the subject matter.",
                    "Learning outcomes are evaluated without reference to source material.",
                    "The subject material relies solely on external ungrounded conjecture.",
                ],
                correct_answer="The curriculum establishes validated analytical principles for active learning.",
                explanation=f"The primary text in {source_name} defines validated instructional guidelines.",
                source_ref=source_name,
                concept="Knowledge Verification",
            ),
            MCQViewModel(
                question="What is the most effective study strategy for mastering new conceptual definitions?",
                choices=[
                    "Active recall paired with spaced self-assessment questions",
                    "Passive single-pass reading without revision",
                    "Relying exclusively on unverified online summaries",
                    "Memorizing disconnected keywords without their context",
                ],
                correct_answer="Active recall paired with spaced self-assessment questions",
                explanation="Evidence-based learning science confirms active retrieval reinforces retention.",
                source_ref=source_name,
                concept="Study Methodology",
            ),
        ]


@dataclass(frozen=True)
class FlashcardReviewState:
    question_key: str
    rating: str = "New"
    interval_days: int = 0
    reviews: int = 0
    ease_factor: float = 2.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QuizAnswerState:
    question_index: int
    selected_answer: str = ""
    correct: bool = False
    submitted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)