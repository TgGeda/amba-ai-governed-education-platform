from __future__ import annotations

import html
import json
from pathlib import Path
import re
from typing import Any, Optional

from PySide6.QtCore import (
    QDateTime,
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    QSettings,
    QSize,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from amba_ai.core.export import export_markdown
from amba_ai.exceptions import ExportError
from amba_ai.learning.multimodal_parser import MultimodalLearningParser
from amba_ai.learning.parser import DocumentAgnosticLearningParser
from amba_ai.learning.schemas import (
    LearningDocument,
    SourceCitation,
    ValidationReport,
)
from amba_ai.learning.source_resolver import resolve_source_name
from amba_ai.learning.validator import LearningDocumentValidator
from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from amba_ai.ui.common.components import (
    AccordionCard,
    ConceptExplorer,
    DocumentOutlinePanel,
    EmptyState,
    LearningFigureView,
    LearningHeader,
    LearningRichText,
    LearningSearchBar,
    LearningTableView,
    MasteryBanner,
    MasterySnapshot,
    ReadingCanvas,
    TechnicalBlockView,
    clean_learning_text,
    repolish,
)
from amba_ai.ui.common.qss_utils import apply_local_qss
from amba_ai.ui.common.theme_loader import apply_learning_theme
from amba_ai.ui.common.ui_icons_utils import icon
from .data_classes import (
    LessonSectionModel,
    ParsedLessonBundle,
    SummarizerRequest,
    SummaryMode,
    SummaryViewModel,
)
from .summarizer_manager import SummarizerManager

SCHEMA_VERSION = "ambaai.summary-workspace.v14.0.0"


def _sanitize_string(value: Any, fallback: str = "") -> str:
    if callable(value):
        try:
            value = value()
        except Exception:
            return fallback

    text = str(value or "").strip()
    if not text:
        return fallback

    if "0x" in text and any(token in text for token in ("method", "object at", "built-in", "function")):
        return fallback

    return text


def _clean_display_title(value: Any) -> str:
    safe = _sanitize_string(value, "Learning Summary")
    title = clean_learning_text(safe)
    title = re.sub(r"(?i)^\s*(?:detected\s+topic|topic|lesson|document)\s*:\s*", "", title)
    title = re.sub(r"\[Page\s*\d+\]\s*", "", title, flags=re.IGNORECASE)
    title = title.replace("_", " ")
    title = re.sub(r"\s+", " ", title).strip()

    if not title:
        return "Learning Summary"

    words = title.split()
    words[0] = words[0].capitalize()
    return " ".join(words)


def _safe_source_name(metadata: dict[str, Any], title: str = "") -> str:
    meta = dict(metadata or {})
    sanitized_meta = {k: _sanitize_string(v) for k, v in meta.items()}
    resolved = resolve_source_name(sanitized_meta, title, fallback="Grounded Material")
    return _sanitize_string(resolved, "Grounded Material")


def _clear_layout(layout: Any) -> None:
    if layout is None:
        return
    while layout.count() > 0:
        item = layout.takeAt(0)
        if item is None:
            continue
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        sub_layout = item.layout()
        if sub_layout is not None:
            _clear_layout(sub_layout)


def _highlight_code_syntax(code_str: str, language: str = "bash") -> str:
    escaped = html.escape(code_str)

    if language.lower() in ("bash", "sh", "shell", "zsh"):
        keywords = r"\b(curl|jq|cat|grep|sed|awk|diff|find|echo|sudo|chmod|chown|mkdir|rm|cp|mv|export|source)\b"
        flags = r"(\s|^)(-[A-Za-z0-9]+|--[A-Za-z0-9\-]+)"
        strings = r"(&quot;.*?&quot;|&#x27;.*?&#x27;|'.*?'|\".*?\")"
        operators = r"(\|{1,2}|&amp;{1,2}|&gt;|&lt;|\$\(.*?\))"

        def _sub_kw(m: re.Match) -> str:
            return f'<span style="color:#38BDF8; font-weight:700;">{m.group(1)}</span>'

        def _sub_flag(m: re.Match) -> str:
            return f'{m.group(1)}<span style="color:#F59E0B;">{m.group(2)}</span>'

        def _sub_str(m: re.Match) -> str:
            return f'<span style="color:#34D399;">{m.group(1)}</span>'

        def _sub_op(m: re.Match) -> str:
            return f'<span style="color:#F472B6; font-weight:700;">{m.group(1)}</span>'

        highlighted = re.sub(strings, _sub_str, escaped)
        highlighted = re.sub(keywords, _sub_kw, highlighted)
        highlighted = re.sub(flags, _sub_flag, highlighted)
        highlighted = re.sub(operators, _sub_op, highlighted)
        return highlighted

    if language.lower() in ("json",):
        keys = r'(&quot;[\w\-]+&quot;)\s*:'
        values = r':\s*(&quot;.*?&quot;)'
        numbers = r'\b(\d+(\.\d+)?)\b'

        highlighted = re.sub(keys, r'<span style="color:#38BDF8; font-weight:700;">\1</span>:', escaped)
        highlighted = re.sub(values, r': <span style="color:#34D399;">\1</span>', highlighted)
        highlighted = re.sub(numbers, r'<span style="color:#F59E0B;">\1</span>', highlighted)
        return highlighted

    return escaped


class InteractiveTerminalBlock(QFrame):
    codeCopied = Signal(str)

    def __init__(self, code: str, language: str = "bash", title: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.code = code.strip()
        self.language = language or "bash"
        self.title = title or f"{self.language.upper()} Snippet"
        self.setObjectName("interactiveTerminalBlock")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("terminalHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 6, 12, 6)
        h_layout.setSpacing(8)

        dots_box = QHBoxLayout()
        dots_box.setSpacing(5)
        for c in ("#EF4444", "#F59E0B", "#10B981"):
            dot = QFrame()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background-color: {c}; border-radius: 5px;")
            dots_box.addWidget(dot)

        h_layout.addLayout(dots_box)

        title_lbl = QLabel(self.title)
        title_lbl.setObjectName("terminalTitle")
        h_layout.addWidget(title_lbl)
        h_layout.addStretch(1)

        lang_badge = QLabel(self.language.upper())
        lang_badge.setObjectName("terminalLangBadge")
        h_layout.addWidget(lang_badge)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("terminalCopyBtn")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy_code)
        h_layout.addWidget(self.copy_btn)

        layout.addWidget(header)

        self.code_browser = QTextBrowser()
        self.code_browser.setObjectName("terminalCodeViewer")
        self.code_browser.setOpenExternalLinks(False)
        self.code_browser.setReadOnly(True)
        self.code_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.code_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        highlighted_html = _highlight_code_syntax(self.code, self.language)
        lines = highlighted_html.split("\n")
        table_rows = []
        for i, line in enumerate(lines, 1):
            table_rows.append(
                f'<tr>'
                f'<td style="color:#475569; user-select:none; text-align:right; padding-right:12px; font-family:\'JetBrains Mono\',\'Cascadia Code\',Consolas,monospace; font-size:12px;">{i}</td>'
                f'<td style="font-family:\'JetBrains Mono\',\'Cascadia Code\',Consolas,monospace; font-size:12px; white-space:pre-wrap; word-break:break-all;">{line}</td>'
                f'</tr>'
            )

        html_content = f"""
        <html>
        <head><style>body {{ margin:0; padding:10px; background-color:#090D16; color:#E2E8F0; }}</style></head>
        <body>
        <table cellpadding="1" cellspacing="0" style="width:100%; border:none;">
        {''.join(table_rows)}
        </table>
        </body>
        </html>
        """
        self.code_browser.setHtml(html_content)

        line_count = len(lines)
        calculated_height = min(max(line_count * 20 + 26, 68), 320)
        self.code_browser.setFixedHeight(calculated_height)

        layout.addWidget(self.code_browser)

    def _copy_code(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self.code)
        self.copy_btn.setText("Copied!")
        self.copy_btn.setStyleSheet("color: #34D399; font-weight: bold;")
        self.codeCopied.emit(self.code)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1800, self._restore_copy_btn)

    def _restore_copy_btn(self) -> None:
        self.copy_btn.setText("Copy")
        self.copy_btn.setStyleSheet("")


class InteractiveLessonCard(QFrame):
    tutorSnippetRequested = Signal(str)
    notesSnippetRequested = Signal(str)
    cardCompleted = Signal(str, bool)

    def __init__(self, section: LessonSectionModel, index: int = 1, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.section = section
        self.index = index
        self.is_expanded = True
        self.setObjectName("interactiveLessonCard")
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        header_frame = QFrame()
        header_frame.setObjectName("lessonCardHeader")
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(10)

        self.toggle_btn = QToolButton()
        self.toggle_btn.setObjectName("lessonCollapseBtn")
        self.toggle_btn.setText("▼")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle_expand)
        h_layout.addWidget(self.toggle_btn)

        num_badge = QLabel(f"{self.index:02d}")
        num_badge.setObjectName("lessonIndexBadge")
        h_layout.addWidget(num_badge)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        self.title_label = QLabel(self.section.title)
        self.title_label.setObjectName("lessonTitleText")
        self.title_label.setWordWrap(True)
        title_box.addWidget(self.title_label)

        if self.section.tags:
            tag_row = QHBoxLayout()
            tag_row.setSpacing(6)
            for tag in self.section.tags:
                badge = QLabel(f"#{tag}")
                badge.setObjectName("lessonTagBadge")
                tag_row.addWidget(badge)
            tag_row.addStretch(1)
            title_box.addLayout(tag_row)

        h_layout.addLayout(title_box, 1)

        self.done_check = QCheckBox("Mastered")
        self.done_check.setObjectName("lessonMasteredCheck")
        self.done_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.done_check.toggled.connect(self._on_mastered_toggled)
        h_layout.addWidget(self.done_check)

        self.actions_menu_btn = QToolButton()
        self.actions_menu_btn.setObjectName("lessonActionsBtn")
        self.actions_menu_btn.setText("•••")
        self.actions_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._setup_action_menu()
        h_layout.addWidget(self.actions_menu_btn)

        main_layout.addWidget(header_frame)

        self.body_container = QWidget()
        self.body_container.setObjectName("lessonBodyContainer")
        self.body_layout = QVBoxLayout(self.body_container)
        self.body_layout.setContentsMargins(0, 4, 0, 0)
        self.body_layout.setSpacing(10)

        if self.section.summary_text:
            exp_label = QLabel(self.section.summary_text)
            exp_label.setObjectName("lessonExplanationText")
            exp_label.setWordWrap(True)
            exp_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.body_layout.addWidget(exp_label)

        if self.section.key_points:
            takeaway_box = QFrame()
            takeaway_box.setObjectName("lessonTakeawayBox")
            t_layout = QVBoxLayout(takeaway_box)
            t_layout.setContentsMargins(12, 8, 12, 8)
            t_layout.setSpacing(4)
            for point in self.section.key_points:
                row = QHBoxLayout()
                bullet = QLabel("✦")
                bullet.setObjectName("takeawayBullet")
                txt = QLabel(point)
                txt.setObjectName("takeawayPoint")
                txt.setWordWrap(True)
                txt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                row.addWidget(bullet, 0, Qt.AlignmentFlag.AlignTop)
                row.addWidget(txt, 1)
                t_layout.addLayout(row)
            self.body_layout.addWidget(takeaway_box)

        for block in self.section.code_blocks:
            tb = InteractiveTerminalBlock(
                code=block.get("code", ""),
                language=block.get("language", "bash"),
                title=block.get("title", ""),
            )
            self.body_layout.addWidget(tb)

        if self.section.bottom_line:
            bl_box = QFrame()
            bl_box.setObjectName("bottomLineCard")
            bl_layout = QHBoxLayout(bl_box)
            bl_layout.setContentsMargins(10, 8, 10, 8)
            bl_icon = QLabel("💡")
            bl_text = QLabel(f"<b>Takeaway:</b> {self.section.bottom_line}")
            bl_text.setWordWrap(True)
            bl_layout.addWidget(bl_icon, 0, Qt.AlignmentFlag.AlignTop)
            bl_layout.addWidget(bl_text, 1)
            self.body_layout.addWidget(bl_box)

        main_layout.addWidget(self.body_container)

    def _setup_action_menu(self) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("Copy Lesson Content")
        copy_action.triggered.connect(self._copy_all_text)

        ask_tutor = menu.addAction("Ask AI Tutor About This")
        ask_tutor.triggered.connect(lambda: self.tutorSnippetRequested.emit(self._full_text_export()))

        send_notes = menu.addAction("Send to Structured Notes")
        send_notes.triggered.connect(lambda: self.notesSnippetRequested.emit(self._full_text_export()))

        self.actions_menu_btn.setMenu(menu)

    def _full_text_export(self) -> str:
        parts = [f"### {self.section.title}"]
        if self.section.summary_text:
            parts.append(self.section.summary_text)
        if self.section.key_points:
            parts.extend([f"- {p}" for p in self.section.key_points])
        for b in self.section.code_blocks:
            parts.append(f"```{b.get('language','bash')}\n{b.get('code','')}\n```")
        if self.section.bottom_line:
            parts.append(f"Key insight: {self.section.bottom_line}")
        return "\n\n".join(parts)

    def _copy_all_text(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self._full_text_export())

    def toggle_expand(self) -> None:
        self.set_expanded(not self.is_expanded)

    def set_expanded(self, expanded: bool) -> None:
        self.is_expanded = expanded
        self.body_container.setVisible(expanded)
        self.toggle_btn.setText("▼" if expanded else "▶")

    def _on_mastered_toggled(self, checked: bool) -> None:
        self.setProperty("completed", checked)
        repolish(self)
        self.cardCompleted.emit(self.section.title, checked)


class SummaryViewAdapter:
    def __init__(self, widget: SummarizerWidget) -> None:
        self._widget = widget
        self._placeholder = ""

    def toPlainText(self) -> str:
        summary = self._widget.current_summary
        return str(summary.markdown or "") if summary else ""

    def setPlaceholderText(self, text: str) -> None:
        self._placeholder = str(text or "")

    def placeholderText(self) -> str:
        return self._placeholder

    def isReadOnly(self) -> bool:
        return True

    def setReadOnly(self, read_only: bool) -> None:
        if not read_only:
            raise RuntimeError("The production Summary workspace is read-only.")

    def clear(self) -> None:
        self._widget._reset_workspace()

    def setFocus(self) -> None:
        self._widget.reader.setFocus()


class KeyConceptsViewAdapter:
    def __init__(self, widget: SummarizerWidget) -> None:
        self._widget = widget
        self._placeholder = ""

    def toPlainText(self) -> str:
        concepts = self._widget.concepts_explorer.concepts()
        if not concepts:
            return ""
        return "\n".join(
            f"- {getattr(c, 'name', '')}: {getattr(c, 'definition', '')}"
            for c in concepts
        )

    def setPlaceholderText(self, text: str) -> None:
        self._placeholder = str(text or "")

    def placeholderText(self) -> str:
        return self._placeholder

    def clear(self) -> None:
        self._widget.concepts_explorer.clear()

    def setFocus(self) -> None:
        self._widget.concepts_explorer.setFocus()


class SummarizerWidget(QWidget):
    summaryGenerated = Signal(int)
    summaryExported = Signal(str)
    statusMessage = Signal(str, str)
    operationStarted = Signal(str)
    operationFinished = Signal(str)

    navigateToNotes = Signal(int)
    navigateToNotesConcept = Signal(int, str)
    navigateToStudy = Signal(int)
    navigateToStudyConcept = Signal(int, str)
    navigateToQuiz = Signal(int)
    navigateToTutor = Signal(int)
    navigateToTutorConcept = Signal(int, str)

    def __init__(
        self,
        settings: QSettings,
        job_service: JobService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.jobs = job_service
        self.summarizer_manager = SummarizerManager(job_service, self)

        self.document_id: int | None = None
        self.current_summary: SummaryViewModel | None = None
        self.current_bundle: Any | None = None
        self.current_learning_doc: LearningDocument | None = None
        self.parsed_lesson: ParsedLessonBundle | None = None

        self.summary_view = SummaryViewAdapter(self)
        self.key_concepts_view = KeyConceptsViewAdapter(self)

        self._lesson_cards: list[InteractiveLessonCard] = []
        self._cards: list[AccordionCard] = []
        self._summary_targets: dict[str, QWidget] = {}
        self._objective_checks: list[QCheckBox] = []
        self._matches: list[QWidget] = []
        self._match_index = -1
        self._is_operation_active = False
        self._focus_mode_active = False
        self._equity_profile: dict[str, Any] = {}
        self._zoom_level = 100

        self.setObjectName("AmbaSummarizerWidgetUI")

        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()
        self._load_styles()
        self._restore_settings()
        self._reset_workspace()
        self._update_ui_for_operation_status()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        self.exit_focus_btn = QPushButton("✕  Exit Focus Mode", self)
        self.exit_focus_btn.setObjectName("exitFocusFloatingBtn")
        self.exit_focus_btn.setVisible(False)
        self.exit_focus_btn.setMinimumWidth(180)
        self.exit_focus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.exit_focus_btn.clicked.connect(self._exit_focus_mode)

        self.compact_header_box = QFrame()
        self.compact_header_box.setObjectName("compactHeaderCard")
        c_layout = QVBoxLayout(self.compact_header_box)
        c_layout.setContentsMargins(14, 12, 14, 12)
        c_layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self.header = LearningHeader()
        self.mastery_banner = MasteryBanner()

        top_row.addWidget(self.header, 1)
        top_row.addWidget(self.mastery_banner, 0)
        c_layout.addLayout(top_row)

        tool_ribbon = QHBoxLayout()
        tool_ribbon.setSpacing(8)

        mode_lbl = QLabel("Mode:")
        mode_lbl.setObjectName("controlRibbonLabel")
        self.summary_mode_combo = QComboBox()
        self.summary_mode_combo.setObjectName("summaryModeCombo")
        self.summary_mode_combo.addItems(SummaryMode.values())

        lang_lbl = QLabel("Language:")
        lang_lbl.setObjectName("controlRibbonLabel")
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("summaryLanguageCombo")
        self.language_combo.addItems(["English", "Amharic", "Afaan Oromo", "Tigrinya", "Somali"])

        self.simple_language_check = QCheckBox(self.tr("Simple Language"))
        self.simple_language_check.setObjectName("summarySimpleLanguageCheck")
        self.simple_language_check.setChecked(True)

        self.force_check = QCheckBox(self.tr("Force Regenerate"))
        self.force_check.setObjectName("summaryForceCheck")

        self.generate_btn = QPushButton(icon("summarizer"), self.tr("Synthesize Summary"))
        self.generate_btn.setObjectName("generateSummaryButton")
        self.generate_btn.setProperty("priority", "primary")
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.export_btn = QPushButton(icon("export"), self.tr("Export Markdown"))
        self.export_btn.setObjectName("exportSummaryButton")
        self.export_btn.setProperty("variant", "secondary")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        tool_ribbon.addWidget(mode_lbl)
        tool_ribbon.addWidget(self.summary_mode_combo)
        tool_ribbon.addWidget(lang_lbl)
        tool_ribbon.addWidget(self.language_combo)
        tool_ribbon.addWidget(self.simple_language_check)
        tool_ribbon.addWidget(self.force_check)
        tool_ribbon.addWidget(self.generate_btn)
        tool_ribbon.addWidget(self.export_btn)
        tool_ribbon.addStretch(1)

        c_layout.addLayout(tool_ribbon)

        action_ribbon = QHBoxLayout()
        action_ribbon.setSpacing(8)

        self.search_bar = LearningSearchBar(placeholder="Search lessons, syntax, concepts, notes...")
        self.expand_btn = QPushButton("Expand All")
        self.collapse_btn = QPushButton("Collapse All")
        self.focus_btn = QPushButton("Focus Mode")
        self.focus_btn.setCheckable(True)

        for btn in (self.expand_btn, self.collapse_btn, self.focus_btn):
            btn.setObjectName("learningCompactAction")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        zoom_box = QHBoxLayout()
        zoom_box.setSpacing(4)
        zoom_lbl = QLabel("Text Size:")
        zoom_lbl.setObjectName("controlRibbonLabel")
        self.zoom_out_btn = QPushButton("A-")
        self.zoom_out_btn.setObjectName("learningCompactAction")
        self.zoom_out_btn.setFixedWidth(32)
        self.zoom_out_btn.clicked.connect(lambda: self._adjust_zoom(-10))
        self.zoom_in_btn = QPushButton("A+")
        self.zoom_in_btn.setObjectName("learningCompactAction")
        self.zoom_in_btn.setFixedWidth(32)
        self.zoom_in_btn.clicked.connect(lambda: self._adjust_zoom(10))
        zoom_box.addWidget(zoom_lbl)
        zoom_box.addWidget(self.zoom_out_btn)
        zoom_box.addWidget(self.zoom_in_btn)

        action_ribbon.addWidget(self.search_bar, 1)
        action_ribbon.addWidget(self.expand_btn)
        action_ribbon.addWidget(self.collapse_btn)
        action_ribbon.addWidget(self.focus_btn)
        action_ribbon.addLayout(zoom_box)

        c_layout.addLayout(action_ribbon)
        root_layout.addWidget(self.compact_header_box)

        self.master_workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.master_workspace_splitter.setObjectName("masterWorkspaceSplitter")

        self.outline_panel = DocumentOutlinePanel()

        self.content_tabs = QTabWidget()
        self.content_tabs.setObjectName("contentTabs")
        self.content_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.reader = ReadingCanvas(maximum_width=1120)
        self.content_tabs.addTab(self.reader, icon("summary"), self.tr("Executive & Structured Lessons"))

        self.concepts_explorer = ConceptExplorer()
        self.content_tabs.addTab(self.concepts_explorer, icon("knowledge"), self.tr("Key Concepts"))

        self.visuals_canvas = ReadingCanvas(maximum_width=1080)
        self.content_tabs.addTab(self.visuals_canvas, icon("tables"), self.tr("Tables & Figures"))

        self._setup_log_tab()

        self.master_workspace_splitter.addWidget(self.outline_panel)
        self.master_workspace_splitter.addWidget(self.content_tabs)
        self.master_workspace_splitter.setSizes([260, 780])

        root_layout.addWidget(self.master_workspace_splitter, 1)
        self._setup_bottom_bar(root_layout)

    def _setup_log_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.summarizer_status_label = QLabel(self.tr("Summarizer Status: Idle"))
        self.summarizer_status_label.setObjectName("summarizerStatusLabel")
        self.summarizer_status_label.setWordWrap(True)
        self.summarizer_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.operation_log = QPlainTextEdit()
        self.operation_log.setObjectName("summarizerOperationLog")
        self.operation_log.setReadOnly(True)
        self.operation_log.setFont(QFont("Consolas", 9))

        layout.addWidget(self.summarizer_status_label)
        layout.addWidget(self.operation_log, 1)

        self.content_tabs.addTab(tab, icon("info"), self.tr("Activity Log"))

    def _setup_bottom_bar(self, root_layout: QVBoxLayout) -> None:
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(6, 4, 6, 4)

        self.overall_status_label = QLabel(self.tr("Ready. Select a document to inspect or generate structured notes."))
        self.overall_status_label.setObjectName("summarizerFooterStatus")
        bottom_bar.addWidget(self.overall_status_label, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(240)
        self.progress_bar.setFixedHeight(12)
        bottom_bar.addWidget(self.progress_bar)

        root_layout.addLayout(bottom_bar)

    def _setup_shortcuts(self) -> None:
        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.esc_shortcut.activated.connect(self._exit_focus_mode)

        self.find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.find_shortcut.activated.connect(lambda: self.search_bar.setFocus())

    def _connect_signals(self) -> None:
        self.generate_btn.clicked.connect(self.generate_summary)
        self.export_btn.clicked.connect(self.export_summary)

        self.expand_btn.clicked.connect(lambda: self._set_all_cards_expanded(True))
        self.collapse_btn.clicked.connect(lambda: self._set_all_cards_expanded(False))
        self.focus_btn.toggled.connect(self._toggle_focus_mode)

        self.search_bar.queryChanged.connect(self._on_search_query_changed)
        self.search_bar.nextRequested.connect(lambda: self._step_search_match(1))
        self.search_bar.previousRequested.connect(lambda: self._step_search_match(-1))

        self.outline_panel.itemSelected.connect(self._on_outline_item_selected)
        self.outline_panel.toggleRequested.connect(self._toggle_outline_sidebar)

        self.concepts_explorer.notesRequested.connect(
            lambda cid: self.navigateToNotesConcept.emit(self.document_id or 0, cid)
        )
        self.concepts_explorer.studyRequested.connect(
            lambda cid: self.navigateToStudyConcept.emit(self.document_id or 0, cid)
        )
        self.concepts_explorer.tutorRequested.connect(
            lambda cid: self.navigateToTutorConcept.emit(self.document_id or 0, cid)
        )

        self.summarizer_manager.summaryStarted.connect(self._on_manager_summary_started)
        self.summarizer_manager.summaryFinished.connect(self._on_manager_summary_finished)
        self.summarizer_manager.summaryFailed.connect(self._on_manager_summary_failed)
        self.summarizer_manager.summaryGenerated.connect(self.summaryGenerated.emit)
        self.summarizer_manager.statusMessage.connect(self._append_status_message)
        self.summarizer_manager.operationStarted.connect(self.operationStarted.emit)
        self.summarizer_manager.operationFinished.connect(self.operationFinished.emit)

    def _adjust_zoom(self, delta: int) -> None:
        self._zoom_level = max(70, min(160, self._zoom_level + delta))
        base_size = int(10 * (self._zoom_level / 100))
        font = self.font()
        font.setPointSize(base_size)
        self.setFont(font)

    def _toggle_outline_sidebar(self) -> None:
        self.outline_panel.setVisible(not self.outline_panel.isVisible())

    def _on_outline_item_selected(self, row: int, item_type: str) -> None:
        if row < 0 or row >= len(self.outline_panel._items_meta):
            return
        _, target_name = self.outline_panel._items_meta[row]

        if item_type == "summary":
            self.content_tabs.setCurrentIndex(0)
            target_widget = self._summary_targets.get(target_name)
            if target_widget:
                if isinstance(target_widget, InteractiveLessonCard):
                    target_widget.set_expanded(True)
                elif isinstance(target_widget, AccordionCard):
                    if hasattr(target_widget, "setExpanded"):
                        target_widget.setExpanded(True)
                self._ensure_widget_visible(target_widget)
                self._highlight_target_widget(target_widget)

        elif item_type == "concept":
            self.content_tabs.setCurrentIndex(1)
            self.concepts_explorer.search_input.setText(target_name)

    def _ensure_widget_visible(self, widget: QWidget) -> None:
        if hasattr(self.reader, "ensureWidgetVisible"):
            self.reader.ensureWidgetVisible(widget, 30, 30)
            return
        scroll_area = getattr(self.reader, "scroll_area", None)
        if scroll_area is not None and hasattr(scroll_area, "ensureWidgetVisible"):
            scroll_area.ensureWidgetVisible(widget, 30, 30)

    def _highlight_target_widget(self, active_widget: QWidget) -> None:
        for card in self._lesson_cards:
            card.setProperty("activeTarget", card is active_widget)
            repolish(card)
        for card in self._cards:
            card.setProperty("activeTarget", card is active_widget)
            repolish(card)

    def _load_styles(self) -> None:
        try:
            apply_learning_theme(self)
        except Exception as exc:
            logger.warning(f"Unable to apply learning theme: {exc}")

        local_qss = Path(__file__).parent / "summarizer.qss"
        if local_qss.exists():
            apply_local_qss(self, local_qss)

    def _restore_settings(self) -> None:
        mode = self.settings.value("Summarizer/mode", SummaryMode.DETAILED.value)
        language = self.settings.value("Summarizer/language", "English")
        simple = str(self.settings.value("Summarizer/simple_language", "true")).lower() in {"1", "true", "yes", "on"}

        mode_index = self.summary_mode_combo.findText(str(mode))
        language_index = self.language_combo.findText(str(language))
        if mode_index >= 0:
            self.summary_mode_combo.setCurrentIndex(mode_index)
        if language_index >= 0:
            self.language_combo.setCurrentIndex(language_index)
        self.simple_language_check.setChecked(simple)

    def _save_settings(self) -> None:
        self.settings.setValue("Summarizer/mode", self.summary_mode_combo.currentText())
        self.settings.setValue("Summarizer/language", self.language_combo.currentText())
        self.settings.setValue("Summarizer/simple_language", self.simple_language_check.isChecked())
        self.settings.sync()

    def _reset_workspace(self) -> None:
        self.current_summary = None
        self.current_bundle = None
        self.current_learning_doc = None
        self.parsed_lesson = None
        self._lesson_cards.clear()
        self._cards.clear()
        self._summary_targets.clear()
        self._objective_checks.clear()
        self._matches.clear()
        self._match_index = -1

        _clear_layout(getattr(self.reader, "content_layout", None))
        _clear_layout(getattr(self.visuals_canvas, "content_layout", None))
        self.concepts_explorer.clear()
        self.outline_panel.setOutlineTree([], [])

        self.reader.content_layout.addWidget(
            EmptyState(
                "No lesson loaded",
                "Select a lesson from your library and click 'Synthesize Summary' to create structured cards.",
            )
        )
        self.visuals_canvas.content_layout.addWidget(
            EmptyState(
                "No visual diagrams",
                "Tables, command matrices, and structural architecture diagrams will populate automatically.",
            )
        )

        self.header.setContent(
            title="Lesson Synthesis",
            citation=None,
            metadata="Select a document or book to start interactive mastery.",
            status="Ready",
        )
        self._update_mastery_snapshot()

    @Slot(int)
    def set_document(self, document_id: int) -> None:
        self.document_id = int(document_id)
        self._reset_workspace()
        self.overall_status_label.setText(self.tr(f"Document #{document_id} active. Ready to synthesize."))
        self.summarizer_status_label.setText(self.tr(f"Document #{document_id} loaded."))
        self._update_ui_for_operation_status()

    @Slot(dict)
    def apply_equity_profile(self, profile: dict[str, Any]) -> None:
        self._equity_profile = dict(profile or {})
        language = str(self._equity_profile.get("target_language") or "")
        simple = bool(self._equity_profile.get("simple_language", self.simple_language_check.isChecked()))

        if language:
            index = self.language_combo.findText(language)
            if index >= 0:
                self.language_combo.setCurrentIndex(index)

        self.simple_language_check.setChecked(simple)
        self.summarizer_manager.apply_equity_profile(self._equity_profile)
        self._update_ui_for_operation_status()

    @Slot()
    def generate_summary(self) -> None:
        if self.document_id is None:
            QMessageBox.warning(
                self,
                self.tr("No Document Selected"),
                self.tr("Select or ingest a document first before synthesizing."),
            )
            return

        self._save_settings()
        mode = SummaryMode.coerce(self.summary_mode_combo.currentText())

        self._is_operation_active = True
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.summarizer_status_label.setText(self.tr(f"Synthesizing structured lesson: {mode.value}"))
        self.overall_status_label.setText(self.tr("Synthesizing learning curriculum..."))
        self._update_ui_for_operation_status()

        request = SummarizerRequest(
            document_id=self.document_id,
            mode=mode,
            force=self.force_check.isChecked(),
            target_language=self.language_combo.currentText(),
            simple_language=self.simple_language_check.isChecked(),
            teacher_review_required=bool(self._equity_profile.get("teacher_review_required", True)),
            max_context_tokens=int(self._equity_profile.get("max_context_tokens", 2048)),
            preferred_model=str(
                self._equity_profile.get("preferred_model", "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M")
            ),
        )

        self.summarizer_manager.generate_summary(request.to_dict())

    def export_summary(self) -> None:
        if not self.current_summary or not self.current_summary.markdown:
            QMessageBox.information(
                self, self.tr("No Summary"), self.tr("Synthesize a summary first before exporting.")
            )
            return

        filename = f"document_{self.document_id or 'lesson'}_mastery.md"

        try:
            result = export_markdown(filename, self.current_summary.markdown)
            self.summaryExported.emit(str(result.path))
            self._append_status_message(f"Exported markdown summary to {result.path}", "INFO")
            QMessageBox.information(
                self,
                self.tr("Export Successful"),
                self.tr(f"Saved structured Markdown summary to:\n{result.path}"),
            )
        except ExportError as exc:
            logger.exception("Summary export failed")
            QMessageBox.critical(self, self.tr("Export Failed"), str(exc))
            self._append_status_message(str(exc), "ERROR")

    @Slot(dict)
    def _on_manager_summary_finished(self, payload: dict[str, Any]) -> None:
        self._is_operation_active = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)

        summary = SummaryViewModel(
            document_id=int(payload.get("document_id") or self.document_id or 0),
            markdown=str(payload.get("markdown") or ""),
            model_name=str(payload.get("model_name") or "unknown"),
            mode=str(payload.get("mode") or self.summary_mode_combo.currentText()),
            cached=bool(payload.get("cached", False)),
            fallback=bool(payload.get("fallback", False)),
            metadata=dict(payload.get("metadata") or {}),
        )

        self.current_summary = summary
        doc_id = summary.document_id or self.document_id or 0
        metadata = dict(summary.metadata or {})
        metadata.setdefault("document_id", doc_id)
        metadata["source_name"] = _safe_source_name(metadata, metadata.get("title", ""))

        self.parsed_lesson = ParsedLessonBundle.from_raw(summary.markdown, metadata)

        try:
            self.current_bundle = MultimodalLearningParser().parse(
                document_id=doc_id,
                markdown=summary.markdown,
                metadata=metadata,
                assets=(),
            )
            self.current_learning_doc = self.current_bundle.document
        except Exception:
            self.current_bundle = None
            self.current_learning_doc = DocumentAgnosticLearningParser().parse(
                document_id=doc_id,
                markdown=summary.markdown,
                metadata=metadata,
            )

        report = LearningDocumentValidator().validate(self.current_learning_doc)
        self._render_workspace(report)

        label = (
            f"Lesson Ready · Model: {summary.model_name} · "
            f"Mode: {summary.mode} · Cache: {'Hit' if summary.cached else 'Synthesized'}"
        )
        self.summarizer_status_label.setText(label)
        self.overall_status_label.setText(self.tr("Curriculum lessons rendered."))
        self.content_tabs.setCurrentIndex(0)

        self._append_status_message(label, "INFO")
        self._update_ui_for_operation_status()

    def _render_workspace(self, report: Optional[ValidationReport] = None) -> None:
        document = self.current_learning_doc
        lesson = self.parsed_lesson
        if lesson is None:
            return

        _clear_layout(getattr(self.reader, "content_layout", None))
        _clear_layout(getattr(self.visuals_canvas, "content_layout", None))
        self._lesson_cards.clear()
        self._cards.clear()
        self._summary_targets.clear()
        self._objective_checks.clear()

        title = _clean_display_title(lesson.title or (document.title if document else "Learning Summary"))
        raw_source = _sanitize_string(
            lesson.source_badge or (document.source_name if document else "Grounded Material")
        )
        citation = SourceCitation(raw_source)
        status_text = "Validated Grounded" if report is not None and report.valid else "Source Grounded"

        reading_minutes = max(1, round(len(lesson.raw_text.split()) / 180))

        self.header.setContent(
            title=title,
            citation=citation,
            metadata=f"SECURITY & CLI · {reading_minutes}-min study · {len(lesson.sections)} Interactive Steps · {status_text}",
            status=status_text,
        )

        overview_card = QFrame()
        overview_card.setObjectName("executiveOverviewCard")
        ov_layout = QVBoxLayout(overview_card)
        ov_layout.setContentsMargins(16, 14, 16, 14)
        ov_layout.setSpacing(10)

        ov_badge_row = QHBoxLayout()
        ov_badge_row.setSpacing(8)

        ov_tag = QLabel("EXECUTIVE SUMMARY")
        ov_tag.setObjectName("executiveTagPill")
        ov_badge_row.addWidget(ov_tag)

        if lesson.source_badge:
            page_pill = QLabel(lesson.source_badge)
            page_pill.setObjectName("sourcePagePill")
            ov_badge_row.addWidget(page_pill)

        ov_badge_row.addStretch(1)
        ov_layout.addLayout(ov_badge_row)

        ov_text = QLabel(lesson.executive_summary)
        ov_text.setObjectName("executiveOverviewText")
        ov_text.setWordWrap(True)
        ov_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        ov_layout.addWidget(ov_text)

        self.reader.content_layout.addWidget(overview_card)
        self._summary_targets["Executive Overview"] = overview_card

        outline_titles: list[str] = ["Executive Overview"]

        steps_header = QFrame()
        steps_header.setObjectName("lessonStepsSectionHeader")
        sh_layout = QHBoxLayout(steps_header)
        sh_layout.setContentsMargins(4, 12, 4, 4)
        sh_label = QLabel(f"CURRICULUM LESSONS ({len(lesson.sections)} MODULES)")
        sh_label.setObjectName("sectionCategoryHeading")
        sh_layout.addWidget(sh_label)
        sh_layout.addStretch(1)
        self.reader.content_layout.addWidget(steps_header)

        for i, section in enumerate(lesson.sections, 1):
            card = InteractiveLessonCard(section=section, index=i)
            card.tutorSnippetRequested.connect(self._send_to_tutor)
            card.notesSnippetRequested.connect(self._send_to_notes)
            card.cardCompleted.connect(self._on_card_completed)
            self.reader.content_layout.addWidget(card)
            self._lesson_cards.append(card)
            self._summary_targets[section.title] = card
            outline_titles.append(section.title)

        if lesson.concepts:
            self.concepts_explorer.setConcepts(lesson.concepts)
            concept_names = [getattr(c, "name", "") for c in self.concepts_explorer.concepts() if getattr(c, "name", "")]
        elif document and document.concepts:
            self.concepts_explorer.setConcepts(document.concepts)
            concept_names = [getattr(c, "name", "") for c in self.concepts_explorer.concepts() if getattr(c, "name", "")]
        else:
            concept_names = []

        self.outline_panel.setOutlineTree(outline_titles, concept_names)

        navigation = QFrame()
        navigation.setObjectName("navigationToolbar")
        nav_layout = QHBoxLayout(navigation)
        nav_layout.setContentsMargins(14, 12, 14, 12)
        nav_layout.setSpacing(12)

        nav_label = QLabel("Active Study Pathways:")
        nav_label.setObjectName("navigationTitleLabel")
        nav_layout.addWidget(nav_label)

        doc_id = self.document_id or 0
        actions = (
            ("notes", "Take Structured Notes", self.navigateToNotes),
            ("study", "Generate Flashcards", self.navigateToStudy),
            ("quiz", "Take Practice Quiz", self.navigateToQuiz),
            ("tutor", "Deep Dive with AI Tutor", self.navigateToTutor),
        )

        for icon_name, label_text, sig in actions:
            btn = QPushButton(icon(icon_name), label_text)
            btn.setObjectName("navPathwayButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, s=sig: s.emit(doc_id))
            nav_layout.addWidget(btn)

        nav_layout.addStretch(1)
        self.reader.content_layout.addWidget(navigation)

        self._render_visuals_canvas(lesson)
        self._update_mastery_snapshot()

    def _render_visuals_canvas(self, lesson: ParsedLessonBundle) -> None:
        _clear_layout(getattr(self.visuals_canvas, "content_layout", None))

        all_blocks = []
        for s in lesson.sections:
            for b in s.code_blocks:
                all_blocks.append((s.title, b))

        if all_blocks:
            matrix_card = QFrame()
            matrix_card.setObjectName("terminalMatrixContainer")
            m_layout = QVBoxLayout(matrix_card)
            m_layout.setContentsMargins(14, 14, 14, 14)
            m_layout.setSpacing(12)

            m_title = QLabel("Command Reference & Syntax Cheatsheet")
            m_title.setObjectName("matrixTitleLabel")
            m_layout.addWidget(m_title)

            for section_title, b in all_blocks:
                block_view = InteractiveTerminalBlock(
                    code=b.get("code", ""),
                    language=b.get("language", "bash"),
                    title=f"{section_title} : {b.get('title', 'Command')}",
                )
                m_layout.addWidget(block_view)

            self.visuals_canvas.content_layout.addWidget(matrix_card)

        if self.current_bundle is not None:
            tables = tuple(getattr(self.current_bundle, "tables", ()) or ())
            for table in tables:
                table_view = LearningTableView()
                table_view.setTable(table)
                self.visuals_canvas.content_layout.addWidget(table_view)

            figures = tuple(getattr(self.current_bundle, "figures", ()) or ())
            for figure in figures:
                fig_view = LearningFigureView()
                fig_view.setFigure(figure)
                self.visuals_canvas.content_layout.addWidget(fig_view)

        if not all_blocks and (self.current_bundle is None or not getattr(self.current_bundle, "tables", None)):
            self.visuals_canvas.content_layout.addWidget(
                EmptyState(
                    "No Multimodal Artifacts",
                    "This lesson contains purely theoretical content with no code matrices or schematics.",
                )
            )

    def _send_to_tutor(self, text: str) -> None:
        self.navigateToTutorConcept.emit(self.document_id or 0, text[:120])
        self.statusMessage.emit("Snippet sent to AI Tutor conversation.", "INFO")

    def _send_to_notes(self, text: str) -> None:
        self.navigateToNotesConcept.emit(self.document_id or 0, text[:120])
        self.statusMessage.emit("Snippet sent to Personal Notes.", "INFO")

    def _on_card_completed(self, title: str, completed: bool) -> None:
        self._update_mastery_snapshot()

    def _update_mastery_snapshot(self) -> None:
        done = sum(1 for card in self._lesson_cards if card.done_check.isChecked())
        total = len(self._lesson_cards)

        self.mastery_banner.setVisible(total > 0 and not self._focus_mode_active)

        snapshot = MasterySnapshot(
            objectives_done=done,
            objectives_total=total,
            notes_done=0,
            notes_total=0,
            cards_done=0,
            cards_total=0,
            quiz_accuracy=0,
        )
        self.mastery_banner.setSnapshot(snapshot)

    def _set_all_cards_expanded(self, expanded: bool) -> None:
        for card in self._lesson_cards:
            card.set_expanded(expanded)
        for card in self._cards:
            if hasattr(card, "setExpanded"):
                card.setExpanded(expanded)

    @Slot(bool)
    def _toggle_focus_mode(self, enabled: bool) -> None:
        self._focus_mode_active = bool(enabled)
        self.compact_header_box.setVisible(not enabled)
        self.content_tabs.tabBar().setVisible(not enabled)
        self.outline_panel.setVisible(not enabled)

        self.exit_focus_btn.setVisible(enabled)
        if enabled:
            self.exit_focus_btn.raise_()
            self._reposition_exit_focus_btn()

        self.mastery_banner.setVisible(not enabled and bool(self._lesson_cards))
        self.focus_btn.setText(self.tr("Exit Focus") if enabled else self.tr("Focus Mode"))

    def _reposition_exit_focus_btn(self) -> None:
        if self._focus_mode_active:
            btn_w = self.exit_focus_btn.sizeHint().width() + 30
            self.exit_focus_btn.move(max(10, self.width() - btn_w - 20), 12)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._reposition_exit_focus_btn()

    def _exit_focus_mode(self) -> None:
        if self.focus_btn.isChecked():
            self.focus_btn.setChecked(False)

    @Slot(str)
    def _on_search_query_changed(self, query: str) -> None:
        normalized = clean_learning_text(query).lower()
        self._matches.clear()
        self._match_index = -1

        if normalized:
            for card in self._lesson_cards:
                text = card.section.title.lower() + " " + card.section.summary_text.lower()
                for b in card.section.code_blocks:
                    text += " " + b.get("code", "").lower()
                for p in card.section.key_points:
                    text += " " + p.lower()
                if normalized in text:
                    self._matches.append(card)
                    card.set_expanded(True)

        if hasattr(self.search_bar, "setMatchCount"):
            self.search_bar.setMatchCount(len(self._matches), 0)

        if self._matches:
            self._step_search_match(1)

    def _step_search_match(self, direction: int) -> None:
        if not self._matches:
            return
        self._match_index = (self._match_index + direction) % len(self._matches)
        target = self._matches[self._match_index]
        self._ensure_widget_visible(target)
        self._highlight_target_widget(target)
        if hasattr(self.search_bar, "setMatchCount"):
            self.search_bar.setMatchCount(len(self._matches), self._match_index + 1)

    @Slot(str)
    def _on_manager_summary_started(self, mode: str) -> None:
        self._is_operation_active = True
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.summarizer_status_label.setText(self.tr(f"Synthesizing: {mode}"))
        self.overall_status_label.setText(self.tr("Synthesizing learning summary..."))
        self._update_ui_for_operation_status()

    @Slot(dict)
    def _on_manager_summary_failed(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        self.progress_bar.setVisible(False)
        message = str(error_context.get("error_message") or "Summary generation failed.")
        self.summarizer_status_label.setText(message)
        self.overall_status_label.setText(message)
        self._append_status_message(message, "ERROR")
        QMessageBox.critical(self, self.tr("Summary Generation Failed"), message)
        self._update_ui_for_operation_status()

    @Slot(str, str)
    def _append_status_message(self, message: str, level: str = "INFO") -> None:
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        self.operation_log.appendPlainText(f"[{timestamp}] [{level.upper()}] {message}")
        self.statusMessage.emit(message, level)

    def _update_ui_for_operation_status(self) -> None:
        inactive = not self._is_operation_active
        has_document = self.document_id is not None
        has_summary = bool(self.current_summary and self.current_summary.markdown)
        self.generate_btn.setEnabled(inactive and has_document)
        self.export_btn.setEnabled(inactive and has_summary)
        self.summary_mode_combo.setEnabled(inactive)
        self.language_combo.setEnabled(inactive)
        self.simple_language_check.setEnabled(inactive)
        self.force_check.setEnabled(inactive)

    def cleanup_before_close(self) -> None:
        self._save_settings()
        self.summarizer_manager.cleanup_before_close()
        logger.info("SummarizerWidget cleanup completed.")

    def retranslateUi(self) -> None:
        self.simple_language_check.setText(self.tr("Simple Language"))
        self.force_check.setText(self.tr("Force Regenerate"))
        self.generate_btn.setText(self.tr("Synthesize Summary"))
        self.export_btn.setText(self.tr("Export Markdown"))
        self.focus_btn.setText(self.tr("Focus Mode"))
        self.content_tabs.setTabText(0, self.tr("Executive & Structured Lessons"))
        self.content_tabs.setTabText(1, self.tr("Key Concepts"))
        self.content_tabs.setTabText(2, self.tr("Tables & Figures"))
        self.content_tabs.setTabText(3, self.tr("Activity Log"))