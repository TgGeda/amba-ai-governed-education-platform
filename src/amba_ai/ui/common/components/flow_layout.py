from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QWidget


class FlowLayout(QLayout):
    """Custom flow layout that wraps widgets horizontally without creating runtime heap objects inside layout loops."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        margin: int = 0,
        horizontal_spacing: int = 8,
        vertical_spacing: int = 8,
        alignment: str = "left",
    ) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._horizontal_spacing = max(0, int(horizontal_spacing))
        self._vertical_spacing = max(0, int(vertical_spacing))
        self._alignment = alignment
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int) -> QLayoutItem | None:
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int) -> QLayoutItem | None:
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return self._do_layout(QRect(0, 0, w, 0), test_only=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_height = effective.x(), effective.y(), 0
        row_items: list[QLayoutItem] = []
        row_width = 0

        def place_row(items: list[QLayoutItem], r_width: int, r_y: int) -> None:
            if not items:
                return
            extra_space = effective.width() - r_width
            offset_x = effective.x()

            if self._alignment == "center":
                offset_x += extra_space // 2

            cur_x = offset_x
            for item in items:
                size = item.sizeHint()
                if not test_only:
                    item.setGeometry(QRect(QPoint(cur_x, r_y), size))
                cur_x += size.width() + self._horizontal_spacing

        for item in self._items:
            w = item.widget()
            if w and not w.isVisible():
                continue
            size = item.sizeHint()
            next_x = x + size.width() + self._horizontal_spacing

            if next_x - self._horizontal_spacing > effective.right() and line_height > 0:
                place_row(row_items, row_width, y)
                row_items, row_width = [], 0
                x = effective.x()
                y += line_height + self._vertical_spacing
                next_x = x + size.width() + self._horizontal_spacing
                line_height = 0

            row_items.append(item)
            row_width += size.width() + self._horizontal_spacing
            x = next_x
            line_height = max(line_height, size.height())

        place_row(row_items, row_width, y)
        return y + line_height - rect.y() + m.bottom()


def configure_flow_widget(widget: QWidget) -> None:
    widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)