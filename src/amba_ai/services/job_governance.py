from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import re
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from amba_ai.governance.approvals import (
    ApprovalDecision,
)
from amba_ai.governance.execution import (
    ExecutionResult,
)
from amba_ai.governance.learning_operations import LEARNING_METHOD_OPERATION_MAP
from amba_ai.governance.models import (
    AuthorizationBasis,
    EnforcementAction,
    GovernanceConfigurationError,
    PipelineEvent,
    PolicyFinding,
    PolicyRecommendation,
    to_canonical_json,
)


_SHA256_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)


JOB_OPERATION_MAP: Mapping[str, str] = LEARNING_METHOD_OPERATION_MAP


_SAFE_INPUT_FIELDS = frozenset(
    {
        "active_tab",
        "document_id",
        "force",
        "max_tokens",
        "mcq_count",
        "output_format",
        "question_length",
        "remember",
        "requested_flashcard_count",
        "top_k",
    }
)


_SAFE_RESULT_FIELDS = frozenset(
    {
        "answer_length",
        "citation_count",
        "document_id",
        "flashcard_count",
        "markdown_length",
        "mcq_count",
        "model_name",
        "output_length",
        "output_type",
        "recorded",
        "tokens_used",
    }
)


@runtime_checkable
class GovernanceEvaluationProtocol(
    Protocol
):
    @property
    def recommendation(
        self,
    ) -> PolicyRecommendation:
        ...

    @property
    def findings(
        self,
    ) -> tuple[object, ...]:
        ...

    @property
    def unresolved_questions(
        self,
    ) -> tuple[str, ...]:
        ...


@runtime_checkable
class GovernanceServiceProtocol(
    Protocol
):
    def evaluate(
        self,
        event: PipelineEvent,
    ) -> GovernanceEvaluationProtocol:
        ...


@runtime_checkable
class ExecutionServiceProtocol(
    Protocol
):
    def execute(
        self,
        *,
        event: PipelineEvent,
        recommendation: PolicyRecommendation,
        approval_decision: (
            ApprovalDecision | None
        ),
        idempotency_key: str,
        execution_details: (
            Mapping[str, Any] | None
        ) = None,
    ) -> ExecutionResult:
        ...


