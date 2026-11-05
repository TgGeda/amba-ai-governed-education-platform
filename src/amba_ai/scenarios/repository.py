from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any

from amba_ai.governance.models import to_canonical_json
from amba_ai.scenarios.models import (
    ScenarioConfigurationError,
    ScenarioFact,
    ScenarioStage,
    normalize_identifiers,
    require_identifier,
    sha256_canonical,
)


@dataclass(frozen=True, slots=True)
class ScenarioDestination:
    destination_id: str
    destination_type: str
    recipient_id: str
    synthetic: bool = True
    legal_effect: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "destination_id",
            "destination_type",
            "recipient_id",
        ):
            object.__setattr__(
                self,
                field_name,
                require_identifier(getattr(self, field_name), field_name),
            )
        _require_synthetic(self.synthetic, self.legal_effect)

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination_id": self.destination_id,
            "destination_type": self.destination_type,
            "recipient_id": self.recipient_id,
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }


@dataclass(frozen=True, slots=True)
class ScenarioEventDefinition:
    event_id: str
    operation_id: str
    stage: ScenarioStage
    destination_id: str
    fact_ids: tuple[str, ...]
    synthetic: bool = True
    legal_effect: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "event_id",
            "operation_id",
            "destination_id",
        ):
            object.__setattr__(
                self,
                field_name,
                require_identifier(getattr(self, field_name), field_name),
            )
        if not isinstance(self.stage, ScenarioStage):
            raise TypeError("stage must be a ScenarioStage")
        fact_ids = normalize_identifiers(self.fact_ids, "fact_ids")
        if not fact_ids:
            raise ScenarioConfigurationError("fact_ids must not be empty")
        object.__setattr__(self, "fact_ids", fact_ids)
        _require_synthetic(self.synthetic, self.legal_effect)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "operation_id": self.operation_id,
            "stage": int(self.stage),
            "destination_id": self.destination_id,
            "fact_ids": list(self.fact_ids),
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    scenario_id: str
    title: str
    configured_stages: tuple[ScenarioStage, ...]
    facts: tuple[ScenarioFact, ...]
    destinations: tuple[ScenarioDestination, ...]
    events: tuple[ScenarioEventDefinition, ...]
    synthetic: bool = True
    legal_effect: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scenario_id",
            require_identifier(self.scenario_id, "scenario_id"),
        )
        if not isinstance(self.title, str) or not self.title.strip():
            raise ScenarioConfigurationError("title must not be empty")
        object.__setattr__(self, "title", " ".join(self.title.split()))
        if not isinstance(self.configured_stages, tuple):
            raise TypeError("configured_stages must be a tuple")
        if not self.configured_stages or any(
            not isinstance(stage, ScenarioStage)
            for stage in self.configured_stages
        ):
            raise ScenarioConfigurationError(
                "configured_stages must contain ScenarioStage values"
            )
        if tuple(sorted(set(self.configured_stages))) != self.configured_stages:
            raise ScenarioConfigurationError(
                "configured_stages must be unique and canonical"
            )
        for field_name, expected in (
            ("facts", ScenarioFact),
            ("destinations", ScenarioDestination),
            ("events", ScenarioEventDefinition),
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise TypeError(f"{field_name} must be a tuple")
            if any(not isinstance(item, expected) for item in value):
                raise TypeError(
                    f"{field_name} must contain {expected.__name__} objects"
                )
        canonical_facts = tuple(
            sorted(self.facts, key=lambda item: (int(item.release_stage), item.fact_id))
        )
        canonical_destinations = tuple(
            sorted(self.destinations, key=lambda item: item.destination_id)
        )
        canonical_events = tuple(
            sorted(self.events, key=lambda item: (int(item.stage), item.event_id))
        )
        if canonical_facts != self.facts:
            raise ScenarioConfigurationError("facts must use canonical stage and identifier order")
        if canonical_destinations != self.destinations:
            raise ScenarioConfigurationError("destinations must use canonical identifier order")
        if canonical_events != self.events:
            raise ScenarioConfigurationError("events must use canonical stage and identifier order")
        _require_unique((item.fact_id for item in self.facts), "fact_id")
        _require_unique((item.destination_id for item in self.destinations), "destination_id")
        _require_unique((item.event_id for item in self.events), "event_id")
        if any(fact.scenario_id != self.scenario_id for fact in self.facts):
            raise ScenarioConfigurationError("all facts must belong to the scenario")
        _require_synthetic(self.synthetic, self.legal_effect)
        if any(not item.synthetic or item.legal_effect for item in (*self.facts, *self.destinations, *self.events)):
            raise ScenarioConfigurationError("all scenario content must be synthetic without legal effect")
        to_canonical_json(self.to_dict())

    @property
    def definition_digest(self) -> str:
        return sha256_canonical(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "configured_stages": [int(stage) for stage in self.configured_stages],
            "facts": [item.to_dict() for item in self.facts],
            "destinations": [item.to_dict() for item in self.destinations],
            "events": [item.to_dict() for item in self.events],
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


class ScenarioRepository:
    def __init__(self) -> None:
        self._definitions: dict[str, ScenarioDefinition] = {}
        self._fact_owners: dict[str, str] = {}
        self._lock = threading.RLock()

    def register(self, definition: ScenarioDefinition) -> None:
        if not isinstance(definition, ScenarioDefinition):
            raise TypeError("definition must be a ScenarioDefinition")
        with self._lock:
            existing = self._definitions.get(definition.scenario_id)
            if existing is definition or existing == definition:
                return
            if existing is not None:
                raise ScenarioConfigurationError("scenario_id is already registered with different content")
            for fact in definition.facts:
                owner = self._fact_owners.get(fact.fact_id)
                if owner is not None and owner != definition.scenario_id:
                    raise ScenarioConfigurationError(
                        f"fact_id {fact.fact_id} is already owned by scenario {owner}"
                    )
            self._definitions[definition.scenario_id] = definition
            for fact in definition.facts:
                self._fact_owners[fact.fact_id] = definition.scenario_id

    def get(self, scenario_id: str) -> ScenarioDefinition:
        normalized = require_identifier(scenario_id, "scenario_id")
        with self._lock:
            value = self._definitions.get(normalized)
        if value is None:
            raise KeyError(f"Scenario {normalized} is not registered")
        return value

    def list_definitions(self) -> tuple[ScenarioDefinition, ...]:
        with self._lock:
            return tuple(self._definitions[key] for key in sorted(self._definitions))

    def scenario_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._definitions))

    def __len__(self) -> int:
        with self._lock:
            return len(self._definitions)


def _require_unique(values: Any, field_name: str) -> None:
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise ScenarioConfigurationError(f"{field_name} values must be globally unique")


def _require_synthetic(synthetic: object, legal_effect: object) -> None:
    if type(synthetic) is not bool or type(legal_effect) is not bool:
        raise TypeError("synthetic and legal_effect must be strict Booleans")
    if not synthetic or legal_effect:
        raise ScenarioConfigurationError("scenario content must be synthetic and without legal effect")
