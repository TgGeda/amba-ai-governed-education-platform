from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget
from .source_chip import SourceChip


class ZoomableLabel(QLabel):
    """QLabel supporting interactive double-click zoom, scroll wheel scaling,
    and drag panning entirely via canvas painting without altering layout geometry."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(140)

        self._pixmap: QPixmap | None = None
        self._zoom_factor: float = 1.0
        self._pan_offset: QPoint = QPoint(0, 0)
        self._dragging: bool = False
        self._drag_start: QPoint = QPoint(0, 0)

    def setPixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.resetZoom()

    def resetZoom(self) -> None:
        self._zoom_factor = 1.0
        self._pan_offset = QPoint(0, 0)
        self._dragging = False
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._zoom_factor > 1.1:
            self.resetZoom()
        else:
            self._zoom_factor = 1.8
            self.update()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._zoom_factor > 1.0 and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            delta = event.pos() - self._drag_start
            self._drag_start = event.pos()
            self._pan_offset += delta
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        angle = event.angleDelta().y()
        factor = 1.15 if angle > 0 else 0.85
        old_zoom = self._zoom_factor
        self._zoom_factor = max(1.0, min(4.0, self._zoom_factor * factor))

        if self._zoom_factor == 1.0:
            self._pan_offset = QPoint(0, 0)

        self.update()
        event.accept()

    def paintEvent(self, event) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            super().paintEvent(event)
            return

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            widget_rect = self.rect()
            scaled_pixmap = self._pixmap.scaled(
                QSize(
                    int(widget_rect.width() * self._zoom_factor),
                    int(widget_rect.height() * self._zoom_factor),
                ),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            x = (widget_rect.width() - scaled_pixmap.width()) // 2 + self._pan_offset.x()
            y = (widget_rect.height() - scaled_pixmap.height()) // 2 + self._pan_offset.y()

            painter.drawPixmap(x, y, scaled_pixmap)
        finally:
            painter.end()


class LearningFigureView(QFrame):
    openRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("learningFigureCard")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        self.image = ZoomableLabel()
        self.image.setObjectName("learningFigureImage")

        self.caption = QLabel("")
        self.caption.setObjectName("learningCaption")
        self.caption.setWordWrap(True)

        self.summary = QLabel("")
        self.summary.setObjectName("learningFigureSummary")
        self.summary.setWordWrap(True)

        self.source = SourceChip()

        self.open_button = QPushButton("Open image")
        self.open_button.setObjectName("learningSecondaryAction")
        self._path = ""
        self.open_button.clicked.connect(lambda: self.openRequested.emit(self._path))

        root.addWidget(self.image)
        root.addWidget(self.caption)
        root.addWidget(self.summary)
        root.addWidget(self.source, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignRight)

    def setFigure(self, figure: object) -> None:
        self._path = str(getattr(figure, "asset_path", "") or "")
        alt = str(getattr(figure, "alt_text", "") or "Visual from learning material")
        self.image.setAccessibleName(alt)

        pixmap = QPixmap(self._path) if self._path and Path(self._path).exists() else QPixmap()
        if pixmap.isNull():
            self.image.setText("Visual unavailable")
        else:
            self.image.setPixmap(pixmap)

        caption = str(getattr(figure, "caption", "") or "")
        summary = str(getattr(figure, "educational_summary", "") or "")

        self.caption.setText(caption)
        self.caption.setVisible(bool(caption))
        self.summary.setText(summary or "No visual explanation available.")

        sources = tuple(getattr(figure, "source_regions", ()) or ())
        self.source.setCitation(sources[0] if sources else None)

        self.open_button.setEnabled(bool(self._path and Path(self._path).exists()))
        self.setAccessibleName(f"Learning figure: {alt}")