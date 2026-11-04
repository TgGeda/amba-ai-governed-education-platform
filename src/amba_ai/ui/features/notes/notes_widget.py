from __future__ import annotations

import html
import json
from pathlib import Path
import re
from typing import Any, Optional

from PySide6.QtCore import (
    QDateTime,
    QSettings,
    QSize,
    Qt,
    Signal,
    Slot,
    QTimer,
)
from PySide6.QtGui import (
    QFont,
    QKeySequence,
    QShortcut,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from amba_ai.core.export import export_markdown
from amba_ai.exceptions import ExportError
from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from amba_ai.ui.common.format_utils import format_markdown_notes_for_ui, safe_filename_stem
from amba_ai.ui.common.qss_utils import apply_local_qss
from amba_ai.ui.common.ui_icons_utils import icon
from .data_classes import (
    InteractiveCodeBlockModel,
    NoteStyle,
    NotesGenerationRequest,
    NotesViewModel,
    ParsedStudyNotesBundle,
    StudyNoteCardModel,
)
from .notes_manager import NotesManager


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

        highlighted = re.sub(strings, r'<span style="color:#34D399;">\1</span>', escaped)
        highlighted = re.sub(keywords, r'<span style="color:#38BDF8; font-weight:700;">\1</span>', highlighted)
        highlighted = re.sub(flags, r'\1<span style="color:#F59E0B;">\2</span>', highlighted)
        highlighted = re.sub(operators, r'<span style="color:#F472B6; font-weight:700;">\1</span>', highlighted)
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
        self.title = title or f"{self.language.upper()} Command"
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
        <head><style>body {{ margin:0; padding:10px; background-color:#070B14; color:#E2E8F0; }}</style></head>
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
        QTimer.singleShot(1800, self._restore_copy_btn)

    def _restore_copy_btn(self) -> None:
        self.copy_btn.setText("Copy")
        self.copy_btn.setStyleSheet("")


class InteractiveCornellNoteCard(QFrame):
    tutorSnippetRequested = Signal(str)
    studyCardRequested = Signal(str, str)
    masteryChanged = Signal(str, bool)
    personalNoteSaved = Signal(str, str)

    def __init__(
        self,
        card_model: StudyNoteCardModel,
        index: int = 1,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.model = card_model
        self.index = index
        self.is_expanded = True
        self.scratchpad_visible = False
        self.setObjectName("interactiveCornellCard")
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        header_frame = QFrame()
        header_frame.setObjectName("cornellHeaderFrame")
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(10)

        self.toggle_btn = QToolButton()
        self.toggle_btn.setObjectName("cornellToggleBtn")
        self.toggle_btn.setText("▼")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle_expand)
        h_layout.addWidget(self.toggle_btn)

        num_badge = QLabel(f"NOTE {self.index:02d}")
        num_badge.setObjectName("cornellIndexBadge")
        h_layout.addWidget(num_badge)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        self.title_label = QLabel(self.model.title)
        self.title_label.setObjectName("cornellTitleText")
        self.title_label.setWordWrap(True)
        title_box.addWidget(self.title_label)

        if self.model.tags:
            tag_row = QHBoxLayout()
            tag_row.setSpacing(6)
            for tag in self.model.tags:
                badge = QLabel(f"#{tag}")
                badge.setObjectName("cornellTagBadge")
                tag_row.addWidget(badge)
            tag_row.addStretch(1)
            title_box.addLayout(tag_row)

        h_layout.addLayout(title_box, 1)

        self.scratchpad_toggle_btn = QPushButton("✏️ Margin Note")
        self.scratchpad_toggle_btn.setObjectName("cornellMarginBtn")
        self.scratchpad_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scratchpad_toggle_btn.clicked.connect(self._toggle_scratchpad)
        h_layout.addWidget(self.scratchpad_toggle_btn)

        self.mastered_check = QCheckBox("Mastered")
        self.mastered_check.setObjectName("cornellMasteredCheck")
        self.mastered_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mastered_check.setChecked(self.model.is_mastered)
        self.mastered_check.toggled.connect(self._on_mastery_toggled)
        h_layout.addWidget(self.mastered_check)

        self.actions_btn = QToolButton()
        self.actions_btn.setObjectName("cornellActionsBtn")
        self.actions_btn.setText("•••")
        self.actions_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._setup_action_menu()
        h_layout.addWidget(self.actions_btn)

        main_layout.addWidget(header_frame)

        self.body_container = QWidget()
        self.body_container.setObjectName("cornellBodyContainer")
        self.body_layout = QVBoxLayout(self.body_container)
        self.body_layout.setContentsMargins(0, 6, 0, 0)
        self.body_layout.setSpacing(10)

        if self.model.cue_question:
            cue_box = QFrame()
            cue_box.setObjectName("cornellCueBox")
            c_layout = QHBoxLayout(cue_box)
            c_layout.setContentsMargins(12, 8, 12, 8)
            c_layout.setSpacing(8)
            cue_icon = QLabel("🎯 RECALL CUE:")
            cue_icon.setObjectName("cornellCueIcon")
            cue_text = QLabel(self.model.cue_question)
            cue_text.setObjectName("cornellCueText")
            cue_text.setWordWrap(True)
            c_layout.addWidget(cue_icon, 0, Qt.AlignmentFlag.AlignTop)
            c_layout.addWidget(cue_text, 1)
            self.body_layout.addWidget(cue_box)

        if self.model.summary_text:
            notes_text = QLabel(self.model.summary_text)
            notes_text.setObjectName("cornellNotesContent")
            notes_text.setWordWrap(True)
            notes_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.body_layout.addWidget(notes_text)

        if self.model.key_points:
            takeaway_box = QFrame()
            takeaway_box.setObjectName("cornellTakeawayBox")
            t_layout = QVBoxLayout(takeaway_box)
            t_layout.setContentsMargins(12, 8, 12, 8)
            t_layout.setSpacing(4)
            for point in self.model.key_points:
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

        for block in self.model.code_blocks:
            tb = InteractiveTerminalBlock(
                code=block.code,
                language=block.language,
                title=block.title,
            )
            self.body_layout.addWidget(tb)

        if self.model.bottom_line:
            bl_box = QFrame()
            bl_box.setObjectName("cornellBottomLineBox")
            bl_layout = QHBoxLayout(bl_box)
            bl_layout.setContentsMargins(12, 8, 12, 8)
            bl_icon = QLabel("💡 TAKEAWAY:")
            bl_icon.setObjectName("cornellBottomLineIcon")
            bl_text = QLabel(self.model.bottom_line)
            bl_text.setObjectName("cornellBottomLineText")
            bl_text.setWordWrap(True)
            bl_layout.addWidget(bl_icon, 0, Qt.AlignmentFlag.AlignTop)
            bl_layout.addWidget(bl_text, 1)
            self.body_layout.addWidget(bl_box)

        self.scratchpad_frame = QFrame()
        self.scratchpad_frame.setObjectName("cornellScratchpadFrame")
        self.scratchpad_frame.setVisible(bool(self.model.personal_note))
        sp_layout = QVBoxLayout(self.scratchpad_frame)
        sp_layout.setContentsMargins(10, 8, 10, 8)
        sp_layout.setSpacing(6)

        sp_header = QLabel("Personal Study Margin / Student Notes:")
        sp_header.setObjectName("scratchpadHeaderLabel")
        sp_layout.addWidget(sp_header)

        self.scratchpad_edit = QTextEdit()
        self.scratchpad_edit.setObjectName("scratchpadTextEdit")
        self.scratchpad_edit.setPlaceholderText("Type personal reflection, exam pointers, or mental models here...")
        self.scratchpad_edit.setText(self.model.personal_note)
        self.scratchpad_edit.setFixedHeight(75)
        self.scratchpad_edit.textChanged.connect(self._on_scratchpad_changed)
        sp_layout.addWidget(self.scratchpad_edit)

        self.body_layout.addWidget(self.scratchpad_frame)
        main_layout.addWidget(self.body_container)

    def _setup_action_menu(self) -> None:
        menu = QMenu(self)

        copy_action = menu.addAction("Copy Formatted Note")
        copy_action.triggered.connect(self._copy_card_content)

        tutor_action = menu.addAction("Ask AI Tutor to Explain Further")
        tutor_action.triggered.connect(lambda: self.tutorSnippetRequested.emit(self._full_text_export()))

        flashcard_action = menu.addAction("Convert Recall Cue to Flashcard")
        flashcard_action.triggered.connect(
            lambda: self.studyCardRequested.emit(self.model.cue_question or self.model.title, self.model.summary_text)
        )

        self.actions_btn.setMenu(menu)

    def _full_text_export(self) -> str:
        parts = [f"## {self.model.title}"]
        if self.model.cue_question:
            parts.append(f"**Recall Cue:** {self.model.cue_question}")
        if self.model.summary_text:
            parts.append(self.model.summary_text)
        for b in self.model.code_blocks:
            parts.append(f"```{b.language}\n{b.code}\n```")
        if self.model.bottom_line:
            parts.append(f"**Key Takeaway:** {self.model.bottom_line}")
        if self.model.personal_note:
            parts.append(f"**Personal Note:** {self.model.personal_note}")
        return "\n\n".join(parts)

    def _copy_card_content(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self._full_text_export())

    def toggle_expand(self) -> None:
        self.set_expanded(not self.is_expanded)

    def set_expanded(self, expanded: bool) -> None:
        self.is_expanded = expanded
        self.body_container.setVisible(expanded)
        self.toggle_btn.setText("▼" if expanded else "▶")

    def _toggle_scratchpad(self) -> None:
        self.scratchpad_visible = not self.scratchpad_frame.isVisible()
        self.scratchpad_frame.setVisible(self.scratchpad_visible)
        if self.scratchpad_visible:
            self.scratchpad_edit.setFocus()

    def _on_scratchpad_changed(self) -> None:
        text = self.scratchpad_edit.toPlainText().strip()
        self.model.personal_note = text
        self.personalNoteSaved.emit(self.model.section_id, text)

    def _on_mastery_toggled(self, checked: bool) -> None:
        self.model.is_mastered = checked
        self.setProperty("completed", checked)
        self.style().unpolish(self)
        self.style().polish(self)
        self.masteryChanged.emit(self.model.title, checked)


class NotesWidget(QWidget):
    notesGenerated = Signal(int)
    notesExported = Signal(str)
    statusMessage = Signal(str, str)
    operationStarted = Signal(str)
    operationFinished = Signal(str)

    navigateToStudy = Signal(int)
    navigateToQuiz = Signal(int)
    navigateToTutor = Signal(int)
    navigateToTutorSnippet = Signal(int, str)

    def __init__(
        self,
        settings: QSettings,
        job_service: JobService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.settings = settings
        self.jobs = job_service
        self.notes_manager = NotesManager(job_service, self)

        self.document_id: int | None = None
        self.current_notes: NotesViewModel | None = None
        self.parsed_bundle: ParsedStudyNotesBundle | None = None
        self._interactive_cards: list[InteractiveCornellNoteCard] = []
        self._target_map: dict[str, QWidget] = {}
        self._search_matches: list[QWidget] = []
        self._match_index = -1
        self._is_operation_active = False
        self._equity_profile: dict[str, Any] = {}
        self._raw_markdown_cache: str = ""
        self._zoom_level = 100

        self.setObjectName("AmbaNotesWidgetUI")

        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()
        self._load_local_styles()
        self._post_init_setup()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self._setup_control_panel(main_layout)
        self._setup_workspace(main_layout)
        self._setup_footer(main_layout)

    def _setup_control_panel(self, main_layout: QVBoxLayout) -> None:
        control_card = QFrame()
        control_card.setObjectName("controlCard")
        c_layout = QVBoxLayout(control_card)
        c_layout.setContentsMargins(14, 10, 14, 10)
        c_layout.setSpacing(8)

        row_top = QHBoxLayout()
        row_top.setSpacing(10)

        style_lbl = QLabel(self.tr("Pedagogy Style:"))
        style_lbl.setObjectName("controlRibbonLabel")
        self.note_style_combo = QComboBox()
        self.note_style_combo.setObjectName("noteStyleCombo")
        self.note_style_combo.addItems(NoteStyle.values())

        lang_lbl = QLabel(self.tr("Language:"))
        lang_lbl.setObjectName("controlRibbonLabel")
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("notesLanguageCombo")
        self.language_combo.addItems(["English", "Amharic", "Afaan Oromo", "Tigrinya", "Somali"])

        self.simple_language_check = QCheckBox(self.tr("Simplified Vocabulary"))
        self.simple_language_check.setObjectName("notesSimpleLanguageCheck")
        self.simple_language_check.setChecked(True)

        self.force_check = QCheckBox(self.tr("Bypass Cache"))
        self.force_check.setObjectName("notesForceCheck")

        row_top.addWidget(style_lbl)
        row_top.addWidget(self.note_style_combo)
        row_top.addWidget(lang_lbl)
        row_top.addWidget(self.language_combo)
        row_top.addWidget(self.simple_language_check)
        row_top.addWidget(self.force_check)
        row_top.addStretch(1)

        self.generate_btn = QPushButton(icon("notes"), self.tr("Synthesize Notes"))
        self.generate_btn.setObjectName("generateNotesButton")
        self.generate_btn.setProperty("priority", "primary")
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.export_btn = QPushButton(icon("export"), self.tr("Export"))
        self.export_btn.setObjectName("exportNotesButton")
        self.export_btn.setProperty("variant", "secondary")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        row_top.addWidget(self.generate_btn)
        row_top.addWidget(self.export_btn)
        c_layout.addLayout(row_top)

        row_sub = QHBoxLayout()
        row_sub.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("Search active recall notes, syntax, or commands..."))
        self.search_input.setObjectName("notesSearchInput")
        self.search_input.textChanged.connect(self._on_search_query_changed)
        row_sub.addWidget(self.search_input, stretch=1)

        self.expand_all_btn = QPushButton("Expand All")
        self.expand_all_btn.setObjectName("learningCompactAction")
        self.expand_all_btn.clicked.connect(lambda: self._set_all_cards_expanded(True))

        self.collapse_all_btn = QPushButton("Collapse All")
        self.collapse_all_btn.setObjectName("learningCompactAction")
        self.collapse_all_btn.clicked.connect(lambda: self._set_all_cards_expanded(False))

        self.copy_all_btn = QPushButton(self.tr("Copy Notes"))
        self.copy_all_btn.setObjectName("learningCompactAction")
        self.copy_all_btn.clicked.connect(self._copy_notes_to_clipboard)

        zoom_lbl = QLabel(self.tr("Zoom:"))
        zoom_lbl.setObjectName("controlRibbonLabel")
        self.zoom_out_btn = QPushButton("A-")
        self.zoom_out_btn.setObjectName("learningCompactAction")
        self.zoom_out_btn.setFixedWidth(32)
        self.zoom_out_btn.clicked.connect(lambda: self._adjust_zoom(-10))
        self.zoom_in_btn = QPushButton("A+")
        self.zoom_in_btn.setObjectName("learningCompactAction")
        self.zoom_in_btn.setFixedWidth(32)
        self.zoom_in_btn.clicked.connect(lambda: self._adjust_zoom(10))

        row_sub.addWidget(self.expand_all_btn)
        row_sub.addWidget(self.collapse_all_btn)
        row_sub.addWidget(self.copy_all_btn)
        row_sub.addWidget(zoom_lbl)
        row_sub.addWidget(self.zoom_out_btn)
        row_sub.addWidget(self.zoom_in_btn)

        c_layout.addLayout(row_sub)
        main_layout.addWidget(control_card)

    def _setup_workspace(self, main_layout: QVBoxLayout) -> None:
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("mainSplitter")

        outline_container = QFrame()
        outline_container.setObjectName("sidebarFrame")
        outline_layout = QVBoxLayout(outline_container)
        outline_layout.setContentsMargins(8, 8, 8, 8)
        outline_layout.setSpacing(8)

        outline_title = QLabel(self.tr("Curriculum Structure"))
        outline_title.setObjectName("sidebarSectionTitle")
        outline_layout.addWidget(outline_title)

        self.outline_tree = QTreeWidget()
        self.outline_tree.setHeaderHidden(True)
        self.outline_tree.setObjectName("outlineTree")
        self.outline_tree.setAnimated(True)
        self.outline_tree.itemClicked.connect(self._on_outline_item_clicked)
        outline_layout.addWidget(self.outline_tree, stretch=1)

        self.mastery_card = QFrame()
        self.mastery_card.setObjectName("notesMasteryProgressCard")
        mp_layout = QVBoxLayout(self.mastery_card)
        mp_layout.setContentsMargins(10, 8, 10, 8)
        mp_layout.setSpacing(4)

        self.mastery_title = QLabel("Study Mastery: 0%")
        self.mastery_title.setObjectName("masteryCardTitle")
        self.mastery_bar = QProgressBar()
        self.mastery_bar.setRange(0, 100)
        self.mastery_bar.setValue(0)
        self.mastery_bar.setFixedHeight(8)
        self.mastery_bar.setTextVisible(False)

        mp_layout.addWidget(self.mastery_title)
        mp_layout.addWidget(self.mastery_bar)
        outline_layout.addWidget(self.mastery_card)

        self.center_tabs = QTabWidget()
        self.center_tabs.setObjectName("centerTabs")

        study_tab = QWidget()
        st_layout = QVBoxLayout(study_tab)
        st_layout.setContentsMargins(6, 6, 6, 6)
        st_layout.setSpacing(6)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setObjectName("notesCardsScroll")
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.cards_canvas = QWidget()
        self.cards_canvas.setObjectName("notesCardsCanvas")
        self.cards_layout = QVBoxLayout(self.cards_canvas)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.cards_scroll.setWidget(self.cards_canvas)
        st_layout.addWidget(self.cards_scroll)

        self.center_tabs.addTab(study_tab, icon("notes"), self.tr("Interactive Study Notes"))

        cheatsheet_tab = QWidget()
        cs_layout = QVBoxLayout(cheatsheet_tab)
        cs_layout.setContentsMargins(8, 8, 8, 8)
        cs_layout.setSpacing(8)

        self.cs_scroll = QScrollArea()
        self.cs_scroll.setWidgetResizable(True)
        self.cs_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.cs_canvas = QWidget()
        self.cs_layout = QVBoxLayout(self.cs_canvas)
        self.cs_layout.setContentsMargins(4, 4, 4, 4)
        self.cs_layout.setSpacing(10)
        self.cs_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.cs_scroll.setWidget(self.cs_canvas)
        cs_layout.addWidget(self.cs_scroll)

        self.center_tabs.addTab(cheatsheet_tab, icon("tables"), self.tr("Command Matrix & Cheatsheet"))

        editor_tab = QWidget()
        ed_layout = QVBoxLayout(editor_tab)
        ed_layout.setContentsMargins(6, 6, 6, 6)
        ed_layout.setSpacing(6)

        self.raw_editor = QTextEdit()
        self.raw_editor.setObjectName("rawNoteEditor")
        self.raw_editor.setFont(QFont("Cascadia Code", 10))
        ed_layout.addWidget(self.raw_editor)

        self.center_tabs.addTab(editor_tab, icon("summary"), self.tr("Markdown Editor"))

        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.setContentsMargins(8, 8, 8, 8)
        log_layout.setSpacing(6)

        self.notes_status_label = QLabel(self.tr("Engine Status: Ready"))
        self.notes_status_label.setObjectName("notesStatusLabel")
        self.notes_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.operation_log = QTextBrowser()
        self.operation_log.setObjectName("notesOperationLog")
        self.operation_log.setReadOnly(True)

        log_layout.addWidget(self.notes_status_label)
        log_layout.addWidget(self.operation_log, stretch=1)

        self.center_tabs.addTab(log_tab, icon("info"), self.tr("Activity Log"))

        self.main_splitter.addWidget(outline_container)
        self.main_splitter.addWidget(self.center_tabs)
        self.main_splitter.setSizes([260, 780])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self.main_splitter, stretch=1)

    def _setup_footer(self, main_layout: QVBoxLayout) -> None:
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(4, 2, 4, 2)
        footer_layout.setSpacing(8)

        self.overall_status_label = QLabel(self.tr("Select a document to begin generating interactive study notes."))
        self.overall_status_label.setObjectName("footerStatusLabel")
        footer_layout.addWidget(self.overall_status_label, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(220)
        self.progress_bar.setFixedHeight(12)
        footer_layout.addWidget(self.progress_bar)

        main_layout.addLayout(footer_layout)

    def _setup_shortcuts(self) -> None:
        self.find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.find_shortcut.activated.connect(lambda: self.search_input.setFocus())

    def _connect_signals(self) -> None:
        self.generate_btn.clicked.connect(self.generate_notes)
        self.export_btn.clicked.connect(self.export_notes)

        self.notes_manager.notesStarted.connect(self._on_manager_notes_started)
        self.notes_manager.notesFinished.connect(self._on_manager_notes_finished)
        self.notes_manager.notesFailed.connect(self._on_manager_notes_failed)
        self.notes_manager.notesGenerated.connect(self.notesGenerated.emit)
        self.notes_manager.statusMessage.connect(self._append_status_message)
        self.notes_manager.operationStarted.connect(self.operationStarted.emit)
        self.notes_manager.operationFinished.connect(self.operationFinished.emit)

    def _post_init_setup(self) -> None:
        self._restore_settings()
        self._update_ui_for_operation_status()

    def _load_local_styles(self) -> None:
        qss_path = Path(__file__).parent / "notes.qss"
        if qss_path.exists():
            apply_local_qss(self, qss_path)

    def _restore_settings(self) -> None:
        style = self.settings.value("Notes/style", NoteStyle.STUDENT.value)
        language = self.settings.value("Notes/language", "English")
        simple = str(self.settings.value("Notes/simple_language", "true")).lower() in {"1", "true", "yes", "on"}

        self._set_combo_text(self.note_style_combo, str(style))
        self._set_combo_text(self.language_combo, str(language))
        self.simple_language_check.setChecked(simple)

    def _save_settings(self) -> None:
        self.settings.setValue("Notes/style", self.note_style_combo.currentText())
        self.settings.setValue("Notes/language", self.language_combo.currentText())
        self.settings.setValue("Notes/simple_language", self.simple_language_check.isChecked())
        self.settings.sync()

    @staticmethod
    def _set_combo_text(combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _adjust_zoom(self, delta: int) -> None:
        self._zoom_level = max(70, min(160, self._zoom_level + delta))
        base_size = int(10 * (self._zoom_level / 100))
        font = self.font()
        font.setPointSize(base_size)
        self.setFont(font)

    @Slot(int)
    def set_document(self, document_id: int) -> None:
        self.document_id = int(document_id)
        self.current_notes = None
        self.parsed_bundle = None
        self._raw_markdown_cache = ""
        self.raw_editor.clear()
        self._interactive_cards.clear()
        self._target_map.clear()
        self.outline_tree.clear()

        _clear_layout(self.cards_layout)
        _clear_layout(self.cs_layout)

        empty_box = QLabel("Select 'Synthesize Notes' to generate interactive study cards and code blocks.")
        empty_box.setObjectName("notesEmptyPlaceholder")
        empty_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cards_layout.addWidget(empty_box)

        self.overall_status_label.setText(self.tr(f"Document #{document_id} loaded. Ready to synthesize study notes."))
        self.notes_status_label.setText(self.tr(f"Document ID: {document_id} Active"))
        self._update_ui_for_operation_status()

    @Slot(dict)
    def apply_equity_profile(self, profile: dict[str, Any]) -> None:
        self._equity_profile = dict(profile or {})
        language = str(self._equity_profile.get("target_language") or "")
        simple = bool(self._equity_profile.get("simple_language", self.simple_language_check.isChecked()))
        preferred_model = str(self._equity_profile.get("preferred_model") or "")

        if language:
            self._set_combo_text(self.language_combo, language)

        self.simple_language_check.setChecked(simple)
        self.notes_manager.apply_equity_profile(self._equity_profile)

        if preferred_model:
            self._append_status_message(f"Equity Switch preferred model applied: {preferred_model}", "INFO")

        self._update_ui_for_operation_status()

    @Slot()
    def generate_notes(self) -> None:
        if self.document_id is None:
            QMessageBox.warning(self, self.tr("No Document"), self.tr("Please select or ingest a document first."))
            return

        self._save_settings()

        request = NotesGenerationRequest(
            document_id=self.document_id,
            force=self.force_check.isChecked(),
            target_language=self.language_combo.currentText(),
            simple_language=self.simple_language_check.isChecked(),
            teacher_review_required=bool(self._equity_profile.get("teacher_review_required", True)),
            preferred_model=str(self._equity_profile.get("preferred_model", "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M")),
            note_style=self.note_style_combo.currentText(),
        )

        _clear_layout(self.cards_layout)
        loading_box = QLabel("⏳ Synthesizing active recall notes & syntax pipelines...")
        loading_box.setObjectName("notesEmptyPlaceholder")
        loading_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cards_layout.addWidget(loading_box)

        self.outline_tree.clear()
        self.notes_manager.generate_notes(request.to_dict())

    @Slot()
    def export_notes(self) -> None:
        markdown = self.raw_editor.toPlainText().strip()
        if not markdown:
            markdown = self._raw_markdown_cache.strip()

        if not markdown:
            QMessageBox.information(self, self.tr("No Notes"), self.tr("Generate notes before attempting export."))
            return

        filename = f"{safe_filename_stem(f'document_{self.document_id}_study_notes')}.md"

        try:
            result = export_markdown(filename, markdown)
            self._append_status_message(f"Exported markdown file to: {result.path}", "INFO")
            QMessageBox.information(self, self.tr("Export Successful"), self.tr(f"Saved Markdown file to:\n{result.path}"))
        except ExportError as exc:
            logger.exception("Notes export failed")
            QMessageBox.critical(self, self.tr("Export Failed"), str(exc))
            self._append_status_message(str(exc), "ERROR")

    @Slot()
    def _copy_notes_to_clipboard(self) -> None:
        content = self.raw_editor.toPlainText() or self._raw_markdown_cache
        if content:
            QApplication.clipboard().setText(content)
            self.overall_status_label.setText(self.tr("Notes copied to clipboard!"))
            self.copy_all_btn.setText("Copied!")
            QTimer.singleShot(1800, lambda: self.copy_all_btn.setText(self.tr("Copy Notes")))

    @Slot(str)
    def _on_search_query_changed(self, text: str) -> None:
        query = text.strip().lower()
        self._search_matches.clear()
        self._match_index = -1

        if not query:
            return

        for card in self._interactive_cards:
            combined = (
                card.model.title.lower()
                + " "
                + card.model.cue_question.lower()
                + " "
                + card.model.summary_text.lower()
                + " "
                + " ".join(b.code.lower() for b in card.model.code_blocks)
            )
            if query in combined:
                self._search_matches.append(card)
                card.set_expanded(True)

        if self._search_matches:
            self._step_search_match(1)

    def _step_search_match(self, direction: int) -> None:
        if not self._search_matches:
            return
        self._match_index = (self._match_index + direction) % len(self._search_matches)
        target = self._search_matches[self._match_index]
        self.cards_scroll.ensureWidgetVisible(target, 20, 20)
        self._highlight_active_card(target)

    def _highlight_active_card(self, active_widget: QWidget) -> None:
        for card in self._interactive_cards:
            card.setProperty("activeTarget", card is active_widget)
            card.style().unpolish(card)
            card.style().polish(card)

    def _set_all_cards_expanded(self, expanded: bool) -> None:
        for card in self._interactive_cards:
            card.set_expanded(expanded)

    @Slot(str)
    def _on_manager_notes_started(self, note_style: str) -> None:
        self._is_operation_active = True
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.notes_status_label.setText(self.tr(f"Synthesizing: {note_style}"))
        self.overall_status_label.setText(self.tr("Synthesizing learning modules..."))
        self._update_ui_for_operation_status()

    @Slot(dict)
    def _on_manager_notes_finished(self, payload: dict[str, Any]) -> None:
        self._is_operation_active = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)

        notes = NotesViewModel(
            document_id=int(payload.get("document_id") or self.document_id or 0),
            markdown=str(payload.get("markdown") or ""),
            model_name=str(payload.get("model_name") or "unknown"),
            note_style=str(payload.get("note_style") or self.note_style_combo.currentText()),
            cached=bool(payload.get("cached", False)),
            fallback=bool(payload.get("fallback", False)),
            metadata=dict(payload.get("metadata") or {}),
        )
        self.current_notes = notes

        cleaned_markdown = format_markdown_notes_for_ui(notes.markdown)
        cleaned_markdown = re.sub(r"<!--.*?-->\n?", "", cleaned_markdown)
        self._raw_markdown_cache = cleaned_markdown
        self.raw_editor.setPlainText(cleaned_markdown)

        self.parsed_bundle = ParsedStudyNotesBundle.from_raw(cleaned_markdown, notes.metadata)
        self._render_interactive_study_canvas(self.parsed_bundle)
        self._render_command_matrix(self.parsed_bundle)
        self._rebuild_outline_tree(self.parsed_bundle)

        badge_cache = "Cached" if notes.cached else "Fresh Inference"
        label = self.tr(
            f"Notes ready • Model: {notes.model_name} • {notes.note_style} ({badge_cache})"
        )

        self.notes_status_label.setText(label)
        self.overall_status_label.setText(label)
        self.center_tabs.setCurrentIndex(0)

        if notes.document_id > 0:
            self.notesGenerated.emit(notes.document_id)

        self._append_status_message(label, "INFO")
        self._update_ui_for_operation_status()

    def _render_interactive_study_canvas(self, bundle: ParsedStudyNotesBundle) -> None:
        _clear_layout(self.cards_layout)
        self._interactive_cards.clear()
        self._target_map.clear()

        overview_card = QFrame()
        overview_card.setObjectName("notesExecutiveOverviewCard")
        ov_layout = QVBoxLayout(overview_card)
        ov_layout.setContentsMargins(16, 14, 16, 14)
        ov_layout.setSpacing(10)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)

        ov_badge = QLabel("STUDENT STUDY GUIDE")
        ov_badge.setObjectName("notesTagPill")
        badge_row.addWidget(ov_badge)

        if bundle.source_badge:
            page_pill = QLabel(bundle.source_badge)
            page_pill.setObjectName("notesSourcePagePill")
            badge_row.addWidget(page_pill)

        badge_row.addStretch(1)
        ov_layout.addLayout(badge_row)

        title_lbl = QLabel(bundle.title)
        title_lbl.setObjectName("notesOverviewTitle")
        title_lbl.setWordWrap(True)
        ov_layout.addWidget(title_lbl)

        if bundle.overview:
            body_lbl = QLabel(bundle.overview)
            body_lbl.setObjectName("notesOverviewBody")
            body_lbl.setWordWrap(True)
            body_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            ov_layout.addWidget(body_lbl)

        self.cards_layout.addWidget(overview_card)
        self._target_map["Overview"] = overview_card

        saved_notes_key = f"Notes/Personal/{self.document_id or 0}"
        saved_margin_notes: dict[str, str] = {}
        try:
            saved_margin_notes = json.loads(self.settings.value(saved_notes_key, "{}", str) or "{}")
        except Exception:
            saved_margin_notes = {}

        saved_mastery_key = f"Notes/Mastery/{self.document_id or 0}"
        saved_mastery: set[str] = set()
        try:
            saved_mastery = set(json.loads(self.settings.value(saved_mastery_key, "[]", str) or "[]"))
        except Exception:
            saved_mastery = set()

        for i, card_model in enumerate(bundle.cards, 1):
            if card_model.section_id in saved_margin_notes:
                card_model.personal_note = saved_margin_notes[card_model.section_id]
            card_model.is_mastered = card_model.title in saved_mastery

            card_widget = InteractiveCornellNoteCard(card_model, index=i)
            card_widget.tutorSnippetRequested.connect(self._on_tutor_snippet_requested)
            card_widget.studyCardRequested.connect(self._on_study_card_requested)
            card_widget.masteryChanged.connect(self._on_card_mastery_changed)
            card_widget.personalNoteSaved.connect(self._on_personal_note_saved)

            self.cards_layout.addWidget(card_widget)
            self._interactive_cards.append(card_widget)
            self._target_map[card_model.title] = card_widget

        nav_toolbar = QFrame()
        nav_toolbar.setObjectName("notesNavigationToolbar")
        nt_layout = QHBoxLayout(nav_toolbar)
        nt_layout.setContentsMargins(14, 12, 14, 12)
        nt_layout.setSpacing(12)

        lbl = QLabel(self.tr("Next Cognitive Milestones:"))
        lbl.setObjectName("notesToolbarLabel")
        nt_layout.addWidget(lbl)

        doc_id = self.document_id or 0
        actions = (
            ("study", "Generate Flashcards", self.navigateToStudy),
            ("quiz", "Take Revision Quiz", self.navigateToQuiz),
            ("tutor", "Ask AI Tutor", self.navigateToTutor),
        )

        for icon_name, label_text, sig in actions:
            btn = QPushButton(icon(icon_name), label_text)
            btn.setObjectName("notesPathwayBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, s=sig: s.emit(doc_id))
            nt_layout.addWidget(btn)

        nt_layout.addStretch(1)
        self.cards_layout.addWidget(nav_toolbar)

        self._update_mastery_ui()

    def _render_command_matrix(self, bundle: ParsedStudyNotesBundle) -> None:
        _clear_layout(self.cs_layout)

        all_blocks = []
        for c in bundle.cards:
            for b in c.code_blocks:
                all_blocks.append((c.title, b))

        if all_blocks:
            title_card = QFrame()
            title_card.setObjectName("notesExecutiveOverviewCard")
            tc_layout = QVBoxLayout(title_card)
            tc_layout.setContentsMargins(14, 12, 14, 12)
            tc_layout.setSpacing(6)

            m_title = QLabel("Fast-Lookup Syntax & Command Matrix")
            m_title.setObjectName("notesOverviewTitle")
            m_sub = QLabel(f"{len(all_blocks)} terminal pipelines and parsing expressions extracted from study notes.")
            m_sub.setObjectName("notesOverviewBody")

            tc_layout.addWidget(m_title)
            tc_layout.addWidget(m_sub)
            self.cs_layout.addWidget(title_card)

            for sec_title, b in all_blocks:
                tb = InteractiveTerminalBlock(
                    code=b.code,
                    language=b.language,
                    title=f"{sec_title} :: {b.title}",
                )
                self.cs_layout.addWidget(tb)
        else:
            empty = QLabel("No command-line or code blocks found in this study material.")
            empty.setObjectName("notesEmptyPlaceholder")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cs_layout.addWidget(empty)

    def _rebuild_outline_tree(self, bundle: ParsedStudyNotesBundle) -> None:
        self.outline_tree.clear()

        root = QTreeWidgetItem(self.outline_tree, [f"📘 {bundle.title}"])
        root.setData(0, Qt.ItemDataRole.UserRole, "Overview")
        root.setExpanded(True)

        for card in bundle.cards:
            status_symbol = "✅" if card.is_mastered else "📌"
            item = QTreeWidgetItem(root, [f"{status_symbol} {card.title}"])
            item.setData(0, Qt.ItemDataRole.UserRole, card.title)

    @Slot(QTreeWidgetItem, int)
    def _on_outline_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        title = item.data(0, Qt.ItemDataRole.UserRole)
        if not title:
            return

        self.center_tabs.setCurrentIndex(0)
        target = self._target_map.get(title)
        if target:
            if isinstance(target, InteractiveCornellNoteCard):
                target.set_expanded(True)
            self.cards_scroll.ensureWidgetVisible(target, 20, 20)
            self._highlight_active_card(target)

    def _on_card_mastery_changed(self, title: str, is_mastered: bool) -> None:
        key = f"Notes/Mastery/{self.document_id or 0}"
        try:
            saved = set(json.loads(self.settings.value(key, "[]", str) or "[]"))
        except Exception:
            saved = set()

        if is_mastered:
            saved.add(title)
        else:
            saved.discard(title)

        self.settings.setValue(key, json.dumps(sorted(saved), ensure_ascii=False))
        self._update_mastery_ui()

        if self.parsed_bundle:
            self._rebuild_outline_tree(self.parsed_bundle)

    def _on_personal_note_saved(self, section_id: str, note_text: str) -> None:
        key = f"Notes/Personal/{self.document_id or 0}"
        try:
            saved = dict(json.loads(self.settings.value(key, "{}", str) or "{}"))
        except Exception:
            saved = {}

        if note_text:
            saved[section_id] = note_text
        else:
            saved.pop(section_id, None)

        self.settings.setValue(key, json.dumps(saved, ensure_ascii=False))

    def _update_mastery_ui(self) -> None:
        total = len(self._interactive_cards)
        if total == 0:
            self.mastery_card.setVisible(False)
            return

        self.mastery_card.setVisible(True)
        done = sum(1 for c in self._interactive_cards if c.model.is_mastered)
        pct = int(round((done / total) * 100))
        self.mastery_title.setText(f"Study Mastery: {pct}% ({done}/{total} Modules)")
        self.mastery_bar.setValue(pct)

    def _on_tutor_snippet_requested(self, snippet: str) -> None:
        self.navigateToTutorSnippet.emit(self.document_id or 0, snippet[:140])
        self.statusMessage.emit("Study note excerpt forwarded to AI Tutor.", "INFO")

    def _on_study_card_requested(self, cue: str, answer: str) -> None:
        self.navigateToStudy.emit(self.document_id or 0)
        self.statusMessage.emit("Concept card prepared for Recall practice.", "INFO")

    @Slot(dict)
    def _on_manager_notes_failed(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        self.progress_bar.setVisible(False)

        message = str(error_context.get("error_message") or "Notes generation failed.")
        self.notes_status_label.setText(message)
        self.overall_status_label.setText(message)
        self._append_status_message(message, "ERROR")

        QMessageBox.critical(self, self.tr("Generation Failed"), message)
        self._update_ui_for_operation_status()

    @Slot(str, str)
    def _append_status_message(self, message: str, level: str = "INFO") -> None:
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        color_map = {
            "INFO": "#38BDF8",
            "WARNING": "#F59E0B",
            "ERROR": "#EF4444",
            "DEBUG": "#94A3B8",
        }
        color = color_map.get(level.upper(), "#E2E8F0")
        safe = str(message).replace("<", "&lt;").replace(">", "&gt;")
        self.operation_log.append(
            f'<span style="color:#64748B;">[{timestamp}]</span> '
            f'<b style="color:{color};">[{level.upper()}]</b> {safe}'
        )
        self.statusMessage.emit(message, level)

    def _update_ui_for_operation_status(self) -> None:
        inactive = not self._is_operation_active
        has_document = self.document_id is not None
        has_notes = bool(self._raw_markdown_cache.strip() or self.raw_editor.toPlainText().strip())

        self.generate_btn.setEnabled(inactive and has_document)
        self.export_btn.setEnabled(inactive and has_notes)
        self.copy_all_btn.setEnabled(inactive and has_notes)
        self.note_style_combo.setEnabled(inactive)
        self.language_combo.setEnabled(inactive)
        self.simple_language_check.setEnabled(inactive)
        self.force_check.setEnabled(inactive)

    def cleanup_before_close(self) -> None:
        self._save_settings()
        self.notes_manager.cleanup_before_close()
        logger.info("NotesWidget cleanup completed.")

    def retranslateUi(self) -> None:
        self.simple_language_check.setText(self.tr("Simplified Vocabulary"))
        self.force_check.setText(self.tr("Bypass Cache"))
        self.generate_btn.setText(self.tr("Synthesize Notes"))
        self.export_btn.setText(self.tr("Export"))
        self.copy_all_btn.setText(self.tr("Copy Notes"))
        self.center_tabs.setTabText(0, self.tr("Interactive Study Notes"))
        self.center_tabs.setTabText(1, self.tr("Command Matrix & Cheatsheet"))
        self.center_tabs.setTabText(2, self.tr("Markdown Editor"))
        self.center_tabs.setTabText(3, self.tr("Activity Log"))