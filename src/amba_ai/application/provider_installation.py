from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from amba_ai.application.health import (
    HealthCheckResult,
    HealthRegistry,
    HealthStatus,
)
from amba_ai.application.lifecycle import ApplicationLifecycle
from amba_ai.application.providers import ProviderRegistry
from amba_ai.application.settings import ApplicationSettings
from amba_ai.db.approval_repository import ApprovalRepository
from amba_ai.db.audit_repository import AuditRepository
from amba_ai.db.database import Database
from amba_ai.db.document_store import DocumentStore
from amba_ai.db.execution_repository import ExecutionRepository
from amba_ai.db.governance_repository import GovernanceRepository
from amba_ai.db.policy_record_repository import PolicyRecordRepository
from amba_ai.governance.approvals import ApprovalService as ApprovalProcessor
from amba_ai.governance.audit import AuditLedger
from amba_ai.governance.audit_verifier import AuditVerifier
from amba_ai.governance.evaluator_registry import EvaluatorRegistry
from amba_ai.governance.evaluators import (
    AuthorizationBasisEvaluator,
    ChildSafeguardingEvaluator,
    CitationIntegrityEvaluator,
    ContentSafetyEvaluator,
    DestinationEvaluator,
    InferenceDataEvaluator,
    ProjectCommercialControlEvaluator,
    ProjectEducationalProcessingEvaluator,
    ProjectTargetedAdControlEvaluator,
)
from amba_ai.governance.execution import ExecutionGateway
from amba_ai.governance.mandates import MandateRegistry
from amba_ai.governance.models import (
    GovernanceConfigurationError,
    UUIDIdentifierProvider,
    to_canonical_json,
)
from amba_ai.governance.operation_registry import (
    DestinationRegistry,
    OperationRegistry,
)
from amba_ai.governance.policy_engine import PolicyEngine
from amba_ai.governance.principals import PrincipalRegistry, SystemClock
from amba_ai.governance.record_registry import PolicyRecordRegistry
from amba_ai.rag.engine import FaissRAGEngine

from amba_ai.governance.distribution import (
    DistributionBlockExecutor,
    DistributionPermitExecutor,
    ReviewQueueExecutor,
)
from amba_ai.institutional.assessors.consumer_protection_assessor import (
    ConsumerProtectionAssessor,
)
from amba_ai.institutional.assessors.data_protection_assessor import (
    DataProtectionAssessor,
)
from amba_ai.institutional.assessors.education_assessor import (
    EducationAssessor,
)
from amba_ai.institutional.conflict_resolution import (
    InstitutionalConflictDetector,
)
from amba_ai.institutional.context_projection import (
    InstitutionalContextProjectionService,
)
from amba_ai.institutional.coordination import (
    InstitutionalCoordinationService,
)
from amba_ai.institutional.registry import (
    InstitutionalAssessorRegistry,
)
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.evidence_release import EvidenceReleaseService
from amba_ai.scenarios.invariant_verifier import ScenarioInvariantVerifier
from amba_ai.scenarios.repository import ScenarioRepository
from amba_ai.scenarios.validator import ScenarioValidator
from amba_ai.services.distribution_service import DistributionService
from amba_ai.services.policy_agent_service import PolicyAgentService
from amba_ai.services.approval_service import ApprovalService
from amba_ai.services.audit_service import AuditService
from amba_ai.services.content_delivery_service import ContentDeliveryService
from amba_ai.services.execution_service import ExecutionService
from amba_ai.services.governance_service import GovernanceService
from amba_ai.services.job_service import JobService
from amba_ai.services.job_governance import JobGovernanceCoordinator
from amba_ai.services.model_service import ModelService

from amba_ai.rag.policy_query import PolicyQueryAdapter
from amba_ai.services.policy_kb_service import PolicyKBService
from amba_ai.standards.ml_intent import (
    MLIntent,
    load_ml_intent,
)
from amba_ai.standards.y3172_registry import (
    Y3172Registry,
)
from amba_ai.standards.y3172_trace_coordinator import (
    Y3172TraceCoordinator,
)

GOVERNANCE_MIGRATION_FILES = (
    "002_governance_records.sql",
    "003_approval_execution_audit.sql",
    "004_policy_records.sql",
)

