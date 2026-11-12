from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
import inspect
import time
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from amba_ai.governance.models import EnforcementAction
from amba_ai.logger import logger
from amba_ai.services.job_governance import JobGovernanceGateError


class WorkerOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    GOVERNANCE_BLOCKED = "governance_blocked"
    HELD_FOR_REVIEW = "held_for_review"
    CONFIGURATION_FAILURE = "configuration_failure"


@dataclass(frozen=True)
class WorkerResult:
    task_name: str
    result: Any = None
    success: bool = True
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkerSignals(QObject):
    started = Signal(str)
    finished = Signal(object)
    error = Signal(dict)
    held = Signal(dict)
    governanceHeld = Signal(dict)
    progress = Signal(str)
    status = Signal(dict)


class FunctionWorker(QRunnable):
    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        task_name: str | None = None,
        max_retries: int = 0,
        backoff_seconds: float = 0.5,
        recoverable_exceptions: tuple[type[BaseException], ...] = (Exception,),
        fatal_exceptions: tuple[type[BaseException], ...] = (),
        **kwargs: Any,
    ):
        super().__init__()

        if max_retries < 0:
            raise ValueError("max_retries must be greater than or equal to 0.")

        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must be greater than or equal to 0.")

        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.task_name = task_name or getattr(fn, "__name__", fn.__class__.__name__)
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.recoverable_exceptions = recoverable_exceptions
        self.fatal_exceptions = fatal_exceptions
        self.signals = WorkerSignals()
        self._started_at: float | None = None

    @property
    def started(self) -> Any:
        return self.signals.started

    @property
    def finished(self) -> Any:
        return self.signals.finished

    @property
    def error(self) -> Any:
        return self.signals.error

    @property
    def held(self) -> Any:
        return self.signals.held

    @property
    def governanceHeld(self) -> Any:
        return self.signals.governanceHeld

    @property
    def progress(self) -> Any:
        return self.signals.progress

    @property
    def status(self) -> Any:
        return self.signals.status

    def __getattr__(self, name: str) -> Any:
        signals = self.__dict__.get("signals")
        if signals is not None and hasattr(signals, name):
            return getattr(signals, name)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def _context(self, *, stage: str, **extra: Any) -> dict[str, Any]:
        context: dict[str, Any] = {
            "task_name": self.task_name,
            "stage": stage,
            "args_count": len(self.args),
            "kwargs_count": len(self.kwargs),
            "max_retries": self.max_retries,
        }
        context.update(extra)
        return context

    def _task_context(self, *, stage: str, **extra: Any) -> dict[str, Any]:
        return self._context(stage=stage, **extra)

    def _emit_status(
        self,
        stage: str | None = None,
        message: str | Mapping[str, Any] | None = None,
        *,
        percent: int | float | None = None,
        **extra: Any,
    ) -> None:
        payload: dict[str, Any] = {
            "task_name": self.task_name,
        }

        if stage is not None:
            payload["stage"] = stage

        if isinstance(message, Mapping):
            payload.update(message)
            msg_text = str(
                payload.get("message")
                or payload.get("error_message")
                or (f"Task {stage}: {self.task_name}" if stage else "")
            )
            payload["message"] = msg_text
            if percent is not None:
                payload["percent"] = percent
            elif "percent" not in payload:
                payload["percent"] = None
        elif message is not None:
            payload["message"] = str(message)
            payload["percent"] = percent
        else:
            if "message" not in extra:
                payload["message"] = f"Task {stage}: {self.task_name}" if stage else ""
            payload["percent"] = percent

        payload.update(extra)

        if "elapsed_time" not in payload:
            started = self._started_at
            if started is not None:
                payload["elapsed_time"] = round(time.perf_counter() - started, 4)
            else:
                payload["elapsed_time"] = 0.0

        self.signals.status.emit(payload)

    def _handle_yielded_update(self, update: Any) -> None:
        if isinstance(update, dict):
            stage = str(update.get("stage", "running"))
            message = str(update.get("message", ""))

            self._emit_status(
                stage=stage,
                message={
                    **update,
                    "message": message,
                },
                percent=update.get("percent"),
            )

            if message:
                self.signals.progress.emit(message)

        elif isinstance(update, str):
            self.signals.progress.emit(update)
            self._emit_status(
                stage="running",
                message=update,
                percent=None,
            )

        else:
            message = str(update)
            self.signals.progress.emit(message)
            self._emit_status(
                stage="running",
                message=message,
                percent=None,
            )

    def _consume_generator(self, generator: Iterable[Any]) -> Any:
        iterator = iter(generator)

        while True:
            try:
                update = next(iterator)
                self._handle_yielded_update(update)

            except StopIteration as stop:
                return stop.value

    def _execute_once(self) -> Any:
        result = self.fn(*self.args, **self.kwargs)

        if inspect.isgenerator(result):
            return self._consume_generator(result)

        return result

    def _is_fatal(self, exc: BaseException) -> bool:
        if isinstance(exc, JobGovernanceGateError):
            return True
        return bool(self.fatal_exceptions) and isinstance(exc, self.fatal_exceptions)

    def _is_recoverable(self, exc: BaseException) -> bool:
        if isinstance(exc, JobGovernanceGateError):
            return False
        return bool(self.recoverable_exceptions) and isinstance(
            exc,
            self.recoverable_exceptions,
        )

    @Slot()
    def run(self) -> None:
        started_at = time.perf_counter()
        self._started_at = started_at

        self.signals.started.emit(self.task_name)
        self._emit_status(
            stage="started",
            message=f"Task started: {self.task_name}",
            percent=0,
            elapsed_time=0.0,
        )

        logger.info(
            "Worker task started",
            extra={"context": self._context(stage="started")},
        )

        attempts_allowed = self.max_retries + 1
        last_error: BaseException | None = None

        for attempt in range(1, attempts_allowed + 1):
            attempt_context = self._context(
                stage="attempt",
                attempt=attempt,
                attempts_allowed=attempts_allowed,
            )

            try:
                self._emit_status(
                    stage="running",
                    message=f"Running task: {self.task_name}",
                    percent=None,
                    attempt=attempt,
                    attempts_allowed=attempts_allowed,
                )

                result = self._execute_once()
                elapsed_time = round(time.perf_counter() - started_at, 4)

                worker_result = WorkerResult(
                    task_name=self.task_name,
                    result=result,
                    success=True,
                    error_message=None,
                    metadata={
                        "attempt": attempt,
                        "attempts_allowed": attempts_allowed,
                        "elapsed_time": elapsed_time,
                        "result_type": type(result).__name__,
                        "outcome": WorkerOutcome.SUCCEEDED.value,
                    },
                )

                logger.info(
                    "Worker task succeeded",
                    extra={
                        "context": {
                            **attempt_context,
                            "elapsed_time": elapsed_time,
                            "result_type": type(result).__name__,
                        }
                    },
                )

                self._emit_status(
                    stage="finished",
                    message=f"Task completed: {self.task_name}",
                    percent=100,
                    elapsed_time=elapsed_time,
                    result_type=type(result).__name__,
                )

                self.signals.finished.emit(worker_result)
                return

            except JobGovernanceGateError as exc:
                elapsed_time = round(time.perf_counter() - started_at, 4)

                if exc.action is EnforcementAction.HOLD_FOR_REVIEW:
                    governance_payload = {
                        **exc.to_dict(),
                        **self._context(stage=WorkerOutcome.HELD_FOR_REVIEW.value),
                        "elapsed_time": elapsed_time,
                        "attempt": attempt,
                        "attempts_allowed": attempts_allowed,
                        "outcome": WorkerOutcome.HELD_FOR_REVIEW.value,
                        "error_message": (
                            f"Task held for review: {self.task_name} "
                            f"(event {exc.event_id})"
                        ),
                    }

                    logger.info(
                        "Worker task held for governance review",
                        extra={"context": governance_payload},
                    )

                    self.signals.held.emit(deepcopy(governance_payload))
                    self.signals.governanceHeld.emit(deepcopy(governance_payload))

                    self._emit_status(
                        stage=WorkerOutcome.HELD_FOR_REVIEW.value,
                        message={
                            **governance_payload,
                            "message": f"Task held for review: {self.task_name}",
                            "level": "WARNING",
                        },
                        percent=None,
                    )

                    held_result = WorkerResult(
                        task_name=self.task_name,
                        result=None,
                        success=False,
                        error_message=governance_payload["error_message"],
                        metadata=governance_payload,
                    )
                    self.signals.finished.emit(held_result)
                    return

                governance_payload = {
                    **exc.to_dict(),
                    **self._context(stage=WorkerOutcome.GOVERNANCE_BLOCKED.value),
                    "elapsed_time": elapsed_time,
                    "attempt": attempt,
                    "attempts_allowed": attempts_allowed,
                    "outcome": WorkerOutcome.GOVERNANCE_BLOCKED.value,
                    "error_message": (
                        f"Task blocked by governance: {self.task_name} "
                        f"(action={exc.action.value})"
                    ),
                }

                logger.warning(
                    "Worker task blocked by governance",
                    extra={"context": governance_payload},
                )

                self._emit_status(
                    stage=WorkerOutcome.GOVERNANCE_BLOCKED.value,
                    message={
                        **governance_payload,
                        "message": f"Task blocked by governance: {self.task_name}",
                        "level": "ERROR",
                    },
                    percent=None,
                )

                self.signals.error.emit(governance_payload)

                blocked_result = WorkerResult(
                    task_name=self.task_name,
                    result=None,
                    success=False,
                    error_message=governance_payload["error_message"],
                    metadata=governance_payload,
                )
                self.signals.finished.emit(blocked_result)
                return

            except BaseException as exc:
                last_error = exc
                elapsed_time = round(time.perf_counter() - started_at, 4)
                tb = traceback.format_exc()

                error_context = {
                    **attempt_context,
                    "elapsed_time": elapsed_time,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": tb,
                    "fatal": self._is_fatal(exc),
                    "recoverable": self._is_recoverable(exc),
                    "outcome": WorkerOutcome.FAILED.value,
                }

                logger.exception(
                    "Worker task failed",
                    extra={"context": error_context},
                )

                self.signals.error.emit(error_context)
                self._emit_status(
                    stage="error",
                    message=f"Task failed: {self.task_name}",
                    percent=None,
                    error_type=type(exc).__name__,
                    attempt=attempt,
                    attempts_allowed=attempts_allowed,
                    elapsed_time=elapsed_time,
                )

                should_retry = (
                    attempt < attempts_allowed
                    and not self._is_fatal(exc)
                    and self._is_recoverable(exc)
                )

                if not should_retry:
                    break

                sleep_for = self.backoff_seconds * (2 ** (attempt - 1))

                logger.warning(
                    "Retrying worker task after failure",
                    extra={
                        "context": {
                            **error_context,
                            "retry_in_seconds": sleep_for,
                        }
                    },
                )

                self._emit_status(
                    stage="retrying",
                    message=f"Retrying task: {self.task_name}",
                    percent=None,
                    attempt=attempt,
                    retry_in_seconds=sleep_for,
                    elapsed_time=elapsed_time,
                )

                time.sleep(sleep_for)

        elapsed_time = round(time.perf_counter() - started_at, 4)

        failure_result = WorkerResult(
            task_name=self.task_name,
            result=None,
            success=False,
            error_message=str(last_error) if last_error else "Unknown worker error.",
            metadata={
                "attempts_allowed": attempts_allowed,
                "elapsed_time": elapsed_time,
                "error_type": type(last_error).__name__ if last_error else None,
                "traceback": traceback.format_exc() if last_error else None,
                "outcome": WorkerOutcome.FAILED.value,
            },
        )

        logger.error(
            "Worker task failed permanently",
            extra={
                "context": self._context(
                    stage="failed",
                    elapsed_time=elapsed_time,
                    error_type=type(last_error).__name__ if last_error else None,
                    error_message=str(last_error) if last_error else None,
                )
            },
        )

        self._emit_status(
            stage="failed",
            message=f"Task failed permanently: {self.task_name}",
            percent=None,
            elapsed_time=elapsed_time,
            error_type=type(last_error).__name__ if last_error else None,
        )

        self.signals.finished.emit(failure_result)


