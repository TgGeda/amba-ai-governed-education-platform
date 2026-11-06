from __future__ import annotations

import io
import inspect

from amba_ai.application.demo_presenter import TerminalDemoPresenter
from amba_ai.application.demo_service import (
    ComposedFourStageDemoService,
    JudgeDemoSummary,
    JudgeEventSummary,
)


def test_demo_service_resolves_verified_provider_graph():
    source=inspect.getsource(ComposedFourStageDemoService.run)
    for provider in (
        "scenario_repository", "operation_registry", "destination_registry",
        "scenario_validator", "scenario_clock", "evidence_release_service",
        "institutional_context_projection_service", "institutional_coordination_service",
        "policy_agent_service", "scenario_invariant_verifier", "audit_service",
    ):
        assert f'"{provider}"' in source


def test_presenter_uses_event_level_summary_without_expected_action_table():
    source=inspect.getsource(TerminalDemoPresenter)
    assert "stage.events" in source
    for forbidden in ("expected_action", "PROCEED", "HOLD_FOR_REVIEW", "BLOCK"):
        assert forbidden not in source


def test_presenter_supports_safe_stream_rendering():
    source=inspect.getsource(TerminalDemoPresenter.render)
    assert "stream.write" in source
    assert "_safe_text" in inspect.getsource(TerminalDemoPresenter)


def test_summary_models_keep_claim_boundaries_and_artifact_ids():
    fields=JudgeDemoSummary.__dataclass_fields__
    assert fields["formal_y3172_conformance_claimed"].default is False
    assert fields["certification_claimed"].default is False
    event_fields=JudgeEventSummary.__dataclass_fields__
    for name in (
        "execution_receipt_id", "review_queue_receipt_id", "acknowledgment_id",
        "event_id", "operation_id", "destination_id",
    ):
        assert name in event_fields
