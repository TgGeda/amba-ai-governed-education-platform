from __future__ import annotations

import inspect
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from amba_ai.logger import logger


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

    def _emit_status(
        self,
        *,
        stage: str,
        message: str,
        percent: int | float | None = None,
        **extra: Any,
    ) -> None:
        payload: dict[str, Any] = {
            "task_name": self.task_name,
            "stage": stage,
            "message": message,
            "percent": percent,
            **extra,
        }
        self.signals.status.emit(payload)

    def _handle_yielded_update(self, update: Any) -> None:
        if isinstance(update, dict):
            payload = {
                "task_name": self.task_name,
                "stage": update.get("stage", "running"),
                "message": update.get("message", ""),
                "percent": update.get("percent"),
                **update,
            }
            self.signals.status.emit(payload)

            message = payload.get("message")
            if message:
                self.signals.progress.emit(str(message))

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
        return bool(self.fatal_exceptions) and isinstance(exc, self.fatal_exceptions)

    def _is_recoverable(self, exc: BaseException) -> bool:
        return bool(self.recoverable_exceptions) and isinstance(
            exc,
            self.recoverable_exceptions,
        )

    @Slot()
    def run(self) -> None:
        started_at = time.perf_counter()

        self.signals.started.emit(self.task_name)
        self._emit_status(
            stage="started",
            message=f"Task started: {self.task_name}",
            percent=0,
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


def unwrap_worker_result(raw_result: Any, *, default_task_name: str = "unknown") -> WorkerResult:
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
        "error_message": result.error_message or metadata.get("error_message") or "Operation failed.",
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
        "error_message": context.get("error_message") or context.get("message") or "Operation failed.",
        "error_type": context.get("error_type") or "Error",
        **context,
    }