Worker = FunctionWorker


def unwrap_worker_result(
    raw_result: Any,
    *,
    default_task_name: str = "unknown",
) -> WorkerResult:
    if isinstance(raw_result, WorkerResult):
        return raw_result

    return WorkerResult(
        task_name=default_task_name,
        result=raw_result,
        success=True,
        error_message=None,
        metadata={},
    )


def worker_result_success(raw_result: Any) -> bool:
    return bool(unwrap_worker_result(raw_result).success)


def normalize_worker_error(
    raw_result: Any,
    *,
    default_task_name: str = "unknown",
) -> dict[str, Any]:
    result = unwrap_worker_result(raw_result, default_task_name=default_task_name)

    if result.success:
        return {}

    metadata = dict(result.metadata or {})

    return {
        "task_name": result.task_name or default_task_name,
        "error_message": (
            result.error_message
            or metadata.get("error_message")
            or "Operation failed."
        ),
        "error_type": metadata.get("error_type") or "Error",
        **metadata,
    }


def normalize_error_context(
    error_context: dict[str, Any] | None,
    *,
    task_name: str = "unknown",
) -> dict[str, Any]:
    context = dict(error_context or {})

    return {
        "task_name": context.get("task_name") or task_name,
        "error_message": (
            context.get("error_message")
            or context.get("message")
            or "Operation failed."
        ),
        "error_type": context.get("error_type") or "Error",
        **context,
    }
