from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import hmac
import json
import math
import re
import threading
from types import MappingProxyType
from typing import Any, Mapping, Protocol
import uuid

HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ALL_ZERO_SHA256 = "0" * 64


class BindingLevel(str, Enum):
    PRIMARY_LEGISLATION = "primary_legislation"
    REGULATION = "regulation"
    DIRECTIVE = "directive"
    NATIONAL_POLICY = "national_policy"
    INSTITUTIONAL_GUIDANCE = "institutional_guidance"
    TECHNICAL_STANDARD = "technical_standard"
    INTERNATIONAL_GUIDANCE = "international_guidance"
    COMPARATIVE_GUIDANCE = "comparative_guidance"
    PROJECT_CONTROL = "project_control"
    SYNTHETIC_TEST_RULE = "synthetic_test_rule"


class ArtifactIntegrityStatus(str, Enum):
    VERIFIED = "verified"
    MISMATCH = "mismatch"
    UNVERIFIED = "unverified"
    CORRUPTED = "corrupted"


class MetadataVerificationStatus(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not_applicable"


class LocatorVerificationStatus(str, Enum):
    VERIFIED_EXACT = "verified_exact"
    VERIFIED_STRUCTURAL = "verified_structural"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not_applicable"


class TranslationStatus(str, Enum):
    OFFICIAL = "official"
    REVIEWED = "reviewed"
    UNREVIEWED = "unreviewed"
    NOT_APPLICABLE = "not_applicable"
    UNRESOLVED = "unresolved"


class LegalReviewStatus(str, Enum):
    NOT_PERFORMED = "not_performed"
    IN_PROGRESS = "in_progress"
    CONFIRMED_APPLICABLE = "confirmed_applicable"
    INAPPLICABLE = "inapplicable"
    QUARANTINED_PENDING_EXTRACTION = "quarantined_pending_extraction"
    NOT_APPLICABLE = "not_applicable"


class ApplicabilityStatus(str, Enum):
    APPLICABLE = "applicable"
    INAPPLICABLE = "inapplicable"
    UNRESOLVED = "unresolved"
    NOT_ASSESSED = "not_assessed"
    NOT_APPLICABLE = "not_applicable"


class ActivationStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"
    DRAFT = "draft"


class FindingSeverity(str, Enum):
    INFO = "info"
    ADVISORY = "advisory"
    WARNING = "warning"
    RESTRICTIVE = "restrictive"
    CRITICAL = "critical"


class PolicyVerdict(str, Enum):
    COMPLIANT = "compliant"
    NONCOMPLIANT = "noncompliant"
    AMBIGUITY = "ambiguity"
    CONFLICT = "conflict"
    POTENTIAL_GAP = "potential_gap"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_APPLICABLE = "not_applicable"
    APPLICABILITY_UNRESOLVED = "applicability_unresolved"
    CONFIGURATION_FAILURE = "configuration_failure"


class EnforcementAction(str, Enum):
    PROCEED = "proceed"
    CONFIRM = "confirm"
    HOLD_FOR_REVIEW = "hold_for_review"
    REQUIRE_APPROVAL = "require_approval"
    MODIFY = "modify"
    BLOCK = "block"
    ABSTAIN = "abstain"


class OperationProtectionClass(str, Enum):
    UNPROTECTED = "unprotected"
    LOW_RISK = "low_risk"
    STANDARD = "standard"
    PROTECTED = "protected"
    HIGH_RISK = "high_risk"
    PROHIBITED_BY_PROJECT_CONTROL = "prohibited_by_project_control"
    RESTRICTED = "restricted"


class FailureBehavior(str, Enum):
    PROCEED = "proceed"
    ABSTAIN = "abstain"
    HOLD_FOR_REVIEW = "hold_for_review"
    BLOCK = "block"
    CONFIGURATION_FAILURE = "configuration_failure"


class EvidenceSufficiency(str, Enum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"
    NOT_ASSESSED = "not_assessed"
    NOT_APPLICABLE = "not_applicable"


class GateStatus(str, Enum):
    PASSED = "passed"
    BLOCKED = "blocked"
    HELD = "held"
    ABSTAINED = "abstained"
    CONFIGURATION_FAILURE = "configuration_failure"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class AuthorizationBasisType(str, Enum):
    GUARDIAN_CONSENT = "guardian_consent"
    STATUTORY_AUTHORITY = "statutory_authority"
    CONTRACTUAL_AUTHORITY = "contractual_authority"
    PUBLIC_TASK = "public_task"
    PROJECT_FIXTURE = "project_fixture"


class GovernanceError(Exception):
    pass


class GovernanceConfigurationError(GovernanceError):
    pass


class InvalidPolicyRecordError(GovernanceError):
    pass


class DuplicatePolicyRecordError(GovernanceError):
    pass


class PolicyRecordNotFoundError(GovernanceError):
    pass


class PolicyRecordAmbiguityError(GovernanceError):
    pass


class InvalidOperationConfigurationError(GovernanceError):
    pass


class UnknownOperationError(GovernanceError):
    pass


class DuplicateEvaluatorError(GovernanceError):
    pass


class MissingEvaluatorsError(GovernanceError):
    pass


def _require_text(value: Any, field_name: str, error_type: type[Exception] = ValueError) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must not be empty")
    return value.strip()


def _require_bool(value: Any, field_name: str, error_type: type[Exception] = ValueError) -> bool:
    if type(value) is not bool:
        raise error_type(f"{field_name} must be a strict Boolean")
    return value


def _require_enum(value: Any, enum_type: type[Enum], field_name: str, error_type: type[Exception] = TypeError) -> Any:
    if not isinstance(value, enum_type):
        raise error_type(f"{field_name} must be a {enum_type.__name__}")
    return value


def _normalize_unique_tuple(
    values: Any,
    field_name: str,
    *,
    allow_empty: bool = True,
    error_type: type[Exception] = ValueError,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise error_type(f"{field_name} must be a tuple")
    normalized = tuple(_require_text(v, field_name, error_type) for v in values)
    if not allow_empty and not normalized:
        raise error_type(f"{field_name} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise error_type(f"{field_name} cannot contain duplicates")
    return tuple(sorted(normalized))


def _parse_iso_datetime(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty ISO 8601 timestamp string")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _validate_hex_sha256(
    value: str,
    field_name: str,
    *,
    allow_empty_content: bool = False,
) -> str:
    if not isinstance(value, str) or HEX_64_PATTERN.fullmatch(value) is None:
        raise InvalidPolicyRecordError(
            f"{field_name} must be a 64-character lowercase SHA-256 digest"
        )
    if value == ALL_ZERO_SHA256:
        raise InvalidPolicyRecordError(f"{field_name} cannot be all zeros")
    if not allow_empty_content and value == EMPTY_SHA256:
        raise InvalidPolicyRecordError(f"{field_name} cannot use the empty-content digest")
    return value


def _normalized_mapping(value: Mapping[Any, Any], freeze: bool) -> Any:
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        if key in normalized:
            raise ValueError("Governance mapping keys collide after string normalization")
        normalized[key] = deep_freeze(raw_value) if freeze else _sanitize_for_serialization(raw_value)
    return MappingProxyType(normalized) if freeze else normalized


def deep_freeze(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        raise TypeError("Set types are prohibited in canonical governance model structures")
    if isinstance(value, Mapping):
        return _normalized_mapping(value, True)
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ValueError("NaN and Infinity are forbidden in governance structures")
    return value


def _sanitize_for_serialization(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (set, frozenset)):
        raise TypeError("Set types are prohibited in canonical governance serialization")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ValueError("NaN and Infinity are forbidden in canonical serialization")
    if isinstance(value, Mapping):
        return _normalized_mapping(value, False)
    if isinstance(value, (tuple, list)):
        return [_sanitize_for_serialization(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _sanitize_for_serialization(to_dict())
    return value


def to_canonical_json(data: Any) -> str:
    return json.dumps(
        _sanitize_for_serialization(data),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


class IdentifierProvider(Protocol):
    def new_id(self, prefix: str) -> str:
        ...


class UUIDIdentifierProvider:
    def new_id(self, prefix: str) -> str:
        return f"{_require_text(prefix, 'prefix')}_{uuid.uuid4().hex[:12]}"


class SequentialIdentifierProvider:
    def __init__(self, initial_index: int = 1) -> None:
        if type(initial_index) is not int or initial_index <= 0:
            raise ValueError("initial_index must be a positive integer")
        self._index = initial_index
        self._lock = threading.Lock()

    def new_id(self, prefix: str) -> str:
        normalized = _require_text(prefix, "prefix")
        with self._lock:
            value = f"{normalized}_{self._index:06d}"
            self._index += 1
        return value


@dataclass(frozen=True, slots=True)
class ContentSafetyResult:
    evaluated: bool
    is_safe: bool | None
    finding_codes: tuple[str, ...]
    evaluator_id: str
    rationale: str
    timestamp: str | None = None

    def __post_init__(self) -> None:
        _require_bool(self.evaluated, "evaluated")
        if self.is_safe is not None:
            _require_bool(self.is_safe, "is_safe")
        if not self.evaluated and self.is_safe is not None:
            raise ValueError("An unevaluated result cannot declare a safety verdict")
        if self.evaluated and self.is_safe is None:
            raise ValueError("An evaluated result requires a safety verdict")
        codes = _normalize_unique_tuple(self.finding_codes, "finding_codes")
        evaluator_id = _require_text(self.evaluator_id, "evaluator_id")
        rationale = _require_text(self.rationale, "rationale")
        timestamp = None if self.timestamp is None else _parse_iso_datetime(self.timestamp, "timestamp").isoformat()
        object.__setattr__(self, "finding_codes", codes)
        object.__setattr__(self, "evaluator_id", evaluator_id)
        object.__setattr__(self, "rationale", rationale)
        object.__setattr__(self, "timestamp", timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluated": self.evaluated,
            "is_safe": self.is_safe,
            "finding_codes": list(self.finding_codes),
            "evaluator_id": self.evaluator_id,
            "rationale": self.rationale,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True, slots=True)
class PolicyRecordIdentity:
    record_id: str
    version_id: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _require_text(self.record_id, "record_id", InvalidPolicyRecordError))
        object.__setattr__(self, "version_id", _require_text(self.version_id, "version_id", InvalidPolicyRecordError))
        object.__setattr__(self, "source_id", _require_text(self.source_id, "source_id", InvalidPolicyRecordError))

    def __str__(self) -> str:
        return f"{self.record_id}@{self.version_id}#{self.source_id}"

    def to_dict(self) -> dict[str, str]:
        return {"record_id": self.record_id, "version_id": self.version_id, "source_id": self.source_id}


@dataclass(frozen=True, slots=True)
class AuthorizationBasis:
    basis_id: str
    basis_type: AuthorizationBasisType
    subject_category: str
    authority_reference: str
    purposes: tuple[str, ...]
    data_categories: tuple[str, ...]
    processing_operations: tuple[str, ...]
    effective_from: str
    expires_at: str | None
    revoked_at: str | None
    artifact_hash: str
    verifier_id: str
    synthetic: bool
    legal_effect: bool

    def __post_init__(self) -> None:
        basis_id = _require_text(self.basis_id, "basis_id")
        _require_enum(self.basis_type, AuthorizationBasisType, "basis_type")
        subject = _require_text(self.subject_category, "subject_category")
        reference = _require_text(self.authority_reference, "authority_reference")
        verifier = _require_text(self.verifier_id, "verifier_id")
        purposes = _normalize_unique_tuple(self.purposes, "purposes", allow_empty=False)
        categories = _normalize_unique_tuple(self.data_categories, "data_categories", allow_empty=False)
        operations = _normalize_unique_tuple(self.processing_operations, "processing_operations", allow_empty=False)
        synthetic = _require_bool(self.synthetic, "synthetic")
        legal_effect = _require_bool(self.legal_effect, "legal_effect")
        if self.basis_type == AuthorizationBasisType.PROJECT_FIXTURE and (not synthetic or legal_effect):
            raise ValueError("PROJECT_FIXTURE basis requires synthetic=True and legal_effect=False")
        artifact = _validate_hex_sha256(self.artifact_hash, "artifact_hash")
        effective = _parse_iso_datetime(self.effective_from, "effective_from")
        expires = None if self.expires_at is None else _parse_iso_datetime(self.expires_at, "expires_at")
        revoked = None if self.revoked_at is None else _parse_iso_datetime(self.revoked_at, "revoked_at")
        if expires is not None and expires <= effective:
            raise ValueError("expires_at must be strictly greater than effective_from")
        if revoked is not None and revoked < effective:
            raise ValueError("revoked_at cannot precede effective_from")
        if revoked is not None and expires is not None and revoked >= expires:
            raise ValueError("revoked_at must precede expires_at")
        object.__setattr__(self, "basis_id", basis_id)
        object.__setattr__(self, "subject_category", subject)
        object.__setattr__(self, "authority_reference", reference)
        object.__setattr__(self, "verifier_id", verifier)
        object.__setattr__(self, "purposes", purposes)
        object.__setattr__(self, "data_categories", categories)
        object.__setattr__(self, "processing_operations", operations)
        object.__setattr__(self, "artifact_hash", artifact)
        object.__setattr__(self, "effective_from", effective.isoformat())
        object.__setattr__(self, "expires_at", None if expires is None else expires.isoformat())
        object.__setattr__(self, "revoked_at", None if revoked is None else revoked.isoformat())

    def is_valid(self, purpose: str, operation: str, now_iso: str) -> bool:
        normalized_purpose = _require_text(purpose, "purpose")
        normalized_operation = _require_text(operation, "operation")
        now = _parse_iso_datetime(now_iso, "now_iso")
        effective = _parse_iso_datetime(self.effective_from, "effective_from")
        if now < effective:
            return False
        if self.expires_at is not None and now >= _parse_iso_datetime(self.expires_at, "expires_at"):
            return False
        if self.revoked_at is not None and now >= _parse_iso_datetime(self.revoked_at, "revoked_at"):
            return False
        return normalized_purpose in self.purposes and normalized_operation in self.processing_operations

    def to_dict(self) -> dict[str, Any]:
        return {
            "basis_id": self.basis_id,
            "basis_type": self.basis_type.value,
            "subject_category": self.subject_category,
            "authority_reference": self.authority_reference,
            "purposes": list(self.purposes),
            "data_categories": list(self.data_categories),
            "processing_operations": list(self.processing_operations),
            "effective_from": self.effective_from,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "artifact_hash": self.artifact_hash,
            "verifier_id": self.verifier_id,
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }


@dataclass(frozen=True, slots=True)
class PolicyRecord:
    identity: PolicyRecordIdentity
    document_title: str
    authority: str
    jurisdiction: str
    scope: str
    binding_level: BindingLevel
    official_locator: str
    page_start: int | None
    page_end: int | None
    normative_text: str
    reviewed_summary: str
    regulated_actor: str
    protected_subject: str
    conditions: Mapping[str, Any]
    prohibitions: tuple[str, ...]
    exceptions: tuple[str, ...]
    artifact_integrity_status: ArtifactIntegrityStatus
    metadata_verification_status: MetadataVerificationStatus
    locator_verification_status: LocatorVerificationStatus
    translation_status: TranslationStatus
    legal_review_status: LegalReviewStatus
    applicability_status: ApplicabilityStatus
    activation_status: ActivationStatus
    artifact_sha256: str
    normative_unit_sha256: str
    eligible_for_project_enforcement: bool
    eligible_for_national_legal_finding: bool
    national_binding_status: bool
    synthetic_only: bool
    legal_effect: bool
    eligible_for_citation: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.identity, PolicyRecordIdentity):
            raise InvalidPolicyRecordError("identity must be a PolicyRecordIdentity")
        for name, enum_type in (
            ("binding_level", BindingLevel),
            ("artifact_integrity_status", ArtifactIntegrityStatus),
            ("metadata_verification_status", MetadataVerificationStatus),
            ("locator_verification_status", LocatorVerificationStatus),
            ("translation_status", TranslationStatus),
            ("legal_review_status", LegalReviewStatus),
            ("applicability_status", ApplicabilityStatus),
            ("activation_status", ActivationStatus),
        ):
            _require_enum(getattr(self, name), enum_type, name, InvalidPolicyRecordError)
        for name in (
            "document_title", "authority", "jurisdiction", "scope", "official_locator",
            "normative_text", "reviewed_summary", "regulated_actor", "protected_subject",
        ):
            object.__setattr__(self, name, _require_text(getattr(self, name), name, InvalidPolicyRecordError))
        if not isinstance(self.conditions, Mapping):
            raise InvalidPolicyRecordError("conditions must be a mapping")
        prohibitions = _normalize_unique_tuple(self.prohibitions, "prohibitions", error_type=InvalidPolicyRecordError)
        exceptions = _normalize_unique_tuple(self.exceptions, "exceptions", error_type=InvalidPolicyRecordError)
        artifact = _validate_hex_sha256(self.artifact_sha256, "artifact_sha256")
        normative = _validate_hex_sha256(self.normative_unit_sha256, "normative_unit_sha256")
        expected = hashlib.sha256(self.normative_text.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(normative, expected):
            raise InvalidPolicyRecordError("normative_unit_sha256 does not match normative_text")
        for name in (
            "eligible_for_project_enforcement", "eligible_for_national_legal_finding",
            "national_binding_status", "synthetic_only", "legal_effect", "eligible_for_citation",
        ):
            _require_bool(getattr(self, name), name, InvalidPolicyRecordError)
        for name in ("page_start", "page_end"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value <= 0):
                raise InvalidPolicyRecordError(f"{name} must be a positive integer")
        if self.page_start is not None and self.page_end is not None and self.page_end < self.page_start:
            raise InvalidPolicyRecordError("page_end cannot precede page_start")
        if self.binding_level == BindingLevel.PROJECT_CONTROL:
            if self.national_binding_status or self.legal_effect or self.eligible_for_national_legal_finding:
                raise InvalidPolicyRecordError("project_control cannot claim national binding, legal effect, or national legal eligibility")
        if self.eligible_for_national_legal_finding:
            if self.activation_status != ActivationStatus.ACTIVE:
                raise InvalidPolicyRecordError("National legal finding requires active status")
            if self.artifact_integrity_status != ArtifactIntegrityStatus.VERIFIED:
                raise InvalidPolicyRecordError("National legal finding requires verified artifact integrity")
            if self.locator_verification_status != LocatorVerificationStatus.VERIFIED_EXACT:
                raise InvalidPolicyRecordError("National legal finding requires verified exact locator")
            if self.legal_review_status in {LegalReviewStatus.NOT_PERFORMED, LegalReviewStatus.IN_PROGRESS}:
                raise InvalidPolicyRecordError("National legal finding requires completed legal review")
        if self.activation_status != ActivationStatus.ACTIVE and (
            self.eligible_for_project_enforcement or self.eligible_for_national_legal_finding or self.eligible_for_citation
        ):
            raise InvalidPolicyRecordError("Inactive records cannot be eligible for enforcement, legal findings, or citation")
        if self.eligible_for_citation:
            if self.artifact_integrity_status != ArtifactIntegrityStatus.VERIFIED:
                raise InvalidPolicyRecordError("Citation eligibility requires verified artifact integrity")
            if self.locator_verification_status not in {
                LocatorVerificationStatus.VERIFIED_EXACT, LocatorVerificationStatus.VERIFIED_STRUCTURAL
            }:
                raise InvalidPolicyRecordError("Citation eligibility requires a verified locator")
        object.__setattr__(self, "conditions", deep_freeze(self.conditions))
        object.__setattr__(self, "prohibitions", prohibitions)
        object.__setattr__(self, "exceptions", exceptions)
        object.__setattr__(self, "artifact_sha256", artifact)
        object.__setattr__(self, "normative_unit_sha256", normative)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(), "document_title": self.document_title,
            "authority": self.authority, "jurisdiction": self.jurisdiction, "scope": self.scope,
            "binding_level": self.binding_level.value, "official_locator": self.official_locator,
            "page_start": self.page_start, "page_end": self.page_end, "normative_text": self.normative_text,
            "reviewed_summary": self.reviewed_summary, "regulated_actor": self.regulated_actor,
            "protected_subject": self.protected_subject, "conditions": _sanitize_for_serialization(self.conditions),
            "prohibitions": list(self.prohibitions), "exceptions": list(self.exceptions),
            "artifact_integrity_status": self.artifact_integrity_status.value,
            "metadata_verification_status": self.metadata_verification_status.value,
            "locator_verification_status": self.locator_verification_status.value,
            "translation_status": self.translation_status.value, "legal_review_status": self.legal_review_status.value,
            "applicability_status": self.applicability_status.value, "activation_status": self.activation_status.value,
            "artifact_sha256": self.artifact_sha256, "normative_unit_sha256": self.normative_unit_sha256,
            "eligible_for_project_enforcement": self.eligible_for_project_enforcement,
            "eligible_for_national_legal_finding": self.eligible_for_national_legal_finding,
            "national_binding_status": self.national_binding_status, "synthetic_only": self.synthetic_only,
            "legal_effect": self.legal_effect, "eligible_for_citation": self.eligible_for_citation,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self)


@dataclass(frozen=True, slots=True)
class ResolvedOperation:
    operation_id: str
    protection_class: OperationProtectionClass
    pre_gate_required: bool
    post_gate_required: bool
    authorization_basis_required: bool
    allowed_authorization_basis_types: tuple[str, ...]
    required_evaluator_ids: tuple[str, ...]
    required_policy_record_ids: tuple[str, ...]
    approval_required: bool
    approval_role: str | None
    failure_behavior: FailureBehavior

    def __post_init__(self) -> None:
        operation_id = _require_text(self.operation_id, "operation_id", InvalidOperationConfigurationError)
        _require_enum(self.protection_class, OperationProtectionClass, "protection_class", InvalidOperationConfigurationError)
        _require_enum(self.failure_behavior, FailureBehavior, "failure_behavior", InvalidOperationConfigurationError)
        for name in ("pre_gate_required", "post_gate_required", "authorization_basis_required", "approval_required"):
            _require_bool(getattr(self, name), name, InvalidOperationConfigurationError)
        allowed = _normalize_unique_tuple(self.allowed_authorization_basis_types, "allowed_authorization_basis_types", error_type=InvalidOperationConfigurationError)
        evaluators = _normalize_unique_tuple(self.required_evaluator_ids, "required_evaluator_ids", error_type=InvalidOperationConfigurationError)
        records = _normalize_unique_tuple(self.required_policy_record_ids, "required_policy_record_ids", error_type=InvalidOperationConfigurationError)
        unknown = set(allowed) - {item.value for item in AuthorizationBasisType}
        if unknown:
            raise InvalidOperationConfigurationError(f"Unknown authorization basis types: {sorted(unknown)}")
        if self.authorization_basis_required != bool(allowed):
            raise InvalidOperationConfigurationError("Authorization-basis requirement and allowed types are inconsistent")
        role = None if self.approval_role is None else _require_text(self.approval_role, "approval_role", InvalidOperationConfigurationError)
        if self.approval_required != (role is not None):
            raise InvalidOperationConfigurationError("Approval requirement and approval_role are inconsistent")
        protected = {
            OperationProtectionClass.STANDARD, OperationProtectionClass.PROTECTED,
            OperationProtectionClass.HIGH_RISK, OperationProtectionClass.PROHIBITED_BY_PROJECT_CONTROL,
            OperationProtectionClass.RESTRICTED,
        }
        if self.protection_class in protected and self.failure_behavior == FailureBehavior.PROCEED:
            raise InvalidOperationConfigurationError("Protected operations cannot configure failure_behavior=proceed")
        if self.protection_class in {
            OperationProtectionClass.PROTECTED, OperationProtectionClass.HIGH_RISK,
            OperationProtectionClass.PROHIBITED_BY_PROJECT_CONTROL, OperationProtectionClass.RESTRICTED,
        } and not evaluators:
            raise InvalidOperationConfigurationError("Protected operations must configure required evaluators")
        if self.protection_class == OperationProtectionClass.PROHIBITED_BY_PROJECT_CONTROL and self.failure_behavior != FailureBehavior.BLOCK:
            raise InvalidOperationConfigurationError("Prohibited operations must configure failure_behavior=block")
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "allowed_authorization_basis_types", allowed)
        object.__setattr__(self, "required_evaluator_ids", evaluators)
        object.__setattr__(self, "required_policy_record_ids", records)
        object.__setattr__(self, "approval_role", role)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id, "protection_class": self.protection_class.value,
            "pre_gate_required": self.pre_gate_required, "post_gate_required": self.post_gate_required,
            "authorization_basis_required": self.authorization_basis_required,
            "allowed_authorization_basis_types": list(self.allowed_authorization_basis_types),
            "required_evaluator_ids": list(self.required_evaluator_ids),
            "required_policy_record_ids": list(self.required_policy_record_ids),
            "approval_required": self.approval_required, "approval_role": self.approval_role,
            "failure_behavior": self.failure_behavior.value,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self)


@dataclass(frozen=True, slots=True)
class PipelineEvent:
    event_id: str
    timestamp: str
    operation_id: str
    source_node: str
    destination_id: str
    payload_type: str
    payload: Mapping[str, Any]
    authorization_basis: AuthorizationBasis | None = None
    synthetic_flag: bool = True

    def __post_init__(self) -> None:
        for name in ("event_id", "operation_id", "source_node", "destination_id", "payload_type"):
            object.__setattr__(self, name, _require_text(getattr(self, name), name))
        timestamp = _parse_iso_datetime(self.timestamp, "timestamp").isoformat()
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        if self.authorization_basis is not None and not isinstance(self.authorization_basis, AuthorizationBasis):
            raise TypeError("authorization_basis must be an AuthorizationBasis or None")
        _require_bool(self.synthetic_flag, "synthetic_flag")
        frozen = deep_freeze(self.payload)
        to_canonical_json(frozen)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "payload", frozen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id, "timestamp": self.timestamp, "operation_id": self.operation_id,
            "source_node": self.source_node, "destination_id": self.destination_id,
            "payload_type": self.payload_type, "payload": _sanitize_for_serialization(self.payload),
            "authorization_basis": None if self.authorization_basis is None else self.authorization_basis.to_dict(),
            "synthetic_flag": self.synthetic_flag,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self)


@dataclass(frozen=True, slots=True)
class PolicyFinding:
    finding_id: str
    event_id: str
    finding_code: str
    basis_category: BindingLevel
    severity: FindingSeverity
    verdict: PolicyVerdict
    evaluator_id: str
    primary_records: tuple[PolicyRecordIdentity, ...]
    supporting_records: tuple[PolicyRecordIdentity, ...]
    rationale: str
    evidence_sufficiency: EvidenceSufficiency
    deterministic_result: bool
    applicability_details: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name in ("finding_id", "event_id", "finding_code", "evaluator_id", "rationale"):
            object.__setattr__(self, name, _require_text(getattr(self, name), name))
        for name, enum_type in (
            ("basis_category", BindingLevel), ("severity", FindingSeverity),
            ("verdict", PolicyVerdict), ("evidence_sufficiency", EvidenceSufficiency),
        ):
            _require_enum(getattr(self, name), enum_type, name)
        _require_bool(self.deterministic_result, "deterministic_result")
        if not isinstance(self.primary_records, tuple) or not isinstance(self.supporting_records, tuple):
            raise TypeError("record collections must be tuples")
        for identity in self.primary_records + self.supporting_records:
            if not isinstance(identity, PolicyRecordIdentity):
                raise TypeError("record collections must contain PolicyRecordIdentity values")
        primary_keys = [str(item) for item in self.primary_records]
        supporting_keys = [str(item) for item in self.supporting_records]
        if len(primary_keys) != len(set(primary_keys)) or len(supporting_keys) != len(set(supporting_keys)):
            raise ValueError("Policy finding record collections cannot contain duplicates")
        if set(primary_keys) & set(supporting_keys):
            raise ValueError("A policy record cannot be both primary and supporting")
        if not isinstance(self.applicability_details, Mapping):
            raise TypeError("applicability_details must be a mapping")
        object.__setattr__(self, "primary_records", tuple(sorted(self.primary_records, key=str)))
        object.__setattr__(self, "supporting_records", tuple(sorted(self.supporting_records, key=str)))
        object.__setattr__(self, "applicability_details", deep_freeze(self.applicability_details))

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id, "event_id": self.event_id, "finding_code": self.finding_code,
            "basis_category": self.basis_category.value, "severity": self.severity.value,
            "verdict": self.verdict.value, "evaluator_id": self.evaluator_id,
            "primary_records": [item.to_dict() for item in self.primary_records],
            "supporting_records": [item.to_dict() for item in self.supporting_records],
            "rationale": self.rationale, "evidence_sufficiency": self.evidence_sufficiency.value,
            "deterministic_result": self.deterministic_result,
            "applicability_details": _sanitize_for_serialization(self.applicability_details),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self)


@dataclass(frozen=True, slots=True)
class PolicyRecommendation:
    recommendation_id: str
    event_id: str
    recommended_action: EnforcementAction
    mitigation_steps: tuple[str, ...]
    requires_approval: bool
    escalation_role: str | None = None

    def __post_init__(self) -> None:
        recommendation_id = _require_text(self.recommendation_id, "recommendation_id")
        event_id = _require_text(self.event_id, "event_id")
        _require_enum(self.recommended_action, EnforcementAction, "recommended_action")
        steps = _normalize_unique_tuple(self.mitigation_steps, "mitigation_steps")
        _require_bool(self.requires_approval, "requires_approval")
        role = None if self.escalation_role is None else _require_text(self.escalation_role, "escalation_role")
        if self.requires_approval != (role is not None):
            raise ValueError("Approval requirement and escalation_role are inconsistent")
        object.__setattr__(self, "recommendation_id", recommendation_id)
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "mitigation_steps", steps)
        object.__setattr__(self, "escalation_role", role)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id, "event_id": self.event_id,
            "recommended_action": self.recommended_action.value,
            "mitigation_steps": list(self.mitigation_steps), "requires_approval": self.requires_approval,
            "escalation_role": self.escalation_role,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self)


