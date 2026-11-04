from __future__ import annotations

import hashlib
from pathlib import Path
import re
import threading
from typing import Any, Iterator, Mapping

import yaml

from amba_ai.governance.models import (
    ActivationStatus,
    ApplicabilityStatus,
    ArtifactIntegrityStatus,
    BindingLevel,
    DuplicatePolicyRecordError,
    GovernanceConfigurationError,
    LegalReviewStatus,
    LocatorVerificationStatus,
    MetadataVerificationStatus,
    PolicyRecord,
    PolicyRecordAmbiguityError,
    PolicyRecordIdentity,
    PolicyRecordNotFoundError,
    TranslationStatus,
)


SAFEGUARDS_SCHEMA_VERSION = "1.0.0"
_CONTROL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

STABLE_RECORD_ID_MAP: dict[str, str] = {
    "educational_processing": "PROJECT-CONTROL-EDUCATIONAL-PROCESSING-V1",
    "commercial_purchases": "PROJECT-CONTROL-COMMERCIAL-PURCHASES-V1",
    "targeted_advertising": "PROJECT-CONTROL-TARGETED-ADVERTISING-V1",
    "human_review": "PROJECT-CONTROL-HUMAN-REVIEW-V1",
    "restricted_destinations": "PROJECT-CONTROL-RESTRICTED-DESTINATIONS-V1",
    "evidence_integrity": "PROJECT-CONTROL-EVIDENCE-INTEGRITY-V1",
    "readiness_separation": "PROJECT-CONTROL-READINESS-SEPARATION-V1",
    "synthetic_scope": "PROJECT-CONTROL-SYNTHETIC-SCOPE-V1",
}


