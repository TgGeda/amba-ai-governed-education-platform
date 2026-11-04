from __future__ import annotations

from pathlib import Path

import pytest

from amba_ai.application.composition import create_test
from amba_ai.application.health import (
    HealthStatus,
)
from amba_ai.application.lifecycle import (
    LifecycleState,
)
from amba_ai.application.provider_installation import (
    install_application_providers,
)
from amba_ai.db.policy_record_repository import (
    PolicyRecordRepository,
)
from amba_ai.governance.models import (
    GovernanceConfigurationError,
    InvalidOperationConfigurationError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIGURATION_ROOT = (
    PROJECT_ROOT
    / "config"
)

KNOWLEDGE_BASE_ROOT = (
    PROJECT_ROOT
    / "kb"
)

MIGRATIONS_ROOT = (
    PROJECT_ROOT
    / "src"
    / "amba_ai"
    / "db"
    / "migrations"
)


def _overrides() -> dict[str, object]:
    return {
        "configuration_root": CONFIGURATION_ROOT,
        "knowledge_base_root": KNOWLEDGE_BASE_ROOT,
        "migrations_root": MIGRATIONS_ROOT,
        "verify_knowledge_base": True,
    }


def test_composition_root_registers_and_initializes_database(
    tmp_path: Path,
) -> None:
    application = create_test(
        project_root=tmp_path,
        settings_overrides={
            **_overrides(),
            "strict_governance": False,
        },
        configure=install_application_providers,
    )

    try:
        repository = application.get(
            "policy_record_repository",
            PolicyRecordRepository,
        )

        assert repository is not None
        assert (
            application.settings.database_path.is_file()
        )
    finally:
        application.stop()


def test_strict_startup_resolves_governance_graph(
    tmp_path: Path,
) -> None:
    application = create_test(
        project_root=tmp_path,
        settings_overrides=_overrides(),
        configure=install_application_providers,
    )

    application.start()

    try:
        assert application.started is True

        assert (
            application.lifecycle.state
            is LifecycleState.RUNNING
        )

        assert (
            application.providers.closed
            is False
        )

        assert application.get(
            "governance_service"
        ) is not None

        assert application.get(
            "approval_service"
        ) is not None

        assert application.get(
            "execution_service"
        ) is not None

        assert application.get(
            "audit_service"
        ) is not None

        health = application.check_health()

        assert (
            health.status
            is HealthStatus.HEALTHY
        )

        health.require_healthy()

    finally:
        application.stop()

    assert application.started is False

    assert (
        application.lifecycle.state
        is LifecycleState.STOPPED
    )

    assert (
        application.providers.closed
        is True
    )

    database_path = (
        application.settings.database_path
    )

    assert database_path.is_file()

    database_path.unlink()

    assert database_path.exists() is False


def test_expensive_providers_are_not_resolved_by_registration(
    tmp_path: Path,
) -> None:
    application = create_test(
        project_root=tmp_path,
        settings_overrides={
            **_overrides(),
            "strict_governance": False,
        },
        configure=install_application_providers,
    )

    try:
        for name in (
            "rag_engine",
            "model_service",
            "content_delivery_service",
            "job_service",
        ):
            assert (
                application.providers.is_resolved(
                    name
                )
                is False
            )
    finally:
        application.stop()