@dataclass(frozen=True, slots=True)
class PolicyEvaluationBundle:
    event_id: str
    operation: ResolvedOperation | None
    findings: tuple[PolicyFinding, ...]
    recommendation: PolicyRecommendation
    unresolved_questions: tuple[str, ...]

    def __post_init__(self) -> None:
        event_id = _require_text(self.event_id, "event_id")
        if self.operation is not None and not isinstance(self.operation, ResolvedOperation):
            raise TypeError("operation must be a ResolvedOperation or None")
        if not isinstance(self.findings, tuple) or any(not isinstance(item, PolicyFinding) for item in self.findings):
            raise TypeError("findings must be a tuple of PolicyFinding values")
        if not isinstance(self.recommendation, PolicyRecommendation):
            raise TypeError("recommendation must be a PolicyRecommendation")
        if self.recommendation.event_id != event_id:
            raise ValueError("Recommendation event identifier does not match evaluation bundle")
        if any(item.event_id != event_id for item in self.findings):
            raise ValueError("Finding event identifier does not match evaluation bundle")
        finding_ids = [item.finding_id for item in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("findings cannot contain duplicate finding IDs")
        questions = _normalize_unique_tuple(self.unresolved_questions, "unresolved_questions")
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "findings", tuple(sorted(self.findings, key=lambda item: item.finding_id)))
        object.__setattr__(self, "unresolved_questions", questions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id, "operation": None if self.operation is None else self.operation.to_dict(),
            "findings": [item.to_dict() for item in self.findings],
            "recommendation": self.recommendation.to_dict(),
            "unresolved_questions": list(self.unresolved_questions),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self)


