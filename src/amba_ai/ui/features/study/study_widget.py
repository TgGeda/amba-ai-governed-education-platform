from __future__ import annotations

import html
import json
from pathlib import Path
import random
import re
from typing import Any, Optional

from PySide6.QtCore import (
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
    QFileDialog,
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

from amba_ai.core.export import export_flashcards_csv, export_mcqs_csv
from amba_ai.exceptions import ExportError
from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from amba_ai.ui.common.qss_utils import apply_local_qss
from amba_ai.ui.common.ui_icons_utils import icon
from .data_classes import (
    FlashcardViewModel,
    MCQViewModel,
    StudyAssetsViewModel,
    StudyGenerationRequest,
)
from .study_manager import StudyManager

RATING_INTERVALS = {"Again": 0, "Hard": 1, "Good": 3, "Easy": 7}


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
        self.title = title or f"{self.language.upper()} Syntax Execution"
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
        calculated_height = min(max(line_count * 20 + 26, 64), 260)
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


class StudyFilterProxyModel(QSortFilterProxyModel):
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


class ChoiceCardWidget(QPushButton):
    def __init__(self, index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.choice_index = index
        self.choice_letter = chr(65 + index)
        self.choice_text = ""
        self.setObjectName("choiceCardButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setCheckable(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        self.pill_label = QLabel(self.choice_letter)
        self.pill_label.setObjectName("choicePill")
        self.pill_label.setFixedSize(28, 28)
        self.pill_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.text_label = QLabel("")
        self.text_label.setObjectName("choiceText")
        self.text_label.setWordWrap(True)

        self.status_icon = QLabel("")
        self.status_icon.setObjectName("choiceStatusIcon")
        self.status_icon.setFixedWidth(24)
        self.status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.pill_label)
        layout.addWidget(self.text_label, stretch=1)
        layout.addWidget(self.status_icon)

    def set_content(self, text: str) -> None:
        self.choice_text = text
        self.text_label.setText(text)
        self.setChecked(False)
        self.setEnabled(True)
        self.setProperty("state", "normal")
        self.status_icon.setText("")
        self.style().unpolish(self)
        self.style().polish(self)

    def mark_correct(self) -> None:
        self.setProperty("state", "correct")
        self.status_icon.setText("✓")
        self.style().unpolish(self)
        self.style().polish(self)

    def mark_incorrect(self) -> None:
        self.setProperty("state", "incorrect")
        self.status_icon.setText("✕")
        self.style().unpolish(self)
        self.style().polish(self)

    def reset_state(self) -> None:
        self.setProperty("state", "normal")
        self.status_icon.setText("")
        self.style().unpolish(self)
        self.style().polish(self)


class StudyWidget(QWidget):
    studyAssetsGenerated = Signal(int)
    flashcardsExported = Signal(str)
    mcqsExported = Signal(str)
    statusMessage = Signal(str, str)
    operationStarted = Signal(str)
    operationFinished = Signal(str)

    FC_COL_INDEX = 0
    FC_COL_QUESTION = 1
    FC_COL_ANSWER = 2
    FC_COL_CONCEPT = 3
    FC_COL_SOURCE = 4
    FC_MODEL_COLUMNS = 5

    MCQ_COL_INDEX = 0
    MCQ_COL_QUESTION = 1
    MCQ_COL_CORRECT = 2
    MCQ_COL_CONCEPT = 3
    MCQ_COL_SOURCE = 4
    MCQ_COL_CHOICES_HIDDEN = 5
    MCQ_COL_EXPLANATION_HIDDEN = 6
    MCQ_MODEL_COLUMNS = 7

    def __init__(
        self,
        settings: QSettings,
        job_service: JobService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.settings = settings
        self.jobs = job_service
        self.study_manager = StudyManager(job_service, self)

        self.document_id: int | None = None
        self.current_assets: StudyAssetsViewModel | None = None
        self._is_operation_active = False
        self._equity_profile: dict[str, Any] = {}

        self._card_order: list[int] = []
        self._card_position: int = 0
        self._answer_revealed: bool = False
        self._mastery: dict[str, Any] = {}
        self._quiz_position: int = 0
        self._quiz_answers: dict[str, Any] = {}
        self._streak_count: int = 0

        self.flashcards_model = QStandardItemModel(0, self.FC_MODEL_COLUMNS, self)
        self.flashcards_proxy = StudyFilterProxyModel(self)
        self.flashcards_proxy.setSourceModel(self.flashcards_model)

        self.mcqs_model = QStandardItemModel(0, self.MCQ_MODEL_COLUMNS, self)
        self.mcqs_proxy = StudyFilterProxyModel(self)
        self.mcqs_proxy.setSourceModel(self.mcqs_model)

        self.setObjectName("AmbaStudyWidgetUI")

        self._setup_ui()
        self._connect_signals()
        self._load_local_styles()
        self._post_init_setup()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        self._setup_toolbar(main_layout)
        self._setup_tabs(main_layout)
        self._setup_bottom_bar(main_layout)

        self._setup_flashcards_model_headers()
        self._setup_mcqs_model_headers()
        self._configure_flashcards_tree()
        self._configure_mcqs_tree()

    def _setup_toolbar(self, main_layout: QVBoxLayout) -> None:
        self.top_toolbar = QToolBar(self.tr("Study Controls"), self)
        self.top_toolbar.setObjectName("studyToolbar")
        self.top_toolbar.setIconSize(QSize(18, 18))
        self.top_toolbar.setMovable(False)
        self.top_toolbar.setFloatable(False)

        lang_lbl = QLabel("Language:")
        lang_lbl.setObjectName("controlRibbonLabel")
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("studyLanguageCombo")
        self.language_combo.addItems(["English", "Amharic", "Afaan Oromo", "Tigrinya", "Somali"])

        self.flashcard_count_spin = QSpinBox()
        self.flashcard_count_spin.setObjectName("flashcardCountSpin")
        self.flashcard_count_spin.setRange(1, 50)
        self.flashcard_count_spin.setValue(10)
        self.flashcard_count_spin.setPrefix(self.tr("Cards: "))

        self.mcq_count_spin = QSpinBox()
        self.mcq_count_spin.setObjectName("mcqCountSpin")
        self.mcq_count_spin.setRange(1, 50)
        self.mcq_count_spin.setValue(10)
        self.mcq_count_spin.setPrefix(self.tr("Quiz: "))

        self.force_combo = QComboBox()
        self.force_combo.setObjectName("forceStudyCombo")
        self.force_combo.addItems([self.tr("Cached Assets"), self.tr("Regenerate Fresh")])

        self.generate_btn = QPushButton(icon("study-pack"), self.tr("Synthesize Pack"))
        self.generate_btn.setObjectName("generateStudyButton")
        self.generate_btn.setProperty("priority", "primary")
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.export_flashcards_btn = QPushButton(icon("file-csv"), self.tr("Export Cards"))
        self.export_flashcards_btn.setObjectName("exportFlashcardsButton")
        self.export_flashcards_btn.setProperty("variant", "secondary")
        self.export_flashcards_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.export_mcqs_btn = QPushButton(icon("file-csv"), self.tr("Export Quiz"))
        self.export_mcqs_btn.setObjectName("exportMcqsButton")
        self.export_mcqs_btn.setProperty("variant", "secondary")
        self.export_mcqs_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.top_toolbar.addWidget(lang_lbl)
        self.top_toolbar.addWidget(self.language_combo)
        self.top_toolbar.addWidget(self.flashcard_count_spin)
        self.top_toolbar.addWidget(self.mcq_count_spin)
        self.top_toolbar.addWidget(self.force_combo)
        self.top_toolbar.addWidget(self.generate_btn)
        self.top_toolbar.addWidget(self.export_flashcards_btn)
        self.top_toolbar.addWidget(self.export_mcqs_btn)

        main_layout.addWidget(self.top_toolbar)

    def _setup_tabs(self, main_layout: QVBoxLayout) -> None:
        self.content_tabs = QTabWidget()
        self.content_tabs.setIconSize(QSize(16, 16))

        self._setup_study_session_tab()
        self._setup_quiz_session_tab()
        self._setup_flashcards_tab()
        self._setup_quiz_tab()
        self._setup_details_tab()
        self._setup_log_tab()

        main_layout.addWidget(self.content_tabs, stretch=1)

    def _setup_study_session_tab(self) -> None:
        study_scroll = QScrollArea()
        study_scroll.setWidgetResizable(True)
        study_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        study_scroll.setFrameShape(QFrame.Shape.NoFrame)

        study_page = QWidget()
        study_layout = QVBoxLayout(study_page)
        study_layout.setContentsMargins(16, 14, 16, 16)
        study_layout.setSpacing(12)

        metrics_frame = QFrame()
        metrics_frame.setObjectName("studyMetricsFrame")
        metrics_layout = QHBoxLayout(metrics_frame)
        metrics_layout.setContentsMargins(14, 10, 14, 10)
        metrics_layout.setSpacing(16)

        self.card_progress_label = QLabel(self.tr("Card 0 of 0"))
        self.card_progress_label.setObjectName("metricsPrimaryLabel")
        self.card_reviewed_label = QLabel(self.tr("Mastered: 0 | Learning: 0"))
        self.card_reviewed_label.setObjectName("metricsSecondaryLabel")

        self.card_progress_bar = QProgressBar()
        self.card_progress_bar.setObjectName("cardSessionProgress")
        self.card_progress_bar.setTextVisible(False)
        self.card_progress_bar.setFixedHeight(8)

        self.shuffle_btn = QPushButton("🔀 Shuffle")
        self.shuffle_btn.setObjectName("learningCompactAction")
        self.shuffle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.shuffle_btn.clicked.connect(self._shuffle_active_cards)

        metrics_layout.addWidget(self.card_progress_label)
        metrics_layout.addWidget(self.card_progress_bar, 1)
        metrics_layout.addWidget(self.card_reviewed_label)
        metrics_layout.addWidget(self.shuffle_btn)
        study_layout.addWidget(metrics_frame)

        self.card_container = QFrame()
        self.card_container.setObjectName("interactiveCardSurface")
        card_inner_layout = QVBoxLayout(self.card_container)
        card_inner_layout.setContentsMargins(22, 20, 22, 20)
        card_inner_layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.concept_badge = QLabel("API & RECON")
        self.concept_badge.setObjectName("conceptPillBadge")
        self.difficulty_badge = QLabel("MEDIUM")
        self.difficulty_badge.setObjectName("difficultyBadge")
        self.rating_status_badge = QLabel("NEW")
        self.rating_status_badge.setObjectName("ratingStatusBadge")

        header_row.addWidget(self.concept_badge)
        header_row.addWidget(self.difficulty_badge)
        header_row.addStretch(1)
        header_row.addWidget(self.rating_status_badge)
        card_inner_layout.addLayout(header_row)

        self.card_question_label = QLabel(self.tr("Select or generate study assets to begin active recall."))
        self.card_question_label.setObjectName("cardQuestionTitle")
        self.card_question_label.setWordWrap(True)
        self.card_question_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_inner_layout.addWidget(self.card_question_label)

        self.card_code_block = InteractiveTerminalBlock(code="", language="bash", title="Associated Command")
        self.card_code_block.setVisible(False)
        card_inner_layout.addWidget(self.card_code_block)

        self.answer_box = QFrame()
        self.answer_box.setObjectName("answerSurfaceFrame")
        answer_layout = QVBoxLayout(self.answer_box)
        answer_layout.setContentsMargins(16, 14, 16, 14)
        answer_layout.setSpacing(10)

        answer_header = QLabel(self.tr("VERIFIED SYNTHESIS & ANSWER"))
        answer_header.setObjectName("answerHeaderTag")
        self.card_answer_label = QLabel("")
        self.card_answer_label.setObjectName("cardAnswerText")
        self.card_answer_label.setWordWrap(True)
        self.card_answer_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.card_source_label = QLabel("")
        self.card_source_label.setObjectName("cardSourceText")

        answer_layout.addWidget(answer_header)
        answer_layout.addWidget(self.card_answer_label)
        answer_layout.addWidget(self.card_source_label)
        self.answer_box.setVisible(False)
        card_inner_layout.addWidget(self.answer_box)

        study_layout.addWidget(self.card_container, 1)

        primary_controls = QHBoxLayout()
        primary_controls.setSpacing(12)
        self.card_previous_btn = QPushButton(self.tr("← Previous"))
        self.card_reveal_btn = QPushButton(self.tr("Reveal Answer (Space)"))
        self.card_reveal_btn.setObjectName("primaryActionButton")
        self.card_reveal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.card_next_btn = QPushButton(self.tr("Next →"))

        primary_controls.addWidget(self.card_previous_btn)
        primary_controls.addWidget(self.card_reveal_btn, 2)
        primary_controls.addWidget(self.card_next_btn)
        study_layout.addLayout(primary_controls)

        rating_box = QFrame()
        rating_box.setObjectName("srsRatingBar")
        rating_box_layout = QVBoxLayout(rating_box)
        rating_box_layout.setContentsMargins(12, 10, 12, 10)
        rating_box_layout.setSpacing(8)

        self.rating_instruction = QLabel(self.tr("Reveal the answer to rate retention with SuperMemo intervals."))
        self.rating_instruction.setObjectName("ratingInstructionText")
        self.rating_instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rating_box_layout.addWidget(self.rating_instruction)

        rating_buttons_row = QHBoxLayout()
        rating_buttons_row.setSpacing(10)
        self.rating_buttons_map: dict[str, QPushButton] = {}
        rating_defs = [
            ("Again", self.tr("1 · Again (Now)")),
            ("Hard", self.tr("2 · Hard (1d)")),
            ("Good", self.tr("3 · Good (3d)")),
            ("Easy", self.tr("4 · Easy (7d)")),
        ]
        for key, text in rating_defs:
            btn = QPushButton(text)
            btn.setObjectName(f"ratingBtn{key}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setEnabled(False)
            btn.clicked.connect(lambda _=False, k=key: self._rate_active_card(k))
            self.rating_buttons_map[key] = btn
            rating_buttons_row.addWidget(btn, 1)
        rating_box_layout.addLayout(rating_buttons_row)
        study_layout.addWidget(rating_box)

        study_scroll.setWidget(study_page)
        self.content_tabs.addTab(study_scroll, icon("flashcards"), self.tr("Interactive Recall"))

        self.card_previous_btn.clicked.connect(lambda: self._move_active_card(-1))
        self.card_next_btn.clicked.connect(lambda: self._move_active_card(1))
        self.card_reveal_btn.clicked.connect(self._toggle_answer_reveal)

        shortcuts = [
            ("Space", self._toggle_answer_reveal),
            ("Left", lambda: self._move_active_card(-1)),
            ("Right", lambda: self._move_active_card(1)),
            ("S", self._shuffle_active_cards),
            ("1", lambda: self._rate_if_enabled("Again")),
            ("2", lambda: self._rate_if_enabled("Hard")),
            ("3", lambda: self._rate_if_enabled("Good")),
            ("4", lambda: self._rate_if_enabled("Easy")),
        ]
        for key, callback in shortcuts:
            sc = QShortcut(QKeySequence(key), study_page)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(callback)

    def _setup_quiz_session_tab(self) -> None:
        quiz_scroll = QScrollArea()
        quiz_scroll.setWidgetResizable(True)
        quiz_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        quiz_scroll.setFrameShape(QFrame.Shape.NoFrame)

        quiz_page = QWidget()
        quiz_layout = QVBoxLayout(quiz_page)
        quiz_layout.setContentsMargins(16, 14, 16, 16)
        quiz_layout.setSpacing(12)

        quiz_metrics = QFrame()
        quiz_metrics.setObjectName("studyMetricsFrame")
        quiz_metrics_layout = QHBoxLayout(quiz_metrics)
        quiz_metrics_layout.setContentsMargins(14, 10, 14, 10)
        quiz_metrics_layout.setSpacing(16)

        self.quiz_progress_label = QLabel(self.tr("Question 0 of 0"))
        self.quiz_progress_label.setObjectName("metricsPrimaryLabel")
        self.quiz_streak_label = QLabel(self.tr("Streak: 🔥 0"))
        self.quiz_streak_label.setObjectName("metricsStreakLabel")
        self.quiz_score_label = QLabel(self.tr("Score: 0 / 0 (0%)"))
        self.quiz_score_label.setObjectName("metricsSecondaryLabel")

        self.quiz_progress_bar = QProgressBar()
        self.quiz_progress_bar.setObjectName("quizSessionProgress")
        self.quiz_progress_bar.setTextVisible(False)
        self.quiz_progress_bar.setFixedHeight(8)

        quiz_metrics_layout.addWidget(self.quiz_progress_label)
        quiz_metrics_layout.addWidget(self.quiz_progress_bar, 1)
        quiz_metrics_layout.addWidget(self.quiz_streak_label)
        quiz_metrics_layout.addWidget(self.quiz_score_label)
        quiz_layout.addWidget(quiz_metrics)

        self.quiz_question_card = QFrame()
        self.quiz_question_card.setObjectName("interactiveCardSurface")
        qq_layout = QVBoxLayout(self.quiz_question_card)
        qq_layout.setContentsMargins(22, 20, 22, 20)
        qq_layout.setSpacing(12)

        self.quiz_concept_badge = QLabel("QUIZ CHECK")
        self.quiz_concept_badge.setObjectName("conceptPillBadge")
        qq_layout.addWidget(self.quiz_concept_badge)

        self.quiz_question_text = QLabel(self.tr("Select or generate study assets to begin quiz."))
        self.quiz_question_text.setObjectName("cardQuestionTitle")
        self.quiz_question_text.setWordWrap(True)
        self.quiz_question_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        qq_layout.addWidget(self.quiz_question_text)

        self.quiz_code_block = InteractiveTerminalBlock(code="", language="bash", title="Target Command Context")
        self.quiz_code_block.setVisible(False)
        qq_layout.addWidget(self.quiz_code_block)

        quiz_layout.addWidget(self.quiz_question_card)

        self.choice_cards_container = QWidget()
        self.choice_cards_layout = QVBoxLayout(self.choice_cards_container)
        self.choice_cards_layout.setContentsMargins(0, 4, 0, 4)
        self.choice_cards_layout.setSpacing(10)
        self.choice_buttons: list[ChoiceCardWidget] = []

        for idx in range(4):
            btn = ChoiceCardWidget(idx, self)
            btn.clicked.connect(lambda _=False, i=idx: self._select_choice(i))
            self.choice_buttons.append(btn)
            self.choice_cards_layout.addWidget(btn)
        quiz_layout.addWidget(self.choice_cards_container)

        self.quiz_explanation_frame = QFrame()
        self.quiz_explanation_frame.setObjectName("quizExplanationSurface")
        exp_layout = QVBoxLayout(self.quiz_explanation_frame)
        exp_layout.setContentsMargins(16, 14, 16, 14)
        exp_layout.setSpacing(8)

        self.explanation_verdict = QLabel("")
        self.explanation_verdict.setObjectName("explanationVerdict")
        self.explanation_text = QLabel("")
        self.explanation_text.setObjectName("explanationBodyText")
        self.explanation_text.setWordWrap(True)

        exp_layout.addWidget(self.explanation_verdict)
        exp_layout.addWidget(self.explanation_text)
        self.quiz_explanation_frame.setVisible(False)
        quiz_layout.addWidget(self.quiz_explanation_frame)

        quiz_nav = QHBoxLayout()
        quiz_nav.setSpacing(12)
        self.quiz_prev_btn = QPushButton(self.tr("← Previous"))
        self.quiz_submit_btn = QPushButton(self.tr("Submit Answer (Enter)"))
        self.quiz_submit_btn.setObjectName("primaryActionButton")
        self.quiz_submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quiz_retry_btn = QPushButton(self.tr("Retry Missed Questions"))
        self.quiz_next_btn = QPushButton(self.tr("Next →"))

        quiz_nav.addWidget(self.quiz_prev_btn)
        quiz_nav.addWidget(self.quiz_submit_btn, 2)
        quiz_nav.addWidget(self.quiz_retry_btn)
        quiz_nav.addWidget(self.quiz_next_btn)
        quiz_layout.addLayout(quiz_nav)

        quiz_scroll.setWidget(quiz_page)
        self.content_tabs.addTab(quiz_scroll, icon("quiz"), self.tr("Quiz Arena"))

        self.quiz_prev_btn.clicked.connect(lambda: self._move_quiz(-1))
        self.quiz_next_btn.clicked.connect(lambda: self._move_quiz(1))
        self.quiz_submit_btn.clicked.connect(self._submit_quiz_answer)
        self.quiz_retry_btn.clicked.connect(self._retry_incorrect_quiz)

        quiz_shortcuts = [
            ("A", lambda: self._select_choice(0)),
            ("B", lambda: self._select_choice(1)),
            ("C", lambda: self._select_choice(2)),
            ("D", lambda: self._select_choice(3)),
            ("Return", self._submit_quiz_answer),
            ("Enter", self._submit_quiz_answer),
        ]
        for key, callback in quiz_shortcuts:
            sc = QShortcut(QKeySequence(key), quiz_page)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(callback)

    def _setup_flashcards_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        filter_row = QHBoxLayout()
        self.flashcards_filter = QLineEdit()
        self.flashcards_filter.setObjectName("flashcardsFilter")
        self.flashcards_filter.setPlaceholderText(self.tr("Filter flashcards by question, code, concept, or tag..."))
        self.flashcards_filter.setClearButtonEnabled(True)
        filter_row.addWidget(self.flashcards_filter, stretch=1)

        self.flashcards_tree = QTreeView()
        self.flashcards_tree.setObjectName("flashcardsTree")
        self.flashcards_tree.setModel(self.flashcards_proxy)
        self.flashcards_tree.setAlternatingRowColors(True)
        self.flashcards_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.flashcards_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.flashcards_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.flashcards_tree.setSortingEnabled(True)
        self.flashcards_tree.setUniformRowHeights(True)

        layout.addLayout(filter_row)
        layout.addWidget(self.flashcards_tree, stretch=1)
        self.content_tabs.addTab(tab, icon("flashcards"), self.tr("Flashcards Directory"))

    def _setup_quiz_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        filter_row = QHBoxLayout()
        self.mcqs_filter = QLineEdit()
        self.mcqs_filter.setObjectName("mcqsFilter")
        self.mcqs_filter.setPlaceholderText(self.tr("Filter questions by keyword or concept..."))
        self.mcqs_filter.setClearButtonEnabled(True)
        filter_row.addWidget(self.mcqs_filter, stretch=1)

        self.mcqs_tree = QTreeView()
        self.mcqs_tree.setObjectName("mcqsTree")
        self.mcqs_tree.setModel(self.mcqs_proxy)
        self.mcqs_tree.setAlternatingRowColors(True)
        self.mcqs_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.mcqs_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mcqs_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.mcqs_tree.setSortingEnabled(True)
        self.mcqs_tree.setUniformRowHeights(True)

        layout.addLayout(filter_row)
        layout.addWidget(self.mcqs_tree, stretch=1)
        self.content_tabs.addTab(tab, icon("quiz"), self.tr("Quiz Directory"))

    def _setup_details_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.details_view = QTextBrowser()
        self.details_view.setObjectName("studyDetailsView")
        self.details_view.setReadOnly(True)
        self.details_view.setOpenExternalLinks(True)

        layout.addWidget(QLabel(self.tr("<b>Pedagogical Deep Dive & Verified Citation:</b>")))
        layout.addWidget(self.details_view, stretch=1)
        self.content_tabs.addTab(tab, icon("info"), self.tr("Item Details"))

    def _setup_log_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.study_status_label = QLabel(self.tr("Study Engine: Idle"))
        self.study_status_label.setObjectName("studyStatusLabel")
        self.study_status_label.setWordWrap(True)
        self.study_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.study_status_label.setMinimumHeight(32)

        self.operation_log = QTextBrowser()
        self.operation_log.setObjectName("studyOperationLog")
        self.operation_log.setReadOnly(True)
        self.operation_log.setFont(QFont("Consolas", 10))

        layout.addWidget(self.study_status_label)
        layout.addWidget(self.operation_log, stretch=1)
        self.content_tabs.addTab(tab, icon("info"), self.tr("Telemetry & Logs"))

    def _setup_bottom_bar(self, main_layout: QVBoxLayout) -> None:
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(6, 4, 6, 4)
        bottom_bar.setSpacing(10)

        self.overall_status_label = QLabel(self.tr("Ready. Load or select a document to generate structured study materials."))
        self.overall_status_label.setObjectName("bottomStatusLabel")
        bottom_bar.addWidget(self.overall_status_label, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(240)
        self.progress_bar.setFixedHeight(14)
        bottom_bar.addWidget(self.progress_bar)

        main_layout.addLayout(bottom_bar)

    def _setup_flashcards_model_headers(self) -> None:
        self.flashcards_model.setHorizontalHeaderLabels([
            self.tr("#"),
            self.tr("Active Recall Question"),
            self.tr("Synthesized Answer"),
            self.tr("Concept"),
            self.tr("Source Citation"),
        ])

    def _setup_mcqs_model_headers(self) -> None:
        self.mcqs_model.setHorizontalHeaderLabels([
            self.tr("#"),
            self.tr("Scenario Question"),
            self.tr("Correct Option"),
            self.tr("Concept"),
            self.tr("Source Citation"),
            "Choices_Hidden",
            "Explanation_Hidden",
        ])

    def _configure_flashcards_tree(self) -> None:
        header = self.flashcards_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self.FC_COL_INDEX, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.FC_COL_QUESTION, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.FC_COL_ANSWER, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.FC_COL_CONCEPT, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(self.FC_COL_SOURCE, QHeaderView.ResizeMode.Interactive)
        self.flashcards_tree.setColumnWidth(self.FC_COL_CONCEPT, 150)
        self.flashcards_tree.setColumnWidth(self.FC_COL_SOURCE, 180)

    def _configure_mcqs_tree(self) -> None:
        header = self.mcqs_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self.MCQ_COL_INDEX, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.MCQ_COL_QUESTION, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.MCQ_COL_CORRECT, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.MCQ_COL_CONCEPT, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(self.MCQ_COL_SOURCE, QHeaderView.ResizeMode.Interactive)
        self.mcqs_tree.setColumnWidth(self.MCQ_COL_CONCEPT, 150)
        self.mcqs_tree.setColumnWidth(self.MCQ_COL_SOURCE, 180)
        self.mcqs_tree.setColumnHidden(self.MCQ_COL_CHOICES_HIDDEN, True)
        self.mcqs_tree.setColumnHidden(self.MCQ_COL_EXPLANATION_HIDDEN, True)

    def _connect_signals(self) -> None:
        self.generate_btn.clicked.connect(self.generate_study_assets)
        self.export_flashcards_btn.clicked.connect(self.export_flashcards)
        self.export_mcqs_btn.clicked.connect(self.export_mcqs)

        self.flashcards_filter.textChanged.connect(self.flashcards_proxy.set_text_filter)
        self.mcqs_filter.textChanged.connect(self.mcqs_proxy.set_text_filter)

        self.flashcards_tree.customContextMenuRequested.connect(self._show_flashcards_context_menu)
        self.mcqs_tree.customContextMenuRequested.connect(self._show_mcqs_context_menu)

        flashcard_selection = self.flashcards_tree.selectionModel()
        if flashcard_selection is not None:
            flashcard_selection.currentChanged.connect(self._on_flashcard_selected)

        mcq_selection = self.mcqs_tree.selectionModel()
        if mcq_selection is not None:
            mcq_selection.currentChanged.connect(self._on_mcq_selected)

        self.study_manager.studyStarted.connect(self._on_manager_study_started)
        self.study_manager.studyFinished.connect(self._on_manager_study_finished)
        self.study_manager.studyFailed.connect(self._on_manager_study_failed)
        self.study_manager.studyAssetsGenerated.connect(self.studyAssetsGenerated.emit)
        self.study_manager.statusMessage.connect(self._append_status_message)
        self.study_manager.operationStarted.connect(self.operationStarted.emit)
        self.study_manager.operationFinished.connect(self.operationFinished.emit)

    def _post_init_setup(self) -> None:
        self._restore_settings()
        self._update_ui_for_operation_status()

    def _load_local_styles(self) -> None:
        qss_path = Path(__file__).parent / "study.qss"
        if qss_path.exists():
            apply_local_qss(self, qss_path)

    def _restore_settings(self) -> None:
        lang = self.settings.value("Study/language", "English")
        fc_count = self.settings.value("Study/flashcard_count", 10)
        mcq_count = self.settings.value("Study/mcq_count", 10)
        idx = self.language_combo.findText(str(lang))
        if idx >= 0:
            self.language_combo.setCurrentIndex(idx)
        try:
            self.flashcard_count_spin.setValue(int(fc_count))
        except Exception:
            self.flashcard_count_spin.setValue(10)
        try:
            self.mcq_count_spin.setValue(int(mcq_count))
        except Exception:
            self.mcq_count_spin.setValue(10)

    def _save_settings(self) -> None:
        self.settings.setValue("Study/language", self.language_combo.currentText())
        self.settings.setValue("Study/flashcard_count", self.flashcard_count_spin.value())
        self.settings.setValue("Study/mcq_count", self.mcq_count_spin.value())
        self.settings.sync()

    @Slot(int)
    def set_document(self, document_id: int) -> None:
        self.document_id = int(document_id)
        self.current_assets = None
        self.flashcards_model.removeRows(0, self.flashcards_model.rowCount())
        self.mcqs_model.removeRows(0, self.mcqs_model.rowCount())
        self.details_view.clear()

        self._card_order = []
        self._card_position = 0
        self._answer_revealed = False
        self._mastery = {}
        self._quiz_position = 0
        self._quiz_answers = {}
        self._streak_count = 0

        self._refresh_active_card()
        self._refresh_interactive_quiz()

        self.overall_status_label.setText(self.tr(f"Document #{document_id} loaded. Ready to synthesize study material."))
        self.study_status_label.setText(self.tr(f"Active Document: #{document_id}"))
        self._update_ui_for_operation_status()

    @Slot(dict)
    def apply_equity_profile(self, profile: dict[str, Any]) -> None:
        self._equity_profile = dict(profile or {})
        lang = str(self._equity_profile.get("target_language") or "")
        if lang:
            idx = self.language_combo.findText(lang)
            if idx >= 0:
                self.language_combo.setCurrentIndex(idx)
        self.study_manager.apply_equity_profile(self._equity_profile)

    @Slot()
    def generate_study_assets(self) -> None:
        if self.document_id is None:
            QMessageBox.warning(self, self.tr("No Document Loaded"), self.tr("Please select or ingest a study document first."))
            return
        self._save_settings()
        req = StudyGenerationRequest(
            document_id=self.document_id,
            force=self.force_combo.currentIndex() == 1,
            flashcard_count=self.flashcard_count_spin.value(),
            mcq_count=self.mcq_count_spin.value(),
            target_language=self.language_combo.currentText(),
            simple_language=bool(self._equity_profile.get("simple_language", True)),
            teacher_review_required=bool(self._equity_profile.get("teacher_review_required", True)),
            preferred_model=str(self._equity_profile.get("preferred_model", "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M")),
        )
        self.flashcards_model.removeRows(0, self.flashcards_model.rowCount())
        self.mcqs_model.removeRows(0, self.mcqs_model.rowCount())
        self.details_view.clear()
        self.study_manager.generate_study_assets(req.to_dict())

    @Slot()
    def export_flashcards(self) -> None:
        if not self.current_assets or not self.current_assets.flashcards:
            QMessageBox.information(self, self.tr("No Flashcards"), self.tr("Generate flashcards first before exporting."))
            return
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Export Flashcards to CSV"), str(Path.home() / f"doc_{self.document_id}_flashcards.csv"), self.tr("CSV Files (*.csv)"))
        if not path:
            return
        try:
            res = export_flashcards_csv(path, self.current_assets.flashcards)
            self.flashcardsExported.emit(str(res.path))
            QMessageBox.information(self, self.tr("Export Completed"), self.tr(f"Flashcards saved to:\n{res.path}"))
        except ExportError as exc:
            QMessageBox.critical(self, self.tr("Export Error"), str(exc))

    @Slot()
    def export_mcqs(self) -> None:
        if not self.current_assets or not self.current_assets.mcqs:
            QMessageBox.information(self, self.tr("No Quiz Questions"), self.tr("Generate quiz questions first before exporting."))
            return
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Export Quiz to CSV"), str(Path.home() / f"doc_{self.document_id}_mcqs.csv"), self.tr("CSV Files (*.csv)"))
        if not path:
            return
        try:
            res = export_mcqs_csv(path, self.current_assets.mcqs)
            self.mcqsExported.emit(str(res.path))
            QMessageBox.information(self, self.tr("Export Completed"), self.tr(f"Quiz questions saved to:\n{res.path}"))
        except ExportError as exc:
            QMessageBox.critical(self, self.tr("Export Error"), str(exc))

    @Slot(str)
    def _on_manager_study_started(self, message: str) -> None:
        self._is_operation_active = True
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.study_status_label.setText(message)
        self.overall_status_label.setText(self.tr("Synthesizing learning curriculum..."))
        self._update_ui_for_operation_status()

    @Slot(dict)
    def _on_manager_study_finished(self, payload: dict[str, Any]) -> None:
        self._is_operation_active = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)

        cards = [
            FlashcardViewModel.from_any(item, fallback_index=idx)
            for idx, item in enumerate(list(payload.get("flashcards") or []), start=1)
        ]
        mcqs = [
            MCQViewModel.from_any(item, fallback_index=idx)
            for idx, item in enumerate(list(payload.get("mcqs") or []), start=1)
        ]

        if not cards:
            cards = StudyAssetsViewModel._build_default_flashcards()
        if not mcqs:
            mcqs = StudyAssetsViewModel._build_default_mcqs()

        assets = StudyAssetsViewModel(
            document_id=int(payload.get("document_id") or 0),
            flashcards=cards,
            mcqs=mcqs,
            cached=bool(payload.get("cached", False)),
            fallback=bool(payload.get("fallback", False)),
            metadata=dict(payload.get("metadata") or {}),
        )
        self.current_assets = assets

        self._display_flashcards(assets.flashcards)
        self._display_mcqs(assets.mcqs)

        self._load_active_session()
        self._refresh_active_card()
        self._refresh_interactive_quiz()

        summary_text = self.tr(f"Ready: {assets.flashcard_count} flashcards & {assets.mcq_count} scenario quiz questions available.")
        self.study_status_label.setText(summary_text)
        self.overall_status_label.setText(summary_text)
        self.content_tabs.setCurrentIndex(0)

        if assets.document_id > 0:
            self.studyAssetsGenerated.emit(assets.document_id)
        self._append_status_message(summary_text, "INFO")
        self._update_ui_for_operation_status()

    @Slot(dict)
    def _on_manager_study_failed(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        self.progress_bar.setVisible(False)
        msg = str(error_context.get("error_message") or "Failed to synthesize study pack.")
        self.study_status_label.setText(msg)
        self.overall_status_label.setText(msg)
        self._append_status_message(msg, "ERROR")
        QMessageBox.critical(self, self.tr("Generation Failed"), msg)
        self._update_ui_for_operation_status()

    def _display_flashcards(self, cards: list[FlashcardViewModel]) -> None:
        self.flashcards_tree.setSortingEnabled(False)
        self.flashcards_model.removeRows(0, self.flashcards_model.rowCount())
        root = self.flashcards_model.invisibleRootItem()
        for idx, card in enumerate(cards, start=1):
            row = [
                QStandardItem(str(idx)),
                QStandardItem(card.question),
                QStandardItem(card.answer),
                QStandardItem(card.concept),
                QStandardItem(card.source_ref),
            ]
            row[0].setData(card.to_dict(), Qt.ItemDataRole.UserRole)
            for item in row:
                item.setEditable(False)
            root.appendRow(row)
        self.flashcards_tree.setSortingEnabled(True)

    def _display_mcqs(self, mcqs: list[MCQViewModel]) -> None:
        self.mcqs_tree.setSortingEnabled(False)
        self.mcqs_model.removeRows(0, self.mcqs_model.rowCount())
        root = self.mcqs_model.invisibleRootItem()
        for idx, mcq in enumerate(mcqs, start=1):
            row = [
                QStandardItem(str(idx)),
                QStandardItem(mcq.question),
                QStandardItem(mcq.correct_answer),
                QStandardItem(mcq.concept),
                QStandardItem(mcq.source_ref),
                QStandardItem("\n".join(mcq.choices)),
                QStandardItem(mcq.explanation),
            ]
            row[0].setData(mcq.to_dict(), Qt.ItemDataRole.UserRole)
            for item in row:
                item.setEditable(False)
            root.appendRow(row)
        self.mcqs_tree.setSortingEnabled(True)

    def _load_active_session(self) -> None:
        if not self.document_id:
            return
        prefix = f"Study/v6/{self.document_id}"
        cards = list(self.current_assets.flashcards if self.current_assets else [])
        raw_mastery = self.settings.value(f"{prefix}/mastery", "")
        self._mastery = json.loads(str(raw_mastery)) if raw_mastery else {}
        self._card_order = list(range(len(cards)))
        self._card_position = 0
        self._quiz_position = 0
        raw_quiz = self.settings.value(f"{prefix}/quiz_answers", "")
        self._quiz_answers = json.loads(str(raw_quiz)) if raw_quiz else {}
        self._streak_count = 0

    def _save_active_session(self) -> None:
        if not self.document_id:
            return
        prefix = f"Study/v6/{self.document_id}"
        self.settings.setValue(f"{prefix}/mastery", json.dumps(self._mastery, ensure_ascii=False))
        self.settings.setValue(f"{prefix}/quiz_answers", json.dumps(self._quiz_answers, ensure_ascii=False))
        self.settings.sync()

    def _refresh_active_card(self) -> None:
        cards = list(self.current_assets.flashcards if self.current_assets else [])
        if not cards:
            self.card_question_label.setText(self.tr("No flashcards available. Click 'Synthesize Pack' above to generate interactive cards."))
            self.card_code_block.setVisible(False)
            self.answer_box.setVisible(False)
            self.concept_badge.setText("CURRICULUM")
            self.difficulty_badge.setText("IDLE")
            self.rating_status_badge.setText("IDLE")
            self.card_progress_label.setText("Card 0 of 0")
            self.card_reviewed_label.setText("Mastered: 0 | Learning: 0")
            self.card_progress_bar.setValue(0)
            for btn in (self.card_previous_btn, self.card_reveal_btn, self.card_next_btn):
                btn.setEnabled(False)
            for btn in self.rating_buttons_map.values():
                btn.setEnabled(False)
            return

        order = self._card_order or list(range(len(cards)))
        pos = max(0, min(self._card_position, len(order) - 1))
        card = cards[order[pos]]
        k = card.card_id
        mastery = self._mastery.get(k, {})
        rating = str(mastery.get("rating", "New"))
        reviews = int(mastery.get("reviews", 0))

        self.concept_badge.setText(card.concept.upper())
        self.difficulty_badge.setText(card.difficulty.upper())
        self.rating_status_badge.setText(f"{rating.upper()} · {reviews} REVIEWS")

        self.card_question_label.setText(card.question)
        self.card_answer_label.setText(card.answer)
        self.card_source_label.setText(f"Citation: {card.source_ref}")

        if card.code_snippet:
            self.card_code_block.code = card.code_snippet
            self.card_code_block.language = card.language or "bash"
            highlighted_html = _highlight_code_syntax(card.code_snippet, card.language or "bash")
            lines = highlighted_html.split("\n")
            table_rows = [
                f'<tr><td style="color:#475569; user-select:none; text-align:right; padding-right:12px; font-family:monospace; font-size:12px;">{i}</td>'
                f'<td style="font-family:monospace; font-size:12px; white-space:pre-wrap;">{l}</td></tr>'
                for i, l in enumerate(lines, 1)
            ]
            self.card_code_block.code_browser.setHtml(
                f'<html><body style="margin:0;padding:10px;background-color:#070B14;color:#E2E8F0;"><table cellpadding="1" cellspacing="0" style="width:100%;border:none;">{"".join(table_rows)}</table></body></html>'
            )
            self.card_code_block.setVisible(True)
        else:
            self.card_code_block.setVisible(False)

        self.answer_box.setVisible(self._answer_revealed)
        self.card_reveal_btn.setText(self.tr("Hide Answer (Space)") if self._answer_revealed else self.tr("Reveal Answer (Space)"))

        self.card_progress_label.setText(f"Card {pos + 1} of {len(order)}")
        mastered_count = sum(1 for m in self._mastery.values() if m.get("rating") in {"Good", "Easy"})
        learning_count = sum(1 for m in self._mastery.values() if m.get("rating") in {"Again", "Hard"})
        self.card_reviewed_label.setText(f"Mastered: {mastered_count} | Learning: {learning_count}")

        self.card_progress_bar.setMaximum(len(order))
        self.card_progress_bar.setValue(pos + 1)

        self.card_previous_btn.setEnabled(len(order) > 1)
        self.card_next_btn.setEnabled(len(order) > 1)
        self.card_reveal_btn.setEnabled(True)

        for btn in self.rating_buttons_map.values():
            btn.setEnabled(self._answer_revealed)
        self.rating_instruction.setText(
            self.tr("Rate your retention accuracy to calibrate spaced repetition intervals:") if self._answer_revealed
            else self.tr("Reveal the answer to rate retention.")
        )

    def _move_active_card(self, delta: int) -> None:
        if not self._card_order:
            return
        self._card_position = (self._card_position + delta) % len(self._card_order)
        self._answer_revealed = False
        self._refresh_active_card()

    def _toggle_answer_reveal(self) -> None:
        cards = list(self.current_assets.flashcards if self.current_assets else [])
        if not cards:
            return
        self._answer_revealed = not self._answer_revealed
        self._refresh_active_card()

    def _shuffle_active_cards(self) -> None:
        if not self._card_order:
            return
        random.shuffle(self._card_order)
        self._card_position = 0
        self._answer_revealed = False
        self._refresh_active_card()

    def _rate_active_card(self, rating: str) -> None:
        cards = list(self.current_assets.flashcards if self.current_assets else [])
        if not cards or not self._card_order or not self._answer_revealed:
            return
        card = cards[self._card_order[self._card_position]]
        k = card.card_id
        prev = self._mastery.get(k, {})
        self._mastery[k] = {
            "question": card.question,
            "rating": rating,
            "interval_days": RATING_INTERVALS[rating],
            "reviews": int(prev.get("reviews", 0)) + 1,
        }
        self._save_active_session()
        self._move_active_card(1)

    def _rate_if_enabled(self, rating: str) -> None:
        btn = self.rating_buttons_map.get(rating)
        if btn and btn.isEnabled():
            self._rate_active_card(rating)

    def _select_choice(self, index: int) -> None:
        state = self._quiz_answers.get(str(self._quiz_position), {})
        if state.get("submitted"):
            return

        for idx, btn in enumerate(self.choice_buttons):
            btn.setChecked(idx == index)
        self.quiz_submit_btn.setEnabled(True)

    def _refresh_interactive_quiz(self) -> None:
        mcqs = list(self.current_assets.mcqs if self.current_assets else [])
        if not mcqs:
            self.quiz_question_text.setText(self.tr("No quiz questions available. Click 'Synthesize Pack' above to generate questions."))
            self.quiz_code_block.setVisible(False)
            for btn in self.choice_buttons:
                btn.setVisible(False)
            self.quiz_explanation_frame.setVisible(False)
            self.quiz_progress_label.setText("Question 0 of 0")
            self.quiz_score_label.setText("Score: 0 / 0 (0%)")
            self.quiz_streak_label.setText("Streak: 🔥 0")
            self.quiz_progress_bar.setValue(0)
            self.quiz_prev_btn.setEnabled(False)
            self.quiz_next_btn.setEnabled(False)
            self.quiz_submit_btn.setEnabled(False)
            self.quiz_retry_btn.setEnabled(False)
            return

        self._quiz_position = max(0, min(self._quiz_position, len(mcqs) - 1))
        question = mcqs[self._quiz_position]
        state = self._quiz_answers.get(str(self._quiz_position), {})
        selected_text = state.get("selected")
        is_submitted = bool(state.get("submitted"))

        self.quiz_concept_badge.setText(question.concept.strip().upper() or "KNOWLEDGE CHECK")
        self.quiz_question_text.setText(question.question)

        if question.code_snippet:
            self.quiz_code_block.code = question.code_snippet
            self.quiz_code_block.language = question.language or "bash"
            highlighted_html = _highlight_code_syntax(question.code_snippet, question.language or "bash")
            lines = highlighted_html.split("\n")
            table_rows = [
                f'<tr><td style="color:#475569; user-select:none; text-align:right; padding-right:12px; font-family:monospace; font-size:12px;">{i}</td>'
                f'<td style="font-family:monospace; font-size:12px; white-space:pre-wrap;">{l}</td></tr>'
                for i, l in enumerate(lines, 1)
            ]
            self.quiz_code_block.code_browser.setHtml(
                f'<html><body style="margin:0;padding:10px;background-color:#070B14;color:#E2E8F0;"><table cellpadding="1" cellspacing="0" style="width:100%;border:none;">{"".join(table_rows)}</table></body></html>'
            )
            self.quiz_code_block.setVisible(True)
        else:
            self.quiz_code_block.setVisible(False)

        for idx, btn in enumerate(self.choice_buttons):
            if idx < len(question.choices):
                choice_str = question.choices[idx]
                btn.set_content(choice_str)
                btn.setVisible(True)

                if is_submitted:
                    btn.setEnabled(False)
                    if choice_str == question.correct_answer:
                        btn.mark_correct()
                    elif selected_text and choice_str == selected_text:
                        btn.mark_incorrect()
                else:
                    btn.reset_state()
                    if selected_text and choice_str == selected_text:
                        btn.setChecked(True)
            else:
                btn.setVisible(False)

        if is_submitted:
            correct = bool(state.get("correct"))
            self.quiz_explanation_frame.setVisible(True)
            self.explanation_verdict.setText("CORRECT ANSWER" if correct else "NEEDS REVIEW")
            self.explanation_verdict.setProperty("status", "correct" if correct else "incorrect")
            self.explanation_verdict.style().unpolish(self.explanation_verdict)
            self.explanation_verdict.style().polish(self.explanation_verdict)
            self.explanation_text.setText(f"{question.explanation}\n\nCitation: {question.source_ref}")
        else:
            self.quiz_explanation_frame.setVisible(False)

        submitted_answers = [v for v in self._quiz_answers.values() if v.get("submitted")]
        correct_count = sum(1 for v in submitted_answers if v.get("correct"))
        score_pct = round((correct_count / len(submitted_answers)) * 100) if submitted_answers else 0

        self.quiz_progress_label.setText(f"Question {self._quiz_position + 1} of {len(mcqs)}")
        self.quiz_score_label.setText(f"Score: {correct_count} / {len(submitted_answers)} ({score_pct}%)")
        self.quiz_streak_label.setText(f"Streak: 🔥 {self._streak_count}")
        self.quiz_progress_bar.setMaximum(len(mcqs))
        self.quiz_progress_bar.setValue(len(submitted_answers))

        self.quiz_prev_btn.setEnabled(len(mcqs) > 1)
        self.quiz_next_btn.setEnabled(len(mcqs) > 1)
        self.quiz_submit_btn.setEnabled(not is_submitted and any(b.isChecked() for b in self.choice_buttons))
        self.quiz_retry_btn.setEnabled(any(v.get("submitted") and not v.get("correct") for v in self._quiz_answers.values()))

    def _move_quiz(self, delta: int) -> None:
        mcqs = list(self.current_assets.mcqs if self.current_assets else [])
        if not mcqs:
            return
        self._quiz_position = (self._quiz_position + delta) % len(mcqs)
        self._refresh_interactive_quiz()

    def _submit_quiz_answer(self) -> None:
        mcqs = list(self.current_assets.mcqs if self.current_assets else [])
        if not mcqs:
            return
        selected_btn = next((b for b in self.choice_buttons if b.isChecked() and b.isVisible()), None)
        if selected_btn is None:
            return

        question = mcqs[self._quiz_position]
        selected_text = selected_btn.choice_text
        is_correct = (selected_text == question.correct_answer)

        if is_correct:
            self._streak_count += 1
        else:
            self._streak_count = 0

        self._quiz_answers[str(self._quiz_position)] = {
            "selected": selected_text,
            "correct": is_correct,
            "submitted": True,
        }
        self._save_active_session()
        self._refresh_interactive_quiz()

        submitted_all = [v for v in self._quiz_answers.values() if v.get("submitted")]
        if len(submitted_all) == len(mcqs):
            total_correct = sum(1 for v in submitted_all if v.get("correct"))
            ratio = round((total_correct / len(mcqs)) * 100)
            QMessageBox.information(
                self,
                self.tr("Quiz Complete"),
                self.tr(f"All questions evaluated!\nScore: {total_correct} / {len(mcqs)} ({ratio}% Accuracy)."),
            )

    def _retry_incorrect_quiz(self) -> None:
        incorrect_indexes = [
            int(i) for i, v in self._quiz_answers.items()
            if str(i).isdigit() and v.get("submitted") and not v.get("correct")
        ]
        if not incorrect_indexes:
            return
        for idx in incorrect_indexes:
            self._quiz_answers.pop(str(idx), None)
        self._quiz_position = incorrect_indexes[0]
        self._save_active_session()
        self._refresh_interactive_quiz()

    @Slot(QModelIndex, QModelIndex)
    def _on_flashcard_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if not current.isValid():
            return
        src = self.flashcards_proxy.mapToSource(current)
        item = self.flashcards_model.item(src.row(), self.FC_COL_INDEX)
        if item and isinstance(item.data(Qt.ItemDataRole.UserRole), dict):
            card = FlashcardViewModel.from_any(item.data(Qt.ItemDataRole.UserRole))
            code_html = ""
            if card.code_snippet:
                code_html = f"""<div style="background:#070B14;border:1px solid #1E293B;border-radius:6px;padding:10px;margin-top:10px;font-family:monospace;color:#38BDF8;">
                {html.escape(card.code_snippet)}
                </div>"""
            html_content = f"""<div style="font-family:'Segoe UI',sans-serif;padding:8px">
            <span style="background:#1e293b;color:#38bdf8;padding:4px 8px;border-radius:4px;font-weight:700">ACTIVE RECALL CARD</span>
            <h2 style="color:#f8fafc;margin-top:12px">{html.escape(card.question)}</h2>
            {code_html}
            <div style="background:#0f172a;border-left:4px solid #14b8a6;padding:12px;border-radius:4px;margin-top:10px">
                <b style="color:#2dd4bf">Answer:</b>
                <p style="color:#e2e8f0;font-size:15px;line-height:1.5">{html.escape(card.answer)}</p>
            </div>
            <p style="color:#94a3b8;margin-top:12px"><b>Pedagogy Citation:</b> {html.escape(card.source_ref)}</p>
            </div>"""
            self.details_view.setHtml(html_content)
            self.content_tabs.setCurrentIndex(4)

    @Slot(QModelIndex, QModelIndex)
    def _on_mcq_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if not current.isValid():
            return
        src = self.mcqs_proxy.mapToSource(current)
        item = self.mcqs_model.item(src.row(), self.MCQ_COL_INDEX)
        if item and isinstance(item.data(Qt.ItemDataRole.UserRole), dict):
            mcq = MCQViewModel.from_any(item.data(Qt.ItemDataRole.UserRole))
            choices_html = "".join(f"<li style='margin-bottom:6px;color:#cbd5e1'>{html.escape(c)}</li>" for c in mcq.choices)
            html_content = f"""<div style="font-family:'Segoe UI',sans-serif;padding:8px">
            <span style="background:#1e293b;color:#a78bfa;padding:4px 8px;border-radius:4px;font-weight:700">QUIZ DEEP DIVE</span>
            <h2 style="color:#f8fafc;margin-top:12px">{html.escape(mcq.question)}</h2>
            <ol style="padding-left:20px;font-size:15px">{choices_html}</ol>
            <div style="background:#0f172a;border-left:4px solid #10b981;padding:12px;border-radius:4px;margin-top:10px">
                <b style="color:#34d399">Correct Answer:</b>
                <p style="color:#e2e8f0;font-size:15px">{html.escape(mcq.correct_answer)}</p>
            </div>
            <div style="background:#0f172a;border-left:4px solid #38bdf8;padding:12px;border-radius:4px;margin-top:10px">
                <b style="color:#7dd3fc">Explanation:</b>
                <p style="color:#e2e8f0;font-size:14px;line-height:1.5">{html.escape(mcq.explanation)}</p>
            </div>
            <p style="color:#94a3b8;margin-top:12px"><b>Source Citation:</b> {html.escape(mcq.source_ref)}</p>
            </div>"""
            self.details_view.setHtml(html_content)
            self.content_tabs.setCurrentIndex(4)

    @Slot(QPoint)
    def _show_flashcards_context_menu(self, pos: QPoint) -> None:
        index = self.flashcards_tree.indexAt(pos)
        if not index.isValid():
            return
        src = self.flashcards_proxy.mapToSource(index)
        item = self.flashcards_model.item(src.row(), self.FC_COL_INDEX)
        if not item or not isinstance(item.data(Qt.ItemDataRole.UserRole), dict):
            return
        card = FlashcardViewModel.from_any(item.data(Qt.ItemDataRole.UserRole))
        menu = QMenu(self.flashcards_tree)
        menu.addAction(self.tr("Copy Question"), lambda: QApplication.clipboard().setText(card.question))
        menu.addAction(self.tr("Copy Answer"), lambda: QApplication.clipboard().setText(card.answer))
        if card.code_snippet:
            menu.addAction(self.tr("Copy Code Snippet"), lambda: QApplication.clipboard().setText(card.code_snippet))
        menu.exec(self.flashcards_tree.viewport().mapToGlobal(pos))

    @Slot(QPoint)
    def _show_mcqs_context_menu(self, pos: QPoint) -> None:
        index = self.mcqs_tree.indexAt(pos)
        if not index.isValid():
            return
        src = self.mcqs_proxy.mapToSource(index)
        item = self.mcqs_model.item(src.row(), self.MCQ_COL_INDEX)
        if not item or not isinstance(item.data(Qt.ItemDataRole.UserRole), dict):
            return
        mcq = MCQViewModel.from_any(item.data(Qt.ItemDataRole.UserRole))
        menu = QMenu(self.mcqs_tree)
        menu.addAction(self.tr("Copy Question"), lambda: QApplication.clipboard().setText(mcq.question))
        menu.addAction(self.tr("Copy Correct Answer"), lambda: QApplication.clipboard().setText(mcq.correct_answer))
        menu.exec(self.mcqs_tree.viewport().mapToGlobal(pos))

    @Slot(str, str)
    def _append_status_message(self, message: str, level: str = "INFO") -> None:
        self.operation_log.append(f"[{level.upper()}] {html.escape(str(message))}")
        self.statusMessage.emit(message, level)

    def _update_ui_for_operation_status(self) -> None:
        active = not self._is_operation_active
        has_doc = self.document_id is not None
        has_assets = self.current_assets is not None
        self.generate_btn.setEnabled(active and has_doc)
        self.export_flashcards_btn.setEnabled(active and has_assets and bool(self.current_assets.flashcards))
        self.export_mcqs_btn.setEnabled(active and has_assets and bool(self.current_assets.mcqs))

    def cleanup_before_close(self) -> None:
        self._save_settings()
        self._save_active_session()
        self.study_manager.cleanup_before_close()
        logger.info("StudyWidget cleanup completed.")