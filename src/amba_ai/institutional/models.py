from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from amba_ai.governance.models import deep_freeze, to_canonical_json
from amba_ai.scenarios.models import (
    ScenarioAccessError,
    ScenarioConfigurationError,
    ScenarioFact,
    ScenarioStage,
    require_identifier,
    require_sha256,
    require_timestamp,
    sha256_canonical,
)


@dataclass(frozen=True, slots=True)
class InstitutionalContextProjection:
    projection_id: str
    scenario_id: str
    stage: ScenarioStage
    recipient_id: str
    source_release_id: str
    source_release_digest: str
    projected_at: str
    facts: tuple[ScenarioFact, ...]
    metadata: Mapping[str, Any]
    projection_digest: str
    synthetic: bool = True
    legal_effect: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "projection_id",
            require_identifier(self.projection_id, "projection_id"),
        )
        object.__setattr__(
            self,
            "scenario_id",
            require_identifier(self.scenario_id, "scenario_id"),
        )
        if not isinstance(self.stage, ScenarioStage):
            raise TypeError("stage must be a ScenarioStage")
        object.__setattr__(
            self,
            "recipient_id",
            require_identifier(self.recipient_id, "recipient_id"),
        )
        object.__setattr__(
            self,
            "source_release_id",
            require_identifier(self.source_release_id, "source_release_id"),
        )
        object.__setattr__(
            self,
            "source_release_digest",
            require_sha256(
                self.source_release_digest,
                "source_release_digest",
            ),
        )
        object.__setattr__(
            self,
            "projected_at",
            require_timestamp(self.projected_at, "projected_at"),
        )
        if not isinstance(self.facts, tuple):
            raise TypeError("facts must be a tuple")
        if any(not isinstance(fact, ScenarioFact) for fact in self.facts):
            raise TypeError("facts must contain ScenarioFact objects")
        fact_ids = tuple(fact.fact_id for fact in self.facts)
        if len(fact_ids) != len(set(fact_ids)):
            raise ScenarioConfigurationError("facts must not contain duplicates")
        canonical_facts = tuple(
            sorted(
                self.facts,
                key=lambda fact: (int(fact.release_stage), fact.fact_id),
            )
        )
        if canonical_facts != self.facts:
            raise ScenarioConfigurationError(
                "facts must use canonical stage and identifier order"
            )
        for fact in self.facts:
            if fact.scenario_id != self.scenario_id:
                raise ScenarioConfigurationError(
                    "fact scenario does not match projection scenario"
                )
            if not fact.visible_to(self.recipient_id, self.stage):
                raise ScenarioAccessError(
                    "projection contains a future-stage or unauthorized fact"
                )
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        metadata = deep_freeze(self.metadata)
        prohibited = {
            "recommended_action",
            "approval_decision",
            "authorization_result",
            "distribution_disposition",
            "national_legal_finding",
        }
        if prohibited.intersection(metadata):
            raise ScenarioConfigurationError(
                "projection metadata must not contain governance decisions"
            )
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(
            self,
            "projection_digest",
            require_sha256(self.projection_digest, "projection_digest"),
        )
        if type(self.synthetic) is not bool:
            raise TypeError("synthetic must be a strict Boolean")
        if type(self.legal_effect) is not bool:
            raise TypeError("legal_effect must be a strict Boolean")
        if not self.synthetic:
            raise ScenarioConfigurationError(
                "institutional projections must remain synthetic"
            )
        if self.legal_effect:
            raise ScenarioConfigurationError(
                "institutional projections must not create legal effect"
            )
        if self.projection_digest != self.compute_digest():
            raise ScenarioConfigurationError(
                "projection_digest does not match projection contents"
            )
        to_canonical_json(self.to_dict())

    @property
    def fact_ids(self) -> tuple[str, ...]:
        return tuple(fact.fact_id for fact in self.facts)

    @property
    def fact_digests(self) -> tuple[str, ...]:
        return tuple(fact.fact_digest for fact in self.facts)

    def digest_payload(self) -> dict[str, Any]:
        return {
            "projection_id": self.projection_id,
            "scenario_id": self.scenario_id,
            "stage": int(self.stage),
            "recipient_id": self.recipient_id,
            "source_release_id": self.source_release_id,
            "source_release_digest": self.source_release_digest,
            "projected_at": self.projected_at,
            "facts": [fact.to_dict() for fact in self.facts],
            "metadata": self.metadata,
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }

    def compute_digest(self) -> str:
        return sha256_canonical(self.digest_payload())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.digest_payload(),
            "projection_digest": self.projection_digest,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())
