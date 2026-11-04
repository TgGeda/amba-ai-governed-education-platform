from __future__ import annotations
from dataclasses import dataclass
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget


@dataclass(frozen=True)
class MasterySnapshot:
    objectives_done: int = 0
    objectives_total: int = 0
    notes_done: int = 0
    notes_total: int = 0
    cards_done: int = 0
    cards_total: int = 0
    quiz_accuracy: int = 0

    @property
    def percentage(self) -> int:
        def ratio(done: int, total: int) -> float:
            return done / total if total else 0.0
        value = (
            ratio(self.objectives_done, self.objectives_total) * .20
            + ratio(self.notes_done, self.notes_total) * .30
            + ratio(self.cards_done, self.cards_total) * .25
            + max(0, min(100, self.quiz_accuracy)) / 100 * .25
        )
        return round(value * 100)


class MasteryBanner(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("learningMasteryBanner")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self.label = QLabel("Overall mastery: 0%")
        self.label.setObjectName("learningMasteryLabel")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.bar = QProgressBar()
        self.bar.setObjectName("learningMasteryProgress")
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(True)
        self.bar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.bar_anim = QPropertyAnimation(self.bar, b"value", self)
        self.bar_anim.setDuration(600)
        self.bar_anim.setEasingCurve(QEasingCurve.InOutCubic)

        self.status = QLabel("📊 Tracking mastery")
        self.status.setObjectName("learningMasteryStatus")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("color: gray; font-style: italic;")

        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        layout.addWidget(self.status)

    def setSnapshot(self, snapshot: MasterySnapshot) -> None:
        value = snapshot.percentage
        self.label.setText(
            f"Overall mastery: {value}%\n"
            f"📖 Reading: {snapshot.notes_done}/{snapshot.notes_total}  |  "
            f"🎯 Objectives: {snapshot.objectives_done}/{snapshot.objectives_total}  |  "
            f"🃏 Cards: {snapshot.cards_done}/{snapshot.cards_total}  |  "
            f"📝 Quiz: {snapshot.quiz_accuracy}%"
        )

        self.bar_anim.stop()
        self.bar_anim.setStartValue(self.bar.value())
        self.bar_anim.setEndValue(value)
        self.bar_anim.start()

        if value >= 100:
            self._celebrate()
        elif value >= 80:
            self.status.setText("✅ Mastery Achieved")
            self.status.setStyleSheet("color: green; font-weight: bold;")
        elif value >= 50:
            self.status.setText("⏳ In Progress")
            self.status.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.status.setText("🚀 Getting Started")
            self.status.setStyleSheet("color: red; font-weight: bold;")

        self.setAccessibleName(f"Mastery banner: {value}% overall mastery")

    def _celebrate(self) -> None:
        """Glow + confetti effect when mastery hits 100%."""
        self.status.setText("🎉 Congratulations! Full Mastery 🎉")
        self.status.setStyleSheet("color: purple; font-weight: bold;")

        # Glow effect by animating background color
        palette = self.palette()
        base_color = QColor("#ffffff")
        glow_color = QColor("#ffd700")  # gold glow

        def set_glow(step: int):
            ratio = step / 10
            mixed = QColor(
                base_color.red() + (glow_color.red() - base_color.red()) * ratio,
                base_color.green() + (glow_color.green() - base_color.green()) * ratio,
                base_color.blue() + (glow_color.blue() - base_color.blue()) * ratio,
            )
            palette.setColor(QPalette.ColorRole.Window, mixed)
            self.setPalette(palette)
            self.setAutoFillBackground(True)

        # Animate glow pulses
        for i in range(10):
            QTimer.singleShot(i * 100, lambda step=i: set_glow(step))
        QTimer.singleShot(1200, lambda: self.setAutoFillBackground(False))
