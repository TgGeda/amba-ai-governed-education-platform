from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import threading


LifecycleHook = Callable[[], None]


class LifecycleState(str, Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class LifecycleRegistration:
    name: str
    startup: LifecycleHook | None = None
    shutdown: LifecycleHook | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("lifecycle registration name must be a string")

        normalized_name = self.name.strip()
        if not normalized_name:
            raise ValueError("lifecycle registration name must not be empty")

        if self.startup is not None and not callable(self.startup):
            raise TypeError("startup hook must be callable or None")

        if self.shutdown is not None and not callable(self.shutdown):
            raise TypeError("shutdown hook must be callable or None")

        object.__setattr__(self, "name", normalized_name)


class ApplicationLifecycle:
    def __init__(self) -> None:
        self._registrations: list[LifecycleRegistration] = []
        self._started: list[LifecycleRegistration] = []
        self._state = LifecycleState.CREATED
        self._lock = threading.RLock()

    @property
    def state(self) -> LifecycleState:
        with self._lock:
            return self._state

    @property
    def running(self) -> bool:
        return self.state is LifecycleState.RUNNING

    def names(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(registration.name for registration in self._registrations)

    def register(
        self,
        name: str,
        *,
        startup: LifecycleHook | None = None,
        shutdown: LifecycleHook | None = None,
    ) -> None:
        registration = LifecycleRegistration(
            name=name,
            startup=startup,
            shutdown=shutdown,
        )

        with self._lock:
            if self._state is not LifecycleState.CREATED:
                raise RuntimeError(
                    "lifecycle hooks can only be registered before startup"
                )

            if any(
                item.name == registration.name
                for item in self._registrations
            ):
                raise ValueError(
                    "lifecycle registration already exists: "
                    f"{registration.name}"
                )

            self._registrations.append(registration)

    def start(self) -> None:
        with self._lock:
            if self._state is LifecycleState.RUNNING:
                return

            if self._state is not LifecycleState.CREATED:
                raise RuntimeError(
                    f"cannot start lifecycle from {self._state.value}"
                )

            self._state = LifecycleState.STARTING
            registrations = tuple(self._registrations)

        try:
            for registration in registrations:
                if registration.startup is not None:
                    registration.startup()

                with self._lock:
                    self._started.append(registration)

            with self._lock:
                self._state = LifecycleState.RUNNING
        except BaseException as startup_error:
            rollback_errors = self._rollback_startup()

            with self._lock:
                self._state = LifecycleState.FAILED

            if rollback_errors:
                startup_error.add_note(
                    "Lifecycle startup rollback also failed: "
                    + "; ".join(
                        f"{name}: {type(error).__name__}"
                        for name, error in rollback_errors
                    )
                )

            raise

    def stop(self) -> None:
        with self._lock:
            if self._state is LifecycleState.STOPPED:
                return

            if self._state is LifecycleState.CREATED:
                self._state = LifecycleState.STOPPED
                return

            if self._state not in {
                LifecycleState.RUNNING,
                LifecycleState.FAILED,
            }:
                raise RuntimeError(
                    f"cannot stop lifecycle from {self._state.value}"
                )

            self._state = LifecycleState.STOPPING
            started = tuple(reversed(self._started))
            self._started.clear()

        errors = self._run_shutdown_hooks(started)

        with self._lock:
            self._state = (
                LifecycleState.FAILED
                if errors
                else LifecycleState.STOPPED
            )

        if errors:
            names = ", ".join(name for name, _error in errors)
            failure = RuntimeError(
                f"{len(errors)} lifecycle shutdown hook(s) failed: {names}"
            )
            for name, error in errors[1:]:
                failure.add_note(
                    f"Additional shutdown failure for {name}: "
                    f"{type(error).__name__}"
                )
            raise failure from errors[0][1]

    def _rollback_startup(self) -> tuple[tuple[str, BaseException], ...]:
        with self._lock:
            started = tuple(reversed(self._started))
            self._started.clear()

        return self._run_shutdown_hooks(started)

    @staticmethod
    def _run_shutdown_hooks(
        registrations: tuple[LifecycleRegistration, ...],
    ) -> tuple[tuple[str, BaseException], ...]:
        errors: list[tuple[str, BaseException]] = []

        for registration in registrations:
            if registration.shutdown is None:
                continue

            try:
                registration.shutdown()
            except BaseException as error:
                errors.append((registration.name, error))

        return tuple(errors)
