from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


class AmbientOverlayState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


class AmbientOverlay(QWidget):
    clicked = Signal()
    dismissed = Signal()
    state_changed = Signal(str)

    DEFAULT_SIZE = 96
    DEFAULT_MARGIN = 24
    ANIMATION_INTERVAL_MS = 16

    COLORS = {
        AmbientOverlayState.IDLE: QColor(80, 170, 255),
        AmbientOverlayState.LISTENING: QColor(80, 255, 180),
        AmbientOverlayState.THINKING: QColor(180, 110, 255),
        AmbientOverlayState.SPEAKING: QColor(255, 205, 90),
        AmbientOverlayState.ERROR: QColor(255, 80, 90),
    }

    LABELS = {
        AmbientOverlayState.IDLE: "Amba",
        AmbientOverlayState.LISTENING: "Listening",
        AmbientOverlayState.THINKING: "Thinking",
        AmbientOverlayState.SPEAKING: "Speaking",
        AmbientOverlayState.ERROR: "Attention",
    }

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        size: int = DEFAULT_SIZE,
        margin: int = DEFAULT_MARGIN,
        always_on_top: bool = True,
        start_visible: bool = False,
    ) -> None:
        super().__init__(parent)

        self._state = AmbientOverlayState.IDLE
        self._size = max(72, int(size))
        self._margin = max(8, int(margin))
        self._phase = 0.0
        self._dragging = False
        self._drag_offset = QPoint()
        self._visible_target = bool(start_visible)

        flags = Qt.FramelessWindowHint | Qt.Tool
        if always_on_top:
            flags |= Qt.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(QSize(self._size, self._size + 30))
        self.setWindowOpacity(0.0)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setText(self.LABELS[self._state])
        self._label.setStyleSheet(
            """
            QLabel {
                color: rgba(255, 255, 255, 225);
                font-size: 11px;
                font-weight: 700;
                background: transparent;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, self._size - 2, 0, 0)
        layout.addWidget(self._label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self.ANIMATION_INTERVAL_MS)

        self._fade_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_animation.setDuration(180)
        self._fade_animation.setEasingCurve(QEasingCurve.OutCubic)

        self.position_bottom_right()

        if start_visible:
            self.show_overlay()
        else:
            self.hide()

    def set_state(self, state: AmbientOverlayState | str) -> None:
        try:
            next_state = AmbientOverlayState(state)
        except ValueError:
            next_state = AmbientOverlayState.IDLE

        if self._state == next_state:
            return

        self._state = next_state
        self._label.setText(self.LABELS[self._state])
        self.state_changed.emit(self._state.value)
        self.update()

    def state(self) -> AmbientOverlayState:
        return self._state

    def set_idle(self) -> None:
        self.show_overlay()
        self.set_state(AmbientOverlayState.IDLE)

    def set_listening(self) -> None:
        self.show_overlay()
        self.set_state(AmbientOverlayState.LISTENING)

    def set_thinking(self) -> None:
        self.show_overlay()
        self.set_state(AmbientOverlayState.THINKING)

    def set_speaking(self) -> None:
        self.show_overlay()
        self.set_state(AmbientOverlayState.SPEAKING)

    def set_error(self) -> None:
        self.show_overlay()
        self.set_state(AmbientOverlayState.ERROR)

    def show_overlay(self) -> None:
        self._visible_target = True
        self.position_bottom_right_if_unmoved()
        if not self.isVisible():
            self.show()
        self.raise_()
        self._animate_opacity(0.92)

    def hide_overlay(self) -> None:
        self._visible_target = False
        self._animate_opacity(0.0, hide_when_done=True)
        self.dismissed.emit()

    def toggle_overlay(self) -> None:
        if self.isVisible() and self.windowOpacity() > 0.05:
            self.hide_overlay()
        else:
            self.show_overlay()

    def position_bottom_right(self) -> None:
        screen = QApplication.screenAt(self.cursor().pos()) or QApplication.primaryScreen()
        if not screen:
            return
        geometry = screen.availableGeometry()
        x = geometry.right() - self.width() - self._margin
        y = geometry.bottom() - self.height() - self._margin
        self.move(max(geometry.left(), x), max(geometry.top(), y))

    def position_bottom_right_if_unmoved(self) -> None:
        if not self._dragging and not self.isVisible():
            self.position_bottom_right()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        circle_rect = QRect(0, 0, self._size, self._size)
        center = circle_rect.center()
        base_color = self.COLORS[self._state]
        pulse = self._pulse_value()
        glow_radius = int((self._size * 0.48) + (pulse * self._size * 0.12))
        core_radius = int(self._size * 0.31)

        glow_color = QColor(base_color)
        glow_color.setAlpha(self._glow_alpha())

        gradient = QRadialGradient(center, glow_radius)
        gradient.setColorAt(0.0, QColor(base_color.red(), base_color.green(), base_color.blue(), 210))
        gradient.setColorAt(0.45, QColor(base_color.red(), base_color.green(), base_color.blue(), 120))
        gradient.setColorAt(0.75, glow_color)
        gradient.setColorAt(1.0, QColor(base_color.red(), base_color.green(), base_color.blue(), 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(center, glow_radius, glow_radius)

        outer_color = QColor(base_color)
        outer_color.setAlpha(170)
        painter.setPen(QPen(outer_color, 2))
        painter.setBrush(QColor(base_color.red(), base_color.green(), base_color.blue(), 42))
        painter.drawEllipse(center, int(self._size * 0.38), int(self._size * 0.38))

        inner_color = QColor(base_color)
        inner_color.setAlpha(230)
        inner_gradient = QRadialGradient(center, core_radius)
        inner_gradient.setColorAt(0.0, QColor(255, 255, 255, 235))
        inner_gradient.setColorAt(0.32, QColor(base_color.red(), base_color.green(), base_color.blue(), 235))
        inner_gradient.setColorAt(1.0, QColor(base_color.red(), base_color.green(), base_color.blue(), 90))

        painter.setPen(Qt.NoPen)
        painter.setBrush(inner_gradient)
        painter.drawEllipse(center, core_radius, core_radius)

        ring_color = QColor(255, 255, 255, 160)
        painter.setPen(QPen(ring_color, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, int(self._size * 0.21), int(self._size * 0.21))

        self._draw_state_indicator(painter, center, base_color)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        if event.button() == Qt.RightButton:
            self.hide_overlay()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            was_dragging = self._dragging
            self._dragging = False
            if was_dragging:
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.position_bottom_right()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def closeEvent(self, event) -> None:
        self.dismissed.emit()
        super().closeEvent(event)

    def _tick(self) -> None:
        self._phase += 0.075
        if self._phase > math.tau:
            self._phase -= math.tau
        self.update()

    def _pulse_value(self) -> float:
        if self._state == AmbientOverlayState.IDLE:
            return 0.18 + 0.08 * math.sin(self._phase)
        if self._state == AmbientOverlayState.LISTENING:
            return 0.45 + 0.32 * math.sin(self._phase * 1.8)
        if self._state == AmbientOverlayState.THINKING:
            return 0.35 + 0.26 * math.sin(self._phase * 2.4)
        if self._state == AmbientOverlayState.SPEAKING:
            return 0.42 + 0.24 * math.sin(self._phase * 3.2)
        if self._state == AmbientOverlayState.ERROR:
            return 0.5 + 0.38 * abs(math.sin(self._phase * 2.8))
        return 0.25

    def _glow_alpha(self) -> int:
        if self._state == AmbientOverlayState.IDLE:
            return 45
        if self._state == AmbientOverlayState.LISTENING:
            return 95
        if self._state == AmbientOverlayState.THINKING:
            return 105
        if self._state == AmbientOverlayState.SPEAKING:
            return 100
        if self._state == AmbientOverlayState.ERROR:
            return 130
        return 80

    def _draw_state_indicator(self, painter: QPainter, center: QPoint, base_color: QColor) -> None:
        if self._state == AmbientOverlayState.THINKING:
            self._draw_orbit_dots(painter, center, base_color)
            return
        if self._state == AmbientOverlayState.LISTENING:
            self._draw_listening_bars(painter, center)
            return
        if self._state == AmbientOverlayState.SPEAKING:
            self._draw_speaking_wave(painter, center)
            return
        if self._state == AmbientOverlayState.ERROR:
            self._draw_error_mark(painter, center)
            return

    def _draw_orbit_dots(self, painter: QPainter, center: QPoint, color: QColor) -> None:
        radius = self._size * 0.31
        painter.setPen(Qt.NoPen)
        for i in range(3):
            angle = self._phase + i * (math.tau / 3)
            x = center.x() + math.cos(angle) * radius
            y = center.y() + math.sin(angle) * radius
            dot_color = QColor(color)
            dot_color.setAlpha(190)
            painter.setBrush(dot_color)
            painter.drawEllipse(QPoint(int(x), int(y)), 3, 3)

    def _draw_listening_bars(self, painter: QPainter, center: QPoint) -> None:
        painter.setPen(QPen(QColor(255, 255, 255, 190), 2))
        base_x = center.x() - 12
        for i in range(5):
            height = 5 + int(9 * abs(math.sin(self._phase * 2.0 + i * 0.7)))
            x = base_x + i * 6
            painter.drawLine(x, center.y() - height // 2, x, center.y() + height // 2)

    def _draw_speaking_wave(self, painter: QPainter, center: QPoint) -> None:
        painter.setPen(QPen(QColor(255, 255, 255, 185), 2))
        points = []
        width = 28
        for i in range(width):
            x = center.x() - width // 2 + i
            y = center.y() + int(math.sin(self._phase * 4 + i * 0.45) * 6)
            points.append(QPoint(x, y))
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])

    def _draw_error_mark(self, painter: QPainter, center: QPoint) -> None:
        painter.setPen(QPen(QColor(255, 255, 255, 220), 3))
        painter.drawLine(center.x(), center.y() - 11, center.x(), center.y() + 4)
        painter.drawPoint(center.x(), center.y() + 12)

    def _animate_opacity(self, target: float, *, hide_when_done: bool = False) -> None:
        try:
            self._fade_animation.stop()
            self._fade_animation.setStartValue(float(self.windowOpacity()))
            self._fade_animation.setEndValue(float(target))
            try:
                self._fade_animation.finished.disconnect()
            except Exception:
                pass
            if hide_when_done:
                self._fade_animation.finished.connect(self._hide_after_fade)
            self._fade_animation.start()
        except Exception:
            self.setWindowOpacity(float(target))
            if hide_when_done:
                self.hide()

    def _hide_after_fade(self) -> None:
        if not self._visible_target:
            self.hide()