@dataclass(frozen=True, slots=True)
class GateResult:
    allowed: bool
    status: GateStatus
    operation_id: str
    finding_ids: tuple[str, ...]
    recommendation_id: str | None
    receipt_id: str | None
    rationale: str

    def __post_init__(self) -> None:
        _require_bool(self.allowed, "allowed")
        _require_enum(self.status, GateStatus, "status")
        operation_id = _require_text(self.operation_id, "operation_id")
        finding_ids = _normalize_unique_tuple(self.finding_ids, "finding_ids")
        recommendation_id = None if self.recommendation_id is None else _require_text(self.recommendation_id, "recommendation_id")
        receipt_id = None if self.receipt_id is None else _require_text(self.receipt_id, "receipt_id")
        rationale = _require_text(self.rationale, "rationale")
        if self.allowed != (self.status == GateStatus.PASSED):
            raise ValueError("Gate allowed state is inconsistent with gate status")
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "finding_ids", finding_ids)
        object.__setattr__(self, "recommendation_id", recommendation_id)
        object.__setattr__(self, "receipt_id", receipt_id)
        object.__setattr__(self, "rationale", rationale)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed, "status": self.status.value, "operation_id": self.operation_id,
            "finding_ids": list(self.finding_ids), "recommendation_id": self.recommendation_id,
            "receipt_id": self.receipt_id, "rationale": self.rationale,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self)
