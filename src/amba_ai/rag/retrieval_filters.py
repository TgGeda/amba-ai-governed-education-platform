from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from amba_ai.governance.models import (
    ActivationStatus,
    BindingLevel,
    PolicyRecord,
)


def _normalize_optional_text(
    value: str | None,
    field_name: str,
    *,
    casefold: bool = False,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized.casefold() if casefold else normalized


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError("effective_at must be a datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("effective_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_record_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class RetrievalFilter:
    jurisdiction: str | None = None
    language: str | None = None
    binding_levels: tuple[BindingLevel, ...] = ()
    binding_use: bool = False
    effective_at: datetime | None = None

    def __post_init__(self) -> None:
        jurisdiction = _normalize_optional_text(
            self.jurisdiction,
            "jurisdiction",
        )
        language = _normalize_optional_text(
            self.language,
            "language",
            casefold=True,
        )

        if not isinstance(self.binding_levels, tuple):
            raise TypeError("binding_levels must be a tuple")
        if any(
            not isinstance(level, BindingLevel)
            for level in self.binding_levels
        ):
            raise TypeError(
                "binding_levels must contain only BindingLevel values"
            )
        if len(self.binding_levels) != len(set(self.binding_levels)):
            raise ValueError("binding_levels cannot contain duplicates")
        if type(self.binding_use) is not bool:
            raise TypeError("binding_use must be a strict Boolean")

        effective_at = _normalize_datetime(self.effective_at)

        object.__setattr__(self, "jurisdiction", jurisdiction)
        object.__setattr__(self, "language", language)
        object.__setattr__(
            self,
            "binding_levels",
            tuple(sorted(self.binding_levels, key=lambda item: item.value)),
        )
        object.__setattr__(self, "effective_at", effective_at)


def _is_effective(record: PolicyRecord, effective_at: datetime) -> bool:
    effective_from = _parse_record_datetime(
        getattr(record, "effective_from", None)
    )
    effective_to = _parse_record_datetime(
        getattr(record, "effective_to", None)
    )

    # Temporal filtering fails closed when the record model does not expose
    # valid effective-date metadata.
    if effective_from is None:
        return False
    if effective_at < effective_from:
        return False
    if effective_to is not None and effective_at >= effective_to:
        return False
    return True


def filter_policy_records(
    records: Iterable[PolicyRecord],
    criteria: RetrievalFilter,
) -> tuple[PolicyRecord, ...]:
    if isinstance(records, (str, bytes, bytearray, dict)):
        raise TypeError("records must be an iterable of PolicyRecord values")
    if not isinstance(criteria, RetrievalFilter):
        raise TypeError("criteria must be a RetrievalFilter")

    try:
        materialized = tuple(records)
    except TypeError as error:
        raise TypeError("records must be iterable") from error

    for record in materialized:
        if not isinstance(record, PolicyRecord):
            raise TypeError(
                "records must contain only PolicyRecord values"
            )

    accepted: list[PolicyRecord] = []

    for record in materialized:
        if record.activation_status is not ActivationStatus.ACTIVE:
            continue

        if (
            criteria.jurisdiction is not None
            and record.jurisdiction != criteria.jurisdiction
        ):
            continue

        if criteria.language is not None:
            record_language = getattr(record, "language", None)
            if (
                not isinstance(record_language, str)
                or record_language.strip().casefold() != criteria.language
            ):
                continue

        if (
            criteria.binding_levels
            and record.binding_level not in criteria.binding_levels
        ):
            continue

        if criteria.binding_use:
            if type(record.eligible_for_project_enforcement) is not bool:
                continue
            if record.eligible_for_project_enforcement is not True:
                continue

        if (
            criteria.effective_at is not None
            and not _is_effective(record, criteria.effective_at)
        ):
            continue

        accepted.append(record)

    return tuple(
        sorted(
            accepted,
            key=lambda record: (
                record.identity.record_id,
                record.identity.version_id,
                record.identity.source_id,
            ),
        )
    )
