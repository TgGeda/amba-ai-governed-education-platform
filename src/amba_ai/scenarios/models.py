from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
import hashlib
import re
from typing import Any

from amba_ai.governance.models import deep_freeze, to_canonical_json


class ScenarioConfigurationError(ValueError):
    pass


class ScenarioAccessError(PermissionError):
    pass


class ScenarioStage(IntEnum):
    STAGE_1 = 1
    STAGE_2 = 2
    STAGE_3 = 3
    STAGE_4 = 4


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def require_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not _ID_PATTERN.fullmatch(normalized):
        raise ScenarioConfigurationError(f"{field_name} has an invalid format")
    return normalized


def require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = " ".join(value.split())
    if not normalized:
        raise ScenarioConfigurationError(f"{field_name} must not be empty")
    return normalized


def require_timestamp(value: object, field_name: str) -> str:
    text = require_text(value, field_name)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ScenarioConfigurationError(
            f"{field_name} must be valid ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ScenarioConfigurationError(
            f"{field_name} must include a timezone"
        )
    return parsed.astimezone(timezone.utc).isoformat()


def require_sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip().lower()
    if _SHA256_PATTERN.fullmatch(normalized) is None:
        raise ScenarioConfigurationError(
            f"{field_name} must be a SHA-256 digest"
        )
    return normalized


def normalize_identifiers(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    normalized = tuple(require_identifier(item, f"{field_name} item") for item in value)
    if len(normalized) != len(set(normalized)):
        raise ScenarioConfigurationError(f"{field_name} must not contain duplicates")
    return normalized


def sha256_canonical(value: object) -> str:
    return hashlib.sha256(to_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ScenarioFact:
    fact_id: str
    scenario_id: str
    release_stage: ScenarioStage
    recipient_ids: tuple[str, ...]
    fact_type: str
    payload: Mapping[str, Any]
    provenance_ids: tuple[str, ...] = ()
    synthetic: bool = True
    legal_effect: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "fact_id", require_identifier(self.fact_id, "fact_id"))
        object.__setattr__(self, "scenario_id", require_identifier(self.scenario_id, "scenario_id"))
        if not isinstance(self.release_stage, ScenarioStage):
            raise TypeError("release_stage must be a ScenarioStage")
        recipients = normalize_identifiers(self.recipient_ids, "recipient_ids")
        if not recipients:
            raise ScenarioConfigurationError("recipient_ids must not be empty")
        object.__setattr__(self, "recipient_ids", recipients)
        object.__setattr__(self, "fact_type", require_identifier(self.fact_type, "fact_type"))
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        object.__setattr__(self, "payload", deep_freeze(self.payload))
        object.__setattr__(self, "provenance_ids", normalize_identifiers(self.provenance_ids, "provenance_ids"))
        if type(self.synthetic) is not bool or type(self.legal_effect) is not bool:
            raise TypeError("synthetic and legal_effect must be strict Booleans")
        if not self.synthetic:
            raise ScenarioConfigurationError("scenario facts must remain synthetic")
        if self.legal_effect:
            raise ScenarioConfigurationError("scenario facts must not create legal effect")
        to_canonical_json(self.to_dict())

    @property
    def fact_digest(self) -> str:
        return sha256_canonical(self.to_dict())

    def visible_to(self, recipient_id: str, stage: ScenarioStage) -> bool:
        recipient = require_identifier(recipient_id, "recipient_id")
        if not isinstance(stage, ScenarioStage):
            raise TypeError("stage must be a ScenarioStage")
        return recipient in self.recipient_ids and self.release_stage <= stage

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "scenario_id": self.scenario_id,
            "release_stage": int(self.release_stage),
            "recipient_ids": list(self.recipient_ids),
            "fact_type": self.fact_type,
            "payload": self.payload,
            "provenance_ids": list(self.provenance_ids),
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }


@dataclass(frozen=True, slots=True)
class EvidenceReleaseEnvelope:
    release_id: str
    scenario_id: str
    stage: ScenarioStage
    recipient_id: str
    released_at: str
    facts: tuple[ScenarioFact, ...]
    previous_release_digest: str | None
    release_digest: str
    synthetic: bool = True
    legal_effect: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "release_id", require_identifier(self.release_id, "release_id"))
        object.__setattr__(self, "scenario_id", require_identifier(self.scenario_id, "scenario_id"))
        if not isinstance(self.stage, ScenarioStage):
            raise TypeError("stage must be a ScenarioStage")
        object.__setattr__(self, "recipient_id", require_identifier(self.recipient_id, "recipient_id"))
        object.__setattr__(self, "released_at", require_timestamp(self.released_at, "released_at"))
        if not isinstance(self.facts, tuple) or any(not isinstance(item, ScenarioFact) for item in self.facts):
            raise TypeError("facts must be a tuple of ScenarioFact objects")
        ids = tuple(item.fact_id for item in self.facts)
        if len(ids) != len(set(ids)):
            raise ScenarioConfigurationError("facts must not contain duplicates")
        canonical_facts = tuple(
            sorted(
                self.facts,
                key=lambda item: (int(item.release_stage), item.fact_id),
            )
        )
        if canonical_facts != self.facts:
            raise ScenarioConfigurationError(
                "facts must use canonical stage and identifier order"
            )
        for fact in self.facts:
            if fact.scenario_id != self.scenario_id:
                raise ScenarioConfigurationError("fact scenario does not match release scenario")
            if not fact.visible_to(self.recipient_id, self.stage):
                raise ScenarioAccessError("release contains a future-stage or unauthorized fact")
        if self.previous_release_digest is not None:
            object.__setattr__(
                self,
                "previous_release_digest",
                require_sha256(
                    self.previous_release_digest,
                    "previous_release_digest",
                ),
            )
        object.__setattr__(
            self,
            "release_digest",
            require_sha256(self.release_digest, "release_digest"),
        )
        if type(self.synthetic) is not bool or type(self.legal_effect) is not bool:
            raise TypeError("synthetic and legal_effect must be strict Booleans")
        if not self.synthetic or self.legal_effect:
            raise ScenarioConfigurationError("releases must be synthetic and without legal effect")
        if self.release_digest != self.compute_digest():
            raise ScenarioConfigurationError("release_digest does not match release contents")
        to_canonical_json(self.to_dict())

    @property
    def fact_ids(self) -> tuple[str, ...]:
        return tuple(fact.fact_id for fact in self.facts)

    def digest_payload(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "scenario_id": self.scenario_id,
            "stage": int(self.stage),
            "recipient_id": self.recipient_id,
            "released_at": self.released_at,
            "facts": [fact.to_dict() for fact in self.facts],
            "previous_release_digest": self.previous_release_digest,
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }

    def compute_digest(self) -> str:
        return sha256_canonical(self.digest_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.digest_payload(), "release_digest": self.release_digest}

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())
