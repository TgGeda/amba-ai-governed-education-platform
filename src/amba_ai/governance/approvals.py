from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import hmac
import re
from typing import Any, Protocol

from amba_ai.governance.mandates import MandateRegistry
from amba_ai.governance.models import (
    GovernanceConfigurationError,
    IdentifierProvider,
    to_canonical_json,
)
from amba_ai.governance.principals import (
    Clock,
    PrincipalRegistry,
    parse_timestamp,
)


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EMPTY_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb924"
    "27ae41e4649b934ca495991b7852b855"
)
ALL_ZERO_SHA256 = "0" * 64


def _require_identifier(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _sha256_material(material: dict[str, Any]) -> str:
    return hashlib.sha256(
        to_canonical_json(material).encode("utf-8")
    ).hexdigest()


def validate_sha256(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if SHA256_PATTERN.fullmatch(normalized) is None:
        raise ValueError(
            f"{field_name} must be a 64-character "
            "lowercase SHA-256 digest"
        )
    if normalized in {EMPTY_SHA256, ALL_ZERO_SHA256}:
        raise ValueError(
            f"{field_name} cannot use an empty-content "
            "or all-zero digest"
        )
    return normalized


def approval_request_semantic_material(
    *,
    event_id: str,
    recommendation_id: str,
    operation_id: str,
    requested_decision: str,
    target_role: str,
    mandate_id: str,
    context_digest: str,
    expires_at: str,
    idempotency_key: str,
    synthetic: bool,
    legal_effect: bool,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "recommendation_id": recommendation_id,
        "operation_id": operation_id,
        "requested_decision": requested_decision,
        "target_role": target_role,
        "mandate_id": mandate_id,
        "context_digest": context_digest,
        "expires_at": expires_at,
        "idempotency_key": idempotency_key,
        "synthetic": synthetic,
        "legal_effect": legal_effect,
    }


def approval_decision_semantic_material(
    *,
    decision_id: str,
    request_id: str,
    principal_id: str,
    mandate_id: str,
    approved: bool,
    rationale: str,
    decided_at: str,
    request_digest: str,
    synthetic: bool,
    legal_effect: bool,
) -> dict[str, Any]:
    return {
        "decision_id": decision_id,
        "request_id": request_id,
        "principal_id": principal_id,
        "mandate_id": mandate_id,
        "approved": approved,
        "rationale": rationale,
        "decided_at": decided_at,
        "request_digest": request_digest,
        "synthetic": synthetic,
        "legal_effect": legal_effect,
    }


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    DUPLICATE = "duplicate"
    CONFIGURATION_FAILURE = "configuration_failure"


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    request_id: str
    event_id: str
    recommendation_id: str
    operation_id: str
    requested_decision: str
    target_role: str
    mandate_id: str
    context_digest: str
    request_digest: str
    created_at: str
    expires_at: str
    idempotency_key: str
    synthetic: bool
    legal_effect: bool

    def __post_init__(self) -> None:
        request_id = _require_identifier(self.request_id, "request_id")
        event_id = _require_identifier(self.event_id, "event_id")
        recommendation_id = _require_identifier(
            self.recommendation_id,
            "recommendation_id",
        )
        operation_id = _require_identifier(self.operation_id, "operation_id")
        requested_decision = _require_identifier(
            self.requested_decision,
            "requested_decision",
        )
        target_role = _require_identifier(self.target_role, "target_role")
        mandate_id = _require_identifier(self.mandate_id, "mandate_id")
        idempotency_key = _require_identifier(
            self.idempotency_key,
            "idempotency_key",
        )
        context_digest = validate_sha256(
            self.context_digest,
            "context_digest",
        )
        request_digest = validate_sha256(
            self.request_digest,
            "request_digest",
        )

        if type(self.synthetic) is not bool or type(self.legal_effect) is not bool:
            raise TypeError("synthetic and legal_effect must be strict Booleans")
        if self.synthetic and self.legal_effect:
            raise ValueError("Synthetic request cannot claim legal effect")

        created_at = parse_timestamp(self.created_at, "created_at").isoformat()
        expires_at = parse_timestamp(self.expires_at, "expires_at").isoformat()
        if expires_at <= created_at:
            raise ValueError("expires_at must be strictly greater than created_at")

        expected_digest = _sha256_material(
            approval_request_semantic_material(
                event_id=event_id,
                recommendation_id=recommendation_id,
                operation_id=operation_id,
                requested_decision=requested_decision,
                target_role=target_role,
                mandate_id=mandate_id,
                context_digest=context_digest,
                expires_at=expires_at,
                idempotency_key=idempotency_key,
                synthetic=self.synthetic,
                legal_effect=self.legal_effect,
            )
        )
        if not hmac.compare_digest(request_digest, expected_digest):
            raise ValueError(
                "request_digest does not match ApprovalRequest semantic content"
            )

        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "recommendation_id", recommendation_id)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "requested_decision", requested_decision)
        object.__setattr__(self, "target_role", target_role)
        object.__setattr__(self, "mandate_id", mandate_id)
        object.__setattr__(self, "context_digest", context_digest)
        object.__setattr__(self, "request_digest", request_digest)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "idempotency_key", idempotency_key)

    @classmethod
    def create(
        cls,
        request_id: str,
        event_id: str,
        recommendation_id: str,
        operation_id: str,
        requested_decision: str,
        target_role: str,
        mandate_id: str,
        context_digest: str,
        created_at: str,
        expires_at: str,
        idempotency_key: str,
        synthetic: bool = True,
        legal_effect: bool = False,
    ) -> ApprovalRequest:
        clean_request_id = _require_identifier(request_id, "request_id")
        clean_event_id = _require_identifier(event_id, "event_id")
        clean_recommendation_id = _require_identifier(
            recommendation_id,
            "recommendation_id",
        )
        clean_operation_id = _require_identifier(operation_id, "operation_id")
        clean_requested_decision = _require_identifier(
            requested_decision,
            "requested_decision",
        )
        clean_target_role = _require_identifier(target_role, "target_role")
        clean_mandate_id = _require_identifier(mandate_id, "mandate_id")
        clean_idempotency_key = _require_identifier(
            idempotency_key,
            "idempotency_key",
        )
        clean_context_digest = validate_sha256(
            context_digest,
            "context_digest",
        )
        created_iso = parse_timestamp(created_at, "created_at").isoformat()
        expires_iso = parse_timestamp(expires_at, "expires_at").isoformat()

        request_digest = _sha256_material(
            approval_request_semantic_material(
                event_id=clean_event_id,
                recommendation_id=clean_recommendation_id,
                operation_id=clean_operation_id,
                requested_decision=clean_requested_decision,
                target_role=clean_target_role,
                mandate_id=clean_mandate_id,
                context_digest=clean_context_digest,
                expires_at=expires_iso,
                idempotency_key=clean_idempotency_key,
                synthetic=synthetic,
                legal_effect=legal_effect,
            )
        )
        return cls(
            request_id=clean_request_id,
            event_id=clean_event_id,
            recommendation_id=clean_recommendation_id,
            operation_id=clean_operation_id,
            requested_decision=clean_requested_decision,
            target_role=clean_target_role,
            mandate_id=clean_mandate_id,
            context_digest=clean_context_digest,
            request_digest=request_digest,
            created_at=created_iso,
            expires_at=expires_iso,
            idempotency_key=clean_idempotency_key,
            synthetic=synthetic,
            legal_effect=legal_effect,
        )

    def to_idempotency_digest(self) -> str:
        return self.request_digest

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "event_id": self.event_id,
            "recommendation_id": self.recommendation_id,
            "operation_id": self.operation_id,
            "requested_decision": self.requested_decision,
            "target_role": self.target_role,
            "mandate_id": self.mandate_id,
            "context_digest": self.context_digest,
            "request_digest": self.request_digest,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "idempotency_key": self.idempotency_key,
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    decision_id: str
    request_id: str
    principal_id: str
    mandate_id: str
    approved: bool
    rationale: str
    decided_at: str
    request_digest: str
    decision_digest: str
    synthetic: bool
    legal_effect: bool

    def __post_init__(self) -> None:
        decision_id = _require_identifier(self.decision_id, "decision_id")
        request_id = _require_identifier(self.request_id, "request_id")
        principal_id = _require_identifier(self.principal_id, "principal_id")
        mandate_id = _require_identifier(self.mandate_id, "mandate_id")
        rationale = _require_identifier(self.rationale, "rationale")
        request_digest = validate_sha256(self.request_digest, "request_digest")
        decision_digest = validate_sha256(self.decision_digest, "decision_digest")

        if type(self.approved) is not bool:
            raise TypeError("approved must be a strict Boolean")
        if type(self.synthetic) is not bool or type(self.legal_effect) is not bool:
            raise TypeError("synthetic and legal_effect must be strict Booleans")
        if self.synthetic and self.legal_effect:
            raise ValueError("Synthetic decision cannot claim legal effect")

        decided_at = parse_timestamp(self.decided_at, "decided_at").isoformat()
        expected_digest = _sha256_material(
            approval_decision_semantic_material(
                decision_id=decision_id,
                request_id=request_id,
                principal_id=principal_id,
                mandate_id=mandate_id,
                approved=self.approved,
                rationale=rationale,
                decided_at=decided_at,
                request_digest=request_digest,
                synthetic=self.synthetic,
                legal_effect=self.legal_effect,
            )
        )
        if not hmac.compare_digest(decision_digest, expected_digest):
            raise ValueError(
                "decision_digest does not match ApprovalDecision semantic content"
            )

        object.__setattr__(self, "decision_id", decision_id)
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "principal_id", principal_id)
        object.__setattr__(self, "mandate_id", mandate_id)
        object.__setattr__(self, "rationale", rationale)
        object.__setattr__(self, "decided_at", decided_at)
        object.__setattr__(self, "request_digest", request_digest)
        object.__setattr__(self, "decision_digest", decision_digest)

    @classmethod
    def create(
        cls,
        *,
        decision_id: str,
        request_id: str,
        principal_id: str,
        mandate_id: str,
        approved: bool,
        rationale: str,
        decided_at: str,
        request_digest: str,
        synthetic: bool = True,
        legal_effect: bool = False,
    ) -> ApprovalDecision:
        clean_decision_id = _require_identifier(decision_id, "decision_id")
        clean_request_id = _require_identifier(request_id, "request_id")
        clean_principal_id = _require_identifier(principal_id, "principal_id")
        clean_mandate_id = _require_identifier(mandate_id, "mandate_id")
        clean_rationale = _require_identifier(rationale, "rationale")
        clean_request_digest = validate_sha256(request_digest, "request_digest")
        decided_iso = parse_timestamp(decided_at, "decided_at").isoformat()
        material = approval_decision_semantic_material(
            decision_id=clean_decision_id,
            request_id=clean_request_id,
            principal_id=clean_principal_id,
            mandate_id=clean_mandate_id,
            approved=approved,
            rationale=clean_rationale,
            decided_at=decided_iso,
            request_digest=clean_request_digest,
            synthetic=synthetic,
            legal_effect=legal_effect,
        )
        return cls(
            decision_id=clean_decision_id,
            request_id=clean_request_id,
            principal_id=clean_principal_id,
            mandate_id=clean_mandate_id,
            approved=approved,
            rationale=clean_rationale,
            decided_at=decided_iso,
            request_digest=clean_request_digest,
            decision_digest=_sha256_material(material),
            synthetic=synthetic,
            legal_effect=legal_effect,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "principal_id": self.principal_id,
            "mandate_id": self.mandate_id,
            "approved": self.approved,
            "rationale": self.rationale,
            "decided_at": self.decided_at,
            "request_digest": self.request_digest,
            "decision_digest": self.decision_digest,
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ApprovalProcessingResult:
    status: ApprovalStatus
    request: ApprovalRequest
    decision: ApprovalDecision | None
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, ApprovalStatus):
            raise TypeError("status must be an ApprovalStatus")
        if not isinstance(self.request, ApprovalRequest):
            raise TypeError("request must be an ApprovalRequest")
        if self.decision is not None and not isinstance(
            self.decision,
            ApprovalDecision,
        ):
            raise TypeError("decision must be an ApprovalDecision or None")
        reason_code = _require_identifier(self.reason_code, "reason_code")
        if self.status in {
            ApprovalStatus.APPROVED,
            ApprovalStatus.DENIED,
            ApprovalStatus.DUPLICATE,
        } and self.decision is None:
            raise ValueError("Decision-bearing approval status requires a decision")
        if self.decision is not None:
            if self.decision.request_id != self.request.request_id:
                raise ValueError("Approval result decision does not match request")
            if not hmac.compare_digest(
                self.decision.request_digest,
                self.request.request_digest,
            ):
                raise ValueError("Approval result decision digest does not match request")
        object.__setattr__(self, "reason_code", reason_code)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "request": self.request.to_dict(),
            "decision": self.decision.to_dict() if self.decision else None,
            "reason_code": self.reason_code,
        }


