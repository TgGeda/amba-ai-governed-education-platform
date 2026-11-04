from __future__ import annotations

import html
import json
from pathlib import Path
import re
from typing import Any, Optional

from PySide6.QtCore import (
    QDateTime,
    QModelIndex,
    QPoint,
    QSettings,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QFont,
    QKeySequence,
    QShortcut,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
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
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QToolBar,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from amba_ai.ui.common.qss_utils import apply_local_qss
from amba_ai.ui.common.ui_icons_utils import icon
from .data_classes import (
    TutorAnswerViewModel,
    TutorCodeSnippet,
    TutorPersona,
    TutorRequest,
    TutorSourceViewModel,
)
from .tutor_manager import TutorManager


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
        sub = item.layout()
        if sub is not None:
            _clear_layout(sub)


def _highlight_code_syntax(code_str: str, language: str = "bash") -> str:
    escaped = html.escape(code_str.strip())
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
    return escaped


class InteractiveTerminalBlock(QFrame):
    def __init__(self, code: str, language: str = "bash", title: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.code = code.strip()
        self.language = language or "bash"
        self.title = title or f"{self.language.upper()} Command Execution"
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
        table_rows = [
            f'<tr><td style="color:#475569; user-select:none; text-align:right; padding-right:12px; font-family:\'JetBrains Mono\',monospace; font-size:12px;">{i}</td>'
            f'<td style="font-family:\'JetBrains Mono\',monospace; font-size:12px; white-space:pre-wrap;">{l}</td></tr>'
            for i, l in enumerate(lines, 1)
        ]

        self.code_browser.setHtml(
            f'<html><body style="margin:0;padding:10px;background-color:#070B14;color:#E2E8F0;"><table cellpadding="1" cellspacing="0" style="width:100%;border:none;">{"".join(table_rows)}</table></body></html>'
        )
        calculated_height = min(max(len(lines) * 20 + 26, 64), 220)
        self.code_browser.setFixedHeight(calculated_height)
        layout.addWidget(self.code_browser)

    def _copy_code(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self.code)
        self.copy_btn.setText("Copied!")
        self.copy_btn.setStyleSheet("color: #34D399; font-weight: bold;")
        QTimer.singleShot(1800, self._restore_copy_btn)

    def _restore_copy_btn(self) -> None:
        self.copy_btn.setText("Copy")
        self.copy_btn.setStyleSheet("")


class InteractiveMessageCard(QFrame):
    saveNotesRequested = Signal(str)
    createFlashcardRequested = Signal(str, str)
    explainSimplerRequested = Signal(str)

    def __init__(
        self,
        sender: str,
        text: str,
        timestamp: str = "",
        model_name: str | None = None,
        key_points: list[str] | None = None,
        code_snippets: list[TutorCodeSnippet] | None = None,
        sources: list[TutorSourceViewModel] | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.sender = sender
        self.text = text
        self.timestamp = timestamp or QDateTime.currentDateTime().toString("HH:mm:ss")
        self.model_name = model_name
        self.key_points = key_points or []
        self.code_snippets = code_snippets or []
        self.sources = sources or []
        self.setObjectName("tutorUserBubble" if sender == "Student" else "tutorAiResponseCard")
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        if self.sender == "Student":
            avatar_pill = QLabel("YOU")
            avatar_pill.setObjectName("studentAvatarBadge")
            sender_title = QLabel("Student Query")
            sender_title.setObjectName("studentTitleLabel")
            header_row.addWidget(avatar_pill)
            header_row.addWidget(sender_title)
        else:
            avatar_pill = QLabel("AMBA TUTOR")
            avatar_pill.setObjectName("aiAvatarBadge")
            sender_title = QLabel("Pedagogical Synthesis")
            sender_title.setObjectName("aiTitleLabel")
            header_row.addWidget(avatar_pill)
            header_row.addWidget(sender_title)
            if self.model_name:
                model_badge = QLabel(self.model_name)
                model_badge.setObjectName("modelIndicatorBadge")
                header_row.addWidget(model_badge)

        header_row.addStretch(1)
        time_lbl = QLabel(f"[{self.timestamp}]")
        time_lbl.setObjectName("timestampLabel")
        header_row.addWidget(time_lbl)
        main_layout.addLayout(header_row)

        content_lbl = QLabel(self.text)
        content_lbl.setObjectName("messageBodyText")
        content_lbl.setWordWrap(True)
        content_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        main_layout.addWidget(content_lbl)

        if self.key_points:
            points_box = QFrame()
            points_box.setObjectName("tutorTakeawaysBox")
            pb_layout = QVBoxLayout(points_box)
            pb_layout.setContentsMargins(12, 8, 12, 8)
            pb_layout.setSpacing(4)
            for point in self.key_points:
                row = QHBoxLayout()
                bullet = QLabel("✦")
                bullet.setObjectName("takeawayBullet")
                txt = QLabel(point)
                txt.setObjectName("takeawayPoint")
                txt.setWordWrap(True)
                txt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                row.addWidget(bullet, 0, Qt.AlignmentFlag.AlignTop)
                row.addWidget(txt, 1)
                pb_layout.addLayout(row)
            main_layout.addWidget(points_box)

        for snippet in self.code_snippets:
            tb = InteractiveTerminalBlock(
                code=snippet.code,
                language=snippet.language,
                title=snippet.title,
            )
            main_layout.addWidget(tb)

        if self.sources:
            src_row = QHBoxLayout()
            src_row.setSpacing(6)
            for s in self.sources[:3]:
                pill = QLabel(f"📚 {s.source}")
                pill.setObjectName("sourceCitationPill")
                src_row.addWidget(pill)
            src_row.addStretch(1)
            main_layout.addLayout(src_row)

        if self.sender != "Student":
            actions_row = QHBoxLayout()
            actions_row.setSpacing(8)

            copy_btn = QPushButton("Copy Explanation")
            copy_btn.setObjectName("tutorActionChip")
            copy_btn.clicked.connect(self._copy_explanation)

            notes_btn = QPushButton("Save to Study Notes")
            notes_btn.setObjectName("tutorActionChip")
            notes_btn.clicked.connect(lambda: self.saveNotesRequested.emit(self.text))

            flashcard_btn = QPushButton("Convert to Flashcard")
            flashcard_btn.setObjectName("tutorActionChip")
            flashcard_btn.clicked.connect(
                lambda: self.createFlashcardRequested.emit(
                    "Explain core principle", self.text
                )
            )

            simpler_btn = QPushButton("Explain Simpler 💡")
            simpler_btn.setObjectName("tutorActionChip")
            simpler_btn.clicked.connect(lambda: self.explainSimplerRequested.emit(self.text))

            actions_row.addWidget(copy_btn)
            actions_row.addWidget(notes_btn)
            actions_row.addWidget(flashcard_btn)
            actions_row.addWidget(simpler_btn)
            actions_row.addStretch(1)
            main_layout.addLayout(actions_row)

    def _copy_explanation(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text)


class TutorSourceFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._text_filter = ""
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_text_filter(self, text: str) -> None:
        normalized = str(text or "").strip().lower()
        if self._text_filter != normalized:
            self._text_filter = normalized
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if not isinstance(model, QStandardItemModel):
            return super().filterAcceptsRow(source_row, source_parent)

        if not self._text_filter:
            return True

        for column in range(model.columnCount()):
            index = model.index(source_row, column, source_parent)
            value = model.data(index, Qt.ItemDataRole.DisplayRole)
            if value and self._text_filter in str(value).lower():
                return True

        return False


class TutorWidget(QWidget):
    tutorAnswerReady = Signal(str)
    tutorError = Signal(dict)
    statusMessage = Signal(str, str)
    operationStarted = Signal(str)
    operationFinished = Signal(str)

    navigateToNotesConcept = Signal(int, str)
    navigateToStudyConcept = Signal(int, str)

    SRC_COL_INDEX = 0
    SRC_COL_SOURCE = 1
    SRC_COL_SCORE = 2
    SRC_MODEL_COLUMNS = 3

    def __init__(
        self,
        settings: QSettings,
        job_service: JobService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.settings = settings
        self.jobs = job_service
        self.tutor_manager = TutorManager(job_service, self)

        self.document_id: int | None = None
        self.active_document_title: str | None = None
        self.current_answer: TutorAnswerViewModel | None = None
        self._is_operation_active = False
        self._equity_profile: dict[str, Any] = {}
        self._message_cards: list[InteractiveMessageCard] = []

        self.sources_model = QStandardItemModel(0, self.SRC_MODEL_COLUMNS, self)
        self.sources_proxy = TutorSourceFilterProxyModel(self)
        self.sources_proxy.setSourceModel(self.sources_model)

        self.setObjectName("AmbaTutorWidgetUI")

        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()
        self._load_local_styles()
        self._post_init_setup()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        self._setup_toolbar(main_layout)
        self._setup_tabs(main_layout)
        self._setup_bottom_bar(main_layout)
        self._setup_sources_model_headers()
        self._configure_sources_tree()

    def _setup_toolbar(self, main_layout: QVBoxLayout) -> None:
        self.top_toolbar = QToolBar(self.tr("Tutor Controls"), self)
        self.top_toolbar.setObjectName("tutorToolbar")
        self.top_toolbar.setIconSize(QSize(16, 16))
        self.top_toolbar.setMovable(False)
        self.top_toolbar.setFloatable(False)

        persona_lbl = QLabel(self.tr("Guide Style:"))
        persona_lbl.setObjectName("controlRibbonLabel")
        self.persona_combo = QComboBox()
        self.persona_combo.setObjectName("tutorPersonaCombo")
        self.persona_combo.addItems(TutorPersona.values())

        lang_lbl = QLabel(self.tr("Language:"))
        lang_lbl.setObjectName("controlRibbonLabel")
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("tutorLanguageCombo")
        self.language_combo.addItems(["English", "Amharic", "Afaan Oromo", "Tigrinya", "Somali"])

        self.top_k_spin = QSpinBox()
        self.top_k_spin.setObjectName("topKSpin")
        self.top_k_spin.setRange(1, 20)
        self.top_k_spin.setValue(5)
        self.top_k_spin.setPrefix(self.tr("Sources: "))

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setObjectName("maxTokensSpin")
        self.max_tokens_spin.setRange(128, 4096)
        self.max_tokens_spin.setValue(900)
        self.max_tokens_spin.setSingleStep(128)
        self.max_tokens_spin.setPrefix(self.tr("Tokens: "))

        self.clear_chat_btn = QPushButton(icon("clear"), self.tr("Clear Session"))
        self.clear_chat_btn.setObjectName("clearChatButton")
        self.clear_chat_btn.setProperty("variant", "secondary")
        self.clear_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.top_toolbar.addWidget(persona_lbl)
        self.top_toolbar.addWidget(self.persona_combo)
        self.top_toolbar.addWidget(lang_lbl)
        self.top_toolbar.addWidget(self.language_combo)
        self.top_toolbar.addWidget(self.top_k_spin)
        self.top_toolbar.addWidget(self.max_tokens_spin)
        self.top_toolbar.addWidget(self.clear_chat_btn)

        main_layout.addWidget(self.top_toolbar)

    def _setup_tabs(self, main_layout: QVBoxLayout) -> None:
        self.content_tabs = QTabWidget()
        self.content_tabs.setIconSize(QSize(14, 14))

        self._setup_chat_tab()
        self._setup_sources_tab()
        self._setup_log_tab()

        main_layout.addWidget(self.content_tabs, stretch=1)

    def _setup_chat_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.grounding_badge = QLabel(self.tr("Curriculum-grounded tutor | Local document context active"))
        self.grounding_badge.setObjectName("tutorGroundingBadge")
        self.grounding_badge.setWordWrap(True)
        layout.addWidget(self.grounding_badge)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setObjectName("tutorChatScroll")
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.chat_canvas = QWidget()
        self.chat_canvas.setObjectName("tutorChatCanvas")
        self.chat_layout = QVBoxLayout(self.chat_canvas)
        self.chat_layout.setContentsMargins(6, 6, 6, 6)
        self.chat_layout.setSpacing(12)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.welcome_card = InteractiveMessageCard(
            sender="AmbaAI",
            text=(
                "Welcome to your AI Study Tutor. Ask any question about your loaded study materials, "
                "request step-by-step CLI walkthroughs, or explore complex concepts in simple terms."
            ),
            key_points=[
                "Ask for code explanations or specific terminal pipelines.",
                "Select 'Simple & Intuitive' in the toolbar for ELI5 explanations.",
                "Grounded strictly in local curriculum material.",
            ],
            code_snippets=[
                TutorCodeSnippet(
                    code="curl -s https://api.target.com/v1/users | jq '.[] | {id, email, admin: .is_admin}'",
                    language="bash",
                    title="Quick Starter Example",
                )
            ],
        )
        self.chat_layout.addWidget(self.welcome_card)
        self._message_cards.append(self.welcome_card)

        self.chat_scroll.setWidget(self.chat_canvas)
        layout.addWidget(self.chat_scroll, stretch=1)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        suggested_queries = [
            "💡 Explain simply",
            "💻 Show practical command",
            "🛡 Security risks & audit",
            "❓ Quiz me on this",
        ]
        for query in suggested_queries:
            btn = QPushButton(query)
            btn.setObjectName("tutorPromptChip")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, q=query: self._submit_prompt_chip(q))
            chips_row.addWidget(btn)
        chips_row.addStretch(1)
        layout.addLayout(chips_row)

        input_frame = QFrame()
        input_frame.setObjectName("tutorInputContainer")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 6, 10, 6)
        input_layout.setSpacing(8)

        self.chat_input = QLineEdit()
        self.chat_input.setObjectName("chatInput")
        self.chat_input.setPlaceholderText(self.tr("Ask a question about the active learning material (e.g. explain jq in simple terms)..."))
        self.chat_input.setClearButtonEnabled(True)

        self.ask_btn = QPushButton(icon("send"), self.tr("Ask Tutor"))
        self.ask_btn.setObjectName("askButton")
        self.ask_btn.setProperty("priority", "primary")
        self.ask_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        input_layout.addWidget(self.chat_input, stretch=1)
        input_layout.addWidget(self.ask_btn)
        layout.addWidget(input_frame)

        self.content_tabs.addTab(tab, icon("tutor"), self.tr("Interactive Chat"))

    def _setup_sources_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.sources_filter = QLineEdit()
        self.sources_filter.setObjectName("sourcesFilter")
        self.sources_filter.setPlaceholderText(self.tr("Filter cited sources by document or concept..."))
        self.sources_filter.setClearButtonEnabled(True)

        self.sources_tree = QTreeView()
        self.sources_tree.setObjectName("sourcesTree")
        self.sources_tree.setModel(self.sources_proxy)
        self.sources_tree.setAlternatingRowColors(True)
        self.sources_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sources_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sources_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sources_tree.setSortingEnabled(True)
        self.sources_tree.setUniformRowHeights(True)

        layout.addWidget(self.sources_filter)
        layout.addWidget(self.sources_tree, stretch=1)

        self.content_tabs.addTab(tab, icon("citation"), self.tr("Cited Knowledge Sources"))

    def _setup_log_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.tutor_status_label = QLabel(self.tr("Tutor Status: Idle"))
        self.tutor_status_label.setObjectName("tutorStatusLabel")
        self.tutor_status_label.setWordWrap(True)
        self.tutor_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tutor_status_label.setMinimumHeight(28)

        self.operation_log = QTextBrowser()
        self.operation_log.setObjectName("tutorOperationLog")
        self.operation_log.setReadOnly(True)
        self.operation_log.setFont(QFont("Consolas", 10))

        layout.addWidget(self.tutor_status_label)
        layout.addWidget(self.operation_log, stretch=1)

        self.content_tabs.addTab(tab, icon("info"), self.tr("Session Telemetry"))

    def _setup_bottom_bar(self, main_layout: QVBoxLayout) -> None:
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(6, 4, 6, 4)
        bottom_bar.setSpacing(8)

        self.overall_status_label = QLabel(self.tr("Ready. Select a document and ask a study question."))
        self.overall_status_label.setObjectName("tutorBottomStatus")
        bottom_bar.addWidget(self.overall_status_label, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(220)
        self.progress_bar.setFixedHeight(12)
        bottom_bar.addWidget(self.progress_bar)

        main_layout.addLayout(bottom_bar)

    def _setup_sources_model_headers(self) -> None:
        self.sources_model.setHorizontalHeaderLabels([
            self.tr("#"),
            self.tr("Grounded Knowledge Source"),
            self.tr("Relevance"),
        ])

    def _configure_sources_tree(self) -> None:
        header = self.sources_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self.SRC_COL_INDEX, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.SRC_COL_SOURCE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.SRC_COL_SCORE, QHeaderView.ResizeMode.Interactive)
        self.sources_tree.setColumnWidth(self.SRC_COL_SCORE, 120)

    def _setup_shortcuts(self) -> None:
        self.find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.find_shortcut.activated.connect(lambda: self.chat_input.setFocus())

    def _connect_signals(self) -> None:
        self.ask_btn.clicked.connect(self.ask_question)
        self.chat_input.returnPressed.connect(self.ask_question)
        self.clear_chat_btn.clicked.connect(self.clear_chat)
        self.sources_filter.textChanged.connect(self.sources_proxy.set_text_filter)
        self.sources_tree.customContextMenuRequested.connect(self._show_sources_context_menu)

        self.tutor_manager.tutorStarted.connect(self._on_manager_tutor_started)
        self.tutor_manager.tutorFinished.connect(self._on_manager_tutor_finished)
        self.tutor_manager.tutorFailed.connect(self._on_manager_tutor_failed)
        self.tutor_manager.tutorAnswerReady.connect(self.tutorAnswerReady.emit)
        self.tutor_manager.statusMessage.connect(self._append_status_message)
        self.tutor_manager.operationStarted.connect(self.operationStarted.emit)
        self.tutor_manager.operationFinished.connect(self.operationFinished.emit)

    def _post_init_setup(self) -> None:
        self._restore_settings()
        self._update_ui_for_operation_status()

    def _load_local_styles(self) -> None:
        qss_path = Path(__file__).parent / "tutor.qss"
        if qss_path.exists():
            apply_local_qss(self, qss_path)

    def _restore_settings(self) -> None:
        language = self.settings.value("Tutor/language", "English")
        persona = self.settings.value("Tutor/persona", TutorPersona.SIMPLE.value)
        top_k = self.settings.value("Tutor/top_k", 5)
        max_tokens = self.settings.value("Tutor/max_tokens", 900)

        self._set_combo_text(self.language_combo, str(language))
        self._set_combo_text(self.persona_combo, str(persona))

        try:
            self.top_k_spin.setValue(int(top_k))
        except Exception:
            self.top_k_spin.setValue(5)

        try:
            self.max_tokens_spin.setValue(int(max_tokens))
        except Exception:
            self.max_tokens_spin.setValue(900)

    def _save_settings(self) -> None:
        self.settings.setValue("Tutor/language", self.language_combo.currentText())
        self.settings.setValue("Tutor/persona", self.persona_combo.currentText())
        self.settings.setValue("Tutor/top_k", self.top_k_spin.value())
        self.settings.setValue("Tutor/max_tokens", self.max_tokens_spin.value())
        self.settings.sync()

    @staticmethod
    def _set_combo_text(combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @Slot(int)
    def set_document(self, document_id: int) -> None:
        self.document_id = int(document_id)
        self.active_document_title = None
        self.current_answer = None
        self.sources_model.removeRows(0, self.sources_model.rowCount())
        self.overall_status_label.setText(self.tr(f"Document #{document_id} active. Ready for questions."))
        self.tutor_status_label.setText(self.tr(f"Document #{document_id} linked."))
        self.grounding_badge.setText(self.tr(f"Curriculum-grounded tutor | Active Document #{document_id}"))
        self._update_ui_for_operation_status()

    @Slot(dict)
    def apply_equity_profile(self, profile: dict[str, Any]) -> None:
        self._equity_profile = dict(profile or {})
        language = str(self._equity_profile.get("target_language") or "")
        preferred_model = str(self._equity_profile.get("preferred_model") or "")
        max_context_tokens = self._equity_profile.get("max_context_tokens")

        if language:
            self._set_combo_text(self.language_combo, language)

        if max_context_tokens:
            try:
                self.max_tokens_spin.setValue(min(max(int(max_context_tokens), 128), 4096))
            except Exception:
                pass

        self.tutor_manager.apply_equity_profile(self._equity_profile)
        if preferred_model:
            self._append_status_message(f"Equity Switch preferred model: {preferred_model}", "INFO")

        self._update_ui_for_operation_status()

    @Slot()
    def ask_question(self) -> None:
        if self._is_operation_active:
            return

        question = self.chat_input.text().strip()
        if not question:
            QMessageBox.information(self, self.tr("Question Required"), self.tr("Please type a question or study topic."))
            return

        self._save_settings()

        request = TutorRequest(
            question=question,
            document_id=self.document_id,
            top_k=self.top_k_spin.value(),
            max_tokens=self.max_tokens_spin.value(),
            active_tab="Tutor",
            active_document_title=self.active_document_title,
            session_id=f"student:document:{self.document_id}" if self.document_id is not None else "student:global",
            target_language=self.language_combo.currentText(),
            simple_language=bool(self._equity_profile.get("simple_language", True)),
            persona=TutorPersona.coerce(self.persona_combo.currentText()),
            preferred_model=str(self._equity_profile.get("preferred_model", "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M")),
        )

        user_card = InteractiveMessageCard(sender="Student", text=question)
        self.chat_layout.addWidget(user_card)
        self._message_cards.append(user_card)
        self.chat_input.clear()
        self._scroll_chat_to_bottom()

        self.tutor_manager.ask(request.to_dict())

    def _submit_prompt_chip(self, query: str) -> None:
        clean = re.sub(r"^[^\w]+", "", query).strip()
        self.chat_input.setText(clean)
        self.ask_question()

    @Slot()
    def clear_chat(self) -> None:
        _clear_layout(self.chat_layout)
        self._message_cards.clear()
        self.sources_model.removeRows(0, self.sources_model.rowCount())
        self.current_answer = None

        welcome = InteractiveMessageCard(
            sender="AmbaAI",
            text="Session cleared. Ready for your next inquiry.",
        )
        self.chat_layout.addWidget(welcome)
        self._message_cards.append(welcome)

        self.overall_status_label.setText(self.tr("Session reset."))
        self.tutor_status_label.setText(self.tr("Tutor Status: Idle"))

    @Slot(str)
    def _on_manager_tutor_started(self, question: str) -> None:
        self._is_operation_active = True
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.tutor_status_label.setText(self.tr("Consulting curriculum knowledge base..."))
        self.overall_status_label.setText(self.tr("Generating tutor answer..."))
        self._update_ui_for_operation_status()

    @Slot(dict)
    def _on_manager_tutor_finished(self, payload: dict[str, Any]) -> None:
        self._is_operation_active = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)

        sources = [
            TutorSourceViewModel(
                index=int(item.get("index") or idx),
                source=str(item.get("source") or "Grounded Material"),
                relevance_score=float(item.get("relevance_score") or 1.0),
            )
            for idx, item in enumerate(list(payload.get("sources") or []), start=1)
            if isinstance(item, dict)
        ]

        snippets = [
            TutorCodeSnippet(
                code=str(s.get("code") or ""),
                language=str(s.get("language") or "bash"),
                title=str(s.get("title") or "CLI Execution"),
            )
            for s in list(payload.get("code_snippets") or [])
            if isinstance(s, dict)
        ]

        answer = TutorAnswerViewModel(
            question=str(payload.get("question") or ""),
            answer_text=str(payload.get("answer_text") or ""),
            model_name=str(payload.get("model_name") or "amba-tutor"),
            sources=sources,
            document_id=payload.get("document_id"),
            fallback=bool(payload.get("fallback", False)),
            low_confidence=bool(payload.get("low_confidence", False)),
            key_points=list(payload.get("key_points") or []),
            code_snippets=snippets,
            metadata=dict(payload.get("metadata") or {}),
        )
        self.current_answer = answer

        response_card = InteractiveMessageCard(
            sender="AmbaAI",
            text=answer.answer_text,
            model_name=answer.model_name,
            key_points=answer.key_points,
            code_snippets=answer.code_snippets,
            sources=answer.sources,
        )
        response_card.saveNotesRequested.connect(lambda txt: self.navigateToNotesConcept.emit(self.document_id or 0, txt[:100]))
        response_card.createFlashcardRequested.connect(lambda q, a: self.navigateToStudyConcept.emit(self.document_id or 0, q))
        response_card.explainSimplerRequested.connect(self._request_simpler_explanation)

        self.chat_layout.addWidget(response_card)
        self._message_cards.append(response_card)
        self._scroll_chat_to_bottom()

        self._display_sources(answer.sources)

        label = self.tr(f"Answer synthesized · Model: {answer.model_name} · Sources: {len(answer.sources)}")
        self.tutor_status_label.setText(label)
        self.overall_status_label.setText(label)
        self._append_status_message(label, "INFO")
        self.tutorAnswerReady.emit(answer.answer_text)
        self._update_ui_for_operation_status()

    def _request_simpler_explanation(self, context_text: str) -> None:
        self.persona_combo.setCurrentText(TutorPersona.SIMPLE.value)
        self.chat_input.setText("Can you break this down in even simpler terms with an analogy?")
        self.ask_question()

    def _scroll_chat_to_bottom(self) -> None:
        QTimer.singleShot(50, lambda: self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum()))

    @Slot(dict)
    def _on_manager_tutor_failed(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        self.progress_bar.setVisible(False)
        message = str(error_context.get("error_message") or "Tutor synthesis error.")
        self.tutor_status_label.setText(message)
        self.overall_status_label.setText(message)
        self._append_status_message(message, "ERROR")
        self.tutorError.emit(error_context)
        self._update_ui_for_operation_status()

    def _display_sources(self, sources: list[TutorSourceViewModel]) -> None:
        self.sources_tree.setSortingEnabled(False)
        self.sources_model.removeRows(0, self.sources_model.rowCount())

        root = self.sources_model.invisibleRootItem()
        for source in sources:
            score_text = f"{int(source.relevance_score * 100)}%" if source.relevance_score <= 1.0 else "High"
            row = [
                QStandardItem(str(source.index)),
                QStandardItem(source.source),
                QStandardItem(score_text),
            ]
            row[0].setData(source.to_dict(), Qt.ItemDataRole.UserRole)
            for item in row:
                item.setEditable(False)
            root.appendRow(row)

        self.sources_tree.setSortingEnabled(True)

    @Slot(QPoint)
    def _show_sources_context_menu(self, pos: QPoint) -> None:
        proxy_index = self.sources_tree.indexAt(pos)
        if not proxy_index.isValid():
            return

        source_index = self.sources_proxy.mapToSource(proxy_index)
        item = self.sources_model.item(source_index.row(), self.SRC_COL_INDEX)
        if item is None or not isinstance(item.data(Qt.ItemDataRole.UserRole), dict):
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        source = TutorSourceViewModel(index=int(data.get("index") or 0), source=str(data.get("source") or ""))

        menu = QMenu(self.sources_tree)
        copy_source = menu.addAction(self.tr("Copy Source Citation"))
        copy_source.triggered.connect(lambda: QApplication.clipboard().setText(source.source))
        menu.exec(self.sources_tree.viewport().mapToGlobal(pos))

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
        safe = html.escape(str(message))
        self.operation_log.append(
            f'<span style="color:#94A3B8;">[{timestamp}]</span> '
            f'<b style="color:{color};">[{level.upper()}]</b> {safe}'
        )
        self.statusMessage.emit(message, level)

    def _update_ui_for_operation_status(self) -> None:
        inactive = not self._is_operation_active
        self.ask_btn.setEnabled(inactive)
        self.chat_input.setEnabled(inactive)
        self.clear_chat_btn.setEnabled(inactive)
        self.language_combo.setEnabled(inactive)
        self.persona_combo.setEnabled(inactive)
        self.top_k_spin.setEnabled(inactive)
        self.max_tokens_spin.setEnabled(inactive)

    def cleanup_before_close(self) -> None:
        self._save_settings()
        self.tutor_manager.cleanup_before_close()
        logger.info("TutorWidget cleanup completed.")

    def retranslateUi(self) -> None:
        self.top_toolbar.setWindowTitle(self.tr("Tutor Controls"))
        self.clear_chat_btn.setText(self.tr("Clear Session"))
        self.ask_btn.setText(self.tr("Ask Tutor"))
        self.chat_input.setPlaceholderText(self.tr("Ask a question about the active learning material..."))
        self.content_tabs.setTabText(0, self.tr("Interactive Chat"))
        self.content_tabs.setTabText(1, self.tr("Cited Knowledge Sources"))
        self.content_tabs.setTabText(2, self.tr("Session Telemetry"))
        self.sources_filter.setPlaceholderText(self.tr("Filter cited sources by document or concept..."))
        self._setup_sources_model_headers()