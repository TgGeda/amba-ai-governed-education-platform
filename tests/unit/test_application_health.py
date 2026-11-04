from __future__ import annotations

import pytest

from amba_ai.application.health import (
    ApplicationHealth,
    HealthCheckResult,
    HealthRegistry,
    HealthStatus,
)


def _result(
    name: str,
    status: HealthStatus = HealthStatus.HEALTHY,
) -> HealthCheckResult:
    return HealthCheckResult(name, status, f"{name} status")


def test_empty_registry_is_unhealthy() -> None:
    health = HealthRegistry().evaluate()
    assert health.status is HealthStatus.UNHEALTHY
    assert health.checks == ()
    with pytest.raises(RuntimeError, match="application health is unhealthy"):
        health.require_healthy()


def test_registry_evaluates_checks_in_deterministic_order() -> None:
    registry = HealthRegistry()
    registry.register("zeta", lambda: _result("zeta"))
    registry.register("alpha", lambda: _result("alpha"))
    health = registry.evaluate()
    assert health.status is HealthStatus.HEALTHY
    assert tuple(check.name for check in health.checks) == (
        "alpha",
        "zeta",
    )
    health.require_healthy()


def test_status_aggregation_uses_most_severe_result() -> None:
    registry = HealthRegistry()
    registry.register(
        "healthy",
        lambda: _result("healthy", HealthStatus.HEALTHY),
    )
    registry.register(
        "degraded",
        lambda: _result("degraded", HealthStatus.DEGRADED),
    )
    assert registry.evaluate().status is HealthStatus.DEGRADED

    registry.register(
        "unhealthy",
        lambda: _result("unhealthy", HealthStatus.UNHEALTHY),
    )
    health = registry.evaluate()
    assert health.status is HealthStatus.UNHEALTHY
    with pytest.raises(RuntimeError, match="degraded=degraded"):
        health.require_healthy()


def test_check_failures_are_fail_closed_without_message_leakage() -> None:
    registry = HealthRegistry()

    def failing_check() -> HealthCheckResult:
        raise RuntimeError("sensitive internal detail")

    registry.register("dependency", failing_check)
    result = registry.evaluate().checks[0]
    assert result.status is HealthStatus.UNHEALTHY
    assert result.message == "health check failed: RuntimeError"
    assert "sensitive internal detail" not in result.message


def test_invalid_check_result_is_fail_closed() -> None:
    registry = HealthRegistry()
    registry.register("invalid", lambda: object())  # type: ignore[arg-type]
    result = registry.evaluate().checks[0]
    assert result.status is HealthStatus.UNHEALTHY
    assert result.message == "health check failed: TypeError"


def test_mismatched_check_name_is_fail_closed() -> None:
    registry = HealthRegistry()
    registry.register("expected", lambda: _result("other"))
    result = registry.evaluate().checks[0]
    assert result.status is HealthStatus.UNHEALTHY
    assert result.message == "health check failed: ValueError"


def test_registration_replacement_and_removal() -> None:
    registry = HealthRegistry()
    registry.register("service", lambda: _result("service"))
    assert registry.contains("service") is True
    assert registry.names() == ("service",)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("service", lambda: _result("service"))

    registry.register(
        "service",
        lambda: _result("service", HealthStatus.DEGRADED),
        replace=True,
    )
    assert registry.evaluate().status is HealthStatus.DEGRADED

    registry.unregister("service")
    assert registry.contains("service") is False
    with pytest.raises(KeyError, match="not registered"):
        registry.unregister("service")


def test_application_health_rejects_inconsistent_or_unsorted_checks() -> None:
    alpha = _result("alpha")
    zeta = _result("zeta")

    with pytest.raises(ValueError, match="sorted"):
        ApplicationHealth(HealthStatus.HEALTHY, (zeta, alpha))

    with pytest.raises(ValueError, match="duplicate"):
        ApplicationHealth(HealthStatus.HEALTHY, (alpha, alpha))

    with pytest.raises(ValueError, match="aggregated"):
        ApplicationHealth(
            HealthStatus.HEALTHY,
            (_result("dependency", HealthStatus.UNHEALTHY),),
        )


def test_health_serialization_and_lookup_are_deterministic() -> None:
    health = ApplicationHealth(
        HealthStatus.HEALTHY,
        (_result("service"),),
    )
    assert health.healthy is True
    assert health.get_check(" service ") == health.checks[0]
    assert health.get_check("missing") is None
    assert health.to_canonical_json() == health.to_canonical_json()
    assert health.checks[0].to_canonical_json() == (
        health.checks[0].to_canonical_json()
    )
