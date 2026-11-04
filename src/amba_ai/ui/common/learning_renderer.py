from __future__ import annotations

import html
import json
from pathlib import Path
import re
from typing import Any, Mapping

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from amba_ai.learning import DocumentAgnosticLearningParser, LearningDocumentValidator
from amba_ai.learning.source_resolver import resolve_source_name

SCHEMA_VERSION = "ambaai.learning-renderer.v7.0"
_INTERNAL_COMMENT = re.compile(r"(?:<!--|&lt;!--)\s*ambaai\.[\s\S]*?(?:-->|--&gt;)", re.IGNORECASE)


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\\n", "\n").replace("\\t", "\t")
    return _INTERNAL_COMMENT.sub("", text).strip()


def clean_title(value: Any) -> str:
    text = clean_text(value)
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"^\s*(?:detected\s+topic|topic)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text.replace("_", " ")).strip()
    return text or "Learning Material"


def extract_payload(payload: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(payload, Mapping):
        meta = dict(payload.get("metadata") or {})
        for key in ("markdown", "markdown_notes", "summary_markdown", "notes", "content"):
            val = payload.get(key)
            if val:
                return clean_text(val), {**payload, **meta}
        return "", {**payload, **meta}
    meta = dict(getattr(payload, "metadata", {}) or {})
    for key in ("markdown", "markdown_notes", "summary_markdown", "notes", "content"):
        val = getattr(payload, key, None)
        if val:
            return clean_text(val), meta
    return clean_text(payload if isinstance(payload, str) else ""), meta


def section_map(markdown: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    current = "Overview"
    body: list[str] = []
    for raw in markdown.splitlines():
        line = raw.strip()
        match = re.match(r"^#{2,4}\s+(.+?)\s*$", line)
        if match:
            if body and any(b.strip() for b in body):
                result.append((current, "\n".join(body).strip()))
            current = clean_title(re.sub(r"[*_`]", "", match.group(1)).strip())
            body = []
        elif not re.match(r"^#\s+", line):
            body.append(raw)
    if body and any(b.strip() for b in body):
        result.append((current, "\n".join(body).strip()))
    return [(h, b) for h, b in result if h.lower() not in {"sources", "source"} or b]


def format_prose_html(text: str, query: str = "") -> str:
    parts: list[str] = []
    in_code = False
    code_lines: list[str] = []

    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            if in_code:
                code_text = html.escape("\n".join(code_lines))
                parts.append(f"<pre style='background:#0D1B2A;color:#FFFFFF;padding:8px;border-radius:6px;'>{code_text}</pre>")
                code_lines = []
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(raw)
            continue
        if not stripped:
            continue

        escaped = html.escape(stripped)
        escaped = re.sub(r"`([^`]+)`", r"<code style='background:#F1F5F9;color:#0F172A;padding:2px 4px;'>\1</code>", escaped)
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)

        if query:
            escaped = re.sub(re.escape(html.escape(query)), lambda m: f"<mark style='background:#FFE066;'>{m.group(0)}</mark>", escaped, flags=re.IGNORECASE)

        if re.match(r"^[-*•]\s+", stripped):
            bullet_text = re.sub(r"^[-*•]\s+", "", escaped)
            parts.append(f"<div style='margin-left:12px;margin-bottom:4px;'>• {bullet_text}</div>")
        else:
            parts.append(f"<p style='margin:4px 0 6px 0;line-height:1.5;'>{escaped}</p>")

    if code_lines:
        parts.append(f"<pre style='background:#0D1B2A;color:#FFFFFF;padding:8px;border-radius:6px;'>{html.escape(chr(10).join(code_lines))}</pre>")

    return "".join(parts)


class AccordionSection(QFrame):
    expandedChanged = Signal(bool)
    reviewChanged = Signal(bool)

    def __init__(self, title: str, body: str, section_id: str, source: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.section_id = section_id
        self.title_text = title
        self.body_text = body

        self.setObjectName("learningSectionCard")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(4)

        header_row = QHBoxLayout()
        self.header = QToolButton()
        self.header.setObjectName("learningAccordionHeader")
        self.header.setText(title)
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setArrowType(Qt.ArrowType.DownArrow)
        self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.header.clicked.connect(self.set_expanded)

        self.reviewed = QCheckBox("Understood")
        self.reviewed.setObjectName("learningUnderstoodToggle")
        self.reviewed.toggled.connect(self.reviewChanged)

        header_row.addWidget(self.header, 1)
        header_row.addWidget(self.reviewed)
        root.addLayout(header_row)

        self.body = QFrame()
        self.body.setObjectName("learningSectionBody")
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(16, 8, 16, 8)

        self.content = QLabel()
        self.content.setObjectName("learningProse")
        self.content.setWordWrap(True)
        self.content.setTextFormat(Qt.TextFormat.RichText)
        self.content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body_layout.addWidget(self.content)

        source_label = QLabel(f"Source: {source}")
        source_label.setObjectName("learningSourceChip")
        body_layout.addWidget(source_label, 0, Qt.AlignmentFlag.AlignLeft)

        root.addWidget(self.body)
        self.set_query("")

    def set_query(self, query: str) -> None:
        self.content.setText(format_prose_html(self.body_text, query))

    def set_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        self.header.setChecked(expanded)
        self.header.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.body.setVisible(expanded)
        self.expandedChanged.emit(expanded)


class DynamicSummaryView(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._cards: list[AccordionSection] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search summary and concepts...")
        self.search.setClearButtonEnabled(True)
        self.expand_btn = QPushButton("Expand all")
        self.collapse_btn = QPushButton("Collapse all")

        tools.addWidget(self.search, 1)
        tools.addWidget(self.expand_btn)
        tools.addWidget(self.collapse_btn)
        root.addLayout(tools)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(16, 8, 16, 16)
        self.layout.setSpacing(10)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        self.search.textChanged.connect(self._search)
        self.expand_btn.clicked.connect(lambda: [c.set_expanded(True) for c in self._cards])
        self.collapse_btn.clicked.connect(lambda: [c.set_expanded(False) for c in self._cards])

    def render(self, title: str, markdown: str, source: str) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        header = QLabel(clean_title(title))
        header.setStyleSheet("font-size: 20px; font-weight: 800; color: #0F172A;")
        sub = QLabel(f"{source} · Grounded summary")
        sub.setStyleSheet("font-size: 12px; color: #64748B;")
        self.layout.addWidget(header)
        self.layout.addWidget(sub)

        for heading, body in section_map(markdown):
            card = AccordionSection(heading, body, heading.lower().replace(" ", "-"), source)
            self._cards.append(card)
            self.layout.addWidget(card)

        self.layout.addStretch(1)

    def _search(self, query: str) -> None:
        q = query.strip().lower()
        for card in self._cards:
            hit = not q or q in card.title_text.lower() or q in card.body_text.lower()
            card.setVisible(hit)
            card.set_query(query.strip())
            if q and hit:
                card.set_expanded(True)


class DynamicNotesView(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = QSettings()
        self._cards: dict[str, AccordionSection] = {}
        self.document_id = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search notes, mechanisms, and procedures...")
        self.search.setClearButtonEnabled(True)
        root.addWidget(self.search)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(200)
        self.tree.setMaximumWidth(320)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(16, 8, 16, 16)
        self.layout.setSpacing(10)
        self.scroll.setWidget(self.container)

        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.scroll)
        self.splitter.setSizes([240, 800])
        root.addWidget(self.splitter, 1)

        self.search.textChanged.connect(self._search)
        self.tree.itemClicked.connect(self._navigate)

    def render(self, title: str, markdown: str, source: str, document_id: int) -> None:
        self.document_id = document_id
        self.tree.clear()
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        header = QLabel(clean_title(title))
        header.setStyleSheet("font-size: 20px; font-weight: 800; color: #0F172A;")
        sub = QLabel(f"{source} · Detailed notes")
        sub.setStyleSheet("font-size: 12px; color: #64748B;")
        self.layout.addWidget(header)
        self.layout.addWidget(sub)

        top_tree_item = QTreeWidgetItem([clean_title(title)])
        self.tree.addTopLevelItem(top_tree_item)

        for heading, body in section_map(markdown):
            sid = heading.lower().replace(" ", "-")
            card = AccordionSection(heading, body, sid, source)
            self._cards[sid] = card
            self.layout.addWidget(card)

            leaf = QTreeWidgetItem([heading])
            leaf.setData(0, Qt.ItemDataRole.UserRole, sid)
            top_tree_item.addChild(leaf)

        top_tree_item.setExpanded(True)
        self.layout.addStretch(1)

    def _navigate(self, item: QTreeWidgetItem, _col: int = 0) -> None:
        sid = item.data(0, Qt.ItemDataRole.UserRole)
        card = self._cards.get(str(sid or ""))
        if card:
            card.set_expanded(True)
            self.scroll.ensureWidgetVisible(card, 30, 30)

    def _search(self, query: str) -> None:
        q = query.strip().lower()
        for sid, card in self._cards.items():
            hit = not q or q in card.title_text.lower() or q in card.body_text.lower()
            card.setVisible(hit)
            card.set_query(query.strip())
            if q and hit:
                card.set_expanded(True)