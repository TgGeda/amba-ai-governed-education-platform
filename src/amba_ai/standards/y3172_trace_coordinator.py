from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from amba_ai.governance.distribution import (
    DistributionDisposition,
    DistributionEffect,
)
from amba_ai.governance.execution import (
    ExecutionResult,
    ExecutionStatus,
)
from amba_ai.governance.models import (
    EnforcementAction,
    IdentifierProvider,
    PipelineEvent,
    PolicyEvaluationBundle,
    to_canonical_json,
)
from amba_ai.governance.principals import parse_timestamp
from amba_ai.standards.y3172_models import (
    AMBA_GOV_Y3172_INTERPRETATION_ID,
    PipelineNodeStatus,
    PipelineNodeTrace,
    Y3172ConfigurationError,
    Y3172Node,
    Y3172PipelineTrace,
    Y3172TraceError,
)
from amba_ai.standards.y3172_registry import (
    Y3172Registry,
)


@runtime_checkable
class ClockProtocol(Protocol):
    def now_iso(self) -> str:
        ...


@dataclass(frozen=True, slots=True)
class Y3172TraceArtifacts:
    collection_artifact_ids: tuple[str, ...] = ()
    preprocessing_artifact_ids: tuple[str, ...] = ()
    model_artifact_ids: tuple[str, ...] = ()
    model_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "collection_artifact_ids",
            "preprocessing_artifact_ids",
            "model_artifact_ids",
            "model_evidence_ids",
        ):
            value = getattr(self, field_name)

            if not isinstance(value, tuple):
                raise TypeError(
                    f"{field_name} must be a tuple"
                )

            normalized = tuple(
                _require_text(
                    item,
                    f"{field_name} item",
                )
                for item in value
            )

            if len(normalized) != len(set(normalized)):
                raise Y3172ConfigurationError(
                    f"{field_name} must not contain duplicates"
                )

            object.__setattr__(
                self,
                field_name,
                normalized,
            )


