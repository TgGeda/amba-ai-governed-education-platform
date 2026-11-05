from __future__ import annotations

from amba_ai.institutional.assessment import ObservationStatus
from amba_ai.institutional.assessors.base import (
    BaseInstitutionalAssessor,
    ObservationDraft,
    contains_any,
)
from amba_ai.institutional.models import InstitutionalContextProjection
from amba_ai.scenarios.models import ScenarioFact


class EducationAssessor(BaseInstitutionalAssessor):
    institution_id = "education_authority"
    mandate_id = "educational_purpose_and_supervision"
    recipient_id = "education"
    relevant_fact_types = frozenset(
        {
            "baseline",
            "classroom_use",
            "educational_purpose",
            "learner_supervision",
            "learner_impact",
            "commercial_signal",
        }
    )

    def _analyze(
        self,
        projection: InstitutionalContextProjection,
        facts: tuple[ScenarioFact, ...],
    ):
        drafts: list[ObservationDraft] = []
        unresolved: list[str] = []
        if not facts:
            return (
                (),
                (
                    "No education-mandate facts were released to the institution.",
                ),
                (
                    "insufficient_education_context",
                ),
            )
        for fact in facts:
            text = self._fact_text(fact)
            if contains_any(text, ("classroom", "teacher", "education", "learning")):
                drafts.append(
                    ObservationDraft(
                        fact_ids=(fact.fact_id,),
                        category="educational_purpose",
                        status=ObservationStatus.OBSERVED,
                        statement=(
                            "The released synthetic context contains an educational-purpose indicator."
                        ),
                        rationale_codes=("EDUCATIONAL_PURPOSE_INDICATOR",),
                    )
                )
            if contains_any(text, ("unsupervised", "no teacher", "without supervision")):
                drafts.append(
                    ObservationDraft(
                        fact_ids=(fact.fact_id,),
                        category="learner_supervision",
                        status=ObservationStatus.POTENTIAL_CONCERN,
                        statement=(
                            "The released context indicates a potential learner-supervision gap."
                        ),
                        rationale_codes=("LEARNER_SUPERVISION_GAP",),
                    )
                )
            if contains_any(text, ("purchase", "commercial", "advertising")):
                unresolved.append(
                    "The relationship between the commercial feature and the stated educational purpose remains unresolved."
                )
        if not drafts:
            unresolved.append(
                "The released facts do not establish educational-purpose alignment."
            )
        return (
            tuple(drafts),
            tuple(dict.fromkeys(unresolved)),
            (
                "assessment_is_synthetic_and_non_authorizing",
                "education_assessor_does_not_determine_legal_applicability",
            ),
        )
