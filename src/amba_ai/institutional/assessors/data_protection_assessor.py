from __future__ import annotations

from amba_ai.institutional.assessment import ObservationStatus
from amba_ai.institutional.assessors.base import (
    BaseInstitutionalAssessor,
    ObservationDraft,
    contains_any,
)
from amba_ai.institutional.models import InstitutionalContextProjection
from amba_ai.scenarios.models import ScenarioFact


class DataProtectionAssessor(BaseInstitutionalAssessor):
    institution_id = "data_protection_authority"
    mandate_id = "personal_data_and_profiling"
    recipient_id = "data_protection"
    relevant_fact_types = frozenset(
        {
            "personal_data",
            "profiling",
            "targeted_advertising",
            "data_processing",
            "purpose_limitation",
            "learner_data",
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
                    "No data-protection-mandate facts were released to the institution.",
                ),
                (
                    "insufficient_data_protection_context",
                ),
            )
        for fact in facts:
            text = self._fact_text(fact)
            if contains_any(text, ("personal data", "learner data", "identifier", "profile")):
                drafts.append(
                    ObservationDraft(
                        fact_ids=(fact.fact_id,),
                        category="personal_data_indicator",
                        status=ObservationStatus.OBSERVED,
                        statement=(
                            "The released synthetic context contains a personal-data or profiling indicator."
                        ),
                        rationale_codes=("PERSONAL_DATA_INDICATOR",),
                    )
                )
            if contains_any(text, ("targeted", "profiling", "advertising")):
                drafts.append(
                    ObservationDraft(
                        fact_ids=(fact.fact_id,),
                        category="profiling_and_targeting",
                        status=ObservationStatus.POTENTIAL_CONCERN,
                        statement=(
                            "The released context indicates potential profiling or targeted-use concerns."
                        ),
                        rationale_codes=("PROFILING_OR_TARGETING_INDICATOR",),
                    )
                )
            if not contains_any(text, ("purpose", "consent", "authorization basis")):
                unresolved.append(
                    "The released context does not establish a verified processing purpose or authorization basis."
                )
        return (
            tuple(drafts),
            tuple(dict.fromkeys(unresolved)),
            (
                "assessment_does_not_establish_ethiopian_legal_applicability",
                "human_legal_review_may_be_required",
            ),
        )