class ApprovalRepositoryProtocol(Protocol):
    def get_request(self, request_id: str) -> ApprovalRequest | None:
        ...

    def get_request_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> ApprovalRequest | None:
        ...

    def get_decision_by_request(
        self,
        request_id: str,
    ) -> ApprovalDecision | None:
        ...

    def get_decision_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> ApprovalDecision | None:
        ...

    def store_request_and_decision(
        self,
        request: ApprovalRequest,
        decision: ApprovalDecision,
    ) -> None:
        ...


class ApprovalService:
    def __init__(
        self,
        principal_registry: PrincipalRegistry,
        mandate_registry: MandateRegistry,
        approval_repository: ApprovalRepositoryProtocol,
        identifier_provider: IdentifierProvider,
        clock: Clock,
    ) -> None:
        if principal_registry is None:
            raise TypeError("principal_registry is required")
        if mandate_registry is None:
            raise TypeError("mandate_registry is required")
        if approval_repository is None:
            raise TypeError("approval_repository is required")
        if identifier_provider is None:
            raise TypeError("identifier_provider is required")
        if clock is None:
            raise TypeError("clock is required")
        self.principals = principal_registry
        self.mandates = mandate_registry
        self.repository = approval_repository
        self.id_provider = identifier_provider
        self.clock = clock

    def process_approval(
        self,
        request: ApprovalRequest,
        principal_id: str,
        plaintext_secret: str,
        approved: bool,
        rationale: str,
    ) -> ApprovalProcessingResult:
        if not isinstance(request, ApprovalRequest):
            raise TypeError("request must be an ApprovalRequest")
        principal_id = _require_identifier(principal_id, "principal_id")
        if not isinstance(plaintext_secret, str) or not plaintext_secret:
            raise ValueError("plaintext_secret must not be empty")
        if type(approved) is not bool:
            raise TypeError("approved must be a strict Boolean")

        normalized_rationale = str(rationale).strip()
        if not normalized_rationale:
            return ApprovalProcessingResult(
                status=ApprovalStatus.CONFIGURATION_FAILURE,
                request=request,
                decision=None,
                reason_code="RATIONALE_REQUIRED",
            )

        now_iso = parse_timestamp(
            self.clock.now_iso(),
            "clock timestamp",
        ).isoformat()
        expires_at = parse_timestamp(
            request.expires_at,
            "request.expires_at",
        ).isoformat()

        request_by_id = self.repository.get_request(request.request_id)
        request_by_key = self.repository.get_request_by_idempotency_key(
            request.idempotency_key
        )

        if (
            request_by_id is not None
            and request_by_key is not None
            and request_by_id != request_by_key
        ):
            raise GovernanceConfigurationError(
                "Approval request identity and idempotency records are inconsistent"
            )

        existing_request = request_by_id or request_by_key
        if existing_request is not None:
            if not hmac.compare_digest(
                existing_request.request_digest,
                request.request_digest,
            ):
                raise GovernanceConfigurationError(
                    "Conflicting approval request registered under the same "
                    "request_id or idempotency_key"
                )
            existing_decision = self.repository.get_decision_by_request(
                existing_request.request_id
            )
            if existing_decision is None:
                raise GovernanceConfigurationError(
                    "Persisted approval request has no decision"
                )
            return ApprovalProcessingResult(
                status=ApprovalStatus.DUPLICATE,
                request=existing_request,
                decision=existing_decision,
                reason_code="IDEMPOTENT_RETRY",
            )

        if now_iso >= expires_at:
            return ApprovalProcessingResult(
                status=ApprovalStatus.EXPIRED,
                request=request,
                decision=None,
                reason_code="REQUEST_EXPIRED",
            )

        if not self.principals.authenticate(
            principal_id,
            plaintext_secret,
            now_iso,
        ):
            return ApprovalProcessingResult(
                status=ApprovalStatus.CONFIGURATION_FAILURE,
                request=request,
                decision=None,
                reason_code="AUTHENTICATION_FAILED",
            )

        principal = self.principals.require(principal_id)
        if principal.role != request.target_role:
            return ApprovalProcessingResult(
                status=ApprovalStatus.CONFIGURATION_FAILURE,
                request=request,
                decision=None,
                reason_code="ROLE_MISMATCH",
            )

        if not self.mandates.authorize(
            mandate_id=request.mandate_id,
            principal_id=principal_id,
            role=principal.role,
            operation_id=request.operation_id,
            decision=request.requested_decision,
            now_iso=now_iso,
        ):
            return ApprovalProcessingResult(
                status=ApprovalStatus.CONFIGURATION_FAILURE,
                request=request,
                decision=None,
                reason_code="MANDATE_NOT_AUTHORIZED",
            )

        decision = ApprovalDecision.create(
            decision_id=self.id_provider.new_id("appdec"),
            request_id=request.request_id,
            principal_id=principal_id,
            mandate_id=request.mandate_id,
            approved=approved,
            rationale=normalized_rationale,
            decided_at=now_iso,
            request_digest=request.request_digest,
            synthetic=True,
            legal_effect=False,
        )
        self.repository.store_request_and_decision(request, decision)

        return ApprovalProcessingResult(
            status=(ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED),
            request=request,
            decision=decision,
            reason_code="DECISION_RECORDED",
        )
