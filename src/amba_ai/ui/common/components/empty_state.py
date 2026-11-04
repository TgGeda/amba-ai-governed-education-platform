from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget


class EmptyState(QFrame):
    def __init__(self, title: str, message: str, *, action_text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("learningEmptyState")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 28, 24, 28)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Title
        heading = QLabel(title)
        heading.setObjectName("learningEmptyTitle")
        heading.setWordWrap(True)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Message
        body = QLabel(message)
        body.setObjectName("learningEmptyBody")
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Action button
        self.action = QPushButton(action_text)
        self.action.setObjectName("learningSecondaryAction")
        self.action.setVisible(bool(action_text))
        self.action.setFixedHeight(32)

        # Layout order
        layout.addWidget(heading)
        layout.addWidget(body)
        layout.addWidget(self.action, 0, Qt.AlignmentFlag.AlignCenter)

        # Accessibility
        self.setAccessibleName(f"Empty state: {title}")
        body.setAccessibleDescription(message)