@runtime_checkable
class AuditServiceProtocol(
    Protocol
):
    def append(
        self,
        *,
        run_id: str,
        scenario_id: str,
        stage_id: str,
        event_id: str,
        operation_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> object:
        ...


@runtime_checkable
class IdentifierProviderProtocol(
    Protocol
):
    def new_id(
        self,
        prefix: str,
    ) -> str:
        ...


@runtime_checkable
class ClockProtocol(
    Protocol
):
    def now_iso(
        self,
    ) -> str:
        ...


class JobGovernanceGateError(
    RuntimeError
):
    def __init__(
        self,
        *,
        method_name: str,
        operation_id: str,
        event_id: str,
        action: EnforcementAction,
        recommendation_id: str | None = None,
        findings: tuple[object, ...] = (),
        review_queue_receipt: str | None = None,
    ) -> None:
        normalized_method = _require_text(
            method_name,
            "method_name",
        )
        normalized_operation = _require_text(
            operation_id,
            "operation_id",
        )
        normalized_event = _require_text(
            event_id,
            "event_id",
        )

        if not isinstance(
            action,
            EnforcementAction,
        ):
            raise TypeError(
                "action must be an "
                "EnforcementAction"
            )

        self.method_name = normalized_method
        self.operation_id = normalized_operation
        self.event_id = normalized_event
        self.action = action
        self.recommendation_id = str(recommendation_id).strip() if recommendation_id else None
        self.findings = tuple(findings)
        self.review_queue_receipt = str(review_queue_receipt).strip() if review_queue_receipt else None

        finding_codes = tuple(
            getattr(finding, "code", getattr(finding, "finding_id", str(finding)))
            for finding in self.findings
        )

        super().__init__(
            "Job governance pre-gate prevented processing: "
            f"method={normalized_method}, "
            f"operation={normalized_operation}, "
            f"action={action.value}, "
            f"findings={finding_codes or ('UNKNOWN',)}, "
            f"event_id={normalized_event}"
        )

    def to_dict(self) -> dict[str, Any]:
        serialized_findings: list[dict[str, Any]] = []
        for finding in self.findings:
            if isinstance(finding, PolicyFinding):
                serialized_findings.append({
                    "finding_id": finding.finding_id,
                    "evaluator_id": finding.evaluator_id,
                    "code": finding.code,
                    "severity": getattr(finding.severity, "value", str(finding.severity)),
                    "verdict": getattr(finding.verdict, "value", str(finding.verdict)),
                    "rationale": finding.rationale,
                    "evidence_sufficiency": getattr(finding.evidence_sufficiency, "value", str(finding.evidence_sufficiency)),
                })
            elif isinstance(finding, dict):
                serialized_findings.append(dict(finding))
            else:
                serialized_findings.append({
                    "code": getattr(finding, "code", str(finding)),
                    "finding_id": getattr(finding, "finding_id", str(finding)),
                    "rationale": getattr(finding, "rationale", ""),
                })

        return {
            "error_type": type(self).__name__,
            "method_name": self.method_name,
            "operation_id": self.operation_id,
            "event_id": self.event_id,
            "action": self.action.value,
            "recommendation_id": self.recommendation_id,
            "review_queue_receipt": self.review_queue_receipt,
            "findings": serialized_findings,
        }


class JobGovernanceDeliveryError(
    RuntimeError
):
    def __init__(
        self,
        *,
        method_name: str,
        operation_id: str,
        event_id: str,
        queued_for_review: bool,
        reason: str | None = None,
    ) -> None:
        normalized_method = _require_text(
            method_name,
            "method_name",
        )
        normalized_operation = _require_text(
            operation_id,
            "operation_id",
        )
        normalized_event = _require_text(
            event_id,
            "event_id",
        )

        if type(queued_for_review) is not bool:
            raise TypeError(
                "queued_for_review must be a strict Boolean"
            )

        self.method_name = normalized_method
        self.operation_id = normalized_operation
        self.event_id = normalized_event
        self.queued_for_review = queued_for_review
        self.reason = str(reason).strip() if reason else None

        disposition = (
            "queued_for_review"
            if queued_for_review
            else "not_acknowledged"
        )

        message = (
            "Governed job output is not authorized for delivery or persistence: "
            f"method={normalized_method}, "
            f"operation={normalized_operation}, "
            f"disposition={disposition}"
        )
        if self.reason:
            message += f", reason={self.reason}"

        super().__init__(message)


@dataclass(frozen=True, slots=True)
class JobGovernanceContext:
    run_id: str
    scenario_id: str
    stage_id: str
    source_node: str
    destination_id: str
    authorization_basis: (
        AuthorizationBasis | None
    ) = None
    approval_decision: (
        ApprovalDecision | None
    ) = None
    synthetic: bool = True

    def __post_init__(self) -> None:
        for field_name in (
            "run_id",
            "scenario_id",
            "stage_id",
            "source_node",
            "destination_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(
                    getattr(
                        self,
                        field_name,
                    ),
                    field_name,
                ),
            )

        if (
            self.authorization_basis
            is not None
            and not isinstance(
                self.authorization_basis,
                AuthorizationBasis,
            )
        ):
            raise TypeError(
                "authorization_basis must be an "
                "AuthorizationBasis or None"
            )

        if (
            self.approval_decision
            is not None
            and not isinstance(
                self.approval_decision,
                ApprovalDecision,
            )
        ):
            raise TypeError(
                "approval_decision must be an "
                "ApprovalDecision or None"
            )

        if type(self.synthetic) is not bool:
            raise TypeError(
                "synthetic must be a strict Boolean"
            )


