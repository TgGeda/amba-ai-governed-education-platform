from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from amba_ai.governance.execution import ExecutionResult
from amba_ai.governance.models import (
    EnforcementAction,
    GovernanceConfigurationError,
    PolicyRecommendation,
)
from amba_ai.services.job_governance import (
    JOB_OPERATION_MAP,
    JobGovernanceContext,
    JobGovernanceCoordinator,
    JobGovernanceGateError,
)


class SequentialIds:
    def __init__(self) -> None:
        self.value = 0

    def new_id(self, prefix: str) -> str:
        self.value += 1
        return f"{prefix}_{self.value}"


class FixedClock:
    def now_iso(self) -> str:
        return "2026-01-01T00:00:00+00:00"


class FakeGovernance:
    def __init__(self, *actions: EnforcementAction) -> None:
        self.actions = list(actions)
        self.events: list[Any] = []

    def evaluate(self, event: Any) -> object:
        self.events.append(event)
        action = self.actions.pop(0)
        recommendation = PolicyRecommendation(
            recommendation_id=f"rec_{len(self.events)}",
            event_id=event.event_id,
            recommended_action=action,
            mitigation_steps=(),
            requires_approval=(action is EnforcementAction.REQUIRE_APPROVAL),
            escalation_role=(
                "school_administrator"
                if action is EnforcementAction.REQUIRE_APPROVAL
                else None
            ),
        )
        return SimpleNamespace(
            recommendation=recommendation,
            findings=(),
            unresolved_questions=(),
        )


class FakeExecution:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute(
        self,
        **kwargs: Any,
    ) -> ExecutionResult:
        self.calls.append(kwargs)

        event = kwargs["event"]

        request = SimpleNamespace(
            event_id=event.event_id,
            operation_id=event.operation_id,
        )

        result = object.__new__(
            ExecutionResult
        )

        object.__setattr__(
            result,
            "request",
            request,
        )
        object.__setattr__(
            result,
            "execution_receipt",
            object(),
        )
        object.__setattr__(
            result,
            "review_queue_receipt",
            None,
        )
        object.__setattr__(
            result,
            "distribution_acknowledgment",
            object(),
        )
        object.__setattr__(
            result,
            "duplicate",
            False,
        )

        return result


