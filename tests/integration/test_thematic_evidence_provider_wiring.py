from __future__ import annotations

from pathlib import Path

from amba_ai.application.composition import create_test
from amba_ai.application.provider_installation import install_application_providers
from amba_ai.services.thematic_evidence_service import ThematicEvidenceService

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_thematic_evidence_providers_are_lazy_singletons(tmp_path: Path) -> None:
    application = create_test(
        project_root=tmp_path,
        settings_overrides={
            "configuration_root": PROJECT_ROOT / "config",
            "knowledge_base_root": PROJECT_ROOT / "kb",
            "migrations_root": PROJECT_ROOT / "src" / "amba_ai" / "db" / "migrations",
            "strict_governance": False,
            "verify_knowledge_base": True,
        },
        configure=install_application_providers,
    )
    try:
        providers = application.providers
        service = providers.get("thematic_evidence_service", ThematicEvidenceService)
        assert service is providers.get("thematic_evidence_service", ThematicEvidenceService)
        assert providers.get("thematic_evidence_resolver", ThematicEvidenceService) is service
        assert providers.get("thematic_evidence_views", tuple) == service.for_stage("STAGE-1").views
        assert providers.get("policy_evidence_gaps", tuple) == service.for_stage("STAGE-2").gaps
        catalog = providers.get("verified_passage_catalog", dict)
        assert catalog["passage_count"] == 90
    finally:
        application.stop()
