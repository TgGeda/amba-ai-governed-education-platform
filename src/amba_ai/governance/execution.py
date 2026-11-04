from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import hmac
from typing import Any, Callable, Mapping, Protocol

from amba_ai.governance.approvals import (
    ApprovalDecision,
    ApprovalRequest,
    validate_sha256,
)
from amba_ai.governance.models import (
    EnforcementAction,
    GovernanceConfigurationError,
    IdentifierProvider,
    PipelineEvent,
    PolicyRecommendation,
    deep_freeze,
    to_canonical_json,
)
from amba_ai.governance.operation_registry import DestinationRegistry
from amba_ai.governance.principals import Clock, parse_timestamp


class ExecutionStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"
    DUPLICATE = "duplicate"
    CANCELLED = "cancelled"


def _require_identifier(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _to_mutable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _to_mutable(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_to_mutable(item) for item in value]
    if isinstance(value, list):
        return [_to_mutable(item) for item in value]
    return value


def _sha256_material(material: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        to_canonical_json(material).encode("utf-8")
    ).hexdigest()


def execution_request_semantic_material(
    *,
    event_id: str,
    operation_id: str,
    recommended_action: EnforcementAction,
    destination_id: str,
    precondition_digest: str,
    recommendation_digest: str,
    approval_decision_id: str | None,
    idempotency_key: str,
    synthetic: bool,
    legal_effect: bool,
) -> dict[str, Any]:
    if not isinstance(recommended_action, EnforcementAction):
        raise TypeError("recommended_action must be an EnforcementAction")
    return {
        "event_id": event_id,
        "operation_id": operation_id,
        "recommended_action": recommended_action.value,
        "destination_id": destination_id,
        "precondition_digest": precondition_digest,
        "recommendation_digest": recommendation_digest,
        "approval_decision_id": approval_decision_id,
        "idempotency_key": idempotency_key,
        "synthetic": synthetic,
        "legal_effect": legal_effect,
    }


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    request_id: str
    event_id: str
    operation_id: str
    recommended_action: EnforcementAction
    destination_id: str
    precondition_digest: str
    recommendation_digest: str
    approval_decision_id: str | None
    idempotency_key: str
    idempotency_digest: str
    created_at: str
    synthetic: bool
    legal_effect: bool

    def __post_init__(self) -> None:
        request_id = _require_identifier(self.request_id, "request_id")
        event_id = _require_identifier(self.event_id, "event_id")
        operation_id = _require_identifier(self.operation_id, "operation_id")
        destination_id = _require_identifier(self.destination_id, "destination_id")
        idempotency_key = _require_identifier(self.idempotency_key, "idempotency_key")
        if not isinstance(self.recommended_action, EnforcementAction):
            raise TypeError("recommended_action must be an EnforcementAction")
        if type(self.synthetic) is not bool or type(self.legal_effect) is not bool:
            raise TypeError("synthetic and legal_effect must be strict Booleans")
        if self.synthetic and self.legal_effect:
            raise ValueError("Synthetic execution request cannot claim legal effect")
        approval_decision_id = None
        if self.approval_decision_id is not None:
            approval_decision_id = _require_identifier(
                self.approval_decision_id,
                "approval_decision_id",
            )
        precondition_digest = validate_sha256(
            self.precondition_digest,
            "precondition_digest",
        )
        recommendation_digest = validate_sha256(
            self.recommendation_digest,
            "recommendation_digest",
        )
        idempotency_digest = validate_sha256(
            self.idempotency_digest,
            "idempotency_digest",
        )
        created_at = parse_timestamp(self.created_at, "created_at").isoformat()
        expected_digest = _sha256_material(
            execution_request_semantic_material(
                event_id=event_id,
                operation_id=operation_id,
                recommended_action=self.recommended_action,
                destination_id=destination_id,
                precondition_digest=precondition_digest,
                recommendation_digest=recommendation_digest,
                approval_decision_id=approval_decision_id,
                idempotency_key=idempotency_key,
                synthetic=self.synthetic,
                legal_effect=self.legal_effect,
            )
        )
        if not hmac.compare_digest(idempotency_digest, expected_digest):
            raise ValueError(
                "idempotency_digest does not match ExecutionRequest semantic content"
            )
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "destination_id", destination_id)
        object.__setattr__(self, "approval_decision_id", approval_decision_id)
        object.__setattr__(self, "idempotency_key", idempotency_key)
        object.__setattr__(self, "precondition_digest", precondition_digest)
        object.__setattr__(self, "recommendation_digest", recommendation_digest)
        object.__setattr__(self, "idempotency_digest", idempotency_digest)
        object.__setattr__(self, "created_at", created_at)

    @classmethod
    def create(
        cls,
        request_id: str,
        event_id: str,
        operation_id: str,
        recommended_action: EnforcementAction,
        destination_id: str,
        precondition_digest: str,
        recommendation_digest: str,
        approval_decision_id: str | None,
        idempotency_key: str,
        created_at: str,
        synthetic: bool = True,
        legal_effect: bool = False,
    ) -> ExecutionRequest:
        clean_request_id = _require_identifier(request_id, "request_id")
        clean_event_id = _require_identifier(event_id, "event_id")
        clean_operation_id = _require_identifier(operation_id, "operation_id")
        clean_destination_id = _require_identifier(destination_id, "destination_id")
        clean_idempotency_key = _require_identifier(idempotency_key, "idempotency_key")
        clean_precondition = validate_sha256(precondition_digest, "precondition_digest")
        clean_recommendation = validate_sha256(
            recommendation_digest,
            "recommendation_digest",
        )
        clean_approval_id = None
        if approval_decision_id is not None:
            clean_approval_id = _require_identifier(
                approval_decision_id,
                "approval_decision_id",
            )
        material = execution_request_semantic_material(
            event_id=clean_event_id,
            operation_id=clean_operation_id,
            recommended_action=recommended_action,
            destination_id=clean_destination_id,
            precondition_digest=clean_precondition,
            recommendation_digest=clean_recommendation,
            approval_decision_id=clean_approval_id,
            idempotency_key=clean_idempotency_key,
            synthetic=synthetic,
            legal_effect=legal_effect,
        )
        return cls(
            request_id=clean_request_id,
            event_id=clean_event_id,
            operation_id=clean_operation_id,
            recommended_action=recommended_action,
            destination_id=clean_destination_id,
            precondition_digest=clean_precondition,
            recommendation_digest=clean_recommendation,
            approval_decision_id=clean_approval_id,
            idempotency_key=clean_idempotency_key,
            idempotency_digest=_sha256_material(material),
            created_at=created_at,
            synthetic=synthetic,
            legal_effect=legal_effect,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "event_id": self.event_id,
            "operation_id": self.operation_id,
            "recommended_action": self.recommended_action.value,
            "destination_id": self.destination_id,
            "precondition_digest": self.precondition_digest,
            "recommendation_digest": self.recommendation_digest,
            "approval_decision_id": self.approval_decision_id,
            "idempotency_key": self.idempotency_key,
            "idempotency_digest": self.idempotency_digest,
            "created_at": self.created_at,
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    receipt_id: str
    request_id: str
    event_id: str
    operation_id: str
    action_executed: EnforcementAction
    status: ExecutionStatus
    executor_id: str
    execution_effect: str
    executed_at: str
    receipt_digest: str
    details: Mapping[str, Any]
    synthetic: bool
    legal_effect: bool

    def __post_init__(self) -> None:
        if not isinstance(self.action_executed, EnforcementAction):
            raise TypeError("action_executed must be an EnforcementAction")
        if not isinstance(self.status, ExecutionStatus):
            raise TypeError("status must be an ExecutionStatus")
        if not isinstance(self.details, Mapping):
            raise TypeError("details must be a mapping")
        if type(self.synthetic) is not bool or type(self.legal_effect) is not bool:
            raise TypeError("synthetic and legal_effect must be strict Booleans")
        if self.synthetic and self.legal_effect:
            raise ValueError("Synthetic execution receipt cannot claim legal effect")
        object.__setattr__(self, "receipt_id", _require_identifier(self.receipt_id, "receipt_id"))
        object.__setattr__(self, "request_id", _require_identifier(self.request_id, "request_id"))
        object.__setattr__(self, "event_id", _require_identifier(self.event_id, "event_id"))
        object.__setattr__(self, "operation_id", _require_identifier(self.operation_id, "operation_id"))
        object.__setattr__(self, "executor_id", _require_identifier(self.executor_id, "executor_id"))
        object.__setattr__(
            self,
            "execution_effect",
            _require_identifier(self.execution_effect, "execution_effect"),
        )
        object.__setattr__(
            self,
            "executed_at",
            parse_timestamp(self.executed_at, "executed_at").isoformat(),
        )
        object.__setattr__(
            self,
            "receipt_digest",
            validate_sha256(self.receipt_digest, "receipt_digest"),
        )
        object.__setattr__(self, "details", deep_freeze(self.details))

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "request_id": self.request_id,
            "event_id": self.event_id,
            "operation_id": self.operation_id,
            "action_executed": self.action_executed.value,
            "status": self.status.value,
            "executor_id": self.executor_id,
            "execution_effect": self.execution_effect,
            "executed_at": self.executed_at,
            "receipt_digest": self.receipt_digest,
            "details": _to_mutable(self.details),
            "synthetic": self.synthetic,
            "legal_effect": self.legal_effect,
        }


