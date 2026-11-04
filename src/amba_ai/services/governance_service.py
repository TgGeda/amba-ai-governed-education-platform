from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any, Protocol, runtime_checkable

from amba_ai.governance.models import (
    GovernanceConfigurationError,
    PipelineEvent,
    PolicyEvaluationBundle,
    PolicyFinding,
    PolicyRecommendation,
    to_canonical_json,
)


@runtime_checkable
class PolicyEngineProtocol(Protocol):
    def evaluate_pipeline_event(
        self,
        event: PipelineEvent,
    ) -> PolicyEvaluationBundle:
        ...


@dataclass(frozen=True, slots=True)
class GovernanceEvaluationResult:
    event: PipelineEvent
    bundle: PolicyEvaluationBundle

    def __post_init__(self) -> None:
        if not isinstance(self.event, PipelineEvent):
            raise TypeError("event must be a PipelineEvent")
        if not isinstance(self.bundle, PolicyEvaluationBundle):
            raise TypeError("bundle must be a PolicyEvaluationBundle")
        if self.bundle.event_id != self.event.event_id:
            raise GovernanceConfigurationError(
                "Policy evaluation bundle event identifier does not match "
                "the evaluated pipeline event"
            )

        operation = self.bundle.operation
        if (
            operation is not None
            and operation.operation_id != self.event.operation_id
        ):
            raise GovernanceConfigurationError(
                "Policy evaluation bundle operation identifier does not match "
                "the evaluated pipeline event"
            )

        for finding in self.bundle.findings:
            if finding.event_id != self.event.event_id:
                raise GovernanceConfigurationError(
                    "Policy finding event identifier does not match "
                    "the evaluated pipeline event"
                )

        if self.bundle.recommendation.event_id != self.event.event_id:
            raise GovernanceConfigurationError(
                "Policy recommendation event identifier does not match "
                "the evaluated pipeline event"
            )

    @property
    def recommendation(self) -> PolicyRecommendation:
        return self.bundle.recommendation

    @property
    def findings(self) -> tuple[PolicyFinding, ...]:
        return self.bundle.findings

    @property
    def unresolved_questions(self) -> tuple[str, ...]:
        return self.bundle.unresolved_questions

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.to_dict(),
            "bundle": self.bundle.to_dict(),
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


class GovernanceService:
    """Application boundary for deterministic policy evaluation.

    The service delegates to the single injected policy engine. It does not
    approve recommendations, execute actions, distribute output, persist
    findings, or append audit records.
    """

    def __init__(self, policy_engine: PolicyEngineProtocol) -> None:
        if policy_engine is None:
            raise TypeError("policy_engine is required")
        if not isinstance(policy_engine, PolicyEngineProtocol):
            raise TypeError(
                "policy_engine must provide a callable "
                "evaluate_pipeline_event method"
            )

        self._policy_engine = policy_engine
        self._lock = threading.RLock()

    @property
    def policy_engine(self) -> PolicyEngineProtocol:
        return self._policy_engine

    def evaluate(
        self,
        event: PipelineEvent,
    ) -> GovernanceEvaluationResult:
        if not isinstance(event, PipelineEvent):
            raise TypeError("event must be a PipelineEvent")

        with self._lock:
            bundle = self._policy_engine.evaluate_pipeline_event(event)

        if not isinstance(bundle, PolicyEvaluationBundle):
            raise GovernanceConfigurationError(
                "Policy engine returned an invalid evaluation result"
            )

        return GovernanceEvaluationResult(
            event=event,
            bundle=bundle,
        )
