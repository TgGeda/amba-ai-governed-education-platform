from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amba_ai.governance.models import to_canonical_json
from amba_ai.institutional.registry import InstitutionalAssessorRegistry
from amba_ai.scenarios.models import ScenarioConfigurationError, ScenarioStage
from amba_ai.scenarios.repository import ScenarioDefinition


@dataclass(frozen=True, slots=True)
class ScenarioValidationResult:
    scenario_id: str
    valid: bool
    checked_fact_count: int
    checked_event_count: int
    checked_destination_count: int

    def __post_init__(self) -> None:
        if type(self.valid) is not bool:
            raise TypeError("valid must be a strict Boolean")
        for name in ("checked_fact_count", "checked_event_count", "checked_destination_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TypeError(f"{name} must be a non-negative integer")
        to_canonical_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "valid": self.valid,
            "checked_fact_count": self.checked_fact_count,
            "checked_event_count": self.checked_event_count,
            "checked_destination_count": self.checked_destination_count,
        }


class ScenarioValidator:
    def __init__(self, *, institutional_registry: InstitutionalAssessorRegistry) -> None:
        if not isinstance(institutional_registry, InstitutionalAssessorRegistry):
            raise TypeError("institutional_registry must be an InstitutionalAssessorRegistry")
        self._institutional_registry = institutional_registry

    def validate(self, definition: ScenarioDefinition) -> ScenarioValidationResult:
        if not isinstance(definition, ScenarioDefinition):
            raise TypeError("definition must be a ScenarioDefinition")
        expected_stages = tuple(
            ScenarioStage(value)
            for value in range(1, int(definition.configured_stages[-1]) + 1)
        )
        if definition.configured_stages != expected_stages:
            raise ScenarioConfigurationError("configured stage sequence contains a gap or does not start at STAGE_1")
        facts_by_stage = {stage: 0 for stage in definition.configured_stages}
        registered_recipients = set(self._institutional_registry.recipient_ids())
        for fact in definition.facts:
            if fact.release_stage not in facts_by_stage:
                raise ScenarioConfigurationError("fact release stage is outside configured stages")
            facts_by_stage[fact.release_stage] += 1
            unknown = set(fact.recipient_ids) - registered_recipients
            if unknown:
                raise ScenarioConfigurationError(
                    "fact references unregistered institutional recipients: "
                    + ", ".join(sorted(unknown))
                )
        missing = tuple(stage for stage, count in facts_by_stage.items() if count == 0)
        if missing:
            raise ScenarioConfigurationError(
                "every configured stage requires at least one fact: "
                + ", ".join(stage.name for stage in missing)
            )
        destinations = {item.destination_id: item for item in definition.destinations}
        unknown_destination_recipients = {
            item.recipient_id
            for item in definition.destinations
            if item.recipient_id not in registered_recipients
        }
        if unknown_destination_recipients:
            raise ScenarioConfigurationError(
                "destinations reference unregistered recipients: "
                + ", ".join(sorted(unknown_destination_recipients))
            )
        fact_ids = {item.fact_id: item for item in definition.facts}
        previous_stage = ScenarioStage.STAGE_1
        for index, event in enumerate(definition.events):
            if event.stage not in facts_by_stage:
                raise ScenarioConfigurationError("event stage is outside configured stages")
            if index and event.stage < previous_stage:
                raise ScenarioConfigurationError("event stages must not move backward")
            previous_stage = event.stage
            if event.destination_id not in destinations:
                raise ScenarioConfigurationError("event destination is not registered")
            for fact_id in event.fact_ids:
                fact = fact_ids.get(fact_id)
                if fact is None:
                    raise ScenarioConfigurationError("event references an unknown fact_id")
                if fact.release_stage > event.stage:
                    raise ScenarioConfigurationError("event references a future-stage fact")
        return ScenarioValidationResult(
            scenario_id=definition.scenario_id,
            valid=True,
            checked_fact_count=len(definition.facts),
            checked_event_count=len(definition.events),
            checked_destination_count=len(definition.destinations),
        )
