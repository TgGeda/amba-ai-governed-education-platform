from __future__ import annotations

from typing import Any

from amba_ai.ui.workers import WorkerResult


def unwrap_worker_result(raw_result: Any, *, default_task_name: str = "unknown") -> WorkerResult:
    if isinstance(raw_result, WorkerResult):
        return raw_result

    return WorkerResult(
        task_name=default_task_name,
        result=raw_result,
        success=True,
        metadata={},
    )


def worker_result_success(raw_result: Any) -> bool:
    result = unwrap_worker_result(raw_result)
    return bool(result.success)


def normalize_worker_error(raw_result: Any, *, default_task_name: str = "unknown") -> dict[str, Any]:
    result = unwrap_worker_result(raw_result, default_task_name=default_task_name)

    if result.success:
        return {}

    metadata = dict(result.metadata or {})

    return {
        **metadata,
        "task_name": result.task_name or default_task_name,
        "error_message": result.error_message or metadata.get("error_message") or "Operation failed.",
        "error_type": metadata.get("error_type") or "Error",
    }


def normalize_error_context(error_context: dict[str, Any] | None, *, task_name: str = "unknown") -> dict[str, Any]:
    context = dict(error_context or {})

    return {
        **context,
        "task_name": context.get("task_name") or task_name,
        "error_message": context.get("error_message") or context.get("message") or "Operation failed.",
        "error_type": context.get("error_type") or "Error",
    }
