"""Registry for Amba-Gov's interpreted ITU-T Y.3172 mapping.

This module loads and validates the repository mapping at:

    kb/mappings/y3172_mapping.yaml

The registry is descriptive. It does not:

- execute pipeline nodes;
- verify that referenced Python symbols exist;
- assert that documented behavior occurred at runtime;
- upgrade implementation statuses;
- establish legal authority;
- establish formal ITU-T Y.3172 conformance;
- establish ITU certification.

Runtime claims require separate executed evidence and tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

import yaml

from amba_ai.governance.models import (
    deep_freeze,
    to_canonical_json,
)
from amba_ai.standards.y3172_models import (
    AMBA_GOV_Y3172_INTERPRETATION_ID,
    Y3172ConfigurationError,
    Y3172Node,
    Y3172_NODE_ORDER,
)


DEFAULT_MAX_MAPPING_BYTES = 1_048_576

EXPECTED_RECOMMENDATION = "ITU-T Y.3172"


class Y3172MappingType(str, Enum):
    """Permitted relationship between Y.3172 and an Amba-Gov component."""

    INTERPRETED = "interpreted"
    PROJECT_EXTENSION = "project_extension"


class Y3172ImplementationStatus(str, Enum):
    """Conservative implementation-evidence vocabulary.

    These values describe implementation availability, coverage, and
    verification evidence. They do not imply formal ITU-T Y.3172
    conformance, complete ML orchestration, ITU certification, or legal
    authority.

    Status meanings:

    PLANNED
        The mapped behavior is designed or configured, but no corresponding
        implementation has been established.

    PARTIAL
        Only part of the mapped behavior is implemented, without stronger
        executed verification evidence.

    IMPLEMENTED_UNVERIFIED
        The mapped implementation exists, but executed verification evidence
        has not been established.

    PARTIALLY_IMPLEMENTED_UNIT_VERIFIED
        Only part of the mapped behavior is implemented, and the implemented
        portion has executed unit-test evidence. End-to-end operational
        behavior remains unverified.

    IMPLEMENTED_UNIT_VERIFIED
        The mapped implementation has executed unit-test evidence, but
        end-to-end operational behavior remains unverified.

    VERIFIED_FOR_DEFINED_SCOPE
        The mapped behavior has executed evidence for an explicitly bounded
        Amba-Gov project scope.

    NOT_OPERATIONALLY_VERIFIED
        A documentary mapping exists, but runtime operation has not been
        demonstrated.

    EXISTING_NOT_OPERATIONALLY_VERIFIED_IN_THIS_MAPPING
        The referenced component exists independently, but this mapping has
        not established executed operational evidence connecting that
        component to the mapped Y.3172 function.
    """

    PLANNED = "planned"

    PARTIAL = "partial"

    IMPLEMENTED_UNVERIFIED = (
        "implemented_unverified"
    )

    PARTIALLY_IMPLEMENTED_UNIT_VERIFIED = (
        "partially_implemented_unit_verified"
    )

    IMPLEMENTED_UNIT_VERIFIED = (
        "implemented_unit_verified"
    )

    VERIFIED_FOR_DEFINED_SCOPE = (
        "verified_for_defined_scope"
    )

    NOT_OPERATIONALLY_VERIFIED = (
        "not_operationally_verified"
    )

    EXISTING_NOT_OPERATIONALLY_VERIFIED_IN_THIS_MAPPING = (
        "existing_not_operationally_verified_in_this_mapping"
    )


class Y3172ReferenceVerificationStatus(str, Enum):
    """Verification state of a documentary code reference."""

    DECLARED = "declared"
    VERIFIED = "verified"
    UNRESOLVED = "unresolved"


def _require_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Y3172ConfigurationError(
            f"{field_name} must be a non-empty string"
        )
    return value.strip()


def _optional_text(
    value: object | None,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


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


def _unique_text_tuple(
    value: object,
    field_name: str,
) -> tuple[str, ...]:
    items = _require_list(value, field_name)

    normalized = tuple(
        _require_text(
            item,
            f"{field_name}[{index}]",
        )
        for index, item in enumerate(items)
    )

    if len(normalized) != len(set(normalized)):
        raise Y3172ConfigurationError(
            f"{field_name} must not contain duplicates"
        )

    return normalized


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
            f"Y.3172 mapping must not be a symbolic link: {source}"
        )

    try:
        resolved_source = source.resolve(strict=True)
    except FileNotFoundError:
        raise FileNotFoundError(source) from None

    if allowed_root is not None:
        root = Path(allowed_root).expanduser()

        try:
            resolved_root = root.resolve(strict=True)
        except FileNotFoundError:
            raise FileNotFoundError(root) from None

        try:
            resolved_source.relative_to(resolved_root)
        except ValueError as exc:
            raise Y3172ConfigurationError(
                "Y.3172 mapping path is outside the allowed root"
            ) from exc

    if not resolved_source.is_file():
        raise Y3172ConfigurationError(
            f"Y.3172 mapping must be a regular file: {resolved_source}"
        )

    size = resolved_source.stat().st_size

    if size == 0:
        raise Y3172ConfigurationError(
            "Y.3172 mapping file must not be empty"
        )

    if size > max_bytes:
        raise Y3172ConfigurationError(
            "Y.3172 mapping file exceeds the configured size limit"
        )

    return resolved_source


def _parse_yaml_mapping(
    source: Path,
) -> Mapping[str, Any]:
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise Y3172ConfigurationError(
            "Y.3172 mapping must be valid UTF-8"
        ) from exc

    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise Y3172ConfigurationError(
            "Y.3172 mapping contains invalid YAML"
        ) from exc

    if parsed is None:
        raise Y3172ConfigurationError(
            "Y.3172 mapping file must not be empty"
        )

    return _require_mapping(
        parsed,
        "Y.3172 mapping root",
    )


def _enum_value(
    enum_type: type[Enum],
    value: object,
    field_name: str,
) -> Enum:
    text = _require_text(value, field_name)

    try:
        return enum_type(text)
    except ValueError as exc:
        allowed = ", ".join(
            str(item.value)
            for item in enum_type
        )
        raise Y3172ConfigurationError(
            f"{field_name} must be one of: {allowed}"
        ) from exc


def _read_first(
    mapping: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    field_name: str,
    required: bool = True,
) -> Any:
    present = [
        key
        for key in keys
        if key in mapping
    ]

    if len(present) > 1:
        raise Y3172ConfigurationError(
            f"{field_name} is declared using conflicting aliases: "
            f"{', '.join(present)}"
        )

    if present:
        return mapping[present[0]]

    if required:
        raise Y3172ConfigurationError(
            f"{field_name} is required"
        )

    return None


@dataclass(frozen=True, slots=True)
class Y3172CodeReference:
    """Documentary link from a mapping node to repository code.

    The registry does not import or execute the referenced symbol.
    """

    reference: str
    verification_status: Y3172ReferenceVerificationStatus = (
        Y3172ReferenceVerificationStatus.DECLARED
    )
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        reference = _require_text(
            self.reference,
            "reference",
        )

        if not isinstance(
            self.verification_status,
            Y3172ReferenceVerificationStatus,
        ):
            raise TypeError(
                "verification_status must be a "
                "Y3172ReferenceVerificationStatus"
            )

        evidence_ids = tuple(
            _require_text(
                item,
                "evidence_ids item",
            )
            for item in self.evidence_ids
        )

        if len(evidence_ids) != len(set(evidence_ids)):
            raise Y3172ConfigurationError(
                "evidence_ids must not contain duplicates"
            )

        if (
            self.verification_status
            is Y3172ReferenceVerificationStatus.VERIFIED
            and not evidence_ids
        ):
            raise Y3172ConfigurationError(
                "verified code reference requires evidence_ids"
            )

        object.__setattr__(
            self,
            "reference",
            reference,
        )
        object.__setattr__(
            self,
            "evidence_ids",
            evidence_ids,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "verification_status": (
                self.verification_status.value
            ),
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class Y3172NodeDefinition:
    """One canonical node in the interpreted Amba-Gov mapping."""

    node: Y3172Node
    official_locator: str
    official_function: str
    amba_component: str
    mapping_type: Y3172MappingType
    implementation_status: Y3172ImplementationStatus
    code_references: tuple[Y3172CodeReference, ...] = ()
    limitations: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.node, Y3172Node):
            raise TypeError(
                "node must be a Y3172Node"
            )

        official_locator = _require_text(
            self.official_locator,
            "official_locator",
        )
        official_function = _require_text(
            self.official_function,
            "official_function",
        )
        amba_component = _require_text(
            self.amba_component,
            "amba_component",
        )

        if not isinstance(
            self.mapping_type,
            Y3172MappingType,
        ):
            raise TypeError(
                "mapping_type must be a Y3172MappingType"
            )

        if not isinstance(
            self.implementation_status,
            Y3172ImplementationStatus,
        ):
            raise TypeError(
                "implementation_status must be a "
                "Y3172ImplementationStatus"
            )

        if not isinstance(
            self.code_references,
            tuple,
        ):
            raise TypeError(
                "code_references must be a tuple"
            )

        if any(
            not isinstance(item, Y3172CodeReference)
            for item in self.code_references
        ):
            raise TypeError(
                "code_references must contain "
                "Y3172CodeReference objects"
            )

        references = tuple(
            item.reference
            for item in self.code_references
        )

        if len(references) != len(set(references)):
            raise Y3172ConfigurationError(
                "code_references must not contain duplicates"
            )

        if not isinstance(self.limitations, tuple):
            raise TypeError(
                "limitations must be a tuple"
            )

        limitations = tuple(
            _require_text(
                item,
                "limitations item",
            )
            for item in self.limitations
        )

        if len(limitations) != len(set(limitations)):
            raise Y3172ConfigurationError(
                "limitations must not contain duplicates"
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
            "official_locator",
            official_locator,
        )
        object.__setattr__(
            self,
            "official_function",
            official_function,
        )
        object.__setattr__(
            self,
            "amba_component",
            amba_component,
        )
        object.__setattr__(
            self,
            "limitations",
            limitations,
        )
        object.__setattr__(
            self,
            "metadata",
            frozen_metadata,
        )

        to_canonical_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node.value,
            "official_locator": self.official_locator,
            "official_function": self.official_function,
            "amba_component": self.amba_component,
            "mapping_type": self.mapping_type.value,
            "implementation_status": (
                self.implementation_status.value
            ),
            "code_references": [
                item.to_dict()
                for item in self.code_references
            ],
            "limitations": list(self.limitations),
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class Y3172ProjectExtension:
    """Amba-Gov extension that is not an ITU-T Y.3172 requirement.

    ``rationale`` is optional because the authoritative mapping may identify
    an extension without yet providing a reviewed explanatory rationale.

    An absent rationale is preserved as ``None``. It must not be replaced by
    fabricated text or inferred from the extension name.
    """

    extension_id: str
    name: str
    rationale: str | None = None
    classification: str = "amba_gov_extension"
    evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        extension_id = _require_text(
            self.extension_id,
            "extension_id",
        )
        name = _require_text(
            self.name,
            "name",
        )
        rationale = _optional_text(
            self.rationale,
            "rationale",
        )
        classification = _require_text(
            self.classification,
            "classification",
        )

        if classification != "amba_gov_extension":
            raise Y3172ConfigurationError(
                "project extension classification must be "
                "'amba_gov_extension'"
            )

        if not isinstance(self.evidence_ids, tuple):
            raise TypeError(
                "evidence_ids must be a tuple"
            )

        evidence_ids = tuple(
            _require_text(
                item,
                "evidence_ids item",
            )
            for item in self.evidence_ids
        )

        if len(evidence_ids) != len(set(evidence_ids)):
            raise Y3172ConfigurationError(
                "extension evidence_ids must not contain duplicates"
            )

        if not isinstance(self.limitations, tuple):
            raise TypeError(
                "limitations must be a tuple"
            )

        limitations = tuple(
            _require_text(
                item,
                "limitations item",
            )
            for item in self.limitations
        )

        if len(limitations) != len(set(limitations)):
            raise Y3172ConfigurationError(
                "extension limitations must not contain duplicates"
            )

        if rationale is None and not limitations:
            limitations = (
                "No reviewed extension rationale is recorded "
                "in the mapping.",
            )

        object.__setattr__(
            self,
            "extension_id",
            extension_id,
        )
        object.__setattr__(
            self,
            "name",
            name,
        )
        object.__setattr__(
            self,
            "rationale",
            rationale,
        )
        object.__setattr__(
            self,
            "classification",
            classification,
        )
        object.__setattr__(
            self,
            "evidence_ids",
            evidence_ids,
        )
        object.__setattr__(
            self,
            "limitations",
            limitations,
        )

        to_canonical_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "extension_id": self.extension_id,
            "name": self.name,
            "rationale": self.rationale,
            "classification": self.classification,
            "evidence_ids": list(self.evidence_ids),
            "limitations": list(self.limitations),
        }

@dataclass(frozen=True, slots=True)
class Y3172MappingIdentity:
    """Identity and claim boundary of the interpreted mapping."""

    recommendation: str
    edition: str
    approval_date: str
    persistent_uri: str
    interpretation_id: str = (
        AMBA_GOV_Y3172_INTERPRETATION_ID
    )
    mapping_type: str = "application_level_interpreted"
    formal_conformance_claimed: bool = False
    certification_claimed: bool = False
    legal_authority_created: bool = False

    def __post_init__(self) -> None:
        recommendation = _require_text(
            self.recommendation,
            "recommendation",
        )
        edition = _require_text(
            self.edition,
            "edition",
        )
        approval_date = _require_text(
            self.approval_date,
            "approval_date",
        )
        persistent_uri = _require_text(
            self.persistent_uri,
            "persistent_uri",
        )
        interpretation_id = _require_text(
            self.interpretation_id,
            "interpretation_id",
        )
        mapping_type = _require_text(
            self.mapping_type,
            "mapping_type",
        )

        if recommendation != EXPECTED_RECOMMENDATION:
            raise Y3172ConfigurationError(
                f"recommendation must be {EXPECTED_RECOMMENDATION}"
            )

        if (
            interpretation_id
            != AMBA_GOV_Y3172_INTERPRETATION_ID
        ):
            raise Y3172ConfigurationError(
                "interpretation_id does not match the registered "
                "Amba-Gov interpretation"
            )

        if mapping_type != "application_level_interpreted":
            raise Y3172ConfigurationError(
                "mapping_type must be "
                "'application_level_interpreted'"
            )

        for field_name in (
            "formal_conformance_claimed",
            "certification_claimed",
            "legal_authority_created",
        ):
            value = getattr(self, field_name)

            if type(value) is not bool:
                raise TypeError(
                    f"{field_name} must be a strict Boolean"
                )

            if value:
                raise Y3172ConfigurationError(
                    f"{field_name} must remain false"
                )

        object.__setattr__(
            self,
            "recommendation",
            recommendation,
        )
        object.__setattr__(
            self,
            "edition",
            edition,
        )
        object.__setattr__(
            self,
            "approval_date",
            approval_date,
        )
        object.__setattr__(
            self,
            "persistent_uri",
            persistent_uri,
        )
        object.__setattr__(
            self,
            "interpretation_id",
            interpretation_id,
        )
        object.__setattr__(
            self,
            "mapping_type",
            mapping_type,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation": self.recommendation,
            "edition": self.edition,
            "approval_date": self.approval_date,
            "persistent_uri": self.persistent_uri,
            "interpretation_id": self.interpretation_id,
            "mapping_type": self.mapping_type,
            "formal_conformance_claimed": False,
            "certification_claimed": False,
            "legal_authority_created": False,
        }


@dataclass(frozen=True, slots=True)
class Y3172Registry:
    """Immutable registry of the interpreted Amba-Gov Y.3172 mapping."""

    schema_version: str
    identity: Y3172MappingIdentity
    definitions: tuple[Y3172NodeDefinition, ...]
    extensions: tuple[Y3172ProjectExtension, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        schema_version = _require_text(
            self.schema_version,
            "schema_version",
        )

        if not isinstance(
            self.identity,
            Y3172MappingIdentity,
        ):
            raise TypeError(
                "identity must be a Y3172MappingIdentity"
            )

        if not isinstance(self.definitions, tuple):
            raise TypeError(
                "definitions must be a tuple"
            )

        if any(
            not isinstance(item, Y3172NodeDefinition)
            for item in self.definitions
        ):
            raise TypeError(
                "definitions must contain "
                "Y3172NodeDefinition objects"
            )

        actual_order = tuple(
            item.node
            for item in self.definitions
        )

        if actual_order != Y3172_NODE_ORDER:
            raise Y3172ConfigurationError(
                "definitions must contain exactly "
                "SRC, C, PP, M, P, D, SINK in canonical order"
            )

        if not isinstance(self.extensions, tuple):
            raise TypeError(
                "extensions must be a tuple"
            )

        if any(
            not isinstance(item, Y3172ProjectExtension)
            for item in self.extensions
        ):
            raise TypeError(
                "extensions must contain "
                "Y3172ProjectExtension objects"
            )

        extension_ids = tuple(
            item.extension_id
            for item in self.extensions
        )

        if len(extension_ids) != len(set(extension_ids)):
            raise Y3172ConfigurationError(
                "extension IDs must not contain duplicates"
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
            "metadata",
            frozen_metadata,
        )

        to_canonical_json(self.to_dict())

    @classmethod
    def load_from_yaml(
        cls,
        path: Path | str,
        *,
        allowed_root: Path | str | None = None,
        max_bytes: int = DEFAULT_MAX_MAPPING_BYTES,
    ) -> "Y3172Registry":
        source = _resolve_regular_file(
            path,
            allowed_root=allowed_root,
            max_bytes=max_bytes,
        )
        document = _parse_yaml_mapping(source)

        schema_version = _require_text(
            document.get(
                "schema_version",
                "1.0.0",
            ),
            "schema_version",
        )

        identity_mapping = _read_identity_mapping(
            document
        )
        identity = _parse_identity(
            identity_mapping
        )

        pipeline_value = _read_first(
            document,
            (
                "pipeline",
                "pipeline_mappings",
            ),
            field_name="pipeline",
        )
        pipeline = _require_list(
            pipeline_value,
            "pipeline",
        )

        if len(pipeline) != len(Y3172_NODE_ORDER):
            raise Y3172ConfigurationError(
                "pipeline must contain exactly seven node mappings"
            )

        definitions = tuple(
            _parse_node_definition(
                raw_entry,
                expected_node=expected_node,
                index=index,
            )
            for index, (
                expected_node,
                raw_entry,
            ) in enumerate(
                zip(
                    Y3172_NODE_ORDER,
                    pipeline,
                    strict=True,
                )
            )
        )

        raw_extensions = document.get(
            "extensions",
            [],
        )
        extension_items = _require_list(
            raw_extensions,
            "extensions",
        )

        extensions = tuple(
            _parse_extension(
                item,
                index=index,
            )
            for index, item in enumerate(
                extension_items
            )
        )

        metadata_value = document.get(
            "metadata",
            {},
        )
        metadata = _require_mapping(
            metadata_value,
            "metadata",
        )

        return cls(
            schema_version=schema_version,
            identity=identity,
            definitions=definitions,
            extensions=extensions,
            metadata=metadata,
        )

    def require(
        self,
        node: Y3172Node,
    ) -> Y3172NodeDefinition:
        if not isinstance(node, Y3172Node):
            raise TypeError(
                "node must be a Y3172Node"
            )

        return self.definitions[
            Y3172_NODE_ORDER.index(node)
        ]

    def list(
        self,
    ) -> tuple[Y3172NodeDefinition, ...]:
        return self.definitions

    def require_extension(
        self,
        extension_id: str,
    ) -> Y3172ProjectExtension:
        normalized_id = _require_text(
            extension_id,
            "extension_id",
        )

        for extension in self.extensions:
            if extension.extension_id == normalized_id:
                return extension

        raise KeyError(
            f"unregistered Y.3172 project extension: "
            f"{normalized_id}"
        )

    def verified_code_references(
        self,
    ) -> tuple[Y3172CodeReference, ...]:
        references = [
            reference
            for definition in self.definitions
            for reference in definition.code_references
            if (
                reference.verification_status
                is Y3172ReferenceVerificationStatus.VERIFIED
            )
        ]

        references.sort(
            key=lambda item: item.reference
        )

        return tuple(references)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "standard": self.identity.to_dict(),
            "pipeline": [
                definition.to_dict()
                for definition in self.definitions
            ],
            "extensions": [
                extension.to_dict()
                for extension in self.extensions
            ],
            "metadata": self.metadata,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(
            self.to_dict()
        )


def _read_identity_mapping(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _read_first(
        document,
        (
            "standard",
            "standard_identity",
        ),
        field_name="standard identity",
    )
    return _require_mapping(
        value,
        "standard identity",
    )


def _parse_identity(
    mapping: Mapping[str, Any],
) -> Y3172MappingIdentity:
    recommendation = _read_first(
        mapping,
        (
            "recommendation",
            "standard_id",
        ),
        field_name="recommendation",
    )

    edition = _read_first(
        mapping,
        (
            "edition",
            "version",
        ),
        field_name="edition",
    )

    approval_date = _read_first(
        mapping,
        ("approval_date",),
        field_name="approval_date",
    )

    persistent_uri = _read_first(
        mapping,
        (
            "persistent_uri",
            "persistent_identifier",
        ),
        field_name="persistent_uri",
    )

    interpretation_id = mapping.get(
        "interpretation_id",
        AMBA_GOV_Y3172_INTERPRETATION_ID,
    )

    mapping_type = mapping.get(
        "mapping_type",
        "application_level_interpreted",
    )

    formal_conformance_claimed = _read_first(
        mapping,
        (
            "formal_conformance_claimed",
            "conformance_claimed",
        ),
        field_name="formal_conformance_claimed",
    )

    certification_claimed = mapping.get(
        "certification_claimed",
        False,
    )

    legal_authority_created = mapping.get(
        "legal_authority_created",
        False,
    )

    return Y3172MappingIdentity(
        recommendation=_require_text(
            recommendation,
            "recommendation",
        ),
        edition=_require_text(
            edition,
            "edition",
        ),
        approval_date=_require_text(
            approval_date,
            "approval_date",
        ),
        persistent_uri=_require_text(
            persistent_uri,
            "persistent_uri",
        ),
        interpretation_id=_require_text(
            interpretation_id,
            "interpretation_id",
        ),
        mapping_type=_require_text(
            mapping_type,
            "mapping_type",
        ),
        formal_conformance_claimed=_strict_boolean(
            formal_conformance_claimed,
            "formal_conformance_claimed",
        ),
        certification_claimed=_strict_boolean(
            certification_claimed,
            "certification_claimed",
        ),
        legal_authority_created=_strict_boolean(
            legal_authority_created,
            "legal_authority_created",
        ),
    )


def _parse_code_references(
    mapping: Mapping[str, Any],
    *,
    field_prefix: str,
) -> tuple[Y3172CodeReference, ...]:
    structured = mapping.get(
        "code_references",
    )
    declared = mapping.get(
        "verified_code_references",
    )
    singular = mapping.get(
        "code_reference",
    )

    present = sum(
        value is not None
        for value in (
            structured,
            declared,
            singular,
        )
    )

    if present > 1:
        raise Y3172ConfigurationError(
            f"{field_prefix} declares conflicting code-reference formats"
        )

    if structured is not None:
        items = _require_list(
            structured,
            f"{field_prefix}.code_references",
        )

        parsed: list[Y3172CodeReference] = []

        for index, item in enumerate(items):
            reference_mapping = _require_mapping(
                item,
                f"{field_prefix}.code_references[{index}]",
            )

            status = _enum_value(
                Y3172ReferenceVerificationStatus,
                reference_mapping.get(
                    "verification_status",
                    "declared",
                ),
                (
                    f"{field_prefix}.code_references"
                    f"[{index}].verification_status"
                ),
            )

            evidence_ids = _unique_text_tuple(
                reference_mapping.get(
                    "evidence_ids",
                    [],
                ),
                (
                    f"{field_prefix}.code_references"
                    f"[{index}].evidence_ids"
                ),
            )

            parsed.append(
                Y3172CodeReference(
                    reference=_require_text(
                        reference_mapping.get(
                            "reference"
                        ),
                        (
                            f"{field_prefix}.code_references"
                            f"[{index}].reference"
                        ),
                    ),
                    verification_status=status,
                    evidence_ids=evidence_ids,
                )
            )

        return tuple(parsed)

    if declared is not None:
        references = _unique_text_tuple(
            declared,
            f"{field_prefix}.verified_code_references",
        )

        # Legacy field name is preserved as documentary input only.
        # References are not considered verified without executed evidence IDs.
        return tuple(
            Y3172CodeReference(
                reference=reference,
                verification_status=(
                    Y3172ReferenceVerificationStatus.DECLARED
                ),
            )
            for reference in references
        )

    if singular is not None:
        return (
            Y3172CodeReference(
                reference=_require_text(
                    singular,
                    f"{field_prefix}.code_reference",
                ),
                verification_status=(
                    Y3172ReferenceVerificationStatus.DECLARED
                ),
            ),
        )

    return ()


def _parse_node_definition(
    raw_entry: object,
    *,
    expected_node: Y3172Node,
    index: int,
) -> Y3172NodeDefinition:
    field_prefix = f"pipeline[{index}]"

    mapping = _require_mapping(
        raw_entry,
        field_prefix,
    )

    node_value = _read_first(
        mapping,
        (
            "node_id",
            "node",
        ),
        field_name=f"{field_prefix}.node",
    )

    try:
        node = Y3172Node(
            _require_text(
                node_value,
                f"{field_prefix}.node",
            )
        )
    except ValueError as exc:
        raise Y3172ConfigurationError(
            f"{field_prefix}.node is not a recognized Y.3172 node"
        ) from exc

    if node is not expected_node:
        raise Y3172ConfigurationError(
            f"{field_prefix} must define {expected_node.value}, "
            f"not {node.value}"
        )

    mapping_type = _enum_value(
        Y3172MappingType,
        mapping.get(
            "mapping_type",
            "interpreted",
        ),
        f"{field_prefix}.mapping_type",
    )

    implementation_status = _enum_value(
        Y3172ImplementationStatus,
        mapping.get(
            "implementation_status",
            "implemented_unverified",
        ),
        f"{field_prefix}.implementation_status",
    )

    official_function = _read_first(
        mapping,
        (
            "official_function",
            "official_concept",
        ),
        field_name=f"{field_prefix}.official_function",
    )

    amba_component = _read_first(
        mapping,
        ("amba_component",),
        field_name=f"{field_prefix}.amba_component",
    )

    official_locator = _read_first(
        mapping,
        ("official_locator",),
        field_name=f"{field_prefix}.official_locator",
    )

    code_references = _parse_code_references(
        mapping,
        field_prefix=field_prefix,
    )

    limitations_value = mapping.get(
        "limitations",
        [],
    )

    if isinstance(limitations_value, str):
        limitations = (
            _require_text(
                limitations_value,
                f"{field_prefix}.limitations",
            ),
        )
    else:
        limitations = _unique_text_tuple(
            limitations_value,
            f"{field_prefix}.limitations",
        )

    metadata = _require_mapping(
        mapping.get(
            "metadata",
            {},
        ),
        f"{field_prefix}.metadata",
    )

    return Y3172NodeDefinition(
        node=node,
        official_locator=_require_text(
            official_locator,
            f"{field_prefix}.official_locator",
        ),
        official_function=_require_text(
            official_function,
            f"{field_prefix}.official_function",
        ),
        amba_component=_require_text(
            amba_component,
            f"{field_prefix}.amba_component",
        ),
        mapping_type=mapping_type,
        implementation_status=implementation_status,
        code_references=code_references,
        limitations=limitations,
        metadata=metadata,
    )


def _parse_extension(
    raw_extension: object,
    *,
    index: int,
) -> Y3172ProjectExtension:
    """Parse one explicitly identified Amba-Gov project extension.

    ``extension_id`` is the stable machine identifier.
    ``name`` is the human-readable title.

    ``rationale`` is optional. Its absence is preserved and disclosed through
    the extension limitations rather than repaired with inferred prose.
    """

    field_prefix = f"extensions[{index}]"

    mapping = _require_mapping(
        raw_extension,
        field_prefix,
    )

    raw_extension_id = mapping.get(
        "extension_id"
    )
    raw_name = mapping.get(
        "name"
    )

    if raw_extension_id is None:
        if raw_name is None:
            raise Y3172ConfigurationError(
                f"{field_prefix}.extension_id is required"
            )

        extension_id = _require_text(
            raw_name,
            f"{field_prefix}.extension_id",
        )
    else:
        extension_id = _require_text(
            raw_extension_id,
            f"{field_prefix}.extension_id",
        )

    if raw_name is None:
        name = extension_id
    else:
        name = _require_text(
            raw_name,
            f"{field_prefix}.name",
        )

    rationale = _optional_text(
        mapping.get("rationale"),
        f"{field_prefix}.rationale",
    )

    classification = _require_text(
        mapping.get(
            "classification",
            "amba_gov_extension",
        ),
        f"{field_prefix}.classification",
    )

    evidence_ids = _unique_text_tuple(
        mapping.get(
            "evidence_ids",
            [],
        ),
        f"{field_prefix}.evidence_ids",
    )

    limitations_value = mapping.get(
        "limitations",
        [],
    )

    if isinstance(limitations_value, str):
        limitations = (
            _require_text(
                limitations_value,
                f"{field_prefix}.limitations",
            ),
        )
    else:
        limitations = _unique_text_tuple(
            limitations_value,
            f"{field_prefix}.limitations",
        )

    return Y3172ProjectExtension(
        extension_id=extension_id,
        name=name,
        rationale=rationale,
        classification=classification,
        evidence_ids=evidence_ids,
        limitations=limitations,
    )