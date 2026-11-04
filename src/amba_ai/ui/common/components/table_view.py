from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHeaderView, QLabel,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)
from .source_chip import SourceChip


class LearningTableView(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("learningTableCard")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # Title
        self.title = QLabel("")
        self.title.setObjectName("learningContentTitle")
        self.title.setWordWrap(True)

        # Caption
        self.caption = QLabel("")
        self.caption.setObjectName("learningCaption")
        self.caption.setWordWrap(True)
        self.caption.setVisible(False)

        # Table
        self.table = QTableWidget()
        self.table.setObjectName("learningDataTable")
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setWordWrap(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)

        # Source chip
        self.source = SourceChip()
        self.source.setFixedHeight(24)  # compact chip size

        root.addWidget(self.title)
        root.addWidget(self.caption)
        root.addWidget(self.table)
        root.addWidget(self.source, 0, Qt.AlignmentFlag.AlignLeft)

    def setTable(self, model: object) -> None:
        headers = tuple(getattr(model, "headers", ()) or ())
        rows = tuple(getattr(model, "rows", ()) or ())

        # Title and caption
        self.title.setText(str(getattr(model, "title", "") or "Table"))
        caption = str(getattr(model, "caption", "") or getattr(model, "summary", "") or "")
        self.caption.setText(caption)
        self.caption.setVisible(bool(caption))

        # Table content
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setRowCount(len(rows))
        self.table.setHorizontalHeaderLabels([str(x) for x in headers])

        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_index, column_index, item)

        self.table.resizeRowsToContents()

        # Source chip
        sources = tuple(getattr(model, "source_regions", ()) or ())
        self.source.setCitation(sources[0] if sources else None)

        self.setAccessibleName(f"Learning table: {self.title.text()}")
