from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from amba_ai.ui.features.summarizer.summarizer_widget import SummarizerWidget


class DummyJobService:
    """Minimal dependency used only for widget construction and state transitions."""

    def summarize_document(self, document_id: int, **kwargs):  # pragma: no cover
        raise AssertionError("smoke test must not invoke background summarization")


def test_summarizer_widget_document_state_resets() -> None:
    app = QApplication.instance() or QApplication([])
    settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "AMBA-GOV", "SummarizerSmoke")
    settings.clear()
    widget = SummarizerWidget(settings, DummyJobService())
    try:
        widget.set_document(42)
        assert widget.document_id == 42

        widget.set_document(99)
        assert widget.document_id == 99
        assert widget.current_summary is None
    finally:
        widget.close()
        settings.clear()
