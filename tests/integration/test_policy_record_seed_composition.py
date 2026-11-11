from __future__ import annotations

from pathlib import Path

from amba_ai.application.bootstrap import create_desktop_services
from amba_ai.governance.models import EnforcementAction
from amba_ai.ui.governance_context import DesktopGovernanceContextFactory


def test_desktop_composition_seeds_required_project_controls():
    bootstrap = create_desktop_services(project_root=Path.cwd())
    try:
        registry = bootstrap.application.providers.get("policy_record_registry")
        for record_id in (
            "PROJECT-CONTROL-EDUCATIONAL-PROCESSING-V1",
            "PROJECT-CONTROL-RESTRICTED-DESTINATIONS-V1",
        ):
            record = registry.require_active_by_record_id(record_id)
            assert registry.eligible_for_project_enforcement(record.identity)
    finally:
        bootstrap.close()


def test_notes_pre_gate_proceeds_with_seeded_controls():
    bootstrap = create_desktop_services(project_root=Path.cwd())
    try:
        context = DesktopGovernanceContextFactory(
            session_id="policy-seed-test"
        ).for_operation("generate_notes", document_id=1)
        invocation = bootstrap.services.governance_coordinator.begin(
            method_name="generate_notes",
            input_metadata={"document_id": 1},
            context=context,
        )
        assert (
            invocation.evaluation.bundle.recommendation.recommended_action
            is EnforcementAction.PROCEED
        )
    finally:
        bootstrap.close()
