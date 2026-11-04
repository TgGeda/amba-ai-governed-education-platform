from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

import yaml

from amba_ai.governance.models import (
    deep_freeze,
    to_canonical_json,
)
from amba_ai.standards.y3172_models import (
    Y3172ConfigurationError,
    Y3172Node,
    Y3172_NODE_ORDER,
)


ML_INTENT_SCHEMA_VERSION = "1.0.0"
ML_INTENT_STANDARD_REFERENCE = "ITU-T Y.3172"
ML_INTENT_STANDARD_LOCATOR = "Clause 7.4"
ML_INTENT_MAPPING_TYPE = "interpreted"
DEFAULT_MAX_ML_INTENT_BYTES = 262_144

REQUIRED_ALLOWED_MODEL_ROLES = frozenset(
    {
        "policy_evidence_retrieval",
        "educational_explanation",
        "document_summary",
        "institutional_context_preparation",
        "policy_gap_candidate_identification",
    }
)

REQUIRED_PROHIBITED_MODEL_ROLES = frozenset(
    {
        "runtime_authorization",
        "human_approval_substitution",
        "national_legal_determination",
        "execution_receipt_fabrication",
        "audit_verification_fabrication",
        "readiness_score_authorization",
    }
)

SECURITY_CRITICAL_MODEL_ROLES = frozenset(
    {
        "runtime_authorization",
        "human_approval_substitution",
        "national_legal_determination",
        "citation_fabrication",
        "execution_receipt_fabrication",
        "distribution_acknowledgment_fabrication",
        "audit_verification_fabrication",
        "readiness_score_authorization",
    }
)

_ROLE_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
)

_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "ml_intent",
    }
)

_INTENT_FIELDS = frozenset(
    {
        "intent_id",
        "title",
        "standard_reference",
        "objective",
        "allowed_model_roles",
        "prohibited_model_roles",
        "pipeline",
        "governance",
        "synthetic_scope",
    }
)

_STANDARD_REFERENCE_FIELDS = frozenset(
    {
        "recommendation",
        "locator",
        "mapping_type",
        "conformance_claimed",
    }
)

_PIPELINE_FIELDS = frozenset(
    {
        "required_nodes",
    }
)

_GOVERNANCE_FIELDS = frozenset(
    {
        "deterministic_policy_node_required",
        "human_approval_required_when_configured",
        "typed_execution_required",
        "registered_destination_required",
        "audit_required",
        "readiness_runtime_separation_required",
    }
)

_SYNTHETIC_SCOPE_FIELDS = frozenset(
    {
        "required",
        "legal_effect",
    }
)


def _require_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Y3172ConfigurationError(
            f"{field_name} must be a non-empty string"
        )

    return value.strip()


