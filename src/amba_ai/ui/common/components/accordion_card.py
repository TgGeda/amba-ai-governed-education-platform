from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QPaintEvent, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QStyle,
    QStyleOption,
    QVBoxLayout,
    QWidget,
)


class _AccordionHeaderFrame(QFrame):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("learningAccordionHeader")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        option = QStyleOption()
        option.initFrom(self)
        painter = QPainter(self)
        try:
            self.style().drawPrimitive(
                QStyle.PrimitiveElement.PE_Widget, option, painter, self
            )
        finally:
            painter.end()


class AccordionCard(QFrame):
    expandedChanged = Signal(bool)
    reviewedChanged = Signal(bool)

    def __init__(
        self,
        title: str,
        *,
        subtitle: str = "",
        badge: str = "",
        expanded: bool = True,
        reviewable: bool = False,
        animated: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._title_text = str(title or "").strip()
        self._subtitle_text = str(subtitle or "").strip()
        self._badge_text = str(badge or "").strip()
        self._expanded = bool(expanded)
        self._animated = bool(animated)
        self._is_animating = False

        self.setObjectName("learningAccordionCard")
        self.setProperty("expanded", self._expanded)
        self.setProperty("reviewed", False)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header (Top Bar of Card)
        self.header_frame = _AccordionHeaderFrame(self)
        self.header_frame.clicked.connect(self.toggle)

        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(10)

        self.chevron_icon = QLabel()
        self.chevron_icon.setObjectName("learningAccordionChevron")
        self.chevron_icon.setFixedSize(16, 16)
        self.chevron_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.chevron_icon, 0)

        title_container = QWidget()
        title_container.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)

        self.title_label = QLabel(self._title_text)
        self.title_label.setObjectName("learningAccordionTitle")
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        title_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(self._subtitle_text)
        self.subtitle_label.setObjectName("learningAccordionSubtitle")
        self.subtitle_label.setVisible(bool(self._subtitle_text))
        self.subtitle_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction
        )
        title_layout.addWidget(self.subtitle_label)

        header_layout.addWidget(title_container, 1)

        self.badge_label = QLabel(self._badge_text)
        self.badge_label.setObjectName("learningAccordionBadge")
        self.badge_label.setVisible(bool(self._badge_text))
        self.badge_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        header_layout.addWidget(self.badge_label, 0)

        self.review_check: QCheckBox | None = None
        if reviewable:
            self.review_check = QCheckBox("Understood")
            self.review_check.setObjectName("learningReviewedCheck")
            self.review_check.setCursor(Qt.CursorShape.PointingHandCursor)
            self.review_check.setAccessibleName(
                f"Mark {self._title_text} as understood"
            )
            self.review_check.toggled.connect(self.setReviewed)
            header_layout.addWidget(
                self.review_check, 0, Qt.AlignmentFlag.AlignRight
            )

        # Body (Content area inside SAME card shell)
        self.body = QFrame()
        self.body.setObjectName("learningAccordionBody")
        self.body.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(16, 14, 16, 16)
        self.body_layout.setSpacing(10)

        root.addWidget(self.header_frame)
        root.addWidget(self.body)

        self._anim = QPropertyAnimation(self.body, b"maximumHeight", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_animation_finished)

        self._apply_expanded_state(self._expanded, animated=False)

    def title(self) -> str:
        return self._title_text

    def setTitle(self, title: str) -> None:
        self._title_text = str(title or "").strip()
        self.title_label.setText(self._title_text)

    def subtitle(self) -> str:
        return self._subtitle_text

    def setSubtitle(self, subtitle: str) -> None:
        self._subtitle_text = str(subtitle or "").strip()
        self.subtitle_label.setText(self._subtitle_text)
        self.subtitle_label.setVisible(bool(self._subtitle_text))

    def badge(self) -> str:
        return self._badge_text

    def setBadge(self, badge: str) -> None:
        self._badge_text = str(badge or "").strip()
        self.badge_label.setText(self._badge_text)
        self.badge_label.setVisible(bool(self._badge_text))

    def isExpanded(self) -> bool:
        return self._expanded

    def is_expanded(self) -> bool:
        return self.isExpanded()

    def setExpanded(self, expanded: bool, animated: bool = True) -> None:
        expanded = bool(expanded)
        if expanded == self._expanded and not self._is_animating:
            return

        changed = expanded != self._expanded
        self._expanded = expanded

        self._apply_expanded_state(expanded, animated=animated and self._animated)

        if changed:
            self.expandedChanged.emit(expanded)

    def set_expanded(self, expanded: bool, animated: bool = True) -> None:
        self.setExpanded(expanded, animated=animated)

    def toggle(self) -> None:
        self.setExpanded(not self._expanded, animated=True)

    def isReviewed(self) -> bool:
        return bool(self.property("reviewed"))

    def setReviewed(self, reviewed: bool) -> None:
        reviewed = bool(reviewed)
        changed = reviewed != self.isReviewed()

        self.setProperty("reviewed", reviewed)

        if self.review_check is not None:
            self.review_check.blockSignals(True)
            self.review_check.setChecked(reviewed)
            self.review_check.setText("Reviewed" if reviewed else "Understood")
            self.review_check.blockSignals(False)

        self._refresh_style()

        if changed:
            self.reviewedChanged.emit(reviewed)

    def addWidget(self, widget: QWidget) -> None:
        self.body_layout.addWidget(widget)

    def addLayout(self, layout: QLayout) -> None:
        self.body_layout.addLayout(layout)

    def clearContent(self) -> None:
        while self.body_layout.count() > 0:
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _apply_expanded_state(self, expanded: bool, animated: bool = True) -> None:
        self.setProperty("expanded", expanded)
        self.chevron_icon.setText("▼" if expanded else "▶")
        self._refresh_style()

        if not animated or not self.isVisible():
            self._anim.stop()
            self._is_animating = False
            self.body.setVisible(expanded)
            self.body.setMaximumHeight(16777215 if expanded else 0)
            return

        self._anim.stop()
        self._is_animating = True

        self.body.setVisible(True)
        start_height = self.body.height()

        if expanded:
            self.body.setMaximumHeight(16777215)
            target_height = self.body_layout.sizeHint().height() + 32
        else:
            target_height = 0

        self._anim.setStartValue(start_height)
        self._anim.setEndValue(target_height)
        self._anim.start()

    def _on_animation_finished(self) -> None:
        self._is_animating = False
        if self._expanded:
            self.body.setMaximumHeight(16777215)
        else:
            self.body.setVisible(False)

    def _refresh_style(self) -> None:
        for widget in (self, self.header_frame, self.body, self.chevron_icon):
            style = widget.style()
            if style is not None:
                style.unpolish(widget)
                style.polish(widget)
                widget.update()