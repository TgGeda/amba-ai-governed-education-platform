from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any, Iterator, Mapping

import yaml

from amba_ai.governance.models import (
    FailureBehavior,
    InvalidOperationConfigurationError,
    OperationProtectionClass,
    ResolvedOperation,
    UnknownOperationError,
    to_canonical_json,
)


OPERATION_SCHEMA_VERSION = "1.0.0"
DESTINATION_SCHEMA_VERSION = "1.0.0"
WILDCARD_OPERATION = "*"


def _require_identifier(
    value: str,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise InvalidOperationConfigurationError(
            f"{field_name} must be a string"
        )

    normalized = value.strip()

    if not normalized:
        raise InvalidOperationConfigurationError(
            f"{field_name} must not be empty"
        )

    return normalized


def _normalize_unique_strings(
    values: tuple[str, ...],
    field_name: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise InvalidOperationConfigurationError(
            f"{field_name} must be a tuple"
        )

    normalized = tuple(
        _require_identifier(value, field_name)
        for value in values
    )

    if not allow_empty and not normalized:
        raise InvalidOperationConfigurationError(
            f"{field_name} must not be empty"
        )

    if len(normalized) != len(set(normalized)):
        raise InvalidOperationConfigurationError(
            f"{field_name} cannot contain duplicates"
        )

    return tuple(sorted(normalized))


def _load_yaml_mapping(
    path: Path | str,
    configuration_name: str,
) -> Mapping[str, Any]:
    yaml_path = Path(path)

    if not yaml_path.is_file():
        raise InvalidOperationConfigurationError(
            f"{configuration_name} configuration file does not exist"
        )

    try:
        text = yaml_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise InvalidOperationConfigurationError(
            f"{configuration_name} configuration could not be read"
        ) from error

    if not text.strip():
        raise InvalidOperationConfigurationError(
            f"{configuration_name} configuration file is empty"
        )

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise InvalidOperationConfigurationError(
            f"{configuration_name} configuration could not be parsed"
        ) from error

    if not isinstance(data, Mapping):
        raise InvalidOperationConfigurationError(
            f"{configuration_name} configuration root must be a mapping"
        )

    return data


def _require_exact_fields(
    mapping: Mapping[str, Any],
    *,
    required: set[str],
    allowed: set[str],
    context: str,
) -> None:
    fields = set(mapping)
    missing = sorted(required - fields)
    unknown = sorted(fields - allowed)

    if missing:
        raise InvalidOperationConfigurationError(
            f"{context} is missing required fields: {', '.join(missing)}"
        )

    if unknown:
        raise InvalidOperationConfigurationError(
            f"{context} contains unknown fields: {', '.join(unknown)}"
        )


def _require_schema_version(
    data: Mapping[str, Any],
    expected: str,
    configuration_name: str,
) -> None:
    raw_version = data.get("schema_version")

    if not isinstance(raw_version, str) or not raw_version.strip():
        raise InvalidOperationConfigurationError(
            f"{configuration_name} configuration requires schema_version"
        )

    if raw_version.strip() != expected:
        raise InvalidOperationConfigurationError(
            f"{configuration_name} configuration schema version is unsupported"
        )


@dataclass(frozen=True, slots=True)
class DestinationSpecification:
    destination_id: str
    destination_class: str
    registered: bool
    synthetic: bool
    allowed_operations: tuple[str, ...]

    def __post_init__(self) -> None:
        destination_id = _require_identifier(
            self.destination_id,
            "destination_id",
        )
        destination_class = _require_identifier(
            self.destination_class,
            "destination_class",
        )

        if type(self.registered) is not bool:
            raise InvalidOperationConfigurationError(
                "registered must be a strict Boolean"
            )

        if type(self.synthetic) is not bool:
            raise InvalidOperationConfigurationError(
                "synthetic must be a strict Boolean"
            )

        allowed_operations = _normalize_unique_strings(
            self.allowed_operations,
            "allowed_operations",
            allow_empty=True,
        )

        object.__setattr__(self, "destination_id", destination_id)
        object.__setattr__(self, "destination_class", destination_class)
        object.__setattr__(self, "allowed_operations", allowed_operations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination_id": self.destination_id,
            "destination_class": self.destination_class,
            "registered": self.registered,
            "synthetic": self.synthetic,
            "allowed_operations": list(self.allowed_operations),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class DestinationRules:
    unknown_destination: FailureBehavior
    unregistered_destination: FailureBehavior
    operation_not_allowed: FailureBehavior
    empty_destination: FailureBehavior
    wildcard_operations_allowed: bool

    def __post_init__(self) -> None:
        for field_name in (
            "unknown_destination",
            "unregistered_destination",
            "operation_not_allowed",
            "empty_destination",
        ):
            if not isinstance(getattr(self, field_name), FailureBehavior):
                raise InvalidOperationConfigurationError(
                    f"{field_name} must be a FailureBehavior"
                )

        if type(self.wildcard_operations_allowed) is not bool:
            raise InvalidOperationConfigurationError(
                "wildcard_operations_allowed must be a strict Boolean"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "unknown_destination": self.unknown_destination.value,
            "unregistered_destination": self.unregistered_destination.value,
            "operation_not_allowed": self.operation_not_allowed.value,
            "empty_destination": self.empty_destination.value,
            "wildcard_operations_allowed": self.wildcard_operations_allowed,
        }


class DestinationRegistry:
    def __init__(
        self,
        destinations: Mapping[str, DestinationSpecification],
        destination_rules: DestinationRules,
    ) -> None:
        if not isinstance(destinations, Mapping):
            raise TypeError("destinations must be a mapping")

        if not isinstance(destination_rules, DestinationRules):
            raise TypeError("destination_rules must be DestinationRules")

        normalized: dict[str, DestinationSpecification] = {}

        for raw_id, specification in destinations.items():
            destination_id = _require_identifier(
                raw_id,
                "destination_id",
            )

            if not isinstance(specification, DestinationSpecification):
                raise TypeError(
                    "destination values must be DestinationSpecification"
                )

            if destination_id != specification.destination_id:
                raise InvalidOperationConfigurationError(
                    "Destination mapping key does not match specification identifier"
                )

            if destination_id in normalized:
                raise InvalidOperationConfigurationError(
                    "Destination identifiers conflict after normalization"
                )

            normalized[destination_id] = specification

        if not normalized:
            raise InvalidOperationConfigurationError(
                "Destination registry must contain at least one destination"
            )

        self._destinations = normalized
        self.rules = destination_rules
        self._lock = threading.RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._destinations)

    def __iter__(self) -> Iterator[DestinationSpecification]:
        return iter(self.list_destinations())

    def __contains__(self, destination_id: object) -> bool:
        if not isinstance(destination_id, str) or not destination_id.strip():
            return False

        with self._lock:
            return destination_id.strip() in self._destinations

    @classmethod
    def load_from_yaml(cls, path: Path | str) -> DestinationRegistry:
        data = _load_yaml_mapping(path, "Destination")
        _require_exact_fields(
            data,
            required={"schema_version", "destination_rules", "destinations"},
            allowed={"schema_version", "destination_rules", "destinations"},
            context="Destination configuration",
        )
        _require_schema_version(
            data,
            DESTINATION_SCHEMA_VERSION,
            "Destination",
        )

        raw_rules = data["destination_rules"]
        if not isinstance(raw_rules, Mapping):
            raise InvalidOperationConfigurationError(
                "destination_rules must be a mapping"
            )

        rule_fields = {
            "unknown_destination",
            "unregistered_destination",
            "operation_not_allowed",
            "empty_destination",
            "wildcard_operations_allowed",
        }
        _require_exact_fields(
            raw_rules,
            required=rule_fields,
            allowed=rule_fields,
            context="destination_rules",
        )

        if type(raw_rules["wildcard_operations_allowed"]) is not bool:
            raise InvalidOperationConfigurationError(
                "destination_rules.wildcard_operations_allowed must be a YAML Boolean"
            )

        try:
            rules = DestinationRules(
                unknown_destination=FailureBehavior(
                    raw_rules["unknown_destination"]
                ),
                unregistered_destination=FailureBehavior(
                    raw_rules["unregistered_destination"]
                ),
                operation_not_allowed=FailureBehavior(
                    raw_rules["operation_not_allowed"]
                ),
                empty_destination=FailureBehavior(
                    raw_rules["empty_destination"]
                ),
                wildcard_operations_allowed=(
                    raw_rules["wildcard_operations_allowed"]
                ),
            )
        except (TypeError, ValueError) as error:
            raise InvalidOperationConfigurationError(
                "destination_rules contains an invalid failure behavior"
            ) from error

        raw_destinations = data["destinations"]
        if not isinstance(raw_destinations, Mapping) or not raw_destinations:
            raise InvalidOperationConfigurationError(
                "Destination configuration requires a nonempty destinations mapping"
            )

        required_destination_fields = {
            "destination_class",
            "registered",
            "synthetic",
            "allowed_operations",
        }
        specifications: dict[str, DestinationSpecification] = {}
        normalized_ids: set[str] = set()

        for raw_destination_id, raw_specification in raw_destinations.items():
            destination_id = _require_identifier(
                raw_destination_id,
                "destination_id",
            )

            if destination_id in normalized_ids:
                raise InvalidOperationConfigurationError(
                    "Destination identifiers conflict after normalization"
                )
            normalized_ids.add(destination_id)

            if not isinstance(raw_specification, Mapping):
                raise InvalidOperationConfigurationError(
                    f"Destination '{destination_id}' specification must be a mapping"
                )

            _require_exact_fields(
                raw_specification,
                required=required_destination_fields,
                allowed=required_destination_fields,
                context=f"Destination '{destination_id}' specification",
            )

            if type(raw_specification["registered"]) is not bool:
                raise InvalidOperationConfigurationError(
                    f"Destination '{destination_id}' registered must be a YAML Boolean"
                )

            if type(raw_specification["synthetic"]) is not bool:
                raise InvalidOperationConfigurationError(
                    f"Destination '{destination_id}' synthetic must be a YAML Boolean"
                )

            raw_operations = raw_specification["allowed_operations"]
            if not isinstance(raw_operations, list):
                raise InvalidOperationConfigurationError(
                    f"Destination '{destination_id}' allowed_operations must be a list"
                )

            if any(not isinstance(value, str) for value in raw_operations):
                raise InvalidOperationConfigurationError(
                    f"Destination '{destination_id}' allowed_operations values must be strings"
                )

            try:
                specification = DestinationSpecification(
                    destination_id=destination_id,
                    destination_class=raw_specification["destination_class"],
                    registered=raw_specification["registered"],
                    synthetic=raw_specification["synthetic"],
                    allowed_operations=tuple(raw_operations),
                )
            except (TypeError, ValueError) as error:
                raise InvalidOperationConfigurationError(
                    f"Destination '{destination_id}' specification is invalid"
                ) from error

            if (
                WILDCARD_OPERATION in specification.allowed_operations
                and not rules.wildcard_operations_allowed
            ):
                raise InvalidOperationConfigurationError(
                    f"Destination '{destination_id}' uses a prohibited wildcard operation"
                )

            specifications[destination_id] = specification

        return cls(specifications, rules)

    def get(
        self,
        destination_id: str,
    ) -> DestinationSpecification | None:
        normalized_id = _require_identifier(
            destination_id,
            "destination_id",
        )

        with self._lock:
            return self._destinations.get(normalized_id)

    def require(
        self,
        destination_id: str,
    ) -> DestinationSpecification:
        specification = self.get(destination_id)

        if specification is None:
            raise InvalidOperationConfigurationError(
                "Required destination is not registered"
            )

        return specification

    def is_registered(self, destination_id: str) -> bool:
        specification = self.get(destination_id)
        return specification is not None and specification.registered

    def is_allowed_for_operation(
        self,
        destination_id: str,
        operation_id: str,
    ) -> bool:
        normalized_operation_id = _require_identifier(
            operation_id,
            "operation_id",
        )
        specification = self.get(destination_id)

        if specification is None or not specification.registered:
            return False

        if (
            self.rules.wildcard_operations_allowed
            and WILDCARD_OPERATION in specification.allowed_operations
        ):
            return True

        return normalized_operation_id in specification.allowed_operations

    def list_destinations(self) -> tuple[DestinationSpecification, ...]:
        with self._lock:
            return tuple(
                self._destinations[destination_id]
                for destination_id in sorted(self._destinations)
            )


class OperationRegistry:
    def __init__(
        self,
        operations: Mapping[str, ResolvedOperation],
    ) -> None:
        if not isinstance(operations, Mapping):
            raise TypeError("operations must be a mapping")

        normalized: dict[str, ResolvedOperation] = {}

        for raw_id, operation in operations.items():
            operation_id = _require_identifier(
                raw_id,
                "operation_id",
            )

            if not isinstance(operation, ResolvedOperation):
                raise TypeError(
                    "operation values must be ResolvedOperation instances"
                )

            if operation_id != operation.operation_id:
                raise InvalidOperationConfigurationError(
                    "Operation mapping key does not match operation identifier"
                )

            if operation_id in normalized:
                raise InvalidOperationConfigurationError(
                    "Operation identifiers conflict after normalization"
                )

            normalized[operation_id] = operation

        if not normalized:
            raise InvalidOperationConfigurationError(
                "Operation registry must contain at least one operation"
            )

        self._operations = normalized
        self._lock = threading.RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._operations)

    def __iter__(self) -> Iterator[ResolvedOperation]:
        return iter(self.list_operations())

    def __contains__(self, operation_id: object) -> bool:
        if not isinstance(operation_id, str) or not operation_id.strip():
            return False

        with self._lock:
            return operation_id.strip() in self._operations

    @classmethod
    def load_from_yaml(cls, path: Path | str) -> OperationRegistry:
        data = _load_yaml_mapping(path, "Operation")
        _require_exact_fields(
            data,
            required={"schema_version", "operations"},
            allowed={"schema_version", "operations"},
            context="Operation configuration",
        )
        _require_schema_version(
            data,
            OPERATION_SCHEMA_VERSION,
            "Operation",
        )

        raw_operations = data["operations"]
        if not isinstance(raw_operations, Mapping) or not raw_operations:
            raise InvalidOperationConfigurationError(
                "Operation configuration requires a nonempty operations mapping"
            )

        required_fields = {
            "protection_class",
            "pre_gate_required",
            "post_gate_required",
            "authorization_basis_required",
            "allowed_authorization_basis_types",
            "required_evaluators",
            "required_policy_records",
            "approval_required",
            "approval_role",
            "failure_behavior",
        }
        resolved_operations: dict[str, ResolvedOperation] = {}
        normalized_ids: set[str] = set()

        for raw_operation_id, raw_specification in raw_operations.items():
            operation_id = _require_identifier(
                raw_operation_id,
                "operation_id",
            )

            if operation_id in normalized_ids:
                raise InvalidOperationConfigurationError(
                    "Operation identifiers conflict after normalization"
                )
            normalized_ids.add(operation_id)

            if not isinstance(raw_specification, Mapping):
                raise InvalidOperationConfigurationError(
                    f"Operation '{operation_id}' specification must be a mapping"
                )

            _require_exact_fields(
                raw_specification,
                required=required_fields,
                allowed=required_fields,
                context=f"Operation '{operation_id}' specification",
            )

            for field_name in (
                "pre_gate_required",
                "post_gate_required",
                "authorization_basis_required",
                "approval_required",
            ):
                if type(raw_specification[field_name]) is not bool:
                    raise InvalidOperationConfigurationError(
                        f"Operation '{operation_id}' {field_name} must be a YAML Boolean"
                    )

            approval_role_raw = raw_specification["approval_role"]
            approval_required = raw_specification["approval_required"]

            if approval_required:
                approval_role = _require_identifier(
                    approval_role_raw,
                    "approval_role",
                )
            else:
                if approval_role_raw is not None:
                    raise InvalidOperationConfigurationError(
                        f"Operation '{operation_id}' approval_role must be null when approval is not required"
                    )
                approval_role = None

            try:
                protection_class = OperationProtectionClass(
                    raw_specification["protection_class"]
                )
                failure_behavior = FailureBehavior(
                    raw_specification["failure_behavior"]
                )
            except (TypeError, ValueError) as error:
                raise InvalidOperationConfigurationError(
                    f"Operation '{operation_id}' contains an invalid enum value"
                ) from error

            list_fields = {
                "allowed_authorization_basis_types": (
                    "allowed_authorization_basis_types"
                ),
                "required_evaluators": "required_evaluators",
                "required_policy_records": "required_policy_records",
            }
            normalized_lists: dict[str, tuple[str, ...]] = {}

            for field_name, error_name in list_fields.items():
                raw_values = raw_specification[field_name]

                if not isinstance(raw_values, list):
                    raise InvalidOperationConfigurationError(
                        f"Operation '{operation_id}' {error_name} must be a list"
                    )

                if any(not isinstance(value, str) for value in raw_values):
                    raise InvalidOperationConfigurationError(
                        f"Operation '{operation_id}' {error_name} values must be strings"
                    )

                normalized_lists[field_name] = _normalize_unique_strings(
                    tuple(raw_values),
                    error_name,
                    allow_empty=True,
                )

            if (
                raw_specification["authorization_basis_required"]
                and not normalized_lists["allowed_authorization_basis_types"]
            ):
                raise InvalidOperationConfigurationError(
                    f"Operation '{operation_id}' requires at least one authorization basis type"
                )

            try:
                resolved = ResolvedOperation(
                    operation_id=operation_id,
                    protection_class=protection_class,
                    pre_gate_required=raw_specification["pre_gate_required"],
                    post_gate_required=raw_specification["post_gate_required"],
                    authorization_basis_required=(
                        raw_specification["authorization_basis_required"]
                    ),
                    allowed_authorization_basis_types=(
                        normalized_lists["allowed_authorization_basis_types"]
                    ),
                    required_evaluator_ids=(
                        normalized_lists["required_evaluators"]
                    ),
                    required_policy_record_ids=(
                        normalized_lists["required_policy_records"]
                    ),
                    approval_required=approval_required,
                    approval_role=approval_role,
                    failure_behavior=failure_behavior,
                )
            except (TypeError, ValueError) as error:
                raise InvalidOperationConfigurationError(
                    f"Operation '{operation_id}' specification is invalid"
                ) from error

            resolved_operations[operation_id] = resolved

        return cls(resolved_operations)

    def get(
        self,
        operation_id: str,
    ) -> ResolvedOperation | None:
        normalized_id = _require_identifier(
            operation_id,
            "operation_id",
        )

        with self._lock:
            return self._operations.get(normalized_id)

    def resolve(
        self,
        operation_id: str,
    ) -> ResolvedOperation | None:
        return self.get(operation_id)

    def require(
        self,
        operation_id: str,
    ) -> ResolvedOperation:
        normalized_id = _require_identifier(
            operation_id,
            "operation_id",
        )

        with self._lock:
            operation = self._operations.get(normalized_id)

        if operation is None:
            raise UnknownOperationError(
                f"Operation '{normalized_id}' is not registered"
            )

        return operation

    def contains(self, operation_id: str) -> bool:
        normalized_id = _require_identifier(
            operation_id,
            "operation_id",
        )

        with self._lock:
            return normalized_id in self._operations

    def list_operations(self) -> tuple[ResolvedOperation, ...]:
        with self._lock:
            return tuple(
                self._operations[operation_id]
                for operation_id in sorted(self._operations)
            )
