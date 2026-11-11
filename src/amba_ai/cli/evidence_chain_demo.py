from __future__ import annotations
from pathlib import Path
import argparse, sys
from amba_ai.application.composition import create_demo
from amba_ai.application.provider_installation import install_application_providers
from amba_ai.application.bootstrap import build_application_services
from amba_ai.application.providers import ProviderRegistry
from amba_ai.application.settings import ApplicationSettings
from amba_ai.governance.models import UUIDIdentifierProvider
from amba_ai.governance.principals import SystemClock
from amba_ai.application.demo_service import ComposedFourStageDemoService
from amba_ai.application.evidence_chain_report import build_evidence_chain_report,write_evidence_chain_report
from amba_ai.scenarios.runner import FourStageScenarioRunner
from amba_ai.scenarios.demo_definition import SCENARIO_ID,create_four_stage_education_scenario
from amba_ai.scenarios.repository import ScenarioRepository
from amba_ai.governance.operation_registry import OperationRegistry,DestinationRegistry
from amba_ai.scenarios.validator import ScenarioValidator
from amba_ai.scenarios.clock import DeterministicScenarioClock
from amba_ai.scenarios.evidence_release import EvidenceReleaseService
from amba_ai.institutional.context_projection import InstitutionalContextProjectionService
from amba_ai.institutional.coordination import InstitutionalCoordinationService
from amba_ai.services.policy_agent_service import PolicyAgentService
from amba_ai.scenarios.invariant_verifier import ScenarioInvariantVerifier
from amba_ai.services.audit_service import AuditService
from amba_ai.scenarios.learning_runner import LearningGovernanceScenarioRunner

EVIDENCE_CHAIN_TIME = "2026-01-01T00:00:00+00:00"


class EvidenceChainIdentifierProvider(UUIDIdentifierProvider):
    """Deterministic UUID-provider subtype accepted by the provider graph."""

    def __init__(self, initial_index: int = 1) -> None:
        if type(initial_index) is not int or initial_index <= 0:
            raise ValueError("initial_index must be a positive integer")
        self._index = initial_index

    def new_id(self, prefix: str) -> str:
        normalized = str(prefix).strip()
        if not normalized:
            raise ValueError("prefix must not be empty")
        value = f"{normalized}_{self._index:012d}"
        self._index += 1
        return value


class EvidenceChainClock(SystemClock):
    """Fixed system-clock subtype accepted by the provider graph."""

    def now_iso(self) -> str:
        return EVIDENCE_CHAIN_TIME


def install_evidence_chain_providers(
    providers: ProviderRegistry,
    settings: ApplicationSettings,
) -> None:
    """Install the real provider graph with deterministic demo primitives."""
    install_application_providers(providers, settings)
    providers.register_instance(
        "identifier_provider",
        EvidenceChainIdentifierProvider(),
        replace=True,
    )
    providers.register_instance(
        "clock",
        EvidenceChainClock(),
        replace=True,
    )


def execute(providers,run_id:str):
    services=build_application_services(providers)
    repo=providers.get('scenario_repository',ScenarioRepository)
    scenario=create_four_stage_education_scenario(operation_registry=providers.get('operation_registry',OperationRegistry),destination_registry=providers.get('destination_registry',DestinationRegistry))
    try: repo.register(scenario)
    except Exception:
        if repo.require(SCENARIO_ID)!=scenario: raise
    runner=FourStageScenarioRunner(scenario_repository=repo,scenario_validator=providers.get('scenario_validator',ScenarioValidator),scenario_clock=providers.get('scenario_clock',DeterministicScenarioClock),evidence_release_service=providers.get('evidence_release_service',EvidenceReleaseService),projection_service=providers.get('institutional_context_projection_service',InstitutionalContextProjectionService),coordination_service=providers.get('institutional_coordination_service',InstitutionalCoordinationService),policy_agent_service=providers.get('policy_agent_service',PolicyAgentService),invariant_verifier=providers.get('scenario_invariant_verifier',ScenarioInvariantVerifier),audit_service=providers.get('audit_service',AuditService))
    return runner.run(scenario_id=SCENARIO_ID,run_id=run_id)
def main(argv=None)->int:
    parser=argparse.ArgumentParser(description='Execute and serialize the deterministic four-stage evidence chain.')
    parser.add_argument('--project-root',type=Path,default=Path.cwd());parser.add_argument('--run-id',default='EVIDENCE-CHAIN-RUN-001');parser.add_argument('--output',type=Path);parser.add_argument('--pretty-output',type=Path);parser.add_argument('--database',type=Path);parser.add_argument('--learning-scenarios',action='store_true');parser.add_argument('--lesson-path',type=Path);parser.add_argument('--answer-key-path',type=Path);parser.add_argument('--sensitive-document-id',type=int);parser.add_argument('--learning-artifacts',type=Path)
    args=parser.parse_args(argv); root=args.project_root.resolve(); output=args.output or root/'submission/artifacts/four_stage_evidence_chain.json'; pretty=args.pretty_output or root/'submission/artifacts/four_stage_evidence_chain_pretty.json'; database=(args.database or root/'build/demo/evidence_chain_demo.db').resolve()
    database.parent.mkdir(parents=True,exist_ok=True)
    for state_file in (database,Path(str(database)+'-wal'),Path(str(database)+'-shm')):
        if state_file.exists(): state_file.unlink()
    app=create_demo(project_root=root,settings_overrides={'database_path':database},configure=install_evidence_chain_providers)
    try:
        app.start(); result=execute(app.providers,args.run_id); payload=build_evidence_chain_report(result); digest=write_evidence_chain_report(payload,output,pretty)
        if args.learning_scenarios:
            required=(args.lesson_path,args.answer_key_path,args.sensitive_document_id)
            if any(value is None for value in required):
                parser.error('--learning-scenarios requires --lesson-path, --answer-key-path, and --sensitive-document-id')
            services=build_application_services(app.providers)
            artifacts=args.learning_artifacts or root/'submission/artifacts'
            LearningGovernanceScenarioRunner(services).run_all(lesson_path=args.lesson_path,answer_key_path=args.answer_key_path,sensitive_document_id=args.sensitive_document_id,artifact_dir=artifacts)
    finally: app.stop()
    print(f'output={output}');print(f'pretty_output={pretty}');print(f'sha256={digest}');print(f'run_digest={payload["run_digest"]}');return 0
if __name__=='__main__': raise SystemExit(main())
