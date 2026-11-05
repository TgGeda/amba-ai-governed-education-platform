from __future__ import annotations

from amba_ai.institutional.assessment import ObservationStatus
from amba_ai.institutional.assessors.base import (
    BaseInstitutionalAssessor,
    ObservationDraft,
    contains_any,
)
from amba_ai.institutional.models import InstitutionalContextProjection
from amba_ai.scenarios.models import ScenarioFact


class ConsumerProtectionAssessor(BaseInstitutionalAssessor):
    institution_id = "consumer_protection_authority"
    mandate_id = "commercial_practices_and_disclosure"
    recipient_id = "consumer_protection"
    relevant_fact_types = frozenset(
        {
            "commercial_signal",
            "purchase_interface",
            "targeted_advertising",
            "commercial_sdk",
            "consumer_disclosure",
            "pricing",
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
                    "No consumer-protection-mandate facts were released to the institution.",
                ),
                (
                    "insufficient_consumer_protection_context",
                ),
            )
        for fact in facts:
            text = self._fact_text(fact)
            if contains_any(text, ("purchase", "price", "payment", "commercial sdk")):
                drafts.append(
                    ObservationDraft(
                        fact_ids=(fact.fact_id,),
                        category="commercial_interface",
                        status=ObservationStatus.POTENTIAL_CONCERN,
                        statement=(
                            "The released synthetic context contains a commercial or purchasing interface indicator."
                        ),
                        rationale_codes=("COMMERCIAL_INTERFACE_INDICATOR",),
                    )
                )
            if contains_any(text, ("advertising", "targeted", "promotion")):
                drafts.append(
                    ObservationDraft(
                        fact_ids=(fact.fact_id,),
                        category="advertising_practice",
                        status=ObservationStatus.POTENTIAL_CONCERN,
                        statement=(
                            "The released context contains an advertising or targeting indicator."
                        ),
                        rationale_codes=("ADVERTISING_INDICATOR",),
                    )
                )
            if not contains_any(text, ("disclosure", "notice", "reviewed")):
                unresolved.append(
                    "The released context does not establish that commercial disclosures were provided and reviewed."
                )
        return (
            tuple(drafts),
            tuple(dict.fromkeys(unresolved)),
            (
                "assessment_is_not_a_consumer_law_determination",
                "commercial_effect_requires_deterministic_governance_review",
            ),
        )
