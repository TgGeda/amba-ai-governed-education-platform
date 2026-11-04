from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QSizePolicy, QVBoxLayout, QWidget


class ReadingCanvas(QScrollArea):
    """Responsive, centered reading surface with debounced width updates and smooth scrolling."""

    def __init__(
        self,
        *,
        maximum_width: int = 1100,
        minimum_reading_width: int = 720,
        horizontal_margin: int = 16,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("learningReadingCanvas")

        self._maximum_width = max(720, int(maximum_width))
        self._minimum_reading_width = max(480, int(minimum_reading_width))
        self._horizontal_margin = max(8, int(horizontal_margin))

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.viewport().setObjectName("learningReadingViewport")

        self.wrapper = QWidget()
        self.wrapper_layout = QHBoxLayout(self.wrapper)
        self.wrapper_layout.setContentsMargins(self._horizontal_margin, 12, self._horizontal_margin, 20)
        self.wrapper_layout.setSpacing(12)
        self.wrapper_layout.addStretch(1)

        self.content_column = QWidget()
        self.content_column.setObjectName("learningReadingColumn")
        self.content_column.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.content_layout = QVBoxLayout(self.content_column)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(12)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.wrapper_layout.addWidget(self.content_column, 0, Qt.AlignmentFlag.AlignTop)
        self.wrapper_layout.addStretch(1)
        self.setWidget(self.wrapper)

        QTimer.singleShot(0, self._update_reading_width)

    def setMaximumReadingWidth(self, width: int) -> None:
        self._maximum_width = max(480, int(width))
        self._update_reading_width()

    def clear(self) -> None:
        """Safely clear all widgets, spacers, and sub-layouts from the canvas."""
        while self.content_layout.count() > 0:
            item = self.content_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            else:
                sub_layout = item.layout()
                if sub_layout is not None:
                    self._clear_layout_recursive(sub_layout)
        self.content_layout.invalidate()

    def _clear_layout_recursive(self, layout) -> None:
        while layout.count() > 0:
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            else:
                sub_layout = item.layout()
                if sub_layout is not None:
                    self._clear_layout_recursive(sub_layout)

    def addWidget(self, widget: QWidget) -> None:
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.content_layout.addWidget(widget)

    def ensureWidgetVisible(self, child_widget: QWidget, xmargin: int = 12, ymargin: int = 12) -> None:
        scrollbar = self.verticalScrollBar()
        if scrollbar is None or not child_widget.isVisible():
            return
        target_pos = child_widget.mapTo(self.widget(), child_widget.rect().topLeft()).y() - ymargin
        animation = QPropertyAnimation(scrollbar, b"value", self)
        animation.setDuration(250)
        animation.setStartValue(scrollbar.value())
        animation.setEndValue(max(0, target_pos))
        animation.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_reading_width()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._update_reading_width)

    def _update_reading_width(self) -> None:
        viewport_width = self.viewport().width()
        if viewport_width <= 0:
            return

        available = max(480, viewport_width - self._horizontal_margin * 2)
        target = min(self._maximum_width, available)

        if available >= self._minimum_reading_width:
            target = max(self._minimum_reading_width, target)

        if self.content_column.width() != target:
            self.content_column.setFixedWidth(target)

            for i in range(self.content_layout.count()):
                widget = self.content_layout.itemAt(i).widget()
                if widget is not None:
                    widget.setMinimumWidth(0)
                    widget.setMaximumWidth(target)
                    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

            self.content_layout.invalidate()
            self.content_column.updateGeometry()