from __future__ import annotations

import inspect

from amba_ai.application.demo_presenter import _safe_text
from amba_ai.application.demo_service import (
    ComposedFourStageDemoService,
    JudgeDemoSummary,
    _approval_status,
    _summarize_event,
)


def test_summary_reads_actual_runtime_artifacts():
    source=inspect.getsource(_summarize_event)
    for required in (
        "response.governance_bundle.recommendation",
        "execution.execution_receipt",
        "execution.review_queue_receipt",
        "execution.distribution_acknowledgment",
        "response.distribution_effect",
        "response.y3172_trace.nodes",
        "response.audit_block.block_index",
        "response.kb_response.results",
    ):
        assert required in source


def test_demo_service_does_not_construct_governance_artifacts():
    source=inspect.getsource(ComposedFourStageDemoService)
    for prohibited in (
        "PolicyRecommendation(", "ApprovalDecision(", "ExecutionReceipt(",
        "ReviewQueueReceipt(", "DistributionEffect(",
        "DistributionAcknowledgment(", "Y3172PipelineTrace(", "AuditBlock(",
    ):
        assert prohibited not in source


def test_approval_state_never_infers_rejection_from_execution():
    source=inspect.getsource(_approval_status)
    assert "execution" not in source
    assert "required_not_supplied" in source


def test_terminal_text_strips_control_characters():
    assert _safe_text("safe\x1b[31mtext\x00") == "safe[31mtext"


def test_judge_summary_exposes_no_operational_surface():
    for name in ("approve","authorize","execute","deliver","distribute","recommend"):
        assert not hasattr(JudgeDemoSummary,name)
