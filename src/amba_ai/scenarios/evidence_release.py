from __future__ import annotations

from collections.abc import Iterable
import threading
from typing import Protocol, runtime_checkable

from amba_ai.governance.models import IdentifierProvider
from amba_ai.scenarios.clock import ScenarioClockProtocol
from amba_ai.scenarios.models import (
    EvidenceReleaseEnvelope,
    ScenarioAccessError,
    ScenarioConfigurationError,
    ScenarioFact,
    ScenarioStage,
    require_identifier,
    sha256_canonical,
)


class EvidenceReleaseService:
    def __init__(self, *, identifier_provider: IdentifierProvider, clock: ScenarioClockProtocol) -> None:
        if not callable(getattr(identifier_provider, "new_id", None)):
            raise TypeError("identifier_provider must provide new_id")
        if not isinstance(clock, ScenarioClockProtocol):
            raise TypeError("clock must implement ScenarioClockProtocol")
        self._identifier_provider = identifier_provider
        self._clock = clock
        self._facts: dict[tuple[str, str], ScenarioFact] = {}
        self._releases: dict[tuple[str, str], list[EvidenceReleaseEnvelope]] = {}
        self._released_fact_ids: set[tuple[str, str, str]] = set()
        self._release_ids: set[str] = set()
        self._lock = threading.RLock()

    @property
    def clock(self) -> ScenarioClockProtocol:
        return self._clock

    def register_fact(self, fact: ScenarioFact) -> None:
        self.register_facts((fact,))

    def register_facts(self, facts: Iterable[ScenarioFact]) -> None:
        if isinstance(facts, (str, bytes, bytearray)):
            raise TypeError(
                "facts must be an iterable of ScenarioFact objects"
            )
        try:
            materialized = tuple(facts)
        except TypeError as exc:
            raise TypeError("facts must be iterable") from exc
        if any(not isinstance(fact, ScenarioFact) for fact in materialized):
            raise TypeError("facts must contain ScenarioFact objects")
        incoming: dict[tuple[str, str], ScenarioFact] = {}
        for fact in materialized:
            key = (fact.scenario_id, fact.fact_id)
            existing = incoming.get(key)
            if existing is not None and existing != fact:
                raise ScenarioConfigurationError(
                    "fact batch contains conflicting identifiers"
                )
            incoming[key] = fact
        with self._lock:
            for key, fact in incoming.items():
                existing = self._facts.get(key)
                if existing is not None and existing != fact:
                    raise ScenarioConfigurationError(
                        "fact identifier is already registered with different content"
                    )
            self._facts.update(incoming)

    def release(self, *, scenario_id: str, recipient_id: str, stage: ScenarioStage) -> EvidenceReleaseEnvelope:
        scenario = require_identifier(scenario_id, "scenario_id")
        recipient = require_identifier(recipient_id, "recipient_id")
        if not isinstance(stage, ScenarioStage):
            raise TypeError("stage must be a ScenarioStage")
        with self._lock:
            snapshot = self._clock.snapshot()
            if stage > snapshot.stage:
                raise ScenarioAccessError(
                    "cannot release evidence for a future scenario stage"
                )
            facts = tuple(
                sorted(
                    (
                        fact for (fact_scenario, _), fact in self._facts.items()
                        if fact_scenario == scenario
                        and fact.visible_to(recipient, stage)
                        and (scenario, recipient, fact.fact_id) not in self._released_fact_ids
                    ),
                    key=lambda item: (int(item.release_stage), item.fact_id),
                )
            )
            chain = self._releases.setdefault((scenario, recipient), [])
            if chain and stage < chain[-1].stage:
                raise ScenarioAccessError("release stage must not regress")
            previous = chain[-1].release_digest if chain else None
            release_id = require_identifier(
                self._identifier_provider.new_id("release"),
                "generated release_id",
            )
            if release_id in self._release_ids:
                raise ScenarioConfigurationError(
                    "identifier provider returned a duplicate release_id"
                )
            released_at = snapshot.timestamp
            payload = {
                "release_id": release_id,
                "scenario_id": scenario,
                "stage": int(stage),
                "recipient_id": recipient,
                "released_at": released_at,
                "facts": [fact.to_dict() for fact in facts],
                "previous_release_digest": previous,
                "synthetic": True,
                "legal_effect": False,
            }
            envelope = EvidenceReleaseEnvelope(
                release_id=release_id,
                scenario_id=scenario,
                stage=stage,
                recipient_id=recipient,
                released_at=released_at,
                facts=facts,
                previous_release_digest=previous,
                release_digest=sha256_canonical(payload),
            )
            chain.append(envelope)
            self._release_ids.add(release_id)
            for fact in facts:
                self._released_fact_ids.add((scenario, recipient, fact.fact_id))
            return envelope

    def releases_for(self, *, scenario_id: str, recipient_id: str) -> tuple[EvidenceReleaseEnvelope, ...]:
        key = (require_identifier(scenario_id, "scenario_id"), require_identifier(recipient_id, "recipient_id"))
        with self._lock:
            return tuple(self._releases.get(key, ()))

    def verify_chain(self, *, scenario_id: str, recipient_id: str) -> bool:
        releases = self.releases_for(scenario_id=scenario_id, recipient_id=recipient_id)
        previous = None
        for envelope in releases:
            if envelope.previous_release_digest != previous:
                return False
            if envelope.compute_digest() != envelope.release_digest:
                return False
            previous = envelope.release_digest
        return True
