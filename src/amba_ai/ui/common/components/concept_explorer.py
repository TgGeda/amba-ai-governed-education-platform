from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .empty_state import EmptyState
from .learning_rich_text import LearningRichText, clean_learning_text
from .source_chip import SourceChip


def clean_concept_name(value: Any) -> str:
    text = clean_learning_text(value)
    text = re.sub(r"^[\s*`_#~•+\-]+", "", text)
    text = re.sub(r"[\s*`_#~]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" :;.,-")


def normalized_concept_key(value: Any) -> str:
    name = clean_concept_name(value)
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def deduplicate_concepts(concepts: Iterable[Any]) -> tuple[Any, ...]:
    unique: dict[str, Any] = {}
    for concept in concepts:
        name = clean_concept_name(getattr(concept, "name", ""))
        if not name:
            continue
        key = normalized_concept_key(name)
        if not key or key in {
            "core concepts",
            "key concepts",
            "learning objectives",
            "overview",
            "sources",
            "revision checklist",
        }:
            continue
        current = unique.get(key)
        if current is None:
            try:
                concept = replace(concept, name=name)
            except Exception:
                try:
                    setattr(concept, "name", name)
                except Exception:
                    pass
            unique[key] = concept
            continue

        current_definition = str(getattr(current, "definition", "") or "")
        candidate_definition = str(getattr(concept, "definition", "") or "")
        if len(candidate_definition) > len(current_definition):
            try:
                concept = replace(concept, name=name)
            except Exception:
                pass
            unique[key] = concept

    return tuple(unique.values())


class TelegramConceptPost(QFrame):
    notesRequested = Signal(str)
    studyRequested = Signal(str)
    tutorRequested = Signal(str)

    def __init__(self, concept: Any, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("telegramConceptPost")
        self._concept = concept

        name = clean_concept_name(getattr(concept, "name", ""))
        definition = clean_learning_text(getattr(concept, "definition", ""))
        relevance = clean_learning_text(getattr(concept, "why_it_matters", ""))
        concept_id = str(getattr(concept, "concept_id", "") or name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 16)
        layout.setSpacing(6)

        # Title Row (Telegram Post Style)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self.title_label = QLabel(f"{index}. 📌  {name}")
        self.title_label.setObjectName("telegramConceptTitle")
        self.title_label.setStyleSheet("font-size: 15px; font-weight: 900; color: #C05C46;")
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        title_row.addWidget(self.title_label, 1)

        # Quick Actions
        notes_btn = QPushButton("Notes")
        notes_btn.setObjectName("telegramActionBtn")
        notes_btn.clicked.connect(lambda: self.notesRequested.emit(concept_id))

        tutor_btn = QPushButton("Ask Tutor")
        tutor_btn.setObjectName("telegramActionBtn")
        tutor_btn.clicked.connect(lambda: self.tutorRequested.emit(concept_id))

        title_row.addWidget(notes_btn)
        title_row.addWidget(tutor_btn)

        layout.addLayout(title_row)

        # Main Definition Text
        if definition:
            def_view = LearningRichText(definition)
            def_view.setObjectName("telegramConceptBody")
            layout.addWidget(def_view)

        # Why it Matters Callout
        if relevance:
            rel_view = LearningRichText(f"💡 *Why it matters:* {relevance}")
            rel_view.setObjectName("telegramConceptRelevance")
            layout.addWidget(rel_view)

        # Divider Line
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #E6D5B8; background-color: #E6D5B8; max-height: 1px; margin-top: 8px;")
        layout.addWidget(divider)


class ConceptExplorer(QWidget):
    conceptSelected = Signal(str)
    notesRequested = Signal(str)
    studyRequested = Signal(str)
    tutorRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("learningConceptExplorer")

        self._concepts: tuple[Any, ...] = ()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Search Bar
        top_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setObjectName("conceptSearchInput")
        self.search_input.setPlaceholderText("🔍 Filter concepts...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_concepts)

        self.counter_label = QLabel("0 concepts")
        self.counter_label.setStyleSheet("font-weight: 700; color: #315343;")

        top_row.addWidget(self.search_input, 1)
        top_row.addWidget(self.counter_label)

        root.addLayout(top_row)

        self.empty_state = EmptyState("No grounded concepts", "No validated concepts were identified.")
        root.addWidget(self.empty_state)

        # Scrollable Feed Container
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.feed_container = QWidget()
        self.feed_layout = QVBoxLayout(self.feed_container)
        self.feed_layout.setContentsMargins(4, 4, 4, 4)
        self.feed_layout.setSpacing(4)
        self.feed_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.feed_container)
        root.addWidget(self.scroll_area, 1)

        self.setConcepts(())

    def concepts(self) -> tuple[Any, ...]:
        return self._concepts

    def setConcepts(self, concepts: Iterable[Any]) -> None:
        self.clear()
        self._concepts = deduplicate_concepts(concepts)

        has_concepts = bool(self._concepts)
        self.empty_state.setVisible(not has_concepts)
        self.scroll_area.setVisible(has_concepts)

        self.counter_label.setText(f"{len(self._concepts)} concepts")

        if not has_concepts:
            return

        for idx, concept in enumerate(self._concepts, 1):
            post = TelegramConceptPost(concept, idx)
            post.notesRequested.connect(self.notesRequested)
            post.studyRequested.connect(self.studyRequested)
            post.tutorRequested.connect(self.tutorRequested)
            self.feed_layout.addWidget(post)

    def set_concepts(self, concepts: Iterable[Any]) -> None:
        self.setConcepts(concepts)

    def clear(self) -> None:
        while self.feed_layout.count() > 0:
            item = self.feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _filter_concepts(self) -> None:
        query = clean_learning_text(self.search_input.text()).lower()
        visible_count = 0

        for i in range(self.feed_layout.count()):
            widget = self.feed_layout.itemAt(i).widget()
            if isinstance(widget, TelegramConceptPost):
                name = clean_concept_name(getattr(widget._concept, "name", "")).lower()
                definition = clean_learning_text(getattr(widget._concept, "definition", "")).lower()
                matches = not query or (query in name or query in definition)
                widget.setVisible(matches)
                if matches:
                    visible_count += 1

        self.counter_label.setText(f"{visible_count} of {len(self._concepts)} concepts")