@dataclass(frozen=True, slots=True)
class ReviewQueueReceipt:
    receipt_id: str
    request_id: str
    event_id: str
    queue_destination_id: str
    enqueued_at: str
    receipt_digest: str
    reason_code: str
    details: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.details, Mapping):
            raise TypeError("details must be a mapping")
        object.__setattr__(self, "receipt_id", _require_identifier(self.receipt_id, "receipt_id"))
        object.__setattr__(self, "request_id", _require_identifier(self.request_id, "request_id"))
        object.__setattr__(self, "event_id", _require_identifier(self.event_id, "event_id"))
        object.__setattr__(
            self,
            "queue_destination_id",
            _require_identifier(self.queue_destination_id, "queue_destination_id"),
        )
        object.__setattr__(self, "reason_code", _require_identifier(self.reason_code, "reason_code"))
        object.__setattr__(
            self,
            "enqueued_at",
            parse_timestamp(self.enqueued_at, "enqueued_at").isoformat(),
        )
        object.__setattr__(
            self,
            "receipt_digest",
            validate_sha256(self.receipt_digest, "receipt_digest"),
        )
        object.__setattr__(self, "details", deep_freeze(self.details))

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "request_id": self.request_id,
            "event_id": self.event_id,
            "queue_destination_id": self.queue_destination_id,
            "enqueued_at": self.enqueued_at,
            "receipt_digest": self.receipt_digest,
            "reason_code": self.reason_code,
            "details": _to_mutable(self.details),
        }


