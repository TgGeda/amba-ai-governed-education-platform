from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from amba_ai.application.bootstrap import build_application_services
from amba_ai.application.composition import create_test
from amba_ai.application.provider_installation import install_application_providers
from amba_ai.governance.execution_context import GovernanceExecutionContext
from amba_ai.services.governed_learning_trace_service import GovernedLearningTraceService


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate governed learning evidence artifacts.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--event-file", type=Path, required=True)
    parser.add_argument("--source-inventory", type=Path, required=True)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    db_path = (args.database or root / "build/evidence/governed_learning_trace.db").resolve()
    app = create_test(
        project_root=root,
        settings_overrides={
            "database_path": db_path,
            "configuration_root": root / "config",
            "migrations_root": root / "src/amba_ai/db/migrations",
            "initialize_database": True,
            "verify_knowledge_base": False,
        },
        configure=install_application_providers,
    )
    app.start()
    try:
        services = build_application_services(app.providers)
        payload = json.loads(args.event_file.read_text(encoding="utf-8"))
        context = GovernanceExecutionContext.from_mapping(payload["execution_context"])
        trace = GovernedLearningTraceService(services)
        record = trace.build_record(
            context=context,
            event_details=tuple(
                (str(item["event_type"]), dict(item.get("details") or {}))
                for item in payload["events"]
            ),
            scenario_ids=tuple(payload.get("scenario_ids") or ()),
            test_matrix=dict(payload.get("test_matrix") or {}),
            source_inventory_sha256=sha256(args.source_inventory),
            audit_verified=bool(payload.get("audit_verified")),
        )
        digest = trace.write_artifacts(
            record=record,
            json_path=root / "submission/artifacts/governed_learning_evidence_chain.json",
            markdown_path=root / "submission/governed_learning_evidence_chain.md",
        )
    finally:
        app.stop()
    print("PASS: Governed learning evidence generated.")
    print(f"sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
