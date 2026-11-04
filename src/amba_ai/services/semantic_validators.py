from __future__ import annotations

import re
from typing import Sequence

from amba_ai.models.schemas import Flashcard, MCQ, SummaryResult


class SemanticQualityGateError(ValueError):
    pass


class FlashcardSemanticValidator:
    MIN_QUESTION_CHARS = 10
    MAX_QUESTION_CHARS = 300
    MIN_ANSWER_CHARS = 5
    MAX_ANSWER_CHARS = 1000

    @classmethod
    def validate(cls, card: Flashcard) -> Flashcard:
        q = re.sub(r"<[^>]+>", "", card.question).strip()
        a = re.sub(r"<[^>]+>", "", card.answer).strip()

        if not (cls.MIN_QUESTION_CHARS <= len(q) <= cls.MAX_QUESTION_CHARS):
            raise SemanticQualityGateError(
                f"Question length {len(q)} outside bounds [{cls.MIN_QUESTION_CHARS}, {cls.MAX_QUESTION_CHARS}]"
            )

        if not (cls.MIN_ANSWER_CHARS <= len(a) <= cls.MAX_ANSWER_CHARS):
            raise SemanticQualityGateError(
                f"Answer length {len(a)} outside bounds [{cls.MIN_ANSWER_CHARS}, {cls.MAX_ANSWER_CHARS}]"
            )

        if re.sub(r"\W+", "", q.lower()) == re.sub(r"\W+", "", a.lower()):
            raise SemanticQualityGateError("Question and answer are tautological")

        return Flashcard(question=q, answer=a, source_ref=card.source_ref)

    @classmethod
    def filter_valid(cls, cards: Sequence[Flashcard]) -> list[Flashcard]:
        valid: list[Flashcard] = []
        seen_keys: set[str] = set()

        for card in cards:
            try:
                v = cls.validate(card)
                k = re.sub(r"\W+", " ", v.question.lower()).strip()
                if k not in seen_keys:
                    seen_keys.add(k)
                    valid.append(v)
            except SemanticQualityGateError:
                continue

        return valid


class MCQSemanticValidator:
    MIN_QUESTION_CHARS = 12
    MAX_QUESTION_CHARS = 350
    MIN_EXPLANATION_CHARS = 10
    MAX_EXPLANATION_CHARS = 1000

    @classmethod
    def validate(cls, mcq: MCQ) -> MCQ:
        q = re.sub(r"<[^>]+>", "", mcq.question).strip()
        exp = re.sub(r"<[^>]+>", "", mcq.explanation).strip()
        ans = re.sub(r"<[^>]+>", "", mcq.correct_answer).strip()
        choices = [re.sub(r"<[^>]+>", "", c).strip() for c in mcq.choices]

        if not (cls.MIN_QUESTION_CHARS <= len(q) <= cls.MAX_QUESTION_CHARS):
            raise SemanticQualityGateError("Question text violates length boundaries")

        if not (cls.MIN_EXPLANATION_CHARS <= len(exp) <= cls.MAX_EXPLANATION_CHARS):
            raise SemanticQualityGateError("Explanation text violates length boundaries")

        if len(choices) != 4:
            raise SemanticQualityGateError(f"MCQ must have exactly 4 choices, found {len(choices)}")

        if any(not c for c in choices):
            raise SemanticQualityGateError("Empty choice option detected")

        norm_choices = [re.sub(r"\s+", " ", c.lower()).strip() for c in choices]
        if len(set(norm_choices)) != 4:
            raise SemanticQualityGateError("Duplicate choices detected in MCQ")

        norm_ans = re.sub(r"\s+", " ", ans.lower()).strip()
        if norm_ans not in norm_choices:
            raise SemanticQualityGateError("Correct answer does not match any choice option")

        canonical_ans = choices[norm_choices.index(norm_ans)]

        return MCQ(
            question=q,
            choices=choices,
            correct_answer=canonical_ans,
            explanation=exp,
            source_ref=mcq.source_ref,
        )

    @classmethod
    def filter_valid(cls, mcqs: Sequence[MCQ]) -> list[MCQ]:
        valid: list[MCQ] = []
        seen_keys: set[str] = set()

        for mcq in mcqs:
            try:
                v = cls.validate(mcq)
                k = re.sub(r"\W+", " ", v.question.lower()).strip()
                if k not in seen_keys:
                    seen_keys.add(k)
                    valid.append(v)
            except SemanticQualityGateError:
                continue

        return valid


