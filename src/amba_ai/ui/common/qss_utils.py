from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget

from amba_ai.logger import logger


def load_qss_text(qss_file: str | Path) -> str:
    path = Path(qss_file)

    if not path.exists():
        logger.warning(f"QSS file not found: {path}")
        return ""

    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Failed to read QSS file {path}: {exc}", exc_info=True)
        return ""


def apply_local_qss(widget: QWidget, qss_file: str | Path) -> bool:
    qss = load_qss_text(qss_file)

    if not qss:
        return False

    try:
        widget.setStyleSheet(qss)
        logger.info(f"Applied local QSS: {Path(qss_file)}")
        return True
    except Exception as exc:
        logger.warning(f"Failed to apply QSS {qss_file}: {exc}", exc_info=True)
        return False