def _require_mapping(
    value: object,
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Y3172ConfigurationError(
            f"{field_name} must be a mapping"
        )

    return value


def _require_list(
    value: object,
    field_name: str,
) -> list[Any]:
    if not isinstance(value, list):
        raise Y3172ConfigurationError(
            f"{field_name} must be a list"
        )

    return value


def _strict_boolean(
    value: object,
    field_name: str,
) -> bool:
    if type(value) is not bool:
        raise Y3172ConfigurationError(
            f"{field_name} must be a strict Boolean"
        )

    return value


def _reject_unknown_fields(
    mapping: Mapping[str, Any],
    allowed_fields: frozenset[str],
    field_name: str,
) -> None:
    unknown = sorted(
        str(key)
        for key in mapping
        if key not in allowed_fields
    )

    if unknown:
        raise Y3172ConfigurationError(
            f"{field_name} contains unsupported fields: "
            f"{', '.join(unknown)}"
        )


def _require_role(
    value: object,
    field_name: str,
) -> str:
    role = _require_text(
        value,
        field_name,
    )

    if _ROLE_PATTERN.fullmatch(role) is None:
        raise Y3172ConfigurationError(
            f"{field_name} must use lowercase snake_case"
        )

    return role


def _require_role_tuple(
    value: object,
    field_name: str,
) -> tuple[str, ...]:
    items = _require_list(
        value,
        field_name,
    )

    roles = tuple(
        _require_role(
            item,
            f"{field_name}[{index}]",
        )
        for index, item in enumerate(items)
    )

    if len(roles) != len(set(roles)):
        raise Y3172ConfigurationError(
            f"{field_name} must not contain duplicates"
        )

    return roles


def _require_node_tuple(
    value: object,
    field_name: str,
) -> tuple[Y3172Node, ...]:
    items = _require_list(
        value,
        field_name,
    )

    nodes: list[Y3172Node] = []

    for index, item in enumerate(items):
        node_text = _require_text(
            item,
            f"{field_name}[{index}]",
        )

        try:
            node = Y3172Node(node_text)
        except ValueError as exc:
            raise Y3172ConfigurationError(
                f"{field_name}[{index}] is not a recognized "
                "Y.3172 node"
            ) from exc

        nodes.append(node)

    node_tuple = tuple(nodes)

    if len(node_tuple) != len(set(node_tuple)):
        raise Y3172ConfigurationError(
            f"{field_name} must not contain duplicate nodes"
        )

    if node_tuple != Y3172_NODE_ORDER:
        raise Y3172ConfigurationError(
            f"{field_name} must contain exactly "
            "SRC, C, PP, M, P, D, SINK in canonical order"
        )

    return node_tuple


def _resolve_regular_file(
    path: Path | str,
    *,
    allowed_root: Path | str | None,
    max_bytes: int,
) -> Path:
    if type(max_bytes) is not int or max_bytes <= 0:
        raise Y3172ConfigurationError(
            "max_bytes must be a positive integer"
        )

    source = Path(path).expanduser()

    if source.is_symlink():
        raise Y3172ConfigurationError(
            f"ML intent must not be a symbolic link: {source}"
        )

    try:
        resolved_source = source.resolve(
            strict=True
        )
    except FileNotFoundError:
        raise FileNotFoundError(source) from None

    if allowed_root is not None:
        root = Path(
            allowed_root
        ).expanduser()

        try:
            resolved_root = root.resolve(
                strict=True
            )
        except FileNotFoundError:
            raise FileNotFoundError(root) from None

        try:
            resolved_source.relative_to(
                resolved_root
            )
        except ValueError as exc:
            raise Y3172ConfigurationError(
                "ML intent path is outside the allowed root"
            ) from exc

    if not resolved_source.is_file():
        raise Y3172ConfigurationError(
            "ML intent path must identify a regular file"
        )

    file_size = resolved_source.stat().st_size

    if file_size == 0:
        raise Y3172ConfigurationError(
            "ML intent file must not be empty"
        )

    if file_size > max_bytes:
        raise Y3172ConfigurationError(
            "ML intent file exceeds the configured size limit"
        )

    return resolved_source


def _parse_yaml_mapping(
    source: Path,
) -> Mapping[str, Any]:
    try:
        text = source.read_text(
            encoding="utf-8"
        )
    except UnicodeDecodeError as exc:
        raise Y3172ConfigurationError(
            "ML intent must be valid UTF-8"
        ) from exc

    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise Y3172ConfigurationError(
            "ML intent contains invalid YAML"
        ) from exc

    if parsed is None:
        raise Y3172ConfigurationError(
            "ML intent file must not be empty"
        )

    return _require_mapping(
        parsed,
        "ML intent document",
    )


@dataclass(frozen=True, slots=True)
class MLIntentStandardReference:
    recommendation: str
    locator: str
    mapping_type: str
    conformance_claimed: bool

    def __post_init__(self) -> None:
        recommendation = _require_text(
            self.recommendation,
            "recommendation",
        )
        locator = _require_text(
            self.locator,
            "locator",
        )
        mapping_type = _require_text(
            self.mapping_type,
            "mapping_type",
        )

        conformance_claimed = _strict_boolean(
            self.conformance_claimed,
            "conformance_claimed",
        )

        if (
            recommendation
            != ML_INTENT_STANDARD_REFERENCE
        ):
            raise Y3172ConfigurationError(
                "recommendation must be "
                f"{ML_INTENT_STANDARD_REFERENCE}"
            )

        if locator != ML_INTENT_STANDARD_LOCATOR:
            raise Y3172ConfigurationError(
                "locator must be "
                f"{ML_INTENT_STANDARD_LOCATOR}"
            )

        if mapping_type != ML_INTENT_MAPPING_TYPE:
            raise Y3172ConfigurationError(
                "mapping_type must be interpreted"
            )

        if conformance_claimed:
            raise Y3172ConfigurationError(
                "formal ITU-T Y.3172 conformance "
                "must not be claimed"
            )

        object.__setattr__(
            self,
            "recommendation",
            recommendation,
        )
        object.__setattr__(
            self,
            "locator",
            locator,
        )
        object.__setattr__(
            self,
            "mapping_type",
            mapping_type,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation": self.recommendation,
            "locator": self.locator,
            "mapping_type": self.mapping_type,
            "conformance_claimed": False,
        }


@dataclass(frozen=True, slots=True)
class MLIntentGovernanceRequirements:
    deterministic_policy_node_required: bool
    human_approval_required_when_configured: bool
    typed_execution_required: bool
    registered_destination_required: bool
    audit_required: bool
    readiness_runtime_separation_required: bool

    def __post_init__(self) -> None:
        for field_name in (
            "deterministic_policy_node_required",
            "human_approval_required_when_configured",
            "typed_execution_required",
            "registered_destination_required",
            "audit_required",
            "readiness_runtime_separation_required",
        ):
            value = _strict_boolean(
                getattr(self, field_name),
                field_name,
            )

            if not value:
                raise Y3172ConfigurationError(
                    f"{field_name} must remain true"
                )

    def to_dict(self) -> dict[str, bool]:
        return {
            "deterministic_policy_node_required": (
                self.deterministic_policy_node_required
            ),
            "human_approval_required_when_configured": (
                self.human_approval_required_when_configured
            ),
            "typed_execution_required": (
                self.typed_execution_required
            ),
            "registered_destination_required": (
                self.registered_destination_required
            ),
            "audit_required": (
                self.audit_required
            ),
            "readiness_runtime_separation_required": (
                self.readiness_runtime_separation_required
            ),
        }


@dataclass(frozen=True, slots=True)
class MLIntentSyntheticScope:
    required: bool
    legal_effect: bool

    def __post_init__(self) -> None:
        required = _strict_boolean(
            self.required,
            "required",
        )
        legal_effect = _strict_boolean(
            self.legal_effect,
            "legal_effect",
        )

        if not required:
            raise Y3172ConfigurationError(
                "synthetic scope must remain required"
            )

        if legal_effect:
            raise Y3172ConfigurationError(
                "synthetic ML intent must not create legal effect"
            )

    def to_dict(self) -> dict[str, bool]:
        return {
            "required": self.required,
            "legal_effect": self.legal_effect,
        }


@dataclass(frozen=True, slots=True)
class MLIntent:
    schema_version: str
    intent_id: str
    title: str
    objective: str
    standard_reference: MLIntentStandardReference
    allowed_model_roles: tuple[str, ...]
    prohibited_model_roles: tuple[str, ...]
    required_nodes: tuple[Y3172Node, ...]
    governance: MLIntentGovernanceRequirements
    synthetic_scope: MLIntentSyntheticScope
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        schema_version = _require_text(
            self.schema_version,
            "schema_version",
        )

        if schema_version != ML_INTENT_SCHEMA_VERSION:
            raise Y3172ConfigurationError(
                "unsupported ML intent schema version"
            )

        intent_id = _require_text(
            self.intent_id,
            "intent_id",
        )
        title = _require_text(
            self.title,
            "title",
        )
        objective = _require_text(
            self.objective,
            "objective",
        )

        if not isinstance(
            self.standard_reference,
            MLIntentStandardReference,
        ):
            raise TypeError(
                "standard_reference must be an "
                "MLIntentStandardReference"
            )

        if not isinstance(
            self.allowed_model_roles,
            tuple,
        ):
            raise TypeError(
                "allowed_model_roles must be a tuple"
            )

        if not isinstance(
            self.prohibited_model_roles,
            tuple,
        ):
            raise TypeError(
                "prohibited_model_roles must be a tuple"
            )

        allowed_model_roles = tuple(
            _require_role(
                item,
                "allowed_model_roles item",
            )
            for item in self.allowed_model_roles
        )

        prohibited_model_roles = tuple(
            _require_role(
                item,
                "prohibited_model_roles item",
            )
            for item in self.prohibited_model_roles
        )

        if (
            len(allowed_model_roles)
            != len(set(allowed_model_roles))
        ):
            raise Y3172ConfigurationError(
                "allowed_model_roles must not contain duplicates"
            )

        if (
            len(prohibited_model_roles)
            != len(set(prohibited_model_roles))
        ):
            raise Y3172ConfigurationError(
                "prohibited_model_roles must not contain duplicates"
            )

        overlap = sorted(
            set(allowed_model_roles)
            & set(prohibited_model_roles)
        )

        if overlap:
            raise Y3172ConfigurationError(
                "model roles cannot be both allowed and prohibited: "
                f"{', '.join(overlap)}"
            )

        missing_allowed = sorted(
            REQUIRED_ALLOWED_MODEL_ROLES
            - set(allowed_model_roles)
        )

        if missing_allowed:
            raise Y3172ConfigurationError(
                "required allowed model roles are missing: "
                f"{', '.join(missing_allowed)}"
            )

        missing_prohibited = sorted(
            REQUIRED_PROHIBITED_MODEL_ROLES
            - set(prohibited_model_roles)
        )

        if missing_prohibited:
            raise Y3172ConfigurationError(
                "required prohibited model roles are missing: "
                f"{', '.join(missing_prohibited)}"
            )

        if not isinstance(
            self.required_nodes,
            tuple,
        ):
            raise TypeError(
                "required_nodes must be a tuple"
            )

        if self.required_nodes != Y3172_NODE_ORDER:
            raise Y3172ConfigurationError(
                "required_nodes must contain exactly "
                "SRC, C, PP, M, P, D, SINK in canonical order"
            )

        if not isinstance(
            self.governance,
            MLIntentGovernanceRequirements,
        ):
            raise TypeError(
                "governance must be an "
                "MLIntentGovernanceRequirements"
            )

        if not isinstance(
            self.synthetic_scope,
            MLIntentSyntheticScope,
        ):
            raise TypeError(
                "synthetic_scope must be an "
                "MLIntentSyntheticScope"
            )

        if not isinstance(self.metadata, Mapping):
            raise TypeError(
                "metadata must be a mapping"
            )

        frozen_metadata = deep_freeze(
            self.metadata
        )

        object.__setattr__(
            self,
            "schema_version",
            schema_version,
        )
        object.__setattr__(
            self,
            "intent_id",
            intent_id,
        )
        object.__setattr__(
            self,
            "title",
            title,
        )
        object.__setattr__(
            self,
            "objective",
            objective,
        )
        object.__setattr__(
            self,
            "allowed_model_roles",
            allowed_model_roles,
        )
        object.__setattr__(
            self,
            "prohibited_model_roles",
            prohibited_model_roles,
        )
        object.__setattr__(
            self,
            "metadata",
            frozen_metadata,
        )

        to_canonical_json(
            self.to_dict()
        )

    def permits_model_role(
        self,
        role: str,
    ) -> bool:
        normalized_role = _require_role(
            role,
            "role",
        )

        return (
            normalized_role
            in self.allowed_model_roles
            and normalized_role
            not in self.prohibited_model_roles
            and normalized_role
            not in SECURITY_CRITICAL_MODEL_ROLES
        )

    def prohibits_model_role(
        self,
        role: str,
    ) -> bool:
        normalized_role = _require_role(
            role,
            "role",
        )

        return not self.permits_model_role(
            normalized_role
        )

    def require_model_role(
        self,
        role: str,
    ) -> None:
        normalized_role = _require_role(
            role,
            "role",
        )

        if not self.permits_model_role(
            normalized_role
        ):
            raise Y3172ConfigurationError(
                f"model role is not permitted: {normalized_role}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ml_intent": {
                "intent_id": self.intent_id,
                "title": self.title,
                "standard_reference": (
                    self.standard_reference.to_dict()
                ),
                "objective": self.objective,
                "allowed_model_roles": list(
                    self.allowed_model_roles
                ),
                "prohibited_model_roles": list(
                    self.prohibited_model_roles
                ),
                "pipeline": {
                    "required_nodes": [
                        node.value
                        for node in self.required_nodes
                    ],
                },
                "governance": (
                    self.governance.to_dict()
                ),
                "synthetic_scope": (
                    self.synthetic_scope.to_dict()
                ),
                "metadata": self.metadata,
            },
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(
            self.to_dict()
        )


def load_ml_intent(
    path: Path | str,
    *,
    allowed_root: Path | str | None = None,
    max_bytes: int = DEFAULT_MAX_ML_INTENT_BYTES,
) -> MLIntent:
    source = _resolve_regular_file(
        path,
        allowed_root=allowed_root,
        max_bytes=max_bytes,
    )

    document = _parse_yaml_mapping(
        source
    )

    _reject_unknown_fields(
        document,
        _TOP_LEVEL_FIELDS,
        "ML intent document",
    )

    schema_version = _require_text(
        document.get("schema_version"),
        "schema_version",
    )

    intent_mapping = _require_mapping(
        document.get("ml_intent"),
        "ml_intent",
    )

    _reject_unknown_fields(
        intent_mapping,
        _INTENT_FIELDS,
        "ml_intent",
    )

    standard_mapping = _require_mapping(
        intent_mapping.get(
            "standard_reference"
        ),
        "ml_intent.standard_reference",
    )

    _reject_unknown_fields(
        standard_mapping,
        _STANDARD_REFERENCE_FIELDS,
        "ml_intent.standard_reference",
    )

    pipeline_mapping = _require_mapping(
        intent_mapping.get("pipeline"),
        "ml_intent.pipeline",
    )

    _reject_unknown_fields(
        pipeline_mapping,
        _PIPELINE_FIELDS,
        "ml_intent.pipeline",
    )

    governance_mapping = _require_mapping(
        intent_mapping.get("governance"),
        "ml_intent.governance",
    )

    _reject_unknown_fields(
        governance_mapping,
        _GOVERNANCE_FIELDS,
        "ml_intent.governance",
    )

    synthetic_scope_mapping = _require_mapping(
        intent_mapping.get(
            "synthetic_scope"
        ),
        "ml_intent.synthetic_scope",
    )

    _reject_unknown_fields(
        synthetic_scope_mapping,
        _SYNTHETIC_SCOPE_FIELDS,
        "ml_intent.synthetic_scope",
    )

    standard_reference = MLIntentStandardReference(
        recommendation=_require_text(
            standard_mapping.get(
                "recommendation"
            ),
            (
                "ml_intent.standard_reference."
                "recommendation"
            ),
        ),
        locator=_require_text(
            standard_mapping.get("locator"),
            "ml_intent.standard_reference.locator",
        ),
        mapping_type=_require_text(
            standard_mapping.get(
                "mapping_type"
            ),
            (
                "ml_intent.standard_reference."
                "mapping_type"
            ),
        ),
        conformance_claimed=_strict_boolean(
            standard_mapping.get(
                "conformance_claimed"
            ),
            (
                "ml_intent.standard_reference."
                "conformance_claimed"
            ),
        ),
    )

    governance = MLIntentGovernanceRequirements(
        deterministic_policy_node_required=_strict_boolean(
            governance_mapping.get(
                "deterministic_policy_node_required"
            ),
            (
                "ml_intent.governance."
                "deterministic_policy_node_required"
            ),
        ),
        human_approval_required_when_configured=_strict_boolean(
            governance_mapping.get(
                "human_approval_required_when_configured"
            ),
            (
                "ml_intent.governance."
                "human_approval_required_when_configured"
            ),
        ),
        typed_execution_required=_strict_boolean(
            governance_mapping.get(
                "typed_execution_required"
            ),
            (
                "ml_intent.governance."
                "typed_execution_required"
            ),
        ),
        registered_destination_required=_strict_boolean(
            governance_mapping.get(
                "registered_destination_required"
            ),
            (
                "ml_intent.governance."
                "registered_destination_required"
            ),
        ),
        audit_required=_strict_boolean(
            governance_mapping.get(
                "audit_required"
            ),
            "ml_intent.governance.audit_required",
        ),
        readiness_runtime_separation_required=_strict_boolean(
            governance_mapping.get(
                "readiness_runtime_separation_required"
            ),
            (
                "ml_intent.governance."
                "readiness_runtime_separation_required"
            ),
        ),
    )

    synthetic_scope = MLIntentSyntheticScope(
        required=_strict_boolean(
            synthetic_scope_mapping.get(
                "required"
            ),
            "ml_intent.synthetic_scope.required",
        ),
        legal_effect=_strict_boolean(
            synthetic_scope_mapping.get(
                "legal_effect"
            ),
            "ml_intent.synthetic_scope.legal_effect",
        ),
    )

    allowed_model_roles = _require_role_tuple(
        intent_mapping.get(
            "allowed_model_roles"
        ),
        "ml_intent.allowed_model_roles",
    )

    prohibited_model_roles = _require_role_tuple(
        intent_mapping.get(
            "prohibited_model_roles"
        ),
        "ml_intent.prohibited_model_roles",
    )

    required_nodes = _require_node_tuple(
        pipeline_mapping.get(
            "required_nodes"
        ),
        "ml_intent.pipeline.required_nodes",
    )

    return MLIntent(
        schema_version=schema_version,
        intent_id=_require_text(
            intent_mapping.get("intent_id"),
            "ml_intent.intent_id",
        ),
        title=_require_text(
            intent_mapping.get("title"),
            "ml_intent.title",
        ),
        objective=_require_text(
            intent_mapping.get("objective"),
            "ml_intent.objective",
        ),
        standard_reference=standard_reference,
        allowed_model_roles=allowed_model_roles,
        prohibited_model_roles=prohibited_model_roles,
        required_nodes=required_nodes,
        governance=governance,
        synthetic_scope=synthetic_scope,
        metadata={},
    )