@dataclass(frozen=True, slots=True)
class JobGovernanceInvocation:
    method_name: str
    operation_id: str
    event: PipelineEvent
    evaluation: GovernanceEvaluationProtocol
    context: JobGovernanceContext

    def __post_init__(self) -> None:
        normalized_method = (
            _require_method_name(
                self.method_name
            )
        )

        expected_operation = (
            JOB_OPERATION_MAP.get(
                normalized_method
            )
        )

        if expected_operation is None:
            raise GovernanceConfigurationError(
                "Invocation method is not mapped "
                "to a governance operation"
            )

        normalized_operation = _require_text(
            self.operation_id,
            "operation_id",
        )

        if (
            normalized_operation
            != expected_operation
        ):
            raise GovernanceConfigurationError(
                "Invocation operation does not "
                "match the method mapping"
            )

        if not isinstance(
            self.event,
            PipelineEvent,
        ):
            raise TypeError(
                "event must be a PipelineEvent"
            )

        if (
            self.event.operation_id
            != normalized_operation
        ):
            raise GovernanceConfigurationError(
                "Invocation event operation does "
                "not match the invocation operation"
            )

        if not isinstance(
            self.context,
            JobGovernanceContext,
        ):
            raise TypeError(
                "context must be a "
                "JobGovernanceContext"
            )

        _validate_evaluation(
            self.evaluation,
            expected_event_id=(
                self.event.event_id
            ),
            phase="pre-gate",
        )

        object.__setattr__(
            self,
            "method_name",
            normalized_method,
        )
        object.__setattr__(
            self,
            "operation_id",
            normalized_operation,
        )


@dataclass(frozen=True, slots=True)
class JobGovernanceCompletion:
    invocation: JobGovernanceInvocation
    post_event: PipelineEvent
    post_evaluation: (
        GovernanceEvaluationProtocol
    )
    execution_result: ExecutionResult
    output_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.invocation,
            JobGovernanceInvocation,
        ):
            raise TypeError(
                "invocation must be a "
                "JobGovernanceInvocation"
            )

        if not isinstance(
            self.post_event,
            PipelineEvent,
        ):
            raise TypeError(
                "post_event must be a PipelineEvent"
            )

        if (
            self.post_event.event_id
            != self.invocation.event.event_id
        ):
            raise GovernanceConfigurationError(
                "Post-event identifier does not "
                "match the invocation event"
            )

        if (
            self.post_event.operation_id
            != self.invocation.operation_id
        ):
            raise GovernanceConfigurationError(
                "Post-event operation does not "
                "match the invocation operation"
            )

        _validate_evaluation(
            self.post_evaluation,
            expected_event_id=(
                self.post_event.event_id
            ),
            phase="post-gate",
        )

        if not isinstance(
            self.execution_result,
            ExecutionResult,
        ):
            raise TypeError(
                "execution_result must be an "
                "ExecutionResult"
            )

        if (
            self.execution_result
            .request
            .event_id
            != self.post_event.event_id
        ):
            raise GovernanceConfigurationError(
                "Execution result event does not "
                "match the post-gate event"
            )

        if (
            self.execution_result
            .request
            .operation_id
            != self.post_event.operation_id
        ):
            raise GovernanceConfigurationError(
                "Execution result operation does "
                "not match the post-gate event"
            )

        normalized_digest = _require_sha256(
            self.output_sha256,
            "output_sha256",
        )

        object.__setattr__(
            self,
            "output_sha256",
            normalized_digest,
        )

    @property
    def delivery_acknowledged(
        self,
    ) -> bool:
        return (
            self.execution_result
            .distribution_acknowledgment
            is not None
        )

    @property
    def queued_for_review(
        self,
    ) -> bool:
        return (
            self.execution_result
            .review_queue_receipt
            is not None
        )

    @property
    def execution_recorded(
        self,
    ) -> bool:
        return (
            self.execution_result
            .execution_receipt
            is not None
        )

    def require_delivery_acknowledged(
        self,
    ) -> None:
        if self.delivery_acknowledged:
            return

        raise JobGovernanceDeliveryError(
            method_name=(
                self.invocation.method_name
            ),
            operation_id=(
                self.invocation.operation_id
            ),
            event_id=self.post_event.event_id,
            queued_for_review=(
                self.queued_for_review
            ),
        )