def _require_text(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise GovernanceConfigurationError(
            f"{field_name} must be a string"
        )

    normalized = value.strip()

    if not normalized:
        raise GovernanceConfigurationError(
            f"{field_name} must not be empty"
        )

    return normalized


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
        raise GovernanceConfigurationError(
            f"{context} is missing required fields: {', '.join(missing)}"
        )

    if unknown:
        raise GovernanceConfigurationError(
            f"{context} contains unknown fields: {', '.join(unknown)}"
        )


def _normalize_rule_text(value: Any, field_name: str) -> str:
    raw = _require_text(value, field_name)
    normalized = " ".join(raw.split())

    if not normalized:
        raise GovernanceConfigurationError(
            f"{field_name} normalized text must not be empty"
        )

    return normalized


def _stable_record_id(control_name: str) -> str:
    stable = STABLE_RECORD_ID_MAP.get(control_name)

    if stable is not None:
        return stable

    if _CONTROL_NAME_PATTERN.fullmatch(control_name) is None:
        raise GovernanceConfigurationError(
            "Control identifiers must use lowercase snake_case"
        )

    return (
        "PROJECT-CONTROL-"
        + control_name.upper().replace("_", "-")
        + "-V1"
    )


class PolicyRecordRegistry:
    def __init__(self) -> None:
        self._records: dict[str, PolicyRecord] = {}
        self._lock = threading.RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def __iter__(self) -> Iterator[PolicyRecord]:
        return iter(self.list_all())

    def __contains__(self, identity: object) -> bool:
        if not isinstance(identity, PolicyRecordIdentity):
            return False

        with self._lock:
            return str(identity) in self._records

    def register(self, record: PolicyRecord) -> None:
        if not isinstance(record, PolicyRecord):
            raise TypeError("record must be a PolicyRecord")

        identity_key = str(record.identity).strip()

        if not identity_key:
            raise GovernanceConfigurationError(
                "Policy record identity must not be empty"
            )

        with self._lock:
            existing = self._records.get(identity_key)

            if existing is None:
                self._records[identity_key] = record
                return

            if existing == record:
                return

            raise DuplicatePolicyRecordError(
                f"Record identity '{identity_key}' is already registered "
                "with conflicting content"
            )

    def get(
        self,
        identity: PolicyRecordIdentity,
    ) -> PolicyRecord | None:
        if not isinstance(identity, PolicyRecordIdentity):
            raise TypeError("identity must be a PolicyRecordIdentity")

        with self._lock:
            return self._records.get(str(identity))

    def require(
        self,
        identity: PolicyRecordIdentity,
    ) -> PolicyRecord:
        record = self.get(identity)

        if record is None:
            raise PolicyRecordNotFoundError(
                f"Policy record '{identity}' is not registered"
            )

        return record

    def get_versions(
        self,
        record_id: str,
    ) -> tuple[PolicyRecord, ...]:
        normalized_id = _require_text(record_id, "record_id")

        with self._lock:
            matches = tuple(
                record
                for record in self._records.values()
                if record.identity.record_id == normalized_id
            )

        return tuple(
            sorted(matches, key=lambda record: str(record.identity))
        )

    def get_active_by_record_id(
        self,
        record_id: str,
    ) -> PolicyRecord | None:
        normalized_id = _require_text(record_id, "record_id")
        active = tuple(
            record
            for record in self.get_versions(normalized_id)
            if record.activation_status == ActivationStatus.ACTIVE
        )

        if not active:
            return None

        if len(active) > 1:
            active_identities = ", ".join(
                str(record.identity) for record in active
            )
            raise PolicyRecordAmbiguityError(
                f"Record ID '{normalized_id}' has multiple active versions: "
                f"{active_identities}"
            )

        return active[0]

    def require_active_by_record_id(
        self,
        record_id: str,
    ) -> PolicyRecord:
        normalized_id = _require_text(record_id, "record_id")
        record = self.get_active_by_record_id(normalized_id)

        if record is None:
            raise PolicyRecordNotFoundError(
                f"No active record is registered for record ID '{normalized_id}'"
            )

        return record

    def list_all(self) -> tuple[PolicyRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._records.values(),
                    key=lambda record: str(record.identity),
                )
            )

    def list_active(self) -> tuple[PolicyRecord, ...]:
        return tuple(
            record
            for record in self.list_all()
            if record.activation_status == ActivationStatus.ACTIVE
        )

    def list_quarantined(self) -> tuple[PolicyRecord, ...]:
        return tuple(
            record
            for record in self.list_all()
            if record.activation_status == ActivationStatus.QUARANTINED
        )

    def eligible_for_project_enforcement(
        self,
        identity: PolicyRecordIdentity,
    ) -> bool:
        record = self.get(identity)
        return bool(
            record is not None
            and record.activation_status == ActivationStatus.ACTIVE
            and record.eligible_for_project_enforcement
        )

    def eligible_for_national_legal_finding(
        self,
        identity: PolicyRecordIdentity,
    ) -> bool:
        record = self.get(identity)
        return bool(
            record is not None
            and record.activation_status == ActivationStatus.ACTIVE
            and record.eligible_for_national_legal_finding
        )

    def eligible_for_citation(
        self,
        identity: PolicyRecordIdentity,
    ) -> bool:
        record = self.get(identity)

        return bool(
            record is not None
            and record.activation_status == ActivationStatus.ACTIVE
            and record.eligible_for_citation
            and record.artifact_integrity_status
            == ArtifactIntegrityStatus.VERIFIED
            and record.locator_verification_status
            in {
                LocatorVerificationStatus.VERIFIED_EXACT,
                LocatorVerificationStatus.VERIFIED_STRUCTURAL,
            }
        )

    @classmethod
    def load_from_safeguards_yaml(
        cls,
        path: Path | str,
    ) -> PolicyRecordRegistry:
        yaml_path = Path(path)

        if not yaml_path.is_file():
            raise GovernanceConfigurationError(
                "Safeguards configuration file does not exist"
            )

        try:
            raw_bytes = yaml_path.read_bytes()
        except OSError as error:
            raise GovernanceConfigurationError(
                "Safeguards configuration could not be read"
            ) from error

        if not raw_bytes.strip():
            raise GovernanceConfigurationError(
                "Safeguards configuration file is empty"
            )

        artifact_sha256 = hashlib.sha256(raw_bytes).hexdigest()

        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeError as error:
            raise GovernanceConfigurationError(
                "Safeguards configuration must be UTF-8"
            ) from error

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as error:
            raise GovernanceConfigurationError(
                "Safeguards configuration contains malformed YAML"
            ) from error

        if not isinstance(data, Mapping):
            raise GovernanceConfigurationError(
                "Safeguards configuration root must be a mapping"
            )

        required_root_fields = {
            "schema_version",
            "policy_id",
            "policy_version",
            "authority",
            "scope",
            "binding_level",
            "national_binding_status",
            "synthetic_only",
            "legal_effect",
            "controls",
        }
        _require_exact_fields(
            data,
            required=required_root_fields,
            allowed=required_root_fields,
            context="Safeguards configuration",
        )

        schema_version = _require_text(
            data["schema_version"],
            "schema_version",
        )
        if schema_version != SAFEGUARDS_SCHEMA_VERSION:
            raise GovernanceConfigurationError(
                "Safeguards configuration schema version is unsupported"
            )

        for field_name in (
            "national_binding_status",
            "synthetic_only",
            "legal_effect",
        ):
            if type(data[field_name]) is not bool:
                raise GovernanceConfigurationError(
                    f"Safeguards {field_name} must be a YAML Boolean"
                )

        if data["binding_level"] != BindingLevel.PROJECT_CONTROL.value:
            raise GovernanceConfigurationError(
                "Safeguards binding_level must be project_control"
            )

        if data["national_binding_status"] is not False:
            raise GovernanceConfigurationError(
                "Safeguards national_binding_status must be False"
            )

        if data["synthetic_only"] is not True:
            raise GovernanceConfigurationError(
                "Safeguards synthetic_only must be True"
            )

        if data["legal_effect"] is not False:
            raise GovernanceConfigurationError(
                "Safeguards legal_effect must be False"
            )

        policy_id = _require_text(data["policy_id"], "policy_id")
        policy_version = _require_text(
            data["policy_version"],
            "policy_version",
        )
        authority = _require_text(data["authority"], "authority")
        scope = _require_text(data["scope"], "scope")

        controls = data["controls"]
        if not isinstance(controls, Mapping) or not controls:
            raise GovernanceConfigurationError(
                "Safeguards controls must be a nonempty mapping"
            )

        registry = cls()
        normalized_control_names: set[str] = set()
        generated_record_ids: set[str] = set()

        for raw_control_name, specification in sorted(
            controls.items(),
            key=lambda item: str(item[0]),
        ):
            control_name = _require_text(
                raw_control_name,
                "control identifier",
            )

            if _CONTROL_NAME_PATTERN.fullmatch(control_name) is None:
                raise GovernanceConfigurationError(
                    "Control identifiers must use lowercase snake_case"
                )

            if control_name in normalized_control_names:
                raise GovernanceConfigurationError(
                    "Control identifiers conflict after normalization"
                )
            normalized_control_names.add(control_name)

            if not isinstance(specification, Mapping):
                raise GovernanceConfigurationError(
                    f"Control '{control_name}' specification must be a mapping"
                )

            _require_exact_fields(
                specification,
                required={"locator", "rule"},
                allowed={"locator", "rule"},
                context=f"Control '{control_name}' specification",
            )

            locator = _require_text(
                specification["locator"],
                f"Control '{control_name}' locator",
            )
            normative_text = _normalize_rule_text(
                specification["rule"],
                f"Control '{control_name}' rule",
            )
            normative_unit_sha256 = hashlib.sha256(
                normative_text.encode("utf-8")
            ).hexdigest()
            record_id = _stable_record_id(control_name)

            if record_id in generated_record_ids:
                raise GovernanceConfigurationError(
                    "Controls generate duplicate stable record identifiers"
                )
            generated_record_ids.add(record_id)

            try:
                identity = PolicyRecordIdentity(
                    record_id=record_id,
                    version_id=policy_version,
                    source_id=policy_id,
                )
                record = PolicyRecord(
                    identity=identity,
                    document_title=policy_id,
                    authority=authority,
                    jurisdiction="project_sandbox",
                    scope=scope,
                    binding_level=BindingLevel.PROJECT_CONTROL,
                    official_locator=locator,
                    page_start=None,
                    page_end=None,
                    normative_text=normative_text,
                    reviewed_summary=(
                        "Synthesized project control rule for "
                        f"{control_name}"
                    ),
                    regulated_actor="Amba-Gov sandbox components",
                    protected_subject="synthetic education participants",
                    conditions={},
                    prohibitions=(),
                    exceptions=(),
                    artifact_integrity_status=(
                        ArtifactIntegrityStatus.VERIFIED
                    ),
                    metadata_verification_status=(
                        MetadataVerificationStatus.VERIFIED
                    ),
                    locator_verification_status=(
                        LocatorVerificationStatus.VERIFIED_STRUCTURAL
                    ),
                    translation_status=TranslationStatus.NOT_APPLICABLE,
                    legal_review_status=LegalReviewStatus.NOT_APPLICABLE,
                    applicability_status=ApplicabilityStatus.APPLICABLE,
                    activation_status=ActivationStatus.ACTIVE,
                    artifact_sha256=artifact_sha256,
                    normative_unit_sha256=normative_unit_sha256,
                    eligible_for_project_enforcement=True,
                    eligible_for_national_legal_finding=False,
                    national_binding_status=False,
                    synthetic_only=True,
                    legal_effect=False,
                    eligible_for_citation=True,
                )
            except (TypeError, ValueError) as error:
                raise GovernanceConfigurationError(
                    f"Control '{control_name}' produced an invalid policy record"
                ) from error

            registry.register(record)

        return registry
