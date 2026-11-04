from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from amba_ai.models.schemas import Flashcard, MCQ


class DomainPlugin(ABC):
    @property
    @abstractmethod
    def domain_name(self) -> str:
        ...

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return ""

    @property
    def capabilities(self) -> set[str]:
        return {
            "flashcard_refinement",
            "mcq_refinement",
            "distractor_reasoning",
            "quality_scoring",
        }

    def refine_flashcards(
        self,
        cards: Sequence[Flashcard],
        raw_text: str,
    ) -> list[Flashcard]:
        return list(cards)

    def refine_mcqs(
        self,
        mcqs: Sequence[MCQ],
        raw_text: str,
    ) -> list[MCQ]:
        return list(mcqs)

    def get_alternative_distractor_rationale(
        self,
        question: str,
        choice: str,
        correct: str,
    ) -> str:
        return (
            "This option conflicts with evidence and "
            "concepts established in the source material."
        )

    def score_flashcard(
        self,
        card: Flashcard,
    ) -> float:
        return 1.0

    def score_mcq(
        self,
        mcq: MCQ,
    ) -> float:
        return 1.0

    def health_check(self) -> bool:
        return True

    def initialize(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"domain='{self.domain_name}', "
            f"version='{self.version}')"
        )