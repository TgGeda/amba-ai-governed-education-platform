from __future__ import annotations

from typing import Any
from PySide6.QtWidgets import QMessageBox, QWidget


def _format_context(context: dict[str, Any] | None) -> str:
    if not context:
        return ""

    lines: list[str] = []

    for key in ["task_name", "operation", "stage", "document_id", "error_type", "error_message"]:
        value = context.get(key)
        if value is not None and str(value).strip():
            lines.append(f"{key}: {value}")

    traceback_text = str(context.get("traceback") or "").strip()
    if traceback_text and traceback_text != "NoneType: None":
        lines.append("")
        lines.append("Traceback:")
        # keep the first 4000 characters (more useful than the tail)
        lines.append(traceback_text[:4000])

    return "\n".join(lines)


def _compose_message(message: str, context: dict[str, Any] | None = None) -> str:
    detail = _format_context(context)
    return f"{message}\n\n{detail}" if detail else message


def show_error(parent: QWidget | None, title: str, message: str, context: dict[str, Any] | None = None) -> None:
    QMessageBox.critical(parent, title, _compose_message(message, context))


def show_warning(parent: QWidget | None, title: str, message: str, context: dict[str, Any] | None = None) -> None:
    QMessageBox.warning(parent, title, _compose_message(message, context))


def show_info(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.information(parent, title, message)


def ask_retry(parent: QWidget | None, title: str, message: str, context: dict[str, Any] | None = None) -> bool:
    text = f"{_compose_message(message, context)}\n\nWould you like to retry?"
    reply = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return reply == QMessageBox.StandardButton.Yes
