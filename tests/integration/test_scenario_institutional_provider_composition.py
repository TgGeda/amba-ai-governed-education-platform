from __future__ import annotations

from pathlib import Path

from amba_ai.application.health import HealthRegistry
from amba_ai.application.lifecycle import ApplicationLifecycle
from amba_ai.application.provider_installation import (
    LAZY_PROVIDER_NAMES,
    install_application_providers,
)
from amba_ai.application.providers import ProviderRegistry
from amba_ai.application.settings import ApplicationProfile, default_settings
from amba_ai.governance.models import UUIDIdentifierProvider
from amba_ai.institutional.conflict_resolution import InstitutionalConflictDetector
from amba_ai.institutional.context_projection import InstitutionalContextProjectionService
from amba_ai.institutional.coordination import InstitutionalCoordinationService
from amba_ai.institutional.registry import InstitutionalAssessorRegistry
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.evidence_release import EvidenceReleaseService
from amba_ai.scenarios.invariant_verifier import ScenarioInvariantVerifier
from amba_ai.scenarios.repository import ScenarioRepository
from amba_ai.scenarios.validator import ScenarioValidator
from amba_ai.services.audit_service import AuditService
from amba_ai.services.distribution_service import DistributionService
from amba_ai.services.execution_service import ExecutionService
from amba_ai.services.governance_service import GovernanceService
from amba_ai.services.policy_agent_service import PolicyAgentService
from amba_ai.services.policy_kb_service import PolicyKBService
from amba_ai.standards.y3172_trace_coordinator import Y3172TraceCoordinator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIGURATION_ROOT = PROJECT_ROOT / "config"
KNOWLEDGE_BASE_ROOT = PROJECT_ROOT / "kb"
MIGRATIONS_ROOT = PROJECT_ROOT / "src" / "amba_ai" / "db" / "migrations"

NEW_PROVIDER_NAMES = (
    "distribution_service",
    "policy_agent_service",
    "scenario_clock",
    "evidence_release_service",
    "institutional_context_projection_service",
    "institutional_assessor_registry",
    "institutional_conflict_detector",
    "institutional_coordination_service",
    "scenario_repository",
    "scenario_validator",
    "scenario_invariant_verifier",
)


class RAGEngineStub:
    def search(self, query: str, top_k: int = 10, min_similarity: float = 0.40) -> list:
        return []


def _providers(tmp_path: Path) -> ProviderRegistry:
    settings = default_settings(
        ApplicationProfile.TEST,
        project_root=tmp_path,
        overrides={
            "configuration_root": CONFIGURATION_ROOT,
            "knowledge_base_root": KNOWLEDGE_BASE_ROOT,
            "migrations_root": MIGRATIONS_ROOT,
            "verify_knowledge_base": False,
        },
    )
    providers = ProviderRegistry()
    providers.register_instance("settings", settings)
    providers.register_instance("lifecycle", ApplicationLifecycle())
    providers.register_instance("health_registry", HealthRegistry())
    install_application_providers(providers, settings)
    return providers


def test_new_provider_graph_is_lazy(tmp_path: Path) -> None:
    providers = _providers(tmp_path)
    try:
        assert set(NEW_PROVIDER_NAMES).issubset(LAZY_PROVIDER_NAMES)
        assert all(not providers.is_resolved(name) for name in NEW_PROVIDER_NAMES)
    finally:
        providers.close()


def test_scenario_repository_and_validator_do_not_resolve_rag(tmp_path: Path) -> None:
    providers = _providers(tmp_path)
    try:
        repository = providers.get("scenario_repository", ScenarioRepository)
        validator = providers.get("scenario_validator", ScenarioValidator)
        assert repository is providers.get("scenario_repository", ScenarioRepository)
        assert validator is providers.get("scenario_validator", ScenarioValidator)
        assert not providers.is_resolved("rag_engine")
        assert not providers.is_resolved("policy_kb_service")
    finally:
        providers.close()


def test_scenario_services_share_clock_and_identifier_provider(tmp_path: Path) -> None:
    providers = _providers(tmp_path)
    try:
        scenario_clock = providers.get("scenario_clock", DeterministicScenarioClock)
        identifiers = providers.get("identifier_provider", UUIDIdentifierProvider)
        evidence = providers.get("evidence_release_service", EvidenceReleaseService)
        projection = providers.get(
            "institutional_context_projection_service",
            InstitutionalContextProjectionService,
        )
        registry = providers.get(
            "institutional_assessor_registry",
            InstitutionalAssessorRegistry,
        )
        coordination = providers.get(
            "institutional_coordination_service",
            InstitutionalCoordinationService,
        )
        assert evidence.clock is scenario_clock
        assert projection.clock is scenario_clock
        assert coordination._clock is scenario_clock
        assert evidence._identifier_provider is identifiers
        assert projection._identifier_provider is identifiers
        assert coordination._identifier_provider is identifiers
        assert len(registry.list_assessors()) == 3
        assert all(assessor._clock is scenario_clock for assessor in registry.list_assessors())
        assert all(
            assessor._identifier_provider is identifiers
            for assessor in registry.list_assessors()
        )
        assert not providers.is_resolved("rag_engine")
    finally:
        providers.close()


def test_scenario_validator_reuses_institutional_registry(tmp_path: Path) -> None:
    providers = _providers(tmp_path)
    try:
        registry = providers.get(
            "institutional_assessor_registry",
            InstitutionalAssessorRegistry,
        )
        validator = providers.get("scenario_validator", ScenarioValidator)
        assert validator._institutional_registry is registry
        assert not providers.is_resolved("rag_engine")
    finally:
        providers.close()


def test_coordination_reuses_registry_detector_and_shared_dependencies(tmp_path: Path) -> None:
    providers = _providers(tmp_path)
    try:
        service = providers.get(
            "institutional_coordination_service",
            InstitutionalCoordinationService,
        )
        assert service._registry is providers.get(
            "institutional_assessor_registry",
            InstitutionalAssessorRegistry,
        )
        assert service._conflict_detector is providers.get(
            "institutional_conflict_detector",
            InstitutionalConflictDetector,
        )
        assert not providers.is_resolved("rag_engine")
    finally:
        providers.close()


def test_policy_agent_reuses_existing_dependency_chain(tmp_path: Path) -> None:
    providers = _providers(tmp_path)
    rag = RAGEngineStub()
    try:
        providers.register_instance("rag_engine", rag, replace=True)
        service = providers.get("policy_agent_service", PolicyAgentService)
        assert service._policy_kb_service is providers.get(
            "policy_kb_service", PolicyKBService
        )
        assert service._governance_service is providers.get(
            "governance_service", GovernanceService
        )
        assert service._execution_service is providers.get(
            "execution_service", ExecutionService
        )
        assert service._distribution_service is providers.get(
            "distribution_service", DistributionService
        )
        assert service._trace_coordinator is providers.get(
            "y3172_trace_coordinator", Y3172TraceCoordinator
        )
        assert service._audit_service is providers.get(
            "audit_service", AuditService
        )
        assert providers.get("rag_engine") is rag
    finally:
        providers.close()


def test_stateless_and_repository_providers_are_cached(tmp_path: Path) -> None:
    providers = _providers(tmp_path)
    try:
        for name, expected in (
            ("distribution_service", DistributionService),
            ("institutional_conflict_detector", InstitutionalConflictDetector),
            ("scenario_repository", ScenarioRepository),
            ("scenario_invariant_verifier", ScenarioInvariantVerifier),
        ):
            assert providers.get(name, expected) is providers.get(name, expected)
    finally:
        providers.close()
