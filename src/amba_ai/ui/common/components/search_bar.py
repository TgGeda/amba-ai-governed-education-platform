from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QKeySequence, QShortcut, QKeyEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget


class LearningSearchBar(QFrame):
    queryChanged = Signal(str)
    previousRequested = Signal()
    nextRequested = Signal()

    def __init__(self, placeholder: str = "Search this lesson", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("learningSearchBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)

        self.input = QLineEdit()
        self.input.setObjectName("learningSearchInput")
        self.input.setPlaceholderText(placeholder)
        self.input.setClearButtonEnabled(True)
        self.input.setAccessibleName(placeholder)

        self.counter = QLabel("0 matches")
        self.counter.setObjectName("learningSearchCount")

        self.status = QLabel("Idle")
        self.status.setObjectName("learningSearchStatus")

        self.previous = QPushButton("Previous")
        self.next = QPushButton("Next")
        for button in (self.previous, self.next):
            button.setObjectName("learningCompactAction")
            button.setEnabled(False)

        layout.addWidget(self.input, 1)
        layout.addWidget(self.counter)
        layout.addWidget(self.status)
        layout.addWidget(self.previous)
        layout.addWidget(self.next)

        self.input.textChanged.connect(self._on_query_changed)
        self.previous.clicked.connect(self.previousRequested)
        self.next.clicked.connect(self.nextRequested)

        # Context-scoped shortcut to avoid window-wide Ctrl+F collisions
        self.shortcut = QShortcut(
            QKeySequence("Ctrl+F"),
            self,
            context=Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self.shortcut.activated.connect(self._focus_search)

    def _focus_search(self) -> None:
        self.show()
        self.raise_()
        self.input.setFocus()
        self.input.selectAll()
        self.status.setText("🔍 Searching")

    def _on_query_changed(self, text: str) -> None:
        self.queryChanged.emit(text)

    def setMatchCount(self, count: int, current: int = 0) -> None:
        self.counter.setText(f"{current}/{count} matches" if count else "0 matches")
        self.previous.setEnabled(count > 0)
        self.next.setEnabled(count > 0)

        if count == 0:
            self.status.setText("No matches")
        else:
            self.status.setText("Found")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                if self.previous.isEnabled():
                    self.previousRequested.emit()
            else:
                if self.next.isEnabled():
                    self.nextRequested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)