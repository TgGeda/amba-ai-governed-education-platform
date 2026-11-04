from __future__ import annotations

import html
import json
from pathlib import Path
import re
from typing import Any

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from amba_ai.learning.source_resolver import resolve_source_name
from amba_ai.ui.common.components.accordion_card import AccordionCard
from amba_ai.ui.common.components.concept_explorer import ConceptExplorer
from amba_ai.ui.common.components.mastery_banner import MasteryBanner, MasterySnapshot

SCHEMA_VERSION = "ambaai.learning-delivery.v7.0"


def clean_markdown(text: Any) -> str:
    val = html.unescape(str(text or ""))
    val = re.sub(r"(?:<!--|&lt;!--)\s*ambaai\.[\s\S]*?(?:-->|--&gt;)", "", val, flags=re.IGNORECASE)
    return val.strip()


def parse_learning_sections(markdown: str) -> list[tuple[str, str, list[str]]]:
    text = clean_markdown(markdown)
    sections: list[tuple[str, str, list[str]]] = []
    current_title = "Overview"
    current_paragraphs: list[str] = []
    current_bullets: list[str] = []

    def flush() -> None:
        if current_paragraphs or current_bullets:
            sections.append((current_title, "\n\n".join(current_paragraphs).strip(), list(current_bullets)))
        current_paragraphs.clear()
        current_bullets.clear()

    for raw in text.splitlines():
        line = raw.strip()
        match = re.match(r"^#{1,4}\s+(.+)$", line)
        if match:
            flush()
            current_title = re.sub(r"[*_`]", "", match.group(1)).strip()
            continue

        bullet_match = re.match(r"^[-*•]\s+(.+)$", line)
        if bullet_match:
            current_bullets.append(bullet_match.group(1).strip())
        elif line:
            current_paragraphs.append(line)

    flush()
    return [(h, p, b) for h, p, b in sections if h.lower() not in {"source", "sources"}]


class DeliverySummaryWorkspace(QWidget):
    jumpToNotes = Signal(str)
    tutorRequested = Signal(str)
    studyRequested = Signal(str)

    def __init__(self, widget: QWidget, payload: Any, markdown: str):
        super().__init__()
        self.settings = QSettings()
        self.doc_id = int(getattr(widget, "document_id", 0) or (payload.get("document_id", 0) if isinstance(payload, dict) else 0) or 0)
        self.source = resolve_source_name(payload) if isinstance(payload, dict) else "Uploaded learning material"
        self.sections = parse_learning_sections(markdown)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

        self.mastery = MasteryBanner()
        root.addWidget(self.mastery)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(20, 10, 20, 20)
        self.layout.setSpacing(12)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        self._build_content()
        self._update_mastery()

    def _build_content(self) -> None:
        title = self.sections[0][0] if self.sections else "Study Summary"
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 22px; font-weight: 800; color: #1D3323;")
        self.layout.addWidget(title_label)

        for heading, body, bullets in self.sections:
            card = AccordionCard(heading)
            if body:
                body_label = QLabel(body)
                body_label.setWordWrap(True)
                card.addWidget(body_label)

            if "objective" in heading.lower():
                key = f"LearningDelivery/v7/summary/{self.doc_id}/objectives"
                checked = set(self.settings.value(key, [], list) or [])
                for obj in bullets:
                    box = QCheckBox(obj)
                    box.setChecked(obj in checked)
                    box.toggled.connect(lambda state, o=obj, k=key: self._save_objective(k, o, state))
                    card.addWidget(box)
            else:
                for b in bullets:
                    b_label = QLabel(f"• {b}")
                    b_label.setWordWrap(True)
                    card.addWidget(b_label)

            self.layout.addWidget(card)

        self.layout.addStretch(1)

    def _save_objective(self, key: str, objective: str, state: bool) -> None:
        vals = set(self.settings.value(key, [], list) or [])
        if state:
            vals.add(objective)
        else:
            vals.discard(objective)
        self.settings.setValue(key, sorted(vals))
        self._update_mastery()

    def _update_mastery(self) -> None:
        key = f"LearningDelivery/v7/summary/{self.doc_id}/objectives"
        done = len(self.settings.value(key, [], list) or [])
        notes_key = f"LearningDelivery/v7/notes/{self.doc_id}/understood"
        notes_done = len(self.settings.value(notes_key, [], list) or [])
        total_sec = max(1, len(self.sections))
        self.mastery.setSnapshot(
            MasterySnapshot(
                objectives_done=done,
                objectives_total=max(1, done),
                notes_done=notes_done,
                notes_total=total_sec,
                cards_done=0,
                cards_total=10,
                quiz_accuracy=0,
            )
        )