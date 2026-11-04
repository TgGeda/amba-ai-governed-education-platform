from __future__ import annotations

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget
)
from .accessibility import repolish
from .source_chip import SourceChip


class LearningHeader(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("learningHeader")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(6)

        top = QHBoxLayout()
        self.title = QLabel("Learning Workspace")
        self.title.setObjectName("learningPageTitle")
        self.title.setWordWrap(True)

        self.source = SourceChip()

        self.status_icon = QLabel("⏳")
        self.status_icon.setObjectName("learningStatusIcon")
        self.status_icon.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.status_text = QLabel("In Progress")
        self.status_text.setObjectName("learningStatusText")
        self.status_text.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        top.addWidget(self.title, 1)
        top.addWidget(self.source)
        top.addWidget(self.status_icon)
        top.addWidget(self.status_text)

        self.meta = QLabel("")
        self.meta.setObjectName("learningMetadata")
        self.meta.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setObjectName("learningProgress")
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)

        self.progress_anim = QPropertyAnimation(self.progress, b"value", self)
        self.progress_anim.setDuration(350)
        self.progress_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        root.addLayout(top)
        root.addWidget(self.meta)
        root.addWidget(self.progress)

    def setContent(
        self,
        *,
        title: str,
        citation: object | None = None,
        metadata: str = "",
        progress: int | None = None,
        status: str | None = None,
    ) -> None:
        self.title.setText(title or "Untitled lesson")
        self.source.setCitation(citation)
        self.meta.setText(metadata)
        self.meta.setVisible(bool(metadata))

        if progress is not None:
            self.progress.setVisible(True)
            self.progress_anim.stop()
            self.progress_anim.setStartValue(self.progress.value())
            self.progress_anim.setEndValue(max(0, min(100, int(progress))))
            self.progress_anim.start()
        else:
            self.progress.setVisible(False)

        if status:
            self.status_text.setText(status)
            status_lower = status.lower()

            if status_lower == "validated":
                self.status_icon.setText("✔")
                self.status_text.setProperty("statusLevel", "validated")
                self.status_icon.setProperty("statusLevel", "validated")
            elif status_lower in ("completed", "complete"):
                self.status_icon.setText("✅")
                self.status_text.setProperty("statusLevel", "completed")
                self.status_icon.setProperty("statusLevel", "completed")
            else:
                self.status_icon.setText("⏳")
                self.status_text.setProperty("statusLevel", "inprogress")
                self.status_icon.setProperty("statusLevel", "inprogress")

            repolish(self.status_text)
            repolish(self.status_icon)

        self.setAccessibleName(f"Learning header: {self.title.text()} ({self.status_text.text()})")