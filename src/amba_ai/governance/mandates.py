from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any, Mapping

import yaml

from amba_ai.governance.models import (
    GovernanceConfigurationError,
    to_canonical_json,
)
from amba_ai.governance.principals import parse_timestamp


MANDATE_SCHEMA_VERSION = "1.0.0"


def _require_identifier(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_unique_values(
    values: tuple[str, ...],
    field_name: str,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")

    normalized = tuple(
        _require_identifier(value, field_name)
        for value in values
    )

    if not normalized:
        raise ValueError(f"{field_name} must not be empty")

    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} cannot contain duplicates")

    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class MandateDefinition:
    mandate_id: str
    principal_id: str
    role: str
    permitted_operations: tuple[str, ...]
    permitted_decisions: tuple[str, ...]
    synthetic: bool
    legal_effect: bool
    active_from: str
    expires_at: str
    revoked_at: str | None

    def __post_init__(self) -> None:
        mandate_id = _require_identifier(
            self.mandate_id,
            "mandate_id",
        )
        principal_id = _require_identifier(
            self.principal_id,
            "principal_id",
        )
        role = _require_identifier(
            self.role,
            "role",
        )
        operations = _normalize_unique_values(
            self.permitted_operations,
            "permitted_operations",
        )
        decisions = _normalize_unique_values(
            self.permitted_decisions,
            "permitted_decisions",
        )

        if type(self.synthetic) is not bool:
            raise TypeError("synthetic must be a strict Boolean")

        if type(self.legal_effect) is not bool:
            raise TypeError("legal_effect must be a strict Boolean")

        if self.synthetic and self.legal_effect:
            raise ValueError(
                "Synthetic mandate cannot claim legal effect"
            )

        active_from = parse_timestamp(
            self.active_from,
            "active_from",
        ).isoformat()
        expires_at = parse_timestamp(
            self.expires_at,
            "expires_at",
        ).isoformat()

        if expires_at <= active_from:
            raise ValueError(
                "expires_at must be later than active_from"
            )

        revoked_at: str | None = None
        if self.revoked_at is not None:
            revoked_at = parse_timestamp(
                self.revoked_at,
                "revoked_at",
            ).isoformat()

            if revoked_at < active_from:
                raise ValueError(
                    "revoked_at cannot precede active_from"
                )

            if revoked_at >= expires_at:
                raise ValueError(
                    "revoked_at must precede expires_at"
                )

        object.__setattr__(self, "mandate_id", mandate_id)
        object.__setattr__(self, "principal_id", principal_id)
        object.__setattr__(self, "role", role)
        object.__setattr__(
            self,
            "permitted_operations",
            operations,
        )
        object.__setattr__(
            self,
            "permitted_decisions",
            decisions,
        )
        object.__setattr__(
            self,
            "active_from",
            active_from,
        )
        object.__setattr__(
            self,
            "expires_at",
            expires_at,
        )
        object.__setattr__(
            self,
            "revoked_at",
            revoked_at,
        )

    def is_active(self, now_iso: str) -> bool:
        now = parse_timestamp(
            now_iso,
            "now_iso",
        ).isoformat()

        if now < self.active_from or now >= self.expires_at:
            return False

        if self.revoked_at is not None and now >= self.revoked_at:
            return False

        return True

    def permits_operation(self, operation_id: str) -> bool:
        normalized = _require_identifier(
            operation_id,
            "operation_id",
        )
        return normalized in self.permitted_operations

    def permits_decision(self, decision: str) -> bool:
        normalized = _require_identifier(
            decision,
            "decision",
        )
        return normalized in self.permitted_decisions

    def to_dict(self) -> dict[str, Any]:
        return {
            "mandate_id": self.mandate_id,
            "principal_id": self.principal_id,
            "role": self.role,
            "permitted_operations": list(
                self.permitted_operations
            ),
            "permitted_decisions": list(
                self.permitted_decisions
            ),
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
            "active_from": self.active_from,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


class MandateRegistry:
    def __init__(self) -> None:
        self._mandates: dict[str, MandateDefinition] = {}
        self._lock = threading.RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._mandates)

    def register(self, mandate: MandateDefinition) -> None:
        if not isinstance(mandate, MandateDefinition):
            raise TypeError(
                "mandate must be a MandateDefinition"
            )

        with self._lock:
            existing = self._mandates.get(
                mandate.mandate_id
            )

            if existing is None:
                self._mandates[mandate.mandate_id] = mandate
                return

            if existing == mandate:
                return

            raise GovernanceConfigurationError(
                "A mandate with the same identifier "
                "has conflicting content"
            )

    def get(
        self,
        mandate_id: str,
    ) -> MandateDefinition | None:
        normalized = _require_identifier(
            mandate_id,
            "mandate_id",
        )

        with self._lock:
            return self._mandates.get(normalized)

    def require(
        self,
        mandate_id: str,
    ) -> MandateDefinition:
        mandate = self.get(mandate_id)

        if mandate is None:
            raise GovernanceConfigurationError(
                "Required mandate is not registered"
            )

        return mandate

    def list_all(self) -> tuple[MandateDefinition, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._mandates.values(),
                    key=lambda mandate: mandate.mandate_id,
                )
            )

    def list_for_principal(
        self,
        principal_id: str,
    ) -> tuple[MandateDefinition, ...]:
        normalized = _require_identifier(
            principal_id,
            "principal_id",
        )

        with self._lock:
            return tuple(
                sorted(
                    (
                        mandate
                        for mandate in self._mandates.values()
                        if mandate.principal_id == normalized
                    ),
                    key=lambda mandate: mandate.mandate_id,
                )
            )

    def is_active(
        self,
        mandate_id: str,
        now_iso: str,
    ) -> bool:
        mandate = self.get(mandate_id)
        return (
            mandate is not None
            and mandate.is_active(now_iso)
        )

    def authorize(
        self,
        mandate_id: str,
        principal_id: str,
        role: str,
        operation_id: str,
        decision: str,
        now_iso: str,
    ) -> bool:
        normalized_mandate_id = _require_identifier(
            mandate_id,
            "mandate_id",
        )
        normalized_principal_id = _require_identifier(
            principal_id,
            "principal_id",
        )
        normalized_role = _require_identifier(
            role,
            "role",
        )
        normalized_operation_id = _require_identifier(
            operation_id,
            "operation_id",
        )
        normalized_decision = _require_identifier(
            decision,
            "decision",
        )
        normalized_now = parse_timestamp(
            now_iso,
            "now_iso",
        ).isoformat()

        with self._lock:
            mandate = self._mandates.get(
                normalized_mandate_id
            )

        if mandate is None:
            return False

        if mandate.principal_id != normalized_principal_id:
            return False

        if mandate.role != normalized_role:
            return False

        if normalized_operation_id not in mandate.permitted_operations:
            return False

        if normalized_decision not in mandate.permitted_decisions:
            return False

        return mandate.is_active(normalized_now)

    @classmethod
    def load_from_yaml(
        cls,
        path: Path | str,
    ) -> MandateRegistry:
        yaml_path = Path(path)

        if not yaml_path.is_file():
            raise GovernanceConfigurationError(
                "Mandate configuration file does not exist"
            )

        try:
            text = yaml_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise GovernanceConfigurationError(
                "Mandate configuration could not be read"
            ) from error

        if not text.strip():
            raise GovernanceConfigurationError(
                "Mandate configuration file is empty"
            )

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as error:
            raise GovernanceConfigurationError(
                "Mandate configuration could not be loaded"
            ) from error

        if not isinstance(data, Mapping):
            raise GovernanceConfigurationError(
                "Mandate configuration root must be a mapping"
            )

        allowed_root_fields = {
            "schema_version",
            "mandates",
        }
        unknown_root_fields = sorted(
            set(data) - allowed_root_fields
        )
        if unknown_root_fields:
            raise GovernanceConfigurationError(
                "Mandate configuration contains unknown "
                f"root fields: {', '.join(unknown_root_fields)}"
            )

        schema_version = str(
            data.get("schema_version", "")
        ).strip()
        if not schema_version:
            raise GovernanceConfigurationError(
                "Mandate configuration requires schema_version"
            )
        if schema_version != MANDATE_SCHEMA_VERSION:
            raise GovernanceConfigurationError(
                "Mandate configuration schema version is unsupported"
            )

        raw_mandates = data.get("mandates")
        if not isinstance(raw_mandates, Mapping):
            raise GovernanceConfigurationError(
                "Mandate configuration requires a mandates mapping"
            )
        if not raw_mandates:
            raise GovernanceConfigurationError(
                "Mandate configuration must define at least one mandate"
            )

        required_fields = {
            "principal_id",
            "role",
            "permitted_operations",
            "permitted_decisions",
            "synthetic",
            "legal_effect",
            "active_from",
            "expires_at",
        }
        allowed_fields = required_fields | {"revoked_at"}
        registry = cls()
        normalized_ids: set[str] = set()

        for raw_mandate_id, specification in raw_mandates.items():
            if not isinstance(raw_mandate_id, str):
                raise GovernanceConfigurationError(
                    "Mandate identifiers must be strings"
                )

            mandate_id = raw_mandate_id.strip()
            if not mandate_id:
                raise GovernanceConfigurationError(
                    "Mandate identifiers must not be empty"
                )
            if mandate_id in normalized_ids:
                raise GovernanceConfigurationError(
                    "Mandate identifiers conflict after normalization"
                )
            normalized_ids.add(mandate_id)

            if not isinstance(specification, Mapping):
                raise GovernanceConfigurationError(
                    "Mandate definition must be a mapping"
                )

            specification_fields = set(specification)
            missing_fields = sorted(
                required_fields - specification_fields
            )
            if missing_fields:
                raise GovernanceConfigurationError(
                    "Mandate definition is missing required "
                    f"fields: {', '.join(missing_fields)}"
                )

            unknown_fields = sorted(
                specification_fields - allowed_fields
            )
            if unknown_fields:
                raise GovernanceConfigurationError(
                    "Mandate definition contains unknown "
                    f"fields: {', '.join(unknown_fields)}"
                )

            if type(specification["synthetic"]) is not bool:
                raise GovernanceConfigurationError(
                    "Mandate synthetic must be a YAML Boolean"
                )
            if type(specification["legal_effect"]) is not bool:
                raise GovernanceConfigurationError(
                    "Mandate legal_effect must be a YAML Boolean"
                )

            operations = specification["permitted_operations"]
            decisions = specification["permitted_decisions"]

            if not isinstance(operations, list):
                raise GovernanceConfigurationError(
                    "permitted_operations must be a list"
                )
            if not isinstance(decisions, list):
                raise GovernanceConfigurationError(
                    "permitted_decisions must be a list"
                )
            if any(not isinstance(value, str) for value in operations):
                raise GovernanceConfigurationError(
                    "permitted_operations values must be strings"
                )
            if any(not isinstance(value, str) for value in decisions):
                raise GovernanceConfigurationError(
                    "permitted_decisions values must be strings"
                )

            try:
                definition = MandateDefinition(
                    mandate_id=mandate_id,
                    principal_id=specification["principal_id"],
                    role=specification["role"],
                    permitted_operations=tuple(operations),
                    permitted_decisions=tuple(decisions),
                    synthetic=specification["synthetic"],
                    legal_effect=specification["legal_effect"],
                    active_from=specification["active_from"],
                    expires_at=specification["expires_at"],
                    revoked_at=specification.get("revoked_at"),
                )
            except (TypeError, ValueError) as error:
                raise GovernanceConfigurationError(
                    "Mandate definition is invalid"
                ) from error

            registry.register(definition)

        return registry