@dataclass(frozen=True, slots=True)
class DistributionAcknowledgment:
    acknowledgment_id: str
    execution_receipt_id: str
    destination_id: str
    disposition: str
    acknowledged_at: str
    acknowledgment_digest: str

    def __post_init__(self) -> None:
        disposition = _require_identifier(self.disposition, "disposition")
        if disposition != "DELIVERED":
            raise ValueError("disposition must be DELIVERED")
        object.__setattr__(
            self,
            "acknowledgment_id",
            _require_identifier(self.acknowledgment_id, "acknowledgment_id"),
        )
        object.__setattr__(
            self,
            "execution_receipt_id",
            _require_identifier(self.execution_receipt_id, "execution_receipt_id"),
        )
        object.__setattr__(
            self,
            "destination_id",
            _require_identifier(self.destination_id, "destination_id"),
        )
        object.__setattr__(self, "disposition", disposition)
        object.__setattr__(
            self,
            "acknowledged_at",
            parse_timestamp(self.acknowledged_at, "acknowledged_at").isoformat(),
        )
        object.__setattr__(
            self,
            "acknowledgment_digest",
            validate_sha256(self.acknowledgment_digest, "acknowledgment_digest"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "acknowledgment_id": self.acknowledgment_id,
            "execution_receipt_id": self.execution_receipt_id,
            "destination_id": self.destination_id,
            "disposition": self.disposition,
            "acknowledged_at": self.acknowledged_at,
            "acknowledgment_digest": self.acknowledgment_digest,
        }


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    request: ExecutionRequest
    execution_receipt: ExecutionReceipt | None
    review_queue_receipt: ReviewQueueReceipt | None
    distribution_acknowledgment: DistributionAcknowledgment | None
    duplicate: bool

    def __post_init__(self) -> None:
        if not isinstance(self.request, ExecutionRequest):
            raise TypeError("request must be an ExecutionRequest")
        if type(self.duplicate) is not bool:
            raise TypeError("duplicate must be a strict Boolean")
        has_execution = self.execution_receipt is not None
        has_review = self.review_queue_receipt is not None
        if has_execution == has_review:
            raise ValueError(
                "ExecutionResult must contain exactly one execution receipt or review queue receipt"
            )
        if self.execution_receipt is not None:
            receipt = self.execution_receipt
            if receipt.request_id != self.request.request_id:
                raise ValueError("Execution receipt request identifier does not match ExecutionRequest")
            if receipt.event_id != self.request.event_id:
                raise ValueError("Execution receipt event identifier does not match ExecutionRequest")
            if receipt.operation_id != self.request.operation_id:
                raise ValueError("Execution receipt operation identifier does not match ExecutionRequest")
        if self.review_queue_receipt is not None:
            receipt = self.review_queue_receipt
            if receipt.request_id != self.request.request_id:
                raise ValueError("Review receipt request identifier does not match ExecutionRequest")
            if receipt.event_id != self.request.event_id:
                raise ValueError("Review receipt event identifier does not match ExecutionRequest")
        acknowledgment = self.distribution_acknowledgment
        receipt = self.execution_receipt
        successful_delivery = (
            receipt is not None
            and receipt.status == ExecutionStatus.SUCCEEDED
            and receipt.action_executed == EnforcementAction.PROCEED
        )
        if successful_delivery and acknowledgment is None:
            raise ValueError(
                "Successful delivery requires a distribution acknowledgment"
            )
        if acknowledgment is None:
            return
        if receipt is None:
            raise ValueError("Distribution acknowledgment requires an execution receipt")
        if receipt.status != ExecutionStatus.SUCCEEDED:
            raise ValueError("Distribution acknowledgment requires a successful execution receipt")
        if receipt.action_executed != EnforcementAction.PROCEED:
            raise ValueError("Distribution acknowledgment is permitted only for successful delivery")
        if acknowledgment.execution_receipt_id != receipt.receipt_id:
            raise ValueError("Distribution acknowledgment does not reference the execution receipt")
        if acknowledgment.destination_id != self.request.destination_id:
            raise ValueError("Distribution acknowledgment destination does not match ExecutionRequest")

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "execution_receipt": (
                self.execution_receipt.to_dict()
                if self.execution_receipt
                else None
            ),
            "review_queue_receipt": (
                self.review_queue_receipt.to_dict()
                if self.review_queue_receipt
                else None
            ),
            "distribution_acknowledgment": (
                self.distribution_acknowledgment.to_dict()
                if self.distribution_acknowledgment
                else None
            ),
            "duplicate": self.duplicate,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


class ApprovalQueryProtocol(Protocol):
    def get_request(self, request_id: str) -> ApprovalRequest | None:
        ...

    def get_decision_by_request(
        self,
        request_id: str,
    ) -> ApprovalDecision | None:
        ...


class ExecutionRepositoryProtocol(Protocol):
    def execute_transaction(
        self,
        request: ExecutionRequest,
        result_factory: Callable[[ExecutionRequest], ExecutionResult],
    ) -> ExecutionResult:
        ...

    def get_execution_result_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> ExecutionResult | None:
        ...

    def store_mitigation_state(
        self,
        event_id: str,
        mandate_id: str,
        actions: tuple[str, ...],
        executed_at: str,
        postconditions: Mapping[str, Any],
    ) -> None:
        ...


class SyntheticMitigationExecutor:
    ALLOWED_ACTIONS = frozenset(
        {
            "disable_commercial_sdk",
            "prevent_purchase_ui_delivery",
            "queue_vendor_review",
        }
    )

    def __init__(
        self,
        repository: ExecutionRepositoryProtocol,
        clock: Clock,
    ) -> None:
        if repository is None:
            raise TypeError("repository is required")
        if clock is None:
            raise TypeError("clock is required")
        self.repository = repository
        self.clock = clock

    def execute_mitigation(
        self,
        event_id: str,
        mandate_id: str,
        actions: tuple[str, ...],
    ) -> dict[str, Any]:
        clean_event_id = _require_identifier(event_id, "event_id")
        clean_mandate_id = _require_identifier(mandate_id, "mandate_id")
        if not isinstance(actions, tuple):
            raise TypeError("actions must be a tuple")
        clean_actions = tuple(str(action).strip() for action in actions)
        if not clean_actions:
            raise GovernanceConfigurationError("Mitigation actions must not be empty")
        if any(not action for action in clean_actions):
            raise GovernanceConfigurationError("Mitigation actions contain an empty value")
        if len(clean_actions) != len(set(clean_actions)):
            raise GovernanceConfigurationError("Mitigation actions contain duplicates")
        if any(action not in self.ALLOWED_ACTIONS for action in clean_actions):
            raise GovernanceConfigurationError("Mitigation action is not permitted")
        now_iso = parse_timestamp(
            self.clock.now_iso(),
            "clock timestamp",
        ).isoformat()
        postconditions = {
            "commercial_sdk_active_after": "disable_commercial_sdk" not in clean_actions,
            "purchase_interface_visible_after": (
                "prevent_purchase_ui_delivery" not in clean_actions
            ),
            "vendor_review_queued": "queue_vendor_review" in clean_actions,
        }
        self.repository.store_mitigation_state(
            event_id=clean_event_id,
            mandate_id=clean_mandate_id,
            actions=clean_actions,
            executed_at=now_iso,
            postconditions=postconditions,
        )
        return dict(postconditions)


class ExecutionGateway:
    def __init__(
        self,
        execution_repository: ExecutionRepositoryProtocol,
        destination_registry: DestinationRegistry,
        approval_query: ApprovalQueryProtocol,
        identifier_provider: IdentifierProvider,
        clock: Clock,
        executor_id: str = "AMBA-GOV-EXEC-GATEWAY-01",
    ) -> None:
        if execution_repository is None:
            raise TypeError("execution_repository is required")
        if destination_registry is None:
            raise TypeError("destination_registry is required")
        if approval_query is None:
            raise GovernanceConfigurationError("Approval verification repository is required")
        if identifier_provider is None:
            raise TypeError("identifier_provider is required")
        if clock is None:
            raise TypeError("clock is required")
        self.repository = execution_repository
        self.destinations = destination_registry
        self.approval_query = approval_query
        self.id_provider = identifier_provider
        self.clock = clock
        self.executor_id = _require_identifier(executor_id, "executor_id")
        self.mitigation_executor = SyntheticMitigationExecutor(
            execution_repository,
            clock,
        )

    def execute(
        self,
        event: PipelineEvent,
        recommendation: PolicyRecommendation,
        approval_decision: ApprovalDecision | None,
        idempotency_key: str,
        execution_details: Mapping[str, Any] | None = None,
    ) -> ExecutionResult:
        if not isinstance(event, PipelineEvent):
            raise TypeError("event must be a PipelineEvent")
        if not isinstance(recommendation, PolicyRecommendation):
            raise TypeError("recommendation must be a PolicyRecommendation")
        if recommendation.event_id != event.event_id:
            raise GovernanceConfigurationError(
                "Policy recommendation does not belong to the execution event"
            )
        clean_idempotency_key = _require_identifier(
            idempotency_key,
            "idempotency_key",
        )
        if execution_details is not None and not isinstance(execution_details, Mapping):
            raise TypeError("execution_details must be a mapping")
        now_iso = parse_timestamp(
            self.clock.now_iso(),
            "clock timestamp",
        ).isoformat()
        details = deep_freeze(dict(execution_details or {}))

        if recommendation.requires_approval:
            if approval_decision is None or not approval_decision.approved:
                request = self._build_execution_request(
                    self.id_provider.new_id("execreq"),
                    event,
                    recommendation,
                    None,
                    clean_idempotency_key,
                    now_iso,
                )
                return self.repository.execute_transaction(
                    request,
                    lambda persisted: self._handle_hold(
                        persisted,
                        event,
                        now_iso,
                        "APPROVAL_REQUIRED",
                        details,
                    ),
                )
            self._validate_approval_binding(event, recommendation, approval_decision)
        elif approval_decision is not None:
            if not approval_decision.approved:
                raise GovernanceConfigurationError(
                    "Denied approval decision supplied for execution"
                )
            self._validate_approval_binding(event, recommendation, approval_decision)

        request = self._build_execution_request(
            self.id_provider.new_id("execreq"),
            event,
            recommendation,
            approval_decision,
            clean_idempotency_key,
            now_iso,
        )
        action = recommendation.recommended_action

        def result_factory(persisted: ExecutionRequest) -> ExecutionResult:
            if action == EnforcementAction.PROCEED:
                self._validate_delivery_destination(
                    event.destination_id,
                    event.operation_id,
                )
                return self._handle_proceed(persisted, event, now_iso, details)
            if action == EnforcementAction.HOLD_FOR_REVIEW:
                return self._handle_hold(
                    persisted,
                    event,
                    now_iso,
                    "POLICY_HOLD",
                    details,
                )
            if action == EnforcementAction.BLOCK:
                return self._handle_block(
                    persisted,
                    event,
                    "Delivery prevented under project controls",
                    now_iso,
                    details,
                )
            if action == EnforcementAction.ABSTAIN:
                return self._handle_abstain(persisted, event, now_iso, details)
            if action == EnforcementAction.REQUIRE_APPROVAL:
                self._validate_delivery_destination(
                    event.destination_id,
                    event.operation_id,
                )
                return self._handle_proceed(persisted, event, now_iso, details)
            if action in {EnforcementAction.CONFIRM, EnforcementAction.MODIFY}:
                return self._handle_not_attempted(
                    persisted,
                    event,
                    action,
                    now_iso,
                    "Execution not attempted because the requested lifecycle is unsupported",
                    details,
                )
            raise GovernanceConfigurationError("Execution action is not supported")

        return self.repository.execute_transaction(request, result_factory)

    def _build_execution_request(
        self,
        request_id: str,
        event: PipelineEvent,
        recommendation: PolicyRecommendation,
        approval_decision: ApprovalDecision | None,
        idempotency_key: str,
        now_iso: str,
    ) -> ExecutionRequest:
        recommendation_digest = _sha256_material(recommendation.to_dict())
        precondition_digest = hashlib.sha256(
            f"{event.event_id}:{event.operation_id}".encode("utf-8")
        ).hexdigest()
        return ExecutionRequest.create(
            request_id=request_id,
            event_id=event.event_id,
            operation_id=event.operation_id,
            recommended_action=recommendation.recommended_action,
            destination_id=event.destination_id,
            precondition_digest=precondition_digest,
            recommendation_digest=recommendation_digest,
            approval_decision_id=(
                approval_decision.decision_id
                if approval_decision is not None
                else None
            ),
            idempotency_key=idempotency_key,
            created_at=now_iso,
            synthetic=True,
            legal_effect=False,
        )

    def _validate_delivery_destination(
        self,
        destination_id: str,
        operation_id: str,
    ) -> None:
        if not self.destinations.is_registered(destination_id):
            raise GovernanceConfigurationError("Delivery destination is not registered")
        if not self.destinations.is_allowed_for_operation(destination_id, operation_id):
            raise GovernanceConfigurationError(
                "Operation is not allowed for delivery destination"
            )

    def _validate_approval_binding(
        self,
        event: PipelineEvent,
        recommendation: PolicyRecommendation,
        decision: ApprovalDecision,
    ) -> None:
        persisted_request = self.approval_query.get_request(decision.request_id)
        if persisted_request is None:
            raise GovernanceConfigurationError("Approval request is not persisted")
        persisted_decision = self.approval_query.get_decision_by_request(
            decision.request_id
        )
        if persisted_decision is None:
            raise GovernanceConfigurationError("Approval decision is not persisted")
        if persisted_decision != decision:
            raise GovernanceConfigurationError(
                "Approval decision does not match the persisted decision"
            )
        if not hmac.compare_digest(
            decision.request_digest,
            persisted_request.request_digest,
        ):
            raise GovernanceConfigurationError(
                "Approval decision request digest mismatch"
            )
        if persisted_request.event_id != event.event_id:
            raise GovernanceConfigurationError(
                "Approval request event does not match execution event"
            )
        if persisted_request.operation_id != event.operation_id:
            raise GovernanceConfigurationError(
                "Approval request operation does not match execution operation"
            )
        if persisted_request.recommendation_id != recommendation.recommendation_id:
            raise GovernanceConfigurationError(
                "Approval request recommendation does not match execution recommendation"
            )
        if persisted_request.mandate_id != decision.mandate_id:
            raise GovernanceConfigurationError(
                "Approval decision mandate does not match the requested mandate"
            )
        if not decision.approved:
            raise GovernanceConfigurationError(
                "A denied approval decision cannot authorize execution"
            )

    def _receipt_digest(
        self,
        receipt_id: str,
        request_id: str,
        action: EnforcementAction,
        timestamp: str,
    ) -> str:
        return _sha256_material(
            {
                "receipt_id": receipt_id,
                "request_id": request_id,
                "action": action.value,
                "executed_at": timestamp,
            }
        )

    def _handle_proceed(
        self,
        request: ExecutionRequest,
        event: PipelineEvent,
        now_iso: str,
        details: Mapping[str, Any],
    ) -> ExecutionResult:
        receipt_id = self.id_provider.new_id("execrcpt")
        receipt = ExecutionReceipt(
            receipt_id=receipt_id,
            request_id=request.request_id,
            event_id=event.event_id,
            operation_id=event.operation_id,
            action_executed=EnforcementAction.PROCEED,
            status=ExecutionStatus.SUCCEEDED,
            executor_id=self.executor_id,
            execution_effect=f"Delivered to {event.destination_id}",
            executed_at=now_iso,
            receipt_digest=self._receipt_digest(
                receipt_id,
                request.request_id,
                EnforcementAction.PROCEED,
                now_iso,
            ),
            details=details,
            synthetic=True,
            legal_effect=False,
        )
        acknowledgment_id = self.id_provider.new_id("distack")
        acknowledgment = DistributionAcknowledgment(
            acknowledgment_id=acknowledgment_id,
            execution_receipt_id=receipt_id,
            destination_id=event.destination_id,
            disposition="DELIVERED",
            acknowledged_at=now_iso,
            acknowledgment_digest=_sha256_material(
                {
                    "acknowledgment_id": acknowledgment_id,
                    "execution_receipt_id": receipt_id,
                    "destination_id": event.destination_id,
                    "acknowledged_at": now_iso,
                }
            ),
        )
        return ExecutionResult(
            request=request,
            execution_receipt=receipt,
            review_queue_receipt=None,
            distribution_acknowledgment=acknowledgment,
            duplicate=False,
        )

    def _handle_block(
        self,
        request: ExecutionRequest,
        event: PipelineEvent,
        reason: str,
        now_iso: str,
        details: Mapping[str, Any],
    ) -> ExecutionResult:
        return self._simple_receipt_result(
            request,
            event,
            EnforcementAction.BLOCK,
            ExecutionStatus.SUCCEEDED,
            f"Delivery prevented: {reason}",
            now_iso,
            details,
        )

    def _handle_abstain(
        self,
        request: ExecutionRequest,
        event: PipelineEvent,
        now_iso: str,
        details: Mapping[str, Any],
    ) -> ExecutionResult:
        return self._simple_receipt_result(
            request,
            event,
            EnforcementAction.ABSTAIN,
            ExecutionStatus.SUCCEEDED,
            "Delivery abstained: no content published",
            now_iso,
            details,
        )

    def _handle_not_attempted(
        self,
        request: ExecutionRequest,
        event: PipelineEvent,
        action: EnforcementAction,
        now_iso: str,
        reason: str,
        details: Mapping[str, Any],
    ) -> ExecutionResult:
        return self._simple_receipt_result(
            request,
            event,
            action,
            ExecutionStatus.NOT_ATTEMPTED,
            reason,
            now_iso,
            details,
        )

    def _simple_receipt_result(
        self,
        request: ExecutionRequest,
        event: PipelineEvent,
        action: EnforcementAction,
        status: ExecutionStatus,
        effect: str,
        now_iso: str,
        details: Mapping[str, Any],
    ) -> ExecutionResult:
        receipt_id = self.id_provider.new_id("execrcpt")
        receipt = ExecutionReceipt(
            receipt_id=receipt_id,
            request_id=request.request_id,
            event_id=event.event_id,
            operation_id=event.operation_id,
            action_executed=action,
            status=status,
            executor_id=self.executor_id,
            execution_effect=effect,
            executed_at=now_iso,
            receipt_digest=self._receipt_digest(
                receipt_id,
                request.request_id,
                action,
                now_iso,
            ),
            details=details,
            synthetic=True,
            legal_effect=False,
        )
        return ExecutionResult(
            request=request,
            execution_receipt=receipt,
            review_queue_receipt=None,
            distribution_acknowledgment=None,
            duplicate=False,
        )

    def _handle_hold(
        self,
        request: ExecutionRequest,
        event: PipelineEvent,
        now_iso: str,
        reason_code: str,
        details: Mapping[str, Any],
    ) -> ExecutionResult:
        queue_destination = "SYNTHETIC-REVIEW-QUEUE"
        if (
            not self.destinations.is_registered(queue_destination)
            or not self.destinations.is_allowed_for_operation(
                queue_destination,
                event.operation_id,
            )
        ):
            return self._handle_not_attempted(
                request,
                event,
                EnforcementAction.HOLD_FOR_REVIEW,
                now_iso,
                "Review queue routing was not attempted because the operation is not eligible for the configured review destination",
                details,
            )
        receipt_id = self.id_provider.new_id("qrcpt")
        receipt = ReviewQueueReceipt(
            receipt_id=receipt_id,
            request_id=request.request_id,
            event_id=event.event_id,
            queue_destination_id=queue_destination,
            enqueued_at=now_iso,
            receipt_digest=_sha256_material(
                {
                    "receipt_id": receipt_id,
                    "request_id": request.request_id,
                    "queue_destination_id": queue_destination,
                    "enqueued_at": now_iso,
                }
            ),
            reason_code=reason_code,
            details=details,
        )
        return ExecutionResult(
            request=request,
            execution_receipt=None,
            review_queue_receipt=receipt,
            distribution_acknowledgment=None,
            duplicate=False,
        )