class SummarySemanticValidator:
    REQUIRED_SECTIONS = (
        r"##\s+Executive\s+Summary",
        r"##\s+(?:Structured\s+Study\s+Notes|Core\s+Concepts)",
        r"##\s+Sources",
    )

    @classmethod
    def validate(cls, summary: SummaryResult) -> SummaryResult:
        md = str(summary.markdown_notes or "").strip()
        if not md:
            raise SemanticQualityGateError("Summary markdown output is completely empty")

        missing: list[str] = []
        for pattern in cls.REQUIRED_SECTIONS:
            if not re.search(pattern, md, flags=re.IGNORECASE):
                missing.append(pattern)

        if missing:
            raise SemanticQualityGateError(f"Summary output missing mandatory structural sections: {missing}")

        sections = re.split(r"(?m)^##\s+", md)
        for s in sections:
            lines = [line.strip() for line in s.splitlines() if line.strip()]
            if len(lines) > 1 and len(" ".join(lines[1:])) < 15:
                raise SemanticQualityGateError("Summary contains empty or degenerate sections")

        return summary


class StudyAssetQualityAssessor:
    MIN_FLASHCARD_SCORE = 0.65
    MIN_MCQ_SCORE = 0.70

    LOW_EFFORT_STARTS = (
        "what is",
        "define",
        "who is",
        "name the",
        "where is",
        "when did",
    )

    @classmethod
    def score_flashcard(cls, card: Flashcard) -> float:
        score = 1.0
        q = card.question.strip().lower()
        a = card.answer.strip()

        if any(q.startswith(prefix) for prefix in cls.LOW_EFFORT_STARTS):
            score -= 0.35

        words_in_a = len(a.split())
        if words_in_a < 6:
            score -= 0.30
        elif words_in_a > 15:
            score += 0.15

        if "?" not in card.question:
            score -= 0.10

        return max(0.0, min(1.0, score))

    @classmethod
    def score_mcq(cls, mcq: MCQ) -> float:
        score = 1.0
        lengths = [len(c.strip()) for c in mcq.choices]
        max_l = max(lengths) if lengths else 1
        min_l = min(lengths) if lengths else 1

        if min_l == 0 or (max_l / max(min_l, 1)) > 3.0:
            score -= 0.35

        exp_words = len(mcq.explanation.split())
        if exp_words < 8:
            score -= 0.25
        elif exp_words >= 15:
            score += 0.10

        q = mcq.question.strip().lower()
        if any(q.startswith(prefix) for prefix in cls.LOW_EFFORT_STARTS):
            score -= 0.15

        return max(0.0, min(1.0, score))

    @classmethod
    def filter_and_rank_flashcards(
        cls, cards: Sequence[Flashcard], min_score: float = MIN_FLASHCARD_SCORE
    ) -> list[Flashcard]:
        scored = [(card, cls.score_flashcard(card)) for card in cards]
        passed = [item for item in scored if item[1] >= min_score]
        passed.sort(key=lambda item: item[1], reverse=True)
        return [card for card, _ in passed]

    @classmethod
    def filter_and_rank_mcqs(
        cls, mcqs: Sequence[MCQ], min_score: float = MIN_MCQ_SCORE
    ) -> list[MCQ]:
        scored = [(mcq, cls.score_mcq(mcq)) for mcq in mcqs]
        passed = [item for item in scored if item[1] >= min_score]
        passed.sort(key=lambda item: item[1], reverse=True)
        return [mcq for mcq, _ in passed]