class Y3172TraceCoordinator:
    def __init__(
        self,
        *,
        registry: Y3172Registry,
        identifier_provider: IdentifierProvider,
        clock: ClockProtocol,
    ) -> None:
        if not isinstance(registry, Y3172Registry):
            raise TypeError(
                "registry must be a Y3172Registry"
            )

        if identifier_provider is None:
            raise TypeError(
                "identifier_provider is required"
            )

        if not callable(
            getattr(
                identifier_provider,
                "new_id",
                None,
            )
        ):
            raise TypeError(
                "identifier_provider must provide new_id"
            )

        if not isinstance(clock, ClockProtocol):
            raise TypeError(
                "clock must implement ClockProtocol"
            )

        self._registry = registry
        self._identifier_provider = (
            identifier_provider
        )
        self._clock = clock

    @property
    def registry(self) -> Y3172Registry:
        return self._registry

    @property
    def identifier_provider(
        self,
    ) -> IdentifierProvider:
        return self._identifier_provider

    @property
    def clock(self) -> ClockProtocol:
        return self._clock

    def build_trace(
        self,
        *,
        run_id: str,
        event: PipelineEvent,
        bundle: PolicyEvaluationBundle,
        execution_result: ExecutionResult | None,
        distribution_effect: DistributionEffect | None,
        artifacts: Y3172TraceArtifacts | None = None,
        pre_gate_stopped: bool = False,
        failed_closed: bool = False,
    ) -> Y3172PipelineTrace:
        normalized_run_id = _require_text(
            run_id,
            "run_id",
        )

        if not isinstance(event, PipelineEvent):
            raise TypeError(
                "event must be a PipelineEvent"
            )

        if not isinstance(
            bundle,
            PolicyEvaluationBundle,
        ):
            raise TypeError(
                "bundle must be a PolicyEvaluationBundle"
            )

        if (
            execution_result is not None
            and not isinstance(
                execution_result,
                ExecutionResult,
            )
        ):
            raise TypeError(
                "execution_result must be an "
                "ExecutionResult or None"
            )

        if (
            distribution_effect is not None
            and not isinstance(
                distribution_effect,
                DistributionEffect,
            )
        ):
            raise TypeError(
                "distribution_effect must be a "
                "DistributionEffect or None"
            )

        if (
            artifacts is not None
            and not isinstance(
                artifacts,
                Y3172TraceArtifacts,
            )
        ):
            raise TypeError(
                "artifacts must be a "
                "Y3172TraceArtifacts or None"
            )

        if type(pre_gate_stopped) is not bool:
            raise TypeError(
                "pre_gate_stopped must be a strict Boolean"
            )

        if type(failed_closed) is not bool:
            raise TypeError(
                "failed_closed must be a strict Boolean"
            )

        if pre_gate_stopped and failed_closed:
            raise Y3172TraceError(
                "pre_gate_stopped and failed_closed "
                "cannot both be true"
            )

        resolved_artifacts = (
            artifacts
            if artifacts is not None
            else Y3172TraceArtifacts()
        )

        self._validate_bundle(
            event=event,
            bundle=bundle,
        )

        self._validate_execution_result(
            event=event,
            bundle=bundle,
            execution_result=execution_result,
        )

        outcome = self._resolve_outcome(
            event=event,
            bundle=bundle,
            execution_result=execution_result,
            distribution_effect=distribution_effect,
            pre_gate_stopped=pre_gate_stopped,
            failed_closed=failed_closed,
        )

        created_at = _clock_timestamp(
            self._clock
        )

        trace_id = _generated_identifier(
            self._identifier_provider,
            "y3172trace",
        )

        node_traces = self._build_node_traces(
            event=event,
            bundle=bundle,
            execution_result=execution_result,
            distribution_effect=distribution_effect,
            artifacts=resolved_artifacts,
            outcome=outcome,
            created_at=created_at,
        )

        extensions = tuple(
            extension.extension_id
            for extension in self._registry.extensions
        )

        return Y3172PipelineTrace(
            trace_id=trace_id,
            run_id=normalized_run_id,
            created_at=created_at,
            nodes=node_traces,
            interpretation_id=(
                AMBA_GOV_Y3172_INTERPRETATION_ID
            ),
            project_extensions=extensions,
            execution_receipt_id=(
                outcome.execution_receipt_id
            ),
            distribution_acknowledgment_id=(
                outcome.acknowledgment_id
            ),
            review_queue_receipt_id=(
                outcome.review_receipt_id
            ),
            formal_conformance_claimed=False,
            certification_claimed=False,
        )

    @staticmethod
    def _validate_bundle(
        *,
        event: PipelineEvent,
        bundle: PolicyEvaluationBundle,
    ) -> None:
        if bundle.event_id != event.event_id:
            raise Y3172TraceError(
                "bundle event identifier does not "
                "match the pipeline event"
            )

        if (
            bundle.recommendation.event_id
            != event.event_id
        ):
            raise Y3172TraceError(
                "recommendation event identifier does "
                "not match the pipeline event"
            )

        if any(
            finding.event_id != event.event_id
            for finding in bundle.findings
        ):
            raise Y3172TraceError(
                "finding event identifier does not "
                "match the pipeline event"
            )

        if (
            bundle.operation is not None
            and bundle.operation.operation_id
            != event.operation_id
        ):
            raise Y3172TraceError(
                "bundle operation identifier does not "
                "match the pipeline event"
            )

    @staticmethod
    def _validate_execution_result(
        *,
        event: PipelineEvent,
        bundle: PolicyEvaluationBundle,
        execution_result: ExecutionResult | None,
    ) -> None:
        if execution_result is None:
            return

        request = execution_result.request

        if request.event_id != event.event_id:
            raise Y3172TraceError(
                "execution request event identifier "
                "does not match the pipeline event"
            )

        if request.operation_id != event.operation_id:
            raise Y3172TraceError(
                "execution request operation identifier "
                "does not match the pipeline event"
            )

        if request.destination_id != event.destination_id:
            raise Y3172TraceError(
                "execution request destination identifier "
                "does not match the pipeline event"
            )

        if (
            request.recommended_action
            is not bundle.recommendation.recommended_action
        ):
            raise Y3172TraceError(
                "execution request action does not match "
                "the policy recommendation"
            )

        execution_receipt = (
            execution_result.execution_receipt
        )
        review_receipt = (
            execution_result.review_queue_receipt
        )
        acknowledgment = (
            execution_result
            .distribution_acknowledgment
        )

        if execution_receipt is not None:
            if (
                execution_receipt.request_id
                != request.request_id
            ):
                raise Y3172TraceError(
                    "execution receipt does not belong "
                    "to the execution request"
                )

            if (
                execution_receipt.event_id
                != event.event_id
            ):
                raise Y3172TraceError(
                    "execution receipt event identifier "
                    "does not match the pipeline event"
                )

            if (
                execution_receipt.operation_id
                != event.operation_id
            ):
                raise Y3172TraceError(
                    "execution receipt operation identifier "
                    "does not match the pipeline event"
                )

        if review_receipt is not None:
            if (
                review_receipt.request_id
                != request.request_id
            ):
                raise Y3172TraceError(
                    "review receipt does not belong "
                    "to the execution request"
                )

            if (
                review_receipt.event_id
                != event.event_id
            ):
                raise Y3172TraceError(
                    "review receipt event identifier does "
                    "not match the pipeline event"
                )

        if acknowledgment is not None:
            if execution_receipt is None:
                raise Y3172TraceError(
                    "distribution acknowledgment requires "
                    "an execution receipt"
                )

            if (
                acknowledgment.execution_receipt_id
                != execution_receipt.receipt_id
            ):
                raise Y3172TraceError(
                    "distribution acknowledgment does not "
                    "reference the execution receipt"
                )

            if (
                acknowledgment.destination_id
                != event.destination_id
            ):
                raise Y3172TraceError(
                    "distribution acknowledgment destination "
                    "does not match the pipeline event"
                )

    def _resolve_outcome(
        self,
        *,
        event: PipelineEvent,
        bundle: PolicyEvaluationBundle,
        execution_result: ExecutionResult | None,
        distribution_effect: DistributionEffect | None,
        pre_gate_stopped: bool,
        failed_closed: bool,
    ) -> "_TraceOutcome":
        if pre_gate_stopped:
            if execution_result is not None:
                raise Y3172TraceError(
                    "pre-gate stop cannot contain an "
                    "execution result"
                )

            if distribution_effect is not None:
                raise Y3172TraceError(
                    "pre-gate stop cannot contain a "
                    "distribution effect"
                )

            if (
                bundle.recommendation.recommended_action
                is EnforcementAction.PROCEED
            ):
                raise Y3172TraceError(
                    "pre-gate stop requires a "
                    "non-proceed recommendation"
                )

            return _TraceOutcome(
                distributor_status=(
                    PipelineNodeStatus.NOT_REACHED
                ),
                sink_status=(
                    PipelineNodeStatus.NOT_REACHED
                ),
                execution_receipt_id=None,
                acknowledgment_id=None,
                review_receipt_id=None,
                distributor_rationale_codes=(
                    "PRE_GATE_STOPPED",
                    bundle.recommendation
                    .recommended_action
                    .value,
                ),
            )

        if failed_closed:
            if execution_result is not None:
                raise Y3172TraceError(
                    "failed-closed trace cannot contain "
                    "an execution result"
                )

            if distribution_effect is not None:
                raise Y3172TraceError(
                    "failed-closed trace cannot contain "
                    "a distribution effect"
                )

            return _TraceOutcome(
                distributor_status=(
                    PipelineNodeStatus.FAILED_CLOSED
                ),
                sink_status=(
                    PipelineNodeStatus.NOT_REACHED
                ),
                execution_receipt_id=None,
                acknowledgment_id=None,
                review_receipt_id=None,
                distributor_rationale_codes=(
                    "DISTRIBUTION_FAILED_CLOSED",
                ),
            )

        if execution_result is None:
            raise Y3172TraceError(
                "completed governance flow requires "
                "an execution result"
            )

        request = execution_result.request
        execution_receipt = (
            execution_result.execution_receipt
        )
        review_receipt = (
            execution_result.review_queue_receipt
        )
        acknowledgment = (
            execution_result
            .distribution_acknowledgment
        )

        if review_receipt is not None:
            if distribution_effect is not None:
                self._validate_review_effect(
                    review_receipt_destination=(
                        review_receipt
                        .queue_destination_id
                    ),
                    effect=distribution_effect,
                )

            return _TraceOutcome(
                distributor_status=(
                    PipelineNodeStatus.HELD
                ),
                sink_status=(
                    PipelineNodeStatus.NOT_REACHED
                ),
                execution_receipt_id=None,
                acknowledgment_id=None,
                review_receipt_id=(
                    review_receipt.receipt_id
                ),
                distributor_rationale_codes=(
                    review_receipt.reason_code,
                ),
            )

        if execution_receipt is None:
            raise Y3172TraceError(
                "execution result does not contain "
                "a completion receipt"
            )

        action = execution_receipt.action_executed
        status = execution_receipt.status

        if (
            action is EnforcementAction.PROCEED
            and status is ExecutionStatus.SUCCEEDED
        ):
            if acknowledgment is None:
                raise Y3172TraceError(
                    "delivered execution requires a "
                    "distribution acknowledgment"
                )

            if distribution_effect is not None:
                self._validate_delivery_effect(
                    event=event,
                    effect=distribution_effect,
                )

            return _TraceOutcome(
                distributor_status=(
                    PipelineNodeStatus.COMPLETED
                ),
                sink_status=(
                    PipelineNodeStatus.COMPLETED
                ),
                execution_receipt_id=(
                    execution_receipt.receipt_id
                ),
                acknowledgment_id=(
                    acknowledgment.acknowledgment_id
                ),
                review_receipt_id=None,
                distributor_rationale_codes=(
                    "DISTRIBUTION_DELIVERED",
                ),
            )

        if (
            action in {
                EnforcementAction.BLOCK,
                EnforcementAction.ABSTAIN,
            }
            and status is ExecutionStatus.SUCCEEDED
        ):
            if acknowledgment is not None:
                raise Y3172TraceError(
                    "prevented execution cannot contain "
                    "a distribution acknowledgment"
                )

            if distribution_effect is not None:
                self._validate_prevention_effect(
                    event=event,
                    effect=distribution_effect,
                )

            return _TraceOutcome(
                distributor_status=(
                    PipelineNodeStatus.PREVENTED
                ),
                sink_status=(
                    PipelineNodeStatus.NOT_REACHED
                ),
                execution_receipt_id=(
                    execution_receipt.receipt_id
                ),
                acknowledgment_id=None,
                review_receipt_id=None,
                distributor_rationale_codes=(
                    "DISTRIBUTION_PREVENTED",
                    action.value,
                ),
            )

        if status is ExecutionStatus.NOT_ATTEMPTED:
            if acknowledgment is not None:
                raise Y3172TraceError(
                    "not-attempted execution cannot contain "
                    "a distribution acknowledgment"
                )

            if distribution_effect is not None:
                raise Y3172TraceError(
                    "not-attempted execution cannot contain "
                    "a distribution effect"
                )

            return _TraceOutcome(
                distributor_status=(
                    PipelineNodeStatus.FAILED_CLOSED
                ),
                sink_status=(
                    PipelineNodeStatus.NOT_REACHED
                ),
                execution_receipt_id=(
                    execution_receipt.receipt_id
                ),
                acknowledgment_id=None,
                review_receipt_id=None,
                distributor_rationale_codes=(
                    "EXECUTION_NOT_ATTEMPTED",
                    request.recommended_action.value,
                ),
            )

        if status in {
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        }:
            if acknowledgment is not None:
                raise Y3172TraceError(
                    "failed execution cannot contain a "
                    "distribution acknowledgment"
                )

            if distribution_effect is not None:
                raise Y3172TraceError(
                    "failed execution cannot contain a "
                    "distribution effect"
                )

            return _TraceOutcome(
                distributor_status=(
                    PipelineNodeStatus.FAILED_CLOSED
                ),
                sink_status=(
                    PipelineNodeStatus.NOT_REACHED
                ),
                execution_receipt_id=(
                    execution_receipt.receipt_id
                ),
                acknowledgment_id=None,
                review_receipt_id=None,
                distributor_rationale_codes=(
                    "EXECUTION_FAILED_CLOSED",
                    status.value,
                ),
            )

        raise Y3172TraceError(
            "execution result cannot be mapped to a "
            "supported Y.3172 distribution outcome"
        )

    @staticmethod
    def _validate_delivery_effect(
        *,
        event: PipelineEvent,
        effect: DistributionEffect,
    ) -> None:
        if (
            effect.disposition
            is not DistributionDisposition.DELIVERED
        ):
            raise Y3172TraceError(
                "delivered execution requires a "
                "DELIVERED distribution effect"
            )

        if effect.destination_id != event.destination_id:
            raise Y3172TraceError(
                "distribution effect destination does not "
                "match the pipeline event"
            )

    @staticmethod
    def _validate_prevention_effect(
        *,
        event: PipelineEvent,
        effect: DistributionEffect,
    ) -> None:
        if (
            effect.disposition
            is not DistributionDisposition.PREVENTED
        ):
            raise Y3172TraceError(
                "prevented execution requires a "
                "PREVENTED distribution effect"
            )

        if effect.destination_id != event.destination_id:
            raise Y3172TraceError(
                "distribution effect destination does not "
                "match the pipeline event"
            )

    @staticmethod
    def _validate_review_effect(
        *,
        review_receipt_destination: str,
        effect: DistributionEffect,
    ) -> None:
        if (
            effect.disposition
            is not
            DistributionDisposition.QUEUED_FOR_REVIEW
        ):
            raise Y3172TraceError(
                "review receipt requires a "
                "QUEUED_FOR_REVIEW distribution effect"
            )

        if (
            effect.destination_id
            != review_receipt_destination
        ):
            raise Y3172TraceError(
                "review distribution effect destination "
                "does not match the review receipt"
            )

    def _build_node_traces(
        self,
        *,
        event: PipelineEvent,
        bundle: PolicyEvaluationBundle,
        execution_result: ExecutionResult | None,
        distribution_effect: DistributionEffect | None,
        artifacts: Y3172TraceArtifacts,
        outcome: "_TraceOutcome",
        created_at: str,
    ) -> tuple[PipelineNodeTrace, ...]:
        finding_ids = tuple(
            finding.finding_id
            for finding in bundle.findings
        )

        policy_evidence_ids = tuple(
            sorted(
                {
                    str(identity)
                    for finding in bundle.findings
                    for identity in (
                        finding.primary_records
                        + finding.supporting_records
                    )
                }
            )
        )

        model_status = (
            PipelineNodeStatus.COMPLETED
            if (
                artifacts.model_artifact_ids
                or artifacts.model_evidence_ids
            )
            else PipelineNodeStatus.NOT_REACHED
        )

        distributor_artifacts = tuple(
            item
            for item in (
                (
                    execution_result
                    .execution_receipt
                    .receipt_id
                    if (
                        execution_result is not None
                        and execution_result
                        .execution_receipt
                        is not None
                    )
                    else None
                ),
                (
                    execution_result
                    .review_queue_receipt
                    .receipt_id
                    if (
                        execution_result is not None
                        and execution_result
                        .review_queue_receipt
                        is not None
                    )
                    else None
                ),
                (
                    distribution_effect.effect_code
                    if distribution_effect is not None
                    else None
                ),
            )
            if item is not None
        )

        sink_artifacts = ()

        if (
            outcome.sink_status
            is PipelineNodeStatus.COMPLETED
        ):
            acknowledgment = (
                execution_result
                .distribution_acknowledgment
                if execution_result is not None
                else None
            )

            if acknowledgment is None:
                raise Y3172TraceError(
                    "completed sink requires a "
                    "distribution acknowledgment"
                )

            sink_artifacts = (
                event.destination_id,
                acknowledgment.acknowledgment_id,
            )

        return (
            self._completed_node(
                node=Y3172Node.SRC,
                timestamp=event.timestamp,
                artifact_ids=(
                    event.event_id,
                ),
                evidence_ids=(),
                rationale_codes=(
                    "PIPELINE_EVENT_ACCEPTED",
                ),
                details={
                    "source_node": event.source_node,
                    "payload_type": event.payload_type,
                    "synthetic": event.synthetic_flag,
                    "mapping_status": (
                        self._registry.require(
                            Y3172Node.SRC
                        ).implementation_status.value
                    ),
                },
            ),
            self._completed_node(
                node=Y3172Node.C,
                timestamp=created_at,
                artifact_ids=(
                    artifacts.collection_artifact_ids
                    or (
                        event.event_id,
                        event.operation_id,
                    )
                ),
                evidence_ids=(),
                rationale_codes=(
                    "CONTEXT_COLLECTED",
                ),
                details={
                    "operation_id": event.operation_id,
                    "destination_id": event.destination_id,
                    "mapping_status": (
                        self._registry.require(
                            Y3172Node.C
                        ).implementation_status.value
                    ),
                },
            ),
            self._completed_node(
                node=Y3172Node.PP,
                timestamp=created_at,
                artifact_ids=(
                    artifacts.preprocessing_artifact_ids
                    or (
                        event.event_id,
                    )
                ),
                evidence_ids=policy_evidence_ids,
                rationale_codes=(
                    "EVENT_NORMALIZED",
                    "PROVENANCE_BOUNDARY_PRESERVED",
                ),
                details={
                    "authorization_basis_present": (
                        event.authorization_basis
                        is not None
                    ),
                    "policy_record_count": len(
                        policy_evidence_ids
                    ),
                    "mapping_status": (
                        self._registry.require(
                            Y3172Node.PP
                        ).implementation_status.value
                    ),
                },
            ),
            self._model_node(
                status=model_status,
                timestamp=created_at,
                artifacts=artifacts,
            ),
            self._completed_node(
                node=Y3172Node.P,
                timestamp=created_at,
                artifact_ids=(
                    bundle.recommendation
                    .recommendation_id,
                ),
                evidence_ids=finding_ids,
                rationale_codes=(
                    bundle.recommendation
                    .recommended_action
                    .value,
                ),
                details={
                    "finding_count": len(
                        bundle.findings
                    ),
                    "unresolved_question_count": len(
                        bundle.unresolved_questions
                    ),
                    "requires_approval": (
                        bundle.recommendation
                        .requires_approval
                    ),
                    "mapping_status": (
                        self._registry.require(
                            Y3172Node.P
                        ).implementation_status.value
                    ),
                },
            ),
            self._distributor_node(
                timestamp=created_at,
                outcome=outcome,
                artifact_ids=distributor_artifacts,
                distribution_effect=(
                    distribution_effect
                ),
                execution_result=(
                    execution_result
                ),
            ),
            self._sink_node(
                timestamp=created_at,
                outcome=outcome,
                artifact_ids=sink_artifacts,
                event=event,
            ),
        )

    def _completed_node(
        self,
        *,
        node: Y3172Node,
        timestamp: str,
        artifact_ids: tuple[str, ...],
        evidence_ids: tuple[str, ...],
        rationale_codes: tuple[str, ...],
        details: dict[str, object],
    ) -> PipelineNodeTrace:
        return PipelineNodeTrace(
            node=node,
            status=PipelineNodeStatus.COMPLETED,
            started_at=timestamp,
            completed_at=timestamp,
            artifact_ids=artifact_ids,
            evidence_ids=evidence_ids,
            rationale_codes=rationale_codes,
            details=details,
        )

    def _model_node(
        self,
        *,
        status: PipelineNodeStatus,
        timestamp: str,
        artifacts: Y3172TraceArtifacts,
    ) -> PipelineNodeTrace:
        details = {
            "decision_authority": False,
            "runtime_authorization": False,
            "mapping_status": (
                self._registry.require(
                    Y3172Node.M
                ).implementation_status.value
            ),
        }

        if status is PipelineNodeStatus.NOT_REACHED:
            return PipelineNodeTrace(
                node=Y3172Node.M,
                status=PipelineNodeStatus.NOT_REACHED,
                started_at=None,
                completed_at=None,
                artifact_ids=(),
                evidence_ids=(),
                rationale_codes=(),
                details=details,
            )

        return PipelineNodeTrace(
            node=Y3172Node.M,
            status=PipelineNodeStatus.COMPLETED,
            started_at=timestamp,
            completed_at=timestamp,
            artifact_ids=(
                artifacts.model_artifact_ids
            ),
            evidence_ids=(
                artifacts.model_evidence_ids
            ),
            rationale_codes=(
                "MODEL_ASSISTANCE_RECORDED",
            ),
            details=details,
        )

    def _distributor_node(
        self,
        *,
        timestamp: str,
        outcome: "_TraceOutcome",
        artifact_ids: tuple[str, ...],
        distribution_effect: DistributionEffect | None,
        execution_result: ExecutionResult | None,
    ) -> PipelineNodeTrace:
        if (
            outcome.distributor_status
            is PipelineNodeStatus.NOT_REACHED
        ):
            return PipelineNodeTrace(
                node=Y3172Node.D,
                status=PipelineNodeStatus.NOT_REACHED,
                started_at=None,
                completed_at=None,
                artifact_ids=(),
                evidence_ids=(),
                rationale_codes=(),
                details={
                    "mapping_status": (
                        self._registry.require(
                            Y3172Node.D
                        ).implementation_status.value
                    ),
                },
            )

        details: dict[str, object] = {
            "mapping_status": (
                self._registry.require(
                    Y3172Node.D
                ).implementation_status.value
            ),
            "duplicate_execution": (
                execution_result.duplicate
                if execution_result is not None
                else False
            ),
        }

        if distribution_effect is not None:
            details.update(
                {
                    "distribution_disposition": (
                        distribution_effect
                        .disposition
                        .value
                    ),
                    "distribution_effect_code": (
                        distribution_effect.effect_code
                    ),
                    "distribution_executor_id": (
                        distribution_effect.executor_id
                    ),
                }
            )

        return PipelineNodeTrace(
            node=Y3172Node.D,
            status=outcome.distributor_status,
            started_at=timestamp,
            completed_at=timestamp,
            artifact_ids=artifact_ids,
            evidence_ids=(),
            rationale_codes=(
                outcome.distributor_rationale_codes
            ),
            details=details,
        )

    def _sink_node(
        self,
        *,
        timestamp: str,
        outcome: "_TraceOutcome",
        artifact_ids: tuple[str, ...],
        event: PipelineEvent,
    ) -> PipelineNodeTrace:
        details = {
            "destination_id": event.destination_id,
            "mapping_status": (
                self._registry.require(
                    Y3172Node.SINK
                ).implementation_status.value
            ),
        }

        if (
            outcome.sink_status
            is PipelineNodeStatus.NOT_REACHED
        ):
            return PipelineNodeTrace(
                node=Y3172Node.SINK,
                status=PipelineNodeStatus.NOT_REACHED,
                started_at=None,
                completed_at=None,
                artifact_ids=(),
                evidence_ids=(),
                rationale_codes=(),
                details=details,
            )

        return PipelineNodeTrace(
            node=Y3172Node.SINK,
            status=PipelineNodeStatus.COMPLETED,
            started_at=timestamp,
            completed_at=timestamp,
            artifact_ids=artifact_ids,
            evidence_ids=(),
            rationale_codes=(
                "DESTINATION_ACKNOWLEDGED",
            ),
            details=details,
        )


@dataclass(frozen=True, slots=True)
class _TraceOutcome:
    distributor_status: PipelineNodeStatus
    sink_status: PipelineNodeStatus
    execution_receipt_id: str | None
    acknowledgment_id: str | None
    review_receipt_id: str | None
    distributor_rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(
            self.distributor_status,
            PipelineNodeStatus,
        ):
            raise TypeError(
                "distributor_status must be a "
                "PipelineNodeStatus"
            )

        if not isinstance(
            self.sink_status,
            PipelineNodeStatus,
        ):
            raise TypeError(
                "sink_status must be a PipelineNodeStatus"
            )

        if not isinstance(
            self.distributor_rationale_codes,
            tuple,
        ):
            raise TypeError(
                "distributor_rationale_codes must be a tuple"
            )

        normalized_codes = tuple(
            _require_text(
                code,
                "distributor_rationale_codes item",
            )
            for code in self.distributor_rationale_codes
        )

        if len(normalized_codes) != len(
            set(normalized_codes)
        ):
            raise Y3172ConfigurationError(
                "distributor_rationale_codes must not "
                "contain duplicates"
            )

        object.__setattr__(
            self,
            "distributor_rationale_codes",
            normalized_codes,
        )


def _require_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string"
        )

    normalized = value.strip()

    if not normalized:
        raise Y3172ConfigurationError(
            f"{field_name} must not be empty"
        )

    return normalized


def _generated_identifier(
    provider: IdentifierProvider,
    prefix: str,
) -> str:
    value = provider.new_id(prefix)

    if not isinstance(value, str):
        raise Y3172ConfigurationError(
            "identifier provider returned a non-string value"
        )

    return _require_text(
        value,
        "generated identifier",
    )


def _clock_timestamp(
    clock: ClockProtocol,
) -> str:
    value = clock.now_iso()

    if not isinstance(value, str):
        raise Y3172ConfigurationError(
            "clock returned a non-string value"
        )

    try:
        return parse_timestamp(
            value,
            "clock timestamp",
        ).isoformat()
    except (TypeError, ValueError) as exc:
        raise Y3172ConfigurationError(
            "clock returned an invalid timestamp"
        ) from exc
