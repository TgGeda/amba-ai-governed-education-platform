from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from amba_ai.logger import logger


@dataclass(frozen=True)
class SmartView:
    """
    Saved semantic/tag-based document filter.

    required_tags uses normalized lowercase tags.
    A document matches the view when it contains all required tags.
    """

    name: str
    required_tags: frozenset[str] = field(default_factory=frozenset)
    description: str = ""

    @staticmethod
    def create(
        *,
        name: str,
        required_tags: Iterable[str] | None = None,
        description: str = "",
    ) -> SmartView:
        """
        Create a normalized SmartView.
        """
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("SmartView name cannot be empty.")

        normalized_tags = frozenset(
            str(tag).strip().lower()
            for tag in (required_tags or [])
            if str(tag).strip()
        )

        return SmartView(
            name=clean_name,
            required_tags=normalized_tags,
            description=str(description or "").strip(),
        )

    def matches_tags(self, tags: Iterable[str]) -> bool:
        """
        Return True when the provided tags satisfy this smart view.
        """
        if not self.required_tags:
            return True

        normalized = {
            str(tag).strip().lower()
            for tag in tags
            if str(tag).strip()
        }

        return self.required_tags.issubset(normalized)


class TagSmartViewsPanel(QWidget):
    """
    Lightweight smart-view selector for the library UI.

    This widget owns no document state. It only displays smart views and emits
    the selected SmartView object for the parent controller/view to apply.
    """

    view_selected = Signal(SmartView)

    EMPTY_TEXT = "No smart views configured."

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._views: list[SmartView] = []

        self.title = QLabel("Smart Views")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status = QLabel(self.EMPTY_TEXT)
        self.status.setStyleSheet("color: gray;")

        self.list = QListWidget()
        self.list.itemClicked.connect(self._emit_selected)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addWidget(self.list)

        self.set_views([])

    def set_views(self, views: Iterable[SmartView]) -> None:
        """
        Replace the displayed smart views.
        """
        self._views = list(views)
        self.list.clear()

        for view in self._views:
            item = QListWidgetItem(view.name)
            item.setData(Qt.ItemDataRole.UserRole, view)
            item.setToolTip(self._tooltip_for(view))
            self.list.addItem(item)

        self.status.setText(
            f"{len(self._views)} smart view(s)."
            if self._views
            else self.EMPTY_TEXT
        )

        logger.info(
            "Smart views updated",
            extra={"context": {"count": len(self._views)}},
        )

    def add_view(self, view: SmartView) -> None:
        """
        Add a single smart view if its name is not already present.
        """
        existing_names = {existing.name.lower() for existing in self._views}
        if view.name.lower() in existing_names:
            logger.warning(
                "Duplicate smart view ignored",
                extra={"context": {"name": view.name}},
            )
            return

        self.set_views([*self._views, view])

    def clear_views(self) -> None:
        """
        Remove all smart views from the panel.
        """
        self.set_views([])

    def selected_view(self) -> SmartView | None:
        """
        Return the currently selected SmartView, if any.
        """
        item = self.list.currentItem()
        if item is None:
            return None

        value = item.data(Qt.ItemDataRole.UserRole)
        return value if isinstance(value, SmartView) else None

    @Slot(QListWidgetItem)
    def _emit_selected(self, item: QListWidgetItem) -> None:
        view = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(view, SmartView):
            logger.warning(
                "Invalid smart view item clicked",
                extra={"context": {"item_text": item.text()}},
            )
            return

        logger.info(
            "Smart view selected",
            extra={
                "context": {
                    "name": view.name,
                    "required_tags": sorted(view.required_tags),
                }
            },
        )

        self.view_selected.emit(view)

    @staticmethod
    def _tooltip_for(view: SmartView) -> str:
        tags = (
            ", ".join(sorted(view.required_tags))
            if view.required_tags
            else "all documents"
        )

        if view.description:
            return f"{view.description}\n\nRequired tags: {tags}"

        return f"Required tags: {tags}"


def default_smart_views() -> list[SmartView]:
    """
    Return useful built-in smart views for AmbaAI library organization.
    """
    return [
        SmartView.create(
            name="All Documents",
            required_tags=[],
            description="Show every active library document.",
        ),
        SmartView.create(
            name="Biology",
            required_tags=["biology"],
            description="Documents tagged as biology.",
        ),
        SmartView.create(
            name="Chemistry",
            required_tags=["chemistry"],
            description="Documents tagged as chemistry.",
        ),
        SmartView.create(
            name="Physics",
            required_tags=["physics"],
            description="Documents tagged as physics.",
        ),
        SmartView.create(
            name="Agriculture",
            required_tags=["agriculture"],
            description="Documents tagged as agriculture.",
        ),
        SmartView.create(
            name="Exam Review",
            required_tags=["exam"],
            description="Materials tagged for exam preparation.",
        ),
        SmartView.create(
            name="Teacher Verified",
            required_tags=["verified"],
            description="Materials reviewed or approved by a teacher.",
        ),
    ]


def filter_documents_by_smart_view(
    documents: Iterable[object],
    smart_view: SmartView,
) -> list[object]:
    """
    Filter arbitrary document objects or dictionaries by SmartView tags.

    Supports:
    - objects with .tags
    - dictionaries with ["tags"]
    """
    matched: list[object] = []

    for document in documents:
        tags = _extract_tags(document)
        if smart_view.matches_tags(tags):
            matched.append(document)

    return matched


def _extract_tags(document: object) -> list[str]:
    if isinstance(document, dict):
        raw_tags = document.get("tags", [])
    else:
        raw_tags = getattr(document, "tags", [])

    if raw_tags is None:
        return []

    if isinstance(raw_tags, str):
        return [tag.strip() for tag in raw_tags.split(",") if tag.strip()]

    if isinstance(raw_tags, (list, tuple, set, frozenset)):
        return [str(tag).strip() for tag in raw_tags if str(tag).strip()]

    return []