from __future__ import annotations

from typing import Any, Iterable
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DocumentOutlinePanel(QFrame):
    itemSelected = Signal(int, str)
    toggleRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("documentOutlinePanel")
        self.setMinimumWidth(210)
        self.setMaximumWidth(280)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        self.title_label = QLabel("COURSE OUTLINE")
        self.title_label.setObjectName("outlinePanelTitle")

        self.collapse_btn = QPushButton("◀")
        self.collapse_btn.setObjectName("outlineToggleBtn")
        self.collapse_btn.setFixedSize(22, 22)
        self.collapse_btn.setToolTip("Toggle Navigation Sidebar")
        self.collapse_btn.clicked.connect(self.toggleRequested.emit)

        top_bar.addWidget(self.title_label, 1)
        top_bar.addWidget(self.collapse_btn, 0)
        root.addLayout(top_bar)

        self.outline_list = QListWidget()
        self.outline_list.setObjectName("outlineListWidget")
        self.outline_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.outline_list.setFrameShape(QFrame.Shape.NoFrame)
        self.outline_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.outline_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.outline_list.currentRowChanged.connect(self._on_row_changed)
        root.addWidget(self.outline_list, 1)

        self._items_meta: list[tuple[str, str]] = []

    def setOutlineTree(self, summary_sections: Iterable[str], concepts: Iterable[str]) -> None:
        self.outline_list.blockSignals(True)
        self.outline_list.clear()
        self._items_meta.clear()

        sec_list = [s.strip() for s in summary_sections if s.strip()]
        concept_list = [c.strip() for c in concepts if c.strip()]

        if sec_list:
            header_item = QListWidgetItem("━━━━ SUMMARY SECTIONS ━━━━")
            header_item.setFlags(Qt.ItemFlag.NoItemFlags)
            header_item.setData(Qt.ItemDataRole.UserRole, "header")
            self.outline_list.addItem(header_item)
            self._items_meta.append(("header", "SUMMARY SECTIONS"))

            for title in sec_list:
                if "executive" in title.lower():
                    icon_str = "📄 "
                elif "takeaway" in title.lower():
                    icon_str = "⚡ "
                elif "objective" in title.lower():
                    icon_str = "🎯 "
                else:
                    icon_str = "📘 "

                item = QListWidgetItem(f"  {icon_str}{title}")
                item.setToolTip(title)
                self.outline_list.addItem(item)
                self._items_meta.append(("summary", title))

        if concept_list:
            header_item2 = QListWidgetItem("━━━━ KEY CONCEPTS ━━━━")
            header_item2.setFlags(Qt.ItemFlag.NoItemFlags)
            header_item2.setData(Qt.ItemDataRole.UserRole, "header")
            self.outline_list.addItem(header_item2)
            self._items_meta.append(("header", "KEY CONCEPTS"))

            for idx, c_name in enumerate(concept_list, 1):
                item = QListWidgetItem(f"  📌 {idx}. {c_name}")
                item.setToolTip(c_name)
                self.outline_list.addItem(item)
                self._items_meta.append(("concept", c_name))

        if self.outline_list.count() > 1:
            self.outline_list.setCurrentRow(1)

        self.outline_list.blockSignals(False)

    def _on_row_changed(self, row: int) -> None:
        if 0 <= row < len(self._items_meta):
            item_type, target_name = self._items_meta[row]
            if item_type != "header":
                self.itemSelected.emit(row, item_type)