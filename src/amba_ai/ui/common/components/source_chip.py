from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Property,
    Signal,
    Qt,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QPushButton, QWidget


class SourceChip(QPushButton):
    sourceRequested = Signal(object)

    def __init__(self, citation: object | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("learningSourceChip")
        self._citation = None

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(80)
        self.setMaximumWidth(160)
        self.setFixedHeight(24)

        self._ripple_radius_val: float = 0.0
        self._ripple_opacity_val: float = 0.0
        self._ripple_center = QPoint(self.width() // 2, self.height() // 2)

        self.clicked.connect(lambda: self.sourceRequested.emit(self._citation))
        self.setCitation(citation)

    @Property(float)
    def rippleRadius(self) -> float:
        return self._ripple_radius_val

    @rippleRadius.setter
    def rippleRadius(self, value: float) -> None:
        self._ripple_radius_val = value
        self.update()

    @Property(float)
    def rippleOpacity(self) -> float:
        return self._ripple_opacity_val

    @rippleOpacity.setter
    def rippleOpacity(self, value: float) -> None:
        self._ripple_opacity_val = value
        self.update()

    def setCitation(self, citation: object | None) -> None:
        """Set citation and update chip label/availability."""
        self._citation = citation
        label = "Source unavailable"
        if citation is not None:
            display = getattr(citation, "display", None)
            label = (
                display()
                if callable(display)
                else str(getattr(citation, "source_name", "") or citation)
            )

        self.setText(label)
        self.setToolTip(label)
        self.setAccessibleName(f"Source: {label}")
        self.setEnabled(citation is not None)

    def mousePressEvent(self, event):
        """Start ripple animation on click."""
        self._ripple_center = event.pos()
        self._ripple_radius_val = 0.0
        self._ripple_opacity_val = 1.0

        self._radius_anim = QPropertyAnimation(self, b"rippleRadius")
        self._radius_anim.setDuration(350)
        self._radius_anim.setStartValue(0.0)
        self._radius_anim.setEndValue(float(max(self.width(), self.height())))
        self._radius_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._radius_anim.start()

        self._opacity_anim = QPropertyAnimation(self, b"rippleOpacity")
        self._opacity_anim.setDuration(350)
        self._opacity_anim.setStartValue(1.0)
        self._opacity_anim.setEndValue(0.0)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._opacity_anim.start()

        super().mousePressEvent(event)

    def paintEvent(self, event):
        """Draw button with ripple overlay."""
        super().paintEvent(event)
        if self._ripple_opacity_val > 0.0 and self._ripple_radius_val > 0.0:
            painter = QPainter(self)
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                color = QColor(0, 0, 0, int(80 * self._ripple_opacity_val))
                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(
                    self._ripple_center,
                    int(self._ripple_radius_val),
                    int(self._ripple_radius_val),
                )
            finally:
                painter.end()