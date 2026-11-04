from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import threading

from amba_ai.governance.models import to_canonical_json


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


_STATUS_PRIORITY = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.DEGRADED: 1,
    HealthStatus.UNHEALTHY: 2,
}


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    name: str
    status: HealthStatus
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("health-check name must be a string")
        if not isinstance(self.status, HealthStatus):
            raise TypeError("health-check status must be a HealthStatus")
        if not isinstance(self.message, str):
            raise TypeError("health-check message must be a string")

        normalized_name = self.name.strip()
        normalized_message = self.message.strip()

        if not normalized_name:
            raise ValueError("health-check name must not be empty")
        if not normalized_message:
            raise ValueError("health-check message must not be empty")

        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "message", normalized_message)

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ApplicationHealth:
    status: HealthStatus
    checks: tuple[HealthCheckResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, HealthStatus):
            raise TypeError("status must be a HealthStatus")
        if not isinstance(self.checks, tuple):
            raise TypeError("checks must be a tuple")
        if any(not isinstance(check, HealthCheckResult) for check in self.checks):
            raise TypeError("checks must contain only HealthCheckResult values")

        names = tuple(check.name for check in self.checks)
        if len(names) != len(set(names)):
            raise ValueError("checks must not contain duplicate names")
        if names != tuple(sorted(names)):
            raise ValueError("checks must be sorted by name")

        expected_status = _aggregate_status(self.checks)
        if self.status is not expected_status:
            raise ValueError("status does not match the aggregated check status")

    @property
    def healthy(self) -> bool:
        return self.status is HealthStatus.HEALTHY

    def get_check(self, name: str) -> HealthCheckResult | None:
        normalized = _require_name(name)
        return next(
            (check for check in self.checks if check.name == normalized),
            None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())

    def require_healthy(self) -> None:
        if self.status is HealthStatus.HEALTHY:
            return

        failed_checks = ", ".join(
            f"{check.name}={check.status.value}"
            for check in self.checks
            if check.status is not HealthStatus.HEALTHY
        )
        suffix = f": {failed_checks}" if failed_checks else ""
        raise RuntimeError(
            f"application health is {self.status.value}{suffix}"
        )


HealthCheck = Callable[[], HealthCheckResult]


def _require_name(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("health-check name must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("health-check name must not be empty")
    return normalized


def _aggregate_status(
    checks: tuple[HealthCheckResult, ...],
) -> HealthStatus:
    if not checks:
        return HealthStatus.UNHEALTHY
    return max(
        (check.status for check in checks),
        key=_STATUS_PRIORITY.__getitem__,
    )


class HealthRegistry:
    def __init__(self) -> None:
        self._checks: dict[str, HealthCheck] = {}
        self._lock = threading.RLock()

    def register(
        self,
        name: str,
        check: HealthCheck,
        *,
        replace: bool = False,
    ) -> None:
        normalized = _require_name(name)
        if not callable(check):
            raise TypeError("health check must be callable")
        if type(replace) is not bool:
            raise TypeError("replace must be a strict Boolean")

        with self._lock:
            if normalized in self._checks and not replace:
                raise ValueError(
                    f"health check already registered: {normalized}"
                )
            self._checks[normalized] = check

    def unregister(self, name: str) -> None:
        normalized = _require_name(name)
        with self._lock:
            if normalized not in self._checks:
                raise KeyError(
                    f"health check is not registered: {normalized}"
                )
            del self._checks[normalized]

    def contains(self, name: str) -> bool:
        normalized = _require_name(name)
        with self._lock:
            return normalized in self._checks

    def names(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._checks))

    def evaluate(self) -> ApplicationHealth:
        with self._lock:
            checks = tuple(sorted(self._checks.items()))

        results: list[HealthCheckResult] = []
        for name, check in checks:
            try:
                result = check()
                if not isinstance(result, HealthCheckResult):
                    raise TypeError(
                        "health check returned an invalid result"
                    )
                if result.name != name:
                    raise ValueError(
                        "health-check result name does not match registration"
                    )
            except Exception as error:
                result = HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=(
                        "health check failed: "
                        f"{type(error).__name__}"
                    ),
                )
            results.append(result)

        ordered_results = tuple(results)
        return ApplicationHealth(
            status=_aggregate_status(ordered_results),
            checks=ordered_results,
        )
