from __future__ import annotations
from typing import Any
from PySide6.QtWidgets import QWidget


def repolish(widget: QWidget) -> None:

    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_state(widget: QWidget, name: str, value: Any) -> None:

    if not isinstance(widget, QWidget):
        raise TypeError("set_state requires a QWidget target")
    widget.setProperty(name, value)
    repolish(widget)