MANDATORY_PROVIDER_NAMES = (
    "database",
    "governance_repository",
    "approval_repository",
    "execution_repository",
    "audit_repository",
    "policy_record_repository",
    "policy_record_registry",
    "operation_registry",
    "destination_registry",
    "evaluator_registry",
    "principal_registry",
    "mandate_registry",
    "policy_engine",
    "approval_processor",
    "execution_gateway",
    "audit_ledger",
    "audit_verifier",
    "governance_service",
    "approval_service",
    "execution_service",
    "audit_service",
)

LAZY_PROVIDER_NAMES = (
    "rag_engine",
    "model_service",
    "content_delivery_service",
    "job_governance_coordinator",
    "job_service",
    "y3172_registry",
    "ml_intent",
    "y3172_trace_coordinator",
    "policy_query_adapter",
    "policy_kb_service",
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

REQUIRED_PROVIDER_NAMES = (
    "clock",
    "identifier_provider",
    "canonical_serializer",
    "document_store",
    *MANDATORY_PROVIDER_NAMES,
    *LAZY_PROVIDER_NAMES,
)


def _required_file(path: Path, description: str) -> Path:
    if not path.is_file():
        raise GovernanceConfigurationError(
            f"Required {description} does not exist: {path.as_posix()}"
        )
    return path


def _build_database(settings: ApplicationSettings) -> Database:
    database = Database(settings.database_path)
    if settings.initialize_database:
        database.initialize()
    return database


def _build_governance_repository(
    settings: ApplicationSettings,
) -> GovernanceRepository:
    repository = GovernanceRepository(settings.database_path)
    if not settings.initialize_database:
        return repository

    for filename in GOVERNANCE_MIGRATION_FILES:
        path = _required_file(
            settings.migrations_root / filename,
            f"governance migration {filename}",
        )
        repository.apply_migration_file(path)

    return repository


def _require_governance_schema(registry: ProviderRegistry) -> None:
    registry.get("governance_repository", GovernanceRepository)


def _build_approval_repository(
    registry: ProviderRegistry,
    settings: ApplicationSettings,
) -> ApprovalRepository:
    _require_governance_schema(registry)
    return ApprovalRepository(settings.database_path)


def _build_execution_repository(
    registry: ProviderRegistry,
    settings: ApplicationSettings,
) -> ExecutionRepository:
    _require_governance_schema(registry)
    return ExecutionRepository(settings.database_path)


def _build_audit_repository(
    registry: ProviderRegistry,
    settings: ApplicationSettings,
) -> AuditRepository:
    _require_governance_schema(registry)
    return AuditRepository(settings.database_path)


def _build_policy_record_repository(
    registry: ProviderRegistry,
    settings: ApplicationSettings,
) -> PolicyRecordRepository:
    _require_governance_schema(registry)
    return PolicyRecordRepository(settings.database_path)


def _build_policy_record_registry(
    registry: ProviderRegistry,
) -> PolicyRecordRegistry:
    repository = registry.get(
        "policy_record_repository",
        PolicyRecordRepository,
    )
    runtime_registry = PolicyRecordRegistry()
    for record in repository.list_all():
        runtime_registry.register(record)
    return runtime_registry


def _build_evaluator_registry(
    registry: ProviderRegistry,
) -> EvaluatorRegistry:
    identifiers = registry.get("identifier_provider", UUIDIdentifierProvider)
    destinations = registry.get("destination_registry", DestinationRegistry)
    operations = registry.get("operation_registry", OperationRegistry)

    evaluator_registry = EvaluatorRegistry()
    evaluators = (
        AuthorizationBasisEvaluator(identifiers),
        DestinationEvaluator(identifiers, destinations),
        ProjectEducationalProcessingEvaluator(identifiers),
        CitationIntegrityEvaluator(identifiers),
        ContentSafetyEvaluator(identifiers),
        ProjectCommercialControlEvaluator(identifiers),
        ChildSafeguardingEvaluator(identifiers),
        ProjectTargetedAdControlEvaluator(identifiers),
        InferenceDataEvaluator(identifiers),
    )
    for evaluator in evaluators:
        evaluator_registry.register(evaluator)

    evaluator_registry.validate_operations(operations)
    return evaluator_registry

def _build_y3172_registry(
    settings: ApplicationSettings,
) -> Y3172Registry:
    mapping_path = _required_file(
        (
            settings.knowledge_base_root
            / "mappings"
            / "y3172_mapping.yaml"
        ),
        "Y.3172 mapping",
    )

    return Y3172Registry.load_from_yaml(
        mapping_path,
        allowed_root=settings.knowledge_base_root,
    )


def _build_ml_intent(
    settings: ApplicationSettings,
) -> MLIntent:
    intent_path = _required_file(
        settings.configuration_root
        / "ml_intent.yaml",
        "ML intent configuration",
    )

    return load_ml_intent(
        intent_path,
        allowed_root=settings.configuration_root,
    )


def _build_y3172_trace_coordinator(
    registry: ProviderRegistry,
) -> Y3172TraceCoordinator:
    return Y3172TraceCoordinator(
        registry=registry.get(
            "y3172_registry",
            Y3172Registry,
        ),
        identifier_provider=registry.get(
            "identifier_provider",
            UUIDIdentifierProvider,
        ),
        clock=registry.get(
            "clock",
            SystemClock,
        ),
    )


def _build_policy_query_adapter(
    registry: ProviderRegistry,
) -> PolicyQueryAdapter:
    return PolicyQueryAdapter(
        registry.get(
            "policy_record_registry",
            PolicyRecordRegistry,
        )
    )


def _build_policy_kb_service(
    registry: ProviderRegistry,
) -> PolicyKBService:
    return PolicyKBService(
        search_engine=registry.get(
            "rag_engine",
        ),
        query_adapter=registry.get(
            "policy_query_adapter",
            PolicyQueryAdapter,
        ),
    )




def _build_distribution_service() -> DistributionService:
    return DistributionService(
        permit_executor=DistributionPermitExecutor(),
        block_executor=DistributionBlockExecutor(),
        review_executor=ReviewQueueExecutor(),
    )


def _build_policy_agent_service(
    registry: ProviderRegistry,
) -> PolicyAgentService:
    return PolicyAgentService(
        policy_kb_service=registry.get(
            "policy_kb_service",
            PolicyKBService,
        ),
        governance_service=registry.get(
            "governance_service",
            GovernanceService,
        ),
        execution_service=registry.get(
            "execution_service",
            ExecutionService,
        ),
        distribution_service=registry.get(
            "distribution_service",
            DistributionService,
        ),
        trace_coordinator=registry.get(
            "y3172_trace_coordinator",
            Y3172TraceCoordinator,
        ),
        audit_service=registry.get(
            "audit_service",
            AuditService,
        ),
    )


def _build_scenario_clock(
    settings: ApplicationSettings,
) -> DeterministicScenarioClock:
    if settings.profile.value not in {"demo", "test"}:
        raise GovernanceConfigurationError(
            "scenario_clock is available only for synthetic demo/test profiles"
        )
    if not settings.synthetic_only:
        raise GovernanceConfigurationError(
            "scenario_clock requires synthetic_only application settings"
        )
    return DeterministicScenarioClock(
        initial_time="2026-01-01T00:00:00Z"
    )


def _build_institutional_assessor_registry(
    registry: ProviderRegistry,
) -> InstitutionalAssessorRegistry:
    identifiers = registry.get(
        "identifier_provider",
        UUIDIdentifierProvider,
    )
    scenario_clock = registry.get(
        "scenario_clock",
        DeterministicScenarioClock,
    )
    assessor_registry = InstitutionalAssessorRegistry()
    for assessor_type in (
        EducationAssessor,
        DataProtectionAssessor,
        ConsumerProtectionAssessor,
    ):
        assessor_registry.register(
            assessor_type(
                identifier_provider=identifiers,
                clock=scenario_clock,
            )
        )
    return assessor_registry

def _resolve_mandatory_providers(registry: ProviderRegistry) -> None:
    for name in MANDATORY_PROVIDER_NAMES:
        registry.get(name)


def _register_health_checks(
    providers: ProviderRegistry,
    settings: ApplicationSettings,
) -> None:
    health = providers.get("health_registry", HealthRegistry)

    def database_schema_check() -> HealthCheckResult:
        try:
            providers.get("policy_record_repository", PolicyRecordRepository)
        except Exception as error:
            return HealthCheckResult(
                name="governance-database-schema",
                status=HealthStatus.UNHEALTHY,
                message=f"governance database schema unavailable: {type(error).__name__}",
            )
        return HealthCheckResult(
            name="governance-database-schema",
            status=HealthStatus.HEALTHY,
            message="governance database schema is available",
        )

    def configuration_check() -> HealthCheckResult:
        required = (
            settings.configuration_root / "operations.yaml",
            settings.configuration_root / "destinations.yaml",
            settings.configuration_root / "agent_mandates.yaml",
        )
        missing = tuple(path.name for path in required if not path.is_file())
        if missing:
            return HealthCheckResult(
                name="governance-configuration",
                status=HealthStatus.UNHEALTHY,
                message="required governance configuration is missing",
            )
        return HealthCheckResult(
            name="governance-configuration",
            status=HealthStatus.HEALTHY,
            message="required governance configuration is available",
        )

    health.register("governance-database-schema", database_schema_check)
    health.register("governance-configuration", configuration_check)


def install_application_providers(
    providers: ProviderRegistry,
    settings: ApplicationSettings,
) -> None:
    if not isinstance(providers, ProviderRegistry):
        raise TypeError("providers must be a ProviderRegistry")
    if not isinstance(settings, ApplicationSettings):
        raise TypeError("settings must be an ApplicationSettings")

    providers.register("clock", lambda _registry: SystemClock())
    providers.register(
        "identifier_provider",
        lambda _registry: UUIDIdentifierProvider(),
    )
    providers.register_instance("canonical_serializer", to_canonical_json)

    providers.register("database", lambda _registry: _build_database(settings))
    providers.register("document_store", lambda _registry: DocumentStore())

    providers.register(
        "governance_repository",
        lambda _registry: _build_governance_repository(settings),
    )
    providers.register(
        "approval_repository",
        lambda registry: _build_approval_repository(registry, settings),
    )
    providers.register(
        "execution_repository",
        lambda registry: _build_execution_repository(registry, settings),
    )
    providers.register(
        "audit_repository",
        lambda registry: _build_audit_repository(registry, settings),
    )
    providers.register(
        "policy_record_repository",
        lambda registry: _build_policy_record_repository(registry, settings),
    )

    providers.register(
        "policy_record_registry",
        _build_policy_record_registry,
    )
    providers.register(
        "operation_registry",
        lambda _registry: OperationRegistry.load_from_yaml(
            _required_file(
                settings.configuration_root / "operations.yaml",
                "operation configuration",
            )
        ),
    )
    providers.register(
        "destination_registry",
        lambda _registry: DestinationRegistry.load_from_yaml(
            _required_file(
                settings.configuration_root / "destinations.yaml",
                "destination configuration",
            )
        ),
    )
    providers.register("evaluator_registry", _build_evaluator_registry)
    providers.register("principal_registry", lambda _registry: PrincipalRegistry())
    providers.register(
        "mandate_registry",
        lambda _registry: MandateRegistry.load_from_yaml(
            _required_file(
                settings.configuration_root / "agent_mandates.yaml",
                "mandate configuration",
            )
        ),
    )

    providers.register(
        "policy_engine",
        lambda registry: PolicyEngine(
            registry.get("policy_record_registry", PolicyRecordRegistry),
            registry.get("operation_registry", OperationRegistry),
            registry.get("evaluator_registry", EvaluatorRegistry),
            registry.get("identifier_provider", UUIDIdentifierProvider),
        ),
    )
    providers.register(
        "approval_processor",
        lambda registry: ApprovalProcessor(
            registry.get("principal_registry", PrincipalRegistry),
            registry.get("mandate_registry", MandateRegistry),
            registry.get("approval_repository", ApprovalRepository),
            registry.get("identifier_provider", UUIDIdentifierProvider),
            registry.get("clock", SystemClock),
        ),
    )
    providers.register(
        "execution_gateway",
        lambda registry: ExecutionGateway(
            registry.get("execution_repository", ExecutionRepository),
            registry.get("destination_registry", DestinationRegistry),
            registry.get("approval_repository", ApprovalRepository),
            registry.get("identifier_provider", UUIDIdentifierProvider),
            registry.get("clock", SystemClock),
        ),
    )
    providers.register(
        "audit_ledger",
        lambda registry: AuditLedger(
            registry.get("audit_repository", AuditRepository),
            registry.get("clock", SystemClock),
        ),
    )
    providers.register(
        "audit_verifier",
        lambda registry: AuditVerifier(registry.get("audit_ledger", AuditLedger)),
    )

    providers.register(
        "governance_service",
        lambda registry: GovernanceService(registry.get("policy_engine", PolicyEngine)),
    )
    providers.register(
        "approval_service",
        lambda registry: ApprovalService(registry.get("approval_processor", ApprovalProcessor)),
    )
    providers.register(
        "execution_service",
        lambda registry: ExecutionService(registry.get("execution_gateway", ExecutionGateway)),
    )
    providers.register(
        "audit_service",
        lambda registry: AuditService(
            registry.get("audit_ledger", AuditLedger),
            registry.get("audit_verifier", AuditVerifier),
        ),
    )

    providers.register(
        "rag_engine",
        lambda registry: FaissRAGEngine(
            registry.get("database", Database),
            kb_dir=settings.knowledge_base_root,
        ),
    )
    providers.register(
    "y3172_registry",
    lambda _registry: _build_y3172_registry(
        settings
        ),
    )

    providers.register(
        "ml_intent",
        lambda _registry: _build_ml_intent(
            settings
        ),
    )

    providers.register(
        "y3172_trace_coordinator",
        _build_y3172_trace_coordinator,
    )

    providers.register(
        "policy_query_adapter",
        _build_policy_query_adapter,
    )

    providers.register(
        "policy_kb_service",
        _build_policy_kb_service,
    )


    providers.register(
        "distribution_service",
        lambda _registry: _build_distribution_service(),
    )
    providers.register(
        "policy_agent_service",
        _build_policy_agent_service,
    )
    providers.register(
        "scenario_clock",
        lambda _registry: _build_scenario_clock(settings),
    )
    providers.register(
        "evidence_release_service",
        lambda registry: EvidenceReleaseService(
            identifier_provider=registry.get(
                "identifier_provider",
                UUIDIdentifierProvider,
            ),
            clock=registry.get(
                "scenario_clock",
                DeterministicScenarioClock,
            ),
        ),
    )
    providers.register(
        "institutional_context_projection_service",
        lambda registry: InstitutionalContextProjectionService(
            identifier_provider=registry.get(
                "identifier_provider",
                UUIDIdentifierProvider,
            ),
            clock=registry.get(
                "scenario_clock",
                DeterministicScenarioClock,
            ),
        ),
    )
    providers.register(
        "institutional_assessor_registry",
        _build_institutional_assessor_registry,
    )
    providers.register(
        "institutional_conflict_detector",
        lambda _registry: InstitutionalConflictDetector(),
    )
    providers.register(
        "institutional_coordination_service",
        lambda registry: InstitutionalCoordinationService(
            registry=registry.get(
                "institutional_assessor_registry",
                InstitutionalAssessorRegistry,
            ),
            conflict_detector=registry.get(
                "institutional_conflict_detector",
                InstitutionalConflictDetector,
            ),
            identifier_provider=registry.get(
                "identifier_provider",
                UUIDIdentifierProvider,
            ),
            clock=registry.get(
                "scenario_clock",
                DeterministicScenarioClock,
            ),
        ),
    )
    providers.register(
        "scenario_repository",
        lambda _registry: ScenarioRepository(),
    )
    providers.register(
        "scenario_validator",
        lambda registry: ScenarioValidator(
            institutional_registry=registry.get(
                "institutional_assessor_registry",
                InstitutionalAssessorRegistry,
            )
        ),
    )
    providers.register(
        "scenario_invariant_verifier",
        lambda _registry: ScenarioInvariantVerifier(),
    )
    providers.register("model_service", lambda _registry: ModelService())
    providers.register(
        "content_delivery_service",
        lambda _registry: ContentDeliveryService(),
    )
    providers.register(
        "job_governance_coordinator",
        lambda registry: JobGovernanceCoordinator(
            governance_service=registry.get("governance_service", GovernanceService),
            execution_service=registry.get("execution_service", ExecutionService),
            audit_service=registry.get("audit_service", AuditService),
            identifier_provider=registry.get("identifier_provider", UUIDIdentifierProvider),
            clock=registry.get("clock", SystemClock),
        ),
    )
    providers.register(
        "job_service",
        lambda registry: JobService(
            db=registry.get("database", Database),
            rag_engine=registry.get("rag_engine", FaissRAGEngine),
            model_service=registry.get("model_service", ModelService),
            content_delivery_service=registry.get(
                "content_delivery_service",
                ContentDeliveryService,
            ),
            governance_coordinator=registry.get(
                "job_governance_coordinator",
                JobGovernanceCoordinator,
            ),
        ),
    )

    lifecycle = providers.get("lifecycle", ApplicationLifecycle)
    lifecycle.register(
        "mandatory-application-providers",
        startup=lambda: _resolve_mandatory_providers(providers),
    )
    _register_health_checks(providers, settings)