class FakeAudit:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def append(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return object()


def context() -> JobGovernanceContext:
    return JobGovernanceContext(
        run_id="run-1",
        scenario_id="scenario-1",
        stage_id="stage-1",
        source_node="SRC",
        destination_id="student_ui",
        synthetic=True,
    )


def coordinator(*actions: EnforcementAction) -> tuple[
    JobGovernanceCoordinator,
    FakeGovernance,
    FakeExecution,
    FakeAudit,
]:
    governance = FakeGovernance(*actions)
    execution = FakeExecution()
    audit = FakeAudit()
    value = JobGovernanceCoordinator(
        governance_service=governance,
        execution_service=execution,
        audit_service=audit,
        identifier_provider=SequentialIds(),
        clock=FixedClock(),
    )
    return value, governance, execution, audit


@pytest.mark.parametrize(
    "action",
    (
        EnforcementAction.CONFIRM,
        EnforcementAction.HOLD_FOR_REVIEW,
        EnforcementAction.REQUIRE_APPROVAL,
        EnforcementAction.MODIFY,
        EnforcementAction.BLOCK,
        EnforcementAction.ABSTAIN,
    ),
)
def test_non_proceed_pre_gate_fails_closed(action: EnforcementAction) -> None:
    value, governance, execution, audit = coordinator(action)

    with pytest.raises(JobGovernanceGateError) as captured:
        value.begin(
            method_name="tutor_answer",
            input_metadata={"question_length": 12},
            context=context(),
        )

    assert captured.value.action is action
    assert len(governance.events) == 1
    assert execution.calls == []
    assert [call["event_type"] for call in audit.calls] == [
        "JOB_GOVERNANCE_PRE_EVALUATED",
        "JOB_GOVERNANCE_PREVENTED",
    ]


def test_unknown_method_and_missing_context_fail_closed() -> None:
    value, _governance, _execution, _audit = coordinator(
        EnforcementAction.PROCEED
    )

    with pytest.raises(GovernanceConfigurationError, match="not mapped"):
        value.begin(
            method_name="delete_document",
            input_metadata={},
            context=context(),
        )

    with pytest.raises(GovernanceConfigurationError, match="required"):
        value.begin(
            method_name="tutor_answer",
            input_metadata={},
            context=None,
        )


def test_pre_gate_rejects_raw_or_unknown_metadata() -> None:
    value, _governance, _execution, _audit = coordinator(
        EnforcementAction.PROCEED
    )

    with pytest.raises(GovernanceConfigurationError, match="non-permitted"):
        value.begin(
            method_name="tutor_answer",
            input_metadata={"question": "learner secret"},
            context=context(),
        )


def test_proceed_then_complete_executes_once_and_audits_safe_metadata() -> None:
    value, governance, execution, audit = coordinator(
        EnforcementAction.PROCEED,
        EnforcementAction.PROCEED,
    )
    invocation = value.begin(
        method_name="tutor_answer",
        input_metadata={
            "document_id": 7,
            "question_length": 15,
            "top_k": 5,
            "max_tokens": 1200,
            "remember": True,
            "active_tab": "Student Tutor",
        },
        context=context(),
    )

    completion = value.complete(
        invocation=invocation,
        result_material={
            "answer_text": "private generated answer",
            "sources": ["source-1"],
            "model_name": "model",
        },
        result_metadata={
            "output_type": "answer_result",
            "answer_length": 24,
            "citation_count": 1,
            "document_id": 7,
            "model_name": "model",
        },
    )

    assert len(governance.events) == 2
    assert governance.events[0].event_id == governance.events[1].event_id
    assert governance.events[0].operation_id == (
        JOB_OPERATION_MAP["tutor_answer"]
    )
    assert len(execution.calls) == 1
    assert execution.calls[0]["event"] is completion.post_event
    assert execution.calls[0]["recommendation"] is (
        completion.post_evaluation.recommendation
    )
    assert execution.calls[0]["approval_decision"] is None
    assert len(completion.output_sha256) == 64

    serialized_audit = repr(audit.calls)
    assert "private generated answer" not in serialized_audit
    assert "learner secret" not in serialized_audit
    assert [call["event_type"] for call in audit.calls] == [
        "JOB_GOVERNANCE_PRE_EVALUATED",
        "JOB_GOVERNANCE_POST_EVALUATED",
        "JOB_EXECUTION_RECORDED",
    ]


def test_output_digest_is_deterministic() -> None:
    first, *_ = coordinator(
        EnforcementAction.PROCEED,
        EnforcementAction.PROCEED,
    )
    second, *_ = coordinator(
        EnforcementAction.PROCEED,
        EnforcementAction.PROCEED,
    )

    kwargs = {
        "result_material": {"b": 2, "a": 1},
        "result_metadata": {
            "output_type": "feedback_event",
            "recorded": True,
        },
    }
    first_result = first.complete(
        invocation=first.begin(
            method_name="record_feedback_event",
            input_metadata={},
            context=context(),
        ),
        **kwargs,
    )
    second_result = second.complete(
        invocation=second.begin(
            method_name="record_feedback_event",
            input_metadata={},
            context=context(),
        ),
        **kwargs,
    )

    assert first_result.output_sha256 == second_result.output_sha256


def test_post_metadata_rejects_content_fields() -> None:
    value, *_ = coordinator(
        EnforcementAction.PROCEED,
        EnforcementAction.PROCEED,
    )
    invocation = value.begin(
        method_name="generate_notes",
        input_metadata={"document_id": 1, "force": False},
        context=context(),
    )

    with pytest.raises(GovernanceConfigurationError, match="non-permitted"):
        value.complete(
            invocation=invocation,
            result_material={"markdown_notes": "private notes"},
            result_metadata={"markdown_notes": "private notes"},
        )
