from __future__ import annotations

import time
from typing import Iterable

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from amba_ai.logger import logger
from amba_ai.db.document_store import LibraryDocument


class RecycleBinView(QWidget):
    """
    Recycle bin view for soft-deleted library documents.

    Responsibilities:
    - Display deleted documents
    - Emit restore requests by document_id
    - Emit purge requests by document_id
    - Avoid direct persistence or database mutation
    """

    restored = Signal(int)
    purged = Signal(int)

    EMPTY_MESSAGE = "Recycle bin is empty."

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._documents: list[LibraryDocument] = []

        self.title = QLabel("Recycle Bin")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status = QLabel(self.EMPTY_MESSAGE)
        self.status.setStyleSheet("color: gray;")

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._update_button_state)

        self.btn_restore = QPushButton("Restore")
        self.btn_purge = QPushButton("Delete Permanently")

        self.btn_restore.clicked.connect(self._restore)
        self.btn_purge.clicked.connect(self._purge)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addWidget(self.list)
        layout.addWidget(self.btn_restore)
        layout.addWidget(self.btn_purge)

        self._update_button_state()

    def load(self, documents: Iterable[LibraryDocument]) -> None:
        """
        Load soft-deleted documents into the recycle bin list.

        Args:
            documents: Deleted LibraryDocument objects.
        """
        self._documents = [doc for doc in documents if doc.deleted]
        self.list.clear()

        for document in self._documents:
            item = QListWidgetItem(self._format_document_label(document))
            item.setData(Qt.ItemDataRole.UserRole, document.document_id)
            item.setToolTip(self._tooltip_for(document))
            self.list.addItem(item)

        self.status.setText(
            f"{len(self._documents)} deleted document(s)."
            if self._documents
            else self.EMPTY_MESSAGE
        )

        self._update_button_state()

        logger.info(
            "Recycle bin loaded",
            extra={"context": {"deleted_count": len(self._documents)}},
        )

    @Slot()
    def _restore(self) -> None:
        document = self._current_document()
        if document is None:
            return

        logger.info(
            "Recycle bin restore requested",
            extra={"context": {"document_id": document.document_id}},
        )

        self.restored.emit(document.document_id)

    @Slot()
    def _purge(self) -> None:
        document = self._current_document()
        if document is None:
            return

        reply = QMessageBox.question(
            self,
            "Delete Permanently",
            (
                "This will permanently delete the document from the recycle bin.\n\n"
                f"{document.title}\n\n"
                "This action cannot be undone. Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        logger.warning(
            "Recycle bin purge requested",
            extra={"context": {"document_id": document.document_id}},
        )

        self.purged.emit(document.document_id)

    def _current_document(self) -> LibraryDocument | None:
        row = self.list.currentRow()

        if row < 0 or row >= len(self._documents):
            return None

        return self._documents[row]

    def _update_button_state(self) -> None:
        has_selection = self.list.currentRow() >= 0
        self.btn_restore.setEnabled(has_selection)
        self.btn_purge.setEnabled(has_selection)

    @classmethod
    def _format_document_label(cls, document: LibraryDocument) -> str:
        deleted_text = cls._deleted_age_text(document.deleted_at)
        return f"{document.title} ({document.kind}) — deleted {deleted_text}"

    @staticmethod
    def _tooltip_for(document: LibraryDocument) -> str:
        deleted_at = (
            time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(document.deleted_at),
            )
            if document.deleted_at
            else "unknown"
        )

        tags = ", ".join(document.tags) if document.tags else "none"

        return (
            f"Document ID: {document.document_id}\n"
            f"Title: {document.title}\n"
            f"Kind: {document.kind}\n"
            f"Created: {document.created_at}\n"
            f"Size: {document.size or 'unknown'}\n"
            f"Tags: {tags}\n"
            f"Usage count: {document.usage_count}\n"
            f"Deleted at: {deleted_at}"
        )

    @staticmethod
    def _deleted_age_text(deleted_at: float | None) -> str:
        if deleted_at is None:
            return "at an unknown time"

        elapsed_seconds = max(0, int(time.time() - deleted_at))

        if elapsed_seconds < 60:
            return "less than 1 minute ago"

        elapsed_minutes = elapsed_seconds // 60
        if elapsed_minutes < 60:
            return f"{elapsed_minutes} minute(s) ago"

        elapsed_hours = elapsed_minutes // 60
        if elapsed_hours < 24:
            return f"{elapsed_hours} hour(s) ago"

        elapsed_days = elapsed_hours // 24
        return f"{elapsed_days} day(s) ago"