class JobGovernanceCoordinator:
    def __init__(
        self,
        *,
        governance_service: (
            GovernanceServiceProtocol
        ),
        execution_service: (
            ExecutionServiceProtocol
        ),
        audit_service: AuditServiceProtocol,
        identifier_provider: (
            IdentifierProviderProtocol
        ),
        clock: ClockProtocol,
    ) -> None:
        if not isinstance(
            governance_service,
            GovernanceServiceProtocol,
        ):
            raise TypeError(
                "governance_service must implement "
                "GovernanceServiceProtocol"
            )

        if not isinstance(
            execution_service,
            ExecutionServiceProtocol,
        ):
            raise TypeError(
                "execution_service must implement "
                "ExecutionServiceProtocol"
            )

        if not isinstance(
            audit_service,
            AuditServiceProtocol,
        ):
            raise TypeError(
                "audit_service must implement "
                "AuditServiceProtocol"
            )

        if not isinstance(
            identifier_provider,
            IdentifierProviderProtocol,
        ):
            raise TypeError(
                "identifier_provider must implement "
                "IdentifierProviderProtocol"
            )

        if not isinstance(
            clock,
            ClockProtocol,
        ):
            raise TypeError(
                "clock must implement ClockProtocol"
            )

        self._governance_service = (
            governance_service
        )
        self._execution_service = (
            execution_service
        )
        self._audit_service = audit_service
        self._identifier_provider = (
            identifier_provider
        )
        self._clock = clock

    @property
    def governance_service(
        self,
    ) -> GovernanceServiceProtocol:
        return self._governance_service

    @property
    def execution_service(
        self,
    ) -> ExecutionServiceProtocol:
        return self._execution_service

    @property
    def audit_service(
        self,
    ) -> AuditServiceProtocol:
        return self._audit_service

    def begin(
        self,
        *,
        method_name: str,
        input_metadata: Mapping[str, Any],
        context: (
            JobGovernanceContext | None
        ),
    ) -> JobGovernanceInvocation:
        normalized_method = (
            _require_method_name(
                method_name
            )
        )

        operation_id = JOB_OPERATION_MAP.get(
            normalized_method
        )

        if operation_id is None:
            raise GovernanceConfigurationError(
                "Job operation is not mapped for "
                f"governance: {normalized_method}"
            )

        if not isinstance(
            context,
            JobGovernanceContext,
        ):
            raise GovernanceConfigurationError(
                "A JobGovernanceContext is required "
                "for governed job processing"
            )

        safe_input = _safe_metadata(
            input_metadata,
            allowed=_SAFE_INPUT_FIELDS,
            field_name="input_metadata",
        )

        event_id = _require_generated_text(
            self._identifier_provider.new_id(
                "jobevt"
            ),
            "identifier",
        )

        timestamp = _require_generated_text(
            self._clock.now_iso(),
            "clock",
        )

        event = PipelineEvent(
            event_id=event_id,
            timestamp=timestamp,
            operation_id=operation_id,
            source_node=context.source_node,
            destination_id=(
                context.destination_id
            ),
            payload_type="job_pre_gate",
            payload={
                "job_operation": (
                    normalized_method
                ),
                "governance_phase": "pre_generation",
                **safe_input,
            },
            authorization_basis=(
                context.authorization_basis
            ),
            synthetic_flag=(
                context.synthetic
            ),
        )

        evaluation = (
            self._governance_service.evaluate(
                event
            )
        )

        recommendation = _validate_evaluation(
            evaluation,
            expected_event_id=event.event_id,
            phase="pre-gate",
        )

        self._append_audit(
            context=context,
            event=event,
            event_type=(
                "JOB_GOVERNANCE_PRE_EVALUATED"
            ),
            payload=_evaluation_audit_payload(
                normalized_method,
                evaluation,
            ),
        )

        if (
            recommendation.recommended_action
            is not EnforcementAction.PROCEED
        ):
            self._append_audit(
                context=context,
                event=event,
                event_type=(
                    "JOB_GOVERNANCE_PREVENTED"
                ),
                payload={
                    "job_operation": (
                        normalized_method
                    ),
                    "recommended_action": (
                        recommendation
                        .recommended_action
                        .value
                    ),
                },
            )

            raise JobGovernanceGateError(
                method_name=normalized_method,
                operation_id=operation_id,
                event_id=event_id,
                action=(
                    recommendation
                    .recommended_action
                ),
                recommendation_id=getattr(
                    recommendation,
                    "recommendation_id",
                    None,
                ),
                findings=getattr(
                    evaluation,
                    "findings",
                    (),
                ),
                review_queue_receipt=getattr(
                    evaluation,
                    "review_queue_receipt",
                    None,
                ),
            )

        return JobGovernanceInvocation(
            method_name=normalized_method,
            operation_id=operation_id,
            event=event,
            evaluation=evaluation,
            context=context,
        )

    def complete(
        self,
        *,
        invocation: JobGovernanceInvocation,
        result_material: Mapping[str, Any],
        result_metadata: Mapping[str, Any],
    ) -> JobGovernanceCompletion:
        if not isinstance(
            invocation,
            JobGovernanceInvocation,
        ):
            raise TypeError(
                "invocation must be a "
                "JobGovernanceInvocation"
            )

        canonical_result = (
            _canonical_result_material(
                result_material
            )
        )

        safe_result = _safe_metadata(
            result_metadata,
            allowed=_SAFE_RESULT_FIELDS,
            field_name="result_metadata",
        )

        output_sha256 = hashlib.sha256(
            canonical_result.encode("utf-8")
        ).hexdigest()

        post_event = PipelineEvent(
            event_id=invocation.event.event_id,
            timestamp=_require_generated_text(
                self._clock.now_iso(),
                "clock",
            ),
            operation_id=(
                invocation.operation_id
            ),
            source_node=(
                invocation.context.source_node
            ),
            destination_id=(
                invocation.context
                .destination_id
            ),
            payload_type="job_post_gate",
            payload={
                "job_operation": (
                    invocation.method_name
                ),
                "output_sha256": (
                    output_sha256
                ),
                "governance_phase": "post_generation",
                **safe_result,
            },
            authorization_basis=(
                invocation.context
                .authorization_basis
            ),
            synthetic_flag=(
                invocation.context.synthetic
            ),
        )

        post_evaluation = (
            self._governance_service.evaluate(
                post_event
            )
        )

        recommendation = _validate_evaluation(
            post_evaluation,
            expected_event_id=(
                post_event.event_id
            ),
            phase="post-gate",
        )

        self._append_audit(
            context=invocation.context,
            event=post_event,
            event_type=(
                "JOB_GOVERNANCE_POST_EVALUATED"
            ),
            payload={
                **_evaluation_audit_payload(
                    invocation.method_name,
                    post_evaluation,
                ),
                "output_sha256": (
                    output_sha256
                ),
                **safe_result,
            },
        )

        idempotency_key = _execution_key(
            invocation=invocation,
            post_event=post_event,
            output_sha256=output_sha256,
        )

        execution_details = {
            "job_operation": (
                invocation.method_name
            ),
            "output_sha256": output_sha256,
            **safe_result,
        }

        execution_result = (
            self._execution_service.execute(
                event=post_event,
                recommendation=recommendation,
                approval_decision=(
                    invocation.context
                    .approval_decision
                ),
                idempotency_key=(
                    idempotency_key
                ),
                execution_details=(
                    execution_details
                ),
            )
        )

        if not isinstance(
            execution_result,
            ExecutionResult,
        ):
            raise GovernanceConfigurationError(
                "Execution service returned an "
                "invalid ExecutionResult"
            )

        self._append_audit(
            context=invocation.context,
            event=post_event,
            event_type=(
                "JOB_EXECUTION_RECORDED"
            ),
            payload={
                "job_operation": (
                    invocation.method_name
                ),
                "recommended_action": (
                    recommendation
                    .recommended_action
                    .value
                ),
                "output_sha256": (
                    output_sha256
                ),
                "duplicate": (
                    execution_result.duplicate
                ),
                "has_execution_receipt": (
                    execution_result
                    .execution_receipt
                    is not None
                ),
                "has_review_queue_receipt": (
                    execution_result
                    .review_queue_receipt
                    is not None
                ),
                "has_distribution_acknowledgment": (
                    execution_result
                    .distribution_acknowledgment
                    is not None
                ),
            },
        )

        return JobGovernanceCompletion(
            invocation=invocation,
            post_event=post_event,
            post_evaluation=post_evaluation,
            execution_result=execution_result,
            output_sha256=output_sha256,
        )

    def _append_audit(
        self,
        *,
        context: JobGovernanceContext,
        event: PipelineEvent,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        normalized_event_type = _require_text(
            event_type,
            "event_type",
        )

        if not isinstance(
            payload,
            Mapping,
        ):
            raise TypeError(
                "payload must be a mapping"
            )

        try:
            canonical_payload = (
                to_canonical_json(
                    dict(payload)
                )
            )
        except (TypeError, ValueError) as error:
            raise GovernanceConfigurationError(
                "Audit payload must be "
                "canonically serializable"
            ) from error

        normalized_payload = (
            _decode_canonical_mapping(
                canonical_payload,
                "audit payload",
            )
        )

        self._audit_service.append(
            run_id=context.run_id,
            scenario_id=context.scenario_id,
            stage_id=context.stage_id,
            event_id=event.event_id,
            operation_id=(
                event.operation_id
            ),
            event_type=(
                normalized_event_type
            ),
            payload=normalized_payload,
        )


def _require_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(field_name, str):
        raise TypeError(
            "field_name must be a string"
        )

    normalized_field = field_name.strip()

    if not normalized_field:
        raise ValueError(
            "field_name must not be empty"
        )

    if not isinstance(value, str):
        raise TypeError(
            f"{normalized_field} must be a string"
        )

    normalized = value.strip()

    if not normalized:
        raise ValueError(
            f"{normalized_field} must not be empty"
        )

    return normalized


def _require_method_name(
    value: object,
) -> str:
    return _require_text(
        value,
        "method_name",
    )


def _require_generated_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise GovernanceConfigurationError(
            f"{field_name} provider returned "
            "a non-string value"
        )

    normalized = value.strip()

    if not normalized:
        raise GovernanceConfigurationError(
            f"{field_name} provider returned "
            "an empty value"
        )

    return normalized


def _require_sha256(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string"
        )

    normalized = value.strip()

    if (
        _SHA256_PATTERN.fullmatch(
            normalized
        )
        is None
    ):
        raise ValueError(
            f"{field_name} must be exactly 64 "
            "lowercase hexadecimal characters"
        )

    return normalized


def _safe_metadata(
    value: Mapping[str, Any],
    *,
    allowed: frozenset[str],
    field_name: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(
            f"{field_name} must be a mapping"
        )

    normalized: dict[str, Any] = {}

    for raw_key, item in value.items():
        if not isinstance(raw_key, str):
            raise GovernanceConfigurationError(
                f"{field_name} keys must "
                "be strings"
            )

        key = raw_key.strip()

        if not key:
            raise GovernanceConfigurationError(
                f"{field_name} keys must not "
                "be empty"
            )

        if key not in allowed:
            raise GovernanceConfigurationError(
                f"{field_name} contains a "
                f"non-permitted field: {key}"
            )

        if key in normalized:
            raise GovernanceConfigurationError(
                f"{field_name} contains a "
                f"duplicate normalized field: "
                f"{key}"
            )

        normalized[key] = item

    try:
        canonical = to_canonical_json(
            normalized
        )
    except (TypeError, ValueError) as error:
        raise GovernanceConfigurationError(
            f"{field_name} must be canonically "
            "serializable"
        ) from error

    return _decode_canonical_mapping(
        canonical,
        field_name,
    )


def _canonical_result_material(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError(
            "result_material must be a mapping"
        )

    material: dict[str, Any] = {}

    for key, item in value.items():
        if not isinstance(key, str):
            raise GovernanceConfigurationError(
                "result_material keys must "
                "be strings"
            )

        normalized_key = key.strip()

        if not normalized_key:
            raise GovernanceConfigurationError(
                "result_material keys must not "
                "be empty"
            )

        if normalized_key in material:
            raise GovernanceConfigurationError(
                "result_material contains a "
                "duplicate normalized field: "
                f"{normalized_key}"
            )

        material[normalized_key] = item

    try:
        return to_canonical_json(material)
    except (TypeError, ValueError) as error:
        raise GovernanceConfigurationError(
            "result_material must be "
            "canonically serializable"
        ) from error


def _recommendation(
    evaluation: object,
) -> PolicyRecommendation:
    recommendation = getattr(
        evaluation,
        "recommendation",
        None,
    )

    if not isinstance(
        recommendation,
        PolicyRecommendation,
    ):
        raise GovernanceConfigurationError(
            "Governance evaluation did not "
            "return a PolicyRecommendation"
        )

    return recommendation


def _validate_evaluation(
    evaluation: object,
    *,
    expected_event_id: str,
    phase: str,
) -> PolicyRecommendation:
    expected_event = _require_text(
        expected_event_id,
        "expected_event_id",
    )
    normalized_phase = _require_text(
        phase,
        "phase",
    )

    recommendation = _recommendation(
        evaluation
    )

    if (
        recommendation.event_id
        != expected_event
    ):
        raise GovernanceConfigurationError(
            f"{normalized_phase} recommendation "
            "event identifier does not match "
            "the governed event"
        )

    findings = getattr(
        evaluation,
        "findings",
        None,
    )
    unresolved = getattr(
        evaluation,
        "unresolved_questions",
        None,
    )

    if not isinstance(findings, tuple):
        raise GovernanceConfigurationError(
            "Governance evaluation findings "
            "must be a tuple"
        )

    if not isinstance(unresolved, tuple):
        raise GovernanceConfigurationError(
            "Governance evaluation unresolved "
            "questions must be a tuple"
        )

    for finding in findings:
        finding_id = getattr(
            finding,
            "finding_id",
            None,
        )

        if (
            not isinstance(finding_id, str)
            or not finding_id.strip()
        ):
            raise GovernanceConfigurationError(
                "Governance evaluation contains "
                "an invalid finding"
            )

        finding_event_id = getattr(
            finding,
            "event_id",
            None,
        )

        if (
            finding_event_id is not None
            and finding_event_id
            != expected_event
        ):
            raise GovernanceConfigurationError(
                "Governance evaluation contains "
                "a finding for another event"
            )

    if any(
        not isinstance(question, str)
        or not question.strip()
        for question in unresolved
    ):
        raise GovernanceConfigurationError(
            "Governance evaluation contains an "
            "invalid unresolved question"
        )

    return recommendation


def _evaluation_audit_payload(
    method_name: str,
    evaluation: object,
) -> dict[str, Any]:
    normalized_method = (
        _require_method_name(
            method_name
        )
    )
    recommendation = _recommendation(
        evaluation
    )

    findings = getattr(
        evaluation,
        "findings",
        None,
    )
    unresolved = getattr(
        evaluation,
        "unresolved_questions",
        None,
    )

    if not isinstance(findings, tuple):
        raise GovernanceConfigurationError(
            "Governance evaluation findings "
            "must be a tuple"
        )

    if not isinstance(unresolved, tuple):
        raise GovernanceConfigurationError(
            "Governance evaluation unresolved "
            "questions must be a tuple"
        )

    finding_ids: list[str] = []

    for finding in findings:
        finding_id = getattr(
            finding,
            "finding_id",
            None,
        )

        if (
            not isinstance(finding_id, str)
            or not finding_id.strip()
        ):
            raise GovernanceConfigurationError(
                "Governance evaluation contains "
                "an invalid finding"
            )

        finding_ids.append(
            finding_id.strip()
        )

    if any(
        not isinstance(question, str)
        or not question.strip()
        for question in unresolved
    ):
        raise GovernanceConfigurationError(
            "Governance evaluation contains an "
            "invalid unresolved question"
        )

    return {
        "job_operation": normalized_method,
        "recommended_action": (
            recommendation
            .recommended_action
            .value
        ),
        "finding_ids": tuple(
            finding_ids
        ),
        "unresolved_question_count": (
            len(unresolved)
        ),
    }


def _execution_key(
    *,
    invocation: JobGovernanceInvocation,
    post_event: PipelineEvent,
    output_sha256: str,
) -> str:
    digest = _require_sha256(
        output_sha256,
        "output_sha256",
    )

    material = {
        "run_id": (
            invocation.context.run_id
        ),
        "event_id": post_event.event_id,
        "operation_id": (
            invocation.operation_id
        ),
        "output_sha256": digest,
    }

    return hashlib.sha256(
        to_canonical_json(
            material
        ).encode("utf-8")
    ).hexdigest()


def _decode_canonical_mapping(
    value: str,
    field_name: str,
) -> dict[str, Any]:
    import json

    try:
        decoded = json.loads(value)
    except (TypeError, ValueError) as error:
        raise GovernanceConfigurationError(
            f"{field_name} is not valid "
            "canonical JSON"
        ) from error

    if not isinstance(decoded, dict):
        raise GovernanceConfigurationError(
            f"{field_name} must decode to "
            "a mapping"
        )

    return decoded