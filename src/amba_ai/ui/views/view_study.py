from __future__ import annotations

import csv
import hashlib
import inspect
import json
import random
import tempfile
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QRectF, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from amba_ai.config import DATA_DIR
from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from amba_ai.ui.workers import FunctionWorker

try:
    from amba_ai.ui.workers import WorkerResult
except ImportError:
    @dataclass
    class WorkerResult:
        task_name: str
        result: Any = None
        success: bool = True
        error: str | None = None
        context: dict[str, Any] | None = None


@dataclass
class StudySessionStats:
    """Track in-memory metrics for the active study session."""

    total: int = 0
    studied: int = 0
    known: int = 0
    unknown: int = 0
    q0: int = 0
    q1: int = 0
    q2: int = 0
    q3: int = 0
    q4: int = 0
    q5: int = 0
    started_at: str = ""
    updated_at: str = ""

    @property
    def accuracy(self) -> float:
        """Return the current known-answer percentage for the session."""
        if self.studied <= 0:
            return 0.0
        return round((self.known / self.studied) * 100.0, 2)


@dataclass
class ScheduleRecord:
    """Persisted spaced-repetition metadata for a single flashcard."""

    card_id: str
    document_id: str
    question: str
    answer: str
    source_ref: str | None = None
    created_at: str = ""
    last_reviewed: str | None = None
    next_due: str | None = None
    confidence: str = "new"
    difficulty: str = "new"
    repetitions: int = 0
    interval_days: int = 0
    ease_factor: float = 2.5
    known_count: int = 0
    unknown_count: int = 0
    tags: list[str] | None = None


class StudyScheduleStore:
    """JSON-backed durable store for SM-2 schedule records."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DATA_DIR / "db" / "study_schedule.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> dict[str, ScheduleRecord]:
        """Load all schedule records, skipping malformed entries safely."""
        if not self.path.exists():
            return {}

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning(
                "Failed to load study schedule store",
                extra={"context": {"path": str(self.path)}},
                exc_info=True,
            )
            return {}

        records: dict[str, ScheduleRecord] = {}
        if not isinstance(data, dict):
            return records

        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            try:
                records[str(key)] = ScheduleRecord(**value)
            except Exception:
                logger.warning(
                    "Invalid schedule record skipped",
                    extra={"context": {"card_id": str(key)}},
                    exc_info=True,
                )

        return records

    def save_all(self, records: dict[str, ScheduleRecord]) -> None:
        """Atomically persist all schedule records to disk."""
        payload = {key: asdict(value) for key, value in records.items()}
        self._atomic_write_json(self.path, payload)

    @staticmethod
    def _atomic_write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.stem}.",
            suffix=".tmp",
            dir=str(path.parent),
            text=True,
        )
        tmp_path = Path(tmp_name)

        try:
            with open(fd, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
                file.write("\n")
            tmp_path.replace(path)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            finally:
                raise


class StudyPieChart(QWidget):
    """Lightweight QWidget pie chart for known versus unknown session answers."""

    COLOR_EMPTY = "#d0d0d0"
    COLOR_KNOWN = "#4caf50"
    COLOR_UNKNOWN = "#f44336"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.known = 0
        self.unknown = 0
        self.setMinimumHeight(120)

    def set_values(self, known: int, unknown: int) -> None:
        """Update pie chart values and trigger repaint."""
        self.known = max(0, known)
        self.unknown = max(0, unknown)
        self.update()

    def paintEvent(self, event: Any) -> None:
        total = self.known + self.unknown
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size = min(self.width(), self.height()) - 20
        if size <= 10:
            return

        rect = QRectF(
            (self.width() - size) / 2,
            (self.height() - size) / 2,
            size,
            size,
        )

        if total <= 0:
            painter.setBrush(QColor(self.COLOR_EMPTY))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(rect)
            return

        segments = [
            (self.known, QColor(self.COLOR_KNOWN)),
            (self.unknown, QColor(self.COLOR_UNKNOWN)),
        ]

        start_angle = 90 * 16
        for value, color in segments:
            if value <= 0:
                continue
            span = int((value / total) * 360 * 16)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(rect, start_angle, span)
            start_angle += span


class StudyView(QWidget):
    """PySide6 study interface with flashcards, SM-2 scheduling, analytics, and exports."""

    status_message = Signal(str)

    FLASHCARD_LIMIT = 20
    MAX_INTERVAL_DAYS = 3650

    COLOR_DUE = "#ffebee"
    COLOR_NEW = "#e3f2fd"
    COLOR_REVIEWED = "#e8f5e9"
    COLOR_ANSWER_BACKGROUND = "#f9f9f9"
    COLOR_MUTED_TEXT = "gray"

    FILTER_ALL = "all"
    FILTER_DUE = "due"
    FILTER_NEW = "new"
    FILTER_HARD = "hard"
    FILTER_MEDIUM = "medium"
    FILTER_EASY = "easy"
    FILTER_KNOWN = "known"
    FILTER_UNKNOWN = "unknown"

    EXPORT_SCOPE_CURRENT_FILTER = "current filter"
    EXPORT_SCOPE_DUE = "due"
    EXPORT_SCOPE_ALL = "all"
    EXPORT_SCOPE_KNOWN = "known"
    EXPORT_SCOPE_UNKNOWN = "unknown"

    def __init__(self, job_service: JobService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.job_service = job_service
        self.thread_pool = QThreadPool.globalInstance()
        self.schedule_store = StudyScheduleStore()

        self.document_id: str | None = None
        self.cards: list[Any] = []
        self.filtered_indexes: list[int] = []
        self.current_filtered_index = 0
        self.shuffle_mode = False
        self.stats = StudySessionStats()
        self.schedule_records: dict[str, ScheduleRecord] = self.schedule_store.load_all()

        self.tabs = QTabWidget()
        self.dashboard_tab = QWidget()
        self.study_tab = QWidget()
        self.library_tab = QWidget()

        self._init_dashboard_tab()
        self._init_study_tab()
        self._init_library_tab()

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.study_tab, "Study")
        self.tabs.addTab(self.library_tab, "Library")

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        self._bind_shortcuts()
        self._set_controls_enabled(False)
        self._update_dashboard()

    def _init_dashboard_tab(self) -> None:
        self.meta_label = QLabel("Mode: None")
        self.meta_label.setStyleSheet(
            f"color: {self.COLOR_MUTED_TEXT}; font-size: 14px; font-weight: bold;"
        )

        self.btn_global_review = QPushButton("Start Global Queue (All Docs)")
        self.btn_global_review.clicked.connect(self.load_global_queue)

        self.btn_generate = QPushButton("Generate Flashcards (Current Doc)")
        self.btn_generate.clicked.connect(self.generate_flashcards)

        top_controls = QHBoxLayout()
        top_controls.addWidget(self.btn_global_review)
        top_controls.addWidget(self.btn_generate)

        self.session_label = QLabel("Session: not started")
        self.due_label = QLabel("Due: 0")
        self.accuracy_label = QLabel("Accuracy: 0%")

        self.study_progress = QProgressBar()
        self.study_progress.setRange(0, 100)
        self.study_progress.setValue(0)

        self.accuracy_progress = QProgressBar()
        self.accuracy_progress.setRange(0, 100)
        self.accuracy_progress.setValue(0)

        self.pie = StudyPieChart()

        grid = QGridLayout()
        grid.addWidget(self.session_label, 0, 0)
        grid.addWidget(self.due_label, 0, 1)
        grid.addWidget(self.accuracy_label, 0, 2)
        grid.addWidget(QLabel("Study Progress"), 1, 0)
        grid.addWidget(self.study_progress, 1, 1, 1, 2)
        grid.addWidget(QLabel("Accuracy"), 2, 0)
        grid.addWidget(self.accuracy_progress, 2, 1, 1, 2)
        grid.addWidget(self.pie, 3, 0, 1, 3)

        self.btn_export_analytics = QPushButton("Export Multi-Document Analytics")
        self.btn_export_analytics.clicked.connect(self.export_analytics)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)

        layout = QVBoxLayout(self.dashboard_tab)
        layout.addWidget(self.meta_label)
        layout.addLayout(top_controls)
        layout.addLayout(grid)
        layout.addWidget(self.btn_export_analytics)
        layout.addWidget(self.progress)
        layout.addStretch()

    def _init_study_tab(self) -> None:
        self.question = QTextEdit()
        self.answer = QTextEdit()
        self.question.setReadOnly(True)
        self.answer.setReadOnly(True)
        self.question.setStyleSheet("font-size: 18px; padding: 10px;")
        self.answer.setStyleSheet(
            f"font-size: 16px; padding: 10px; background-color: {self.COLOR_ANSWER_BACKGROUND};"
        )

        self.btn_show = QPushButton("Show Answer")
        self.btn_show.clicked.connect(self.show_answer)

        self.btn_q0 = QPushButton("0 - Blackout")
        self.btn_q1 = QPushButton("1 - Wrong")
        self.btn_q2 = QPushButton("2 - Hard")
        self.btn_q3 = QPushButton("3 - Medium")
        self.btn_q4 = QPushButton("4 - Good")
        self.btn_q5 = QPushButton("5 - Easy")

        self.btn_q0.clicked.connect(lambda: self.mark_quality(0))
        self.btn_q1.clicked.connect(lambda: self.mark_quality(1))
        self.btn_q2.clicked.connect(lambda: self.mark_quality(2))
        self.btn_q3.clicked.connect(lambda: self.mark_quality(3))
        self.btn_q4.clicked.connect(lambda: self.mark_quality(4))
        self.btn_q5.clicked.connect(lambda: self.mark_quality(5))

        for button in self._quality_buttons():
            button.setStyleSheet("padding: 10px; font-weight: bold;")

        self.btn_q0.setStyleSheet(
            self.btn_q0.styleSheet() + f"background-color: {self.COLOR_DUE};"
        )
        self.btn_q5.setStyleSheet(
            self.btn_q5.styleSheet() + f"background-color: {self.COLOR_REVIEWED};"
        )

        quality_layout = QHBoxLayout()
        for button in self._quality_buttons():
            quality_layout.addWidget(button)

        self.btn_prev = QPushButton("Previous")
        self.btn_next = QPushButton("Next")
        self.btn_prev.clicked.connect(self.prev_card)
        self.btn_next.clicked.connect(self.next_card)

        navigation_layout = QHBoxLayout()
        navigation_layout.addWidget(self.btn_prev)
        navigation_layout.addWidget(self.btn_show)
        navigation_layout.addWidget(self.btn_next)

        layout = QVBoxLayout(self.study_tab)
        layout.addWidget(QLabel("Question"))
        layout.addWidget(self.question)
        layout.addWidget(QLabel("Answer"))
        layout.addWidget(self.answer)
        layout.addLayout(navigation_layout)
        layout.addLayout(quality_layout)

    def _init_library_tab(self) -> None:
        self.filter_box = QComboBox()
        self.filter_box.addItems(["All", "Due", "New", "Hard", "Medium", "Easy", "Known", "Unknown"])
        self.filter_box.currentTextChanged.connect(self.apply_filter)

        self.export_scope = QComboBox()
        self.export_scope.addItems(["Current Filter", "Due", "All", "Known", "Unknown"])

        self.btn_shuffle = QPushButton("Shuffle: OFF")
        self.btn_shuffle.clicked.connect(self.toggle_shuffle)

        self.btn_export = QPushButton("Export Cards")
        self.btn_export.clicked.connect(self.export_flashcards)

        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Filter:"))
        top_layout.addWidget(self.filter_box)
        top_layout.addWidget(QLabel("Export Scope:"))
        top_layout.addWidget(self.export_scope)
        top_layout.addWidget(self.btn_shuffle)
        top_layout.addWidget(self.btn_export)

        self.card_list = QListWidget()
        self.card_list.currentRowChanged.connect(self._on_card_selected)

        layout = QVBoxLayout(self.library_tab)
        layout.addLayout(top_layout)
        layout.addWidget(self.card_list)

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self.prev_card)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self.next_card)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.show_answer)
        QShortcut(QKeySequence(Qt.Key.Key_0), self, activated=lambda: self.mark_quality(0))
        QShortcut(QKeySequence(Qt.Key.Key_1), self, activated=lambda: self.mark_quality(1))
        QShortcut(QKeySequence(Qt.Key.Key_2), self, activated=lambda: self.mark_quality(2))
        QShortcut(QKeySequence(Qt.Key.Key_3), self, activated=lambda: self.mark_quality(3))
        QShortcut(QKeySequence(Qt.Key.Key_4), self, activated=lambda: self.mark_quality(4))
        QShortcut(QKeySequence(Qt.Key.Key_5), self, activated=lambda: self.mark_quality(5))

    def _quality_buttons(self) -> list[QPushButton]:
        return [self.btn_q0, self.btn_q1, self.btn_q2, self.btn_q3, self.btn_q4, self.btn_q5]

    def set_document(self, document_id: int | str) -> None:
        """Load the study queue for a single document."""
        self.document_id = str(document_id)
        self._reset_session_state()
        self.cards = [
            {
                "card_id": record.card_id,
                "document_id": record.document_id,
                "question": record.question,
                "answer": record.answer,
                "source_ref": record.source_ref,
            }
            for record in self.schedule_records.values()
            if str(record.document_id) == self.document_id
        ]

        self.apply_filter()
        self._set_controls_enabled(True)
        self._update_dashboard()

    @Slot()
    def load_global_queue(self) -> None:
        """Load all due cards across all documents."""
        self.document_id = None
        self._reset_session_state()
        self.cards = [
            {
                "card_id": record.card_id,
                "document_id": record.document_id,
                "question": record.question,
                "answer": record.answer,
                "source_ref": record.source_ref,
            }
            for record in self.schedule_records.values()
        ]

        self.filter_box.setCurrentText("Due")
        self.apply_filter(show_empty_due_message=True)
        self._set_controls_enabled(True)
        self._update_dashboard()

    def _reset_session_state(self) -> None:
        now = self._now()
        self.cards.clear()
        self.filtered_indexes.clear()
        self.current_filtered_index = 0
        self.shuffle_mode = False
        self.stats = StudySessionStats(started_at=now, updated_at=now)
        self.card_list.clear()
        self.question.clear()
        self.answer.clear()
        self.btn_shuffle.setText("Shuffle: OFF")

    @Slot()
    def generate_flashcards(self) -> None:
        if not self.document_id:
            QMessageBox.information(self, "Study", "Select a document first.")
            return

        logger.info(
            "Flashcard generation started",
            extra={
                "context": {
                    "operation": "generate_flashcards",
                    "document_id": self.document_id,
                    "limit": self.FLASHCARD_LIMIT,
                }
            },
        )

        self._set_busy(True, "Generating flashcards...")

        worker = self._create_worker(
            self._generate_flashcards_job,
            task_name="Generate Flashcards",
            max_retries=1,
        )
        worker.signals.finished.connect(self._on_flashcards_generated)
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)

    def _create_worker(self, fn: Callable[[], Any], task_name: str, max_retries: int = 0) -> FunctionWorker:
        """Create a FunctionWorker compatible with both simple and enriched worker implementations."""
        try:
            signature = inspect.signature(FunctionWorker)
            if "task_name" in signature.parameters:
                return FunctionWorker(fn, task_name=task_name, max_retries=max_retries)
        except Exception:
            pass

        return FunctionWorker(fn)

    def _generate_flashcards_job(self) -> Any:
        if hasattr(self.job_service, "generate_flashcards"):
            return self.job_service.generate_flashcards(self.document_id, limit=self.FLASHCARD_LIMIT)

        result = self.job_service.generate_study_assets(int(self.document_id))
        if isinstance(result, dict):
            return result.get("flashcards", [])
        return result

    @Slot(object)
    def _on_flashcards_generated(self, raw: Any) -> None:
        self._set_busy(False)
        result = self._unwrap(raw)

        if not result.success:
            self._handle_failure(result, "generation")
            return

        new_cards = list(result.result or [])
        if not new_cards:
            QMessageBox.warning(self, "Study", "No flashcards were generated.")
            return

        for card in new_cards[: self.FLASHCARD_LIMIT]:
            if isinstance(card, dict):
                card["document_id"] = self.document_id
            self.cards.append(card)

        self._ensure_schedule_records()
        self.apply_filter()

        logger.info(
            "Flashcard generation completed",
            extra={
                "context": {
                    "operation": "generate_flashcards",
                    "document_id": self.document_id,
                    "count": len(new_cards),
                }
            },
        )

    @Slot(object)
    def _on_worker_error(self, context: Any) -> None:
        self._set_busy(False)

        if isinstance(context, dict):
            error_context = context
        else:
            error_context = {
                "operation": "worker",
                "error_message": str(context),
                "traceback": traceback.format_exc(),
            }

        self._show_error_dialog("generation", error_context, retry=self.generate_flashcards)

    def _handle_failure(self, result: WorkerResult, category: str) -> None:
        context = getattr(result, "context", None) or {
            "operation": getattr(result, "task_name", "unknown"),
            "error_message": getattr(result, "error", "Unknown error"),
        }
        retry = self.generate_flashcards if category == "generation" else None
        self._show_error_dialog(category, context, retry=retry)

    @Slot()
    def apply_filter(self, show_empty_due_message: bool = False) -> None:
        selected = self.filter_box.currentText().lower()
        indexes: list[int] = []

        for index, card in enumerate(self.cards):
            record = self._record_for_card(card)
            if self._matches_filter(record, selected):
                indexes.append(index)

        indexes.sort(key=lambda i: self._record_for_card(self.cards[i]).next_due or "")

        self.filtered_indexes = indexes
        self.current_filtered_index = 0
        self.stats.total = len(self.filtered_indexes)
        self._refresh_cards()

        if show_empty_due_message and not self.filtered_indexes:
            QMessageBox.information(self, "Study", "You're all caught up! No due cards found.")

    def _matches_filter(self, record: ScheduleRecord, selected: str) -> bool:
        if selected == self.FILTER_ALL:
            return True
        if selected == self.FILTER_DUE:
            return self._is_due(record)
        if selected == self.FILTER_NEW:
            return record.difficulty == "new"
        if selected == self.FILTER_EASY:
            return record.difficulty == "easy"
        if selected == self.FILTER_MEDIUM:
            return record.difficulty == "medium"
        if selected == self.FILTER_HARD:
            return record.difficulty in {"hard", "wrong", "blackout"}
        if selected == self.FILTER_KNOWN:
            return record.known_count > record.unknown_count
        if selected == self.FILTER_UNKNOWN:
            return record.unknown_count >= record.known_count and (record.known_count + record.unknown_count) > 0
        return True

    def _refresh_cards(self) -> None:
        self.card_list.blockSignals(True)
        self.card_list.clear()

        for card_index in self.filtered_indexes:
            card = self.cards[card_index]
            record = self._record_for_card(card)
            item = QListWidgetItem(self._get_question(card) or "(empty question)")
            item.setToolTip(self._tooltip_for(record))
            item.setData(Qt.ItemDataRole.UserRole, record.card_id)
            item.setBackground(QColor(self._color_for_record(record)))
            self.card_list.addItem(item)

        self.card_list.blockSignals(False)
        self._update_dashboard()
        self.render_current()

    def _color_for_record(self, record: ScheduleRecord) -> str:
        if self._is_due(record):
            return self.COLOR_DUE
        if record.difficulty == "new":
            return self.COLOR_NEW
        return self.COLOR_REVIEWED

    def render_current(self) -> None:
        if not self.cards or not self.filtered_indexes:
            self.question.clear()
            self.answer.clear()
            return

        self.current_filtered_index = max(
            0,
            min(self.current_filtered_index, len(self.filtered_indexes) - 1),
        )

        card = self.cards[self.filtered_indexes[self.current_filtered_index]]
        self.question.setPlainText(self._get_question(card))
        self.answer.clear()

        self.card_list.blockSignals(True)
        self.card_list.setCurrentRow(self.current_filtered_index)
        self.card_list.blockSignals(False)

    @Slot()
    def show_answer(self) -> None:
        card = self._current_card()
        if card is None:
            return
        self.answer.setPlainText(self._get_answer(card))

    @Slot()
    def next_card(self) -> None:
        if not self.filtered_indexes:
            return
        self.current_filtered_index = min(
            self.current_filtered_index + 1,
            len(self.filtered_indexes) - 1,
        )
        self.render_current()

    @Slot()
    def prev_card(self) -> None:
        if not self.filtered_indexes:
            return
        self.current_filtered_index = max(0, self.current_filtered_index - 1)
        self.render_current()

    @Slot()
    def toggle_shuffle(self) -> None:
        if not self.cards:
            return

        self.shuffle_mode = not self.shuffle_mode
        self.btn_shuffle.setText(f"Shuffle: {'ON' if self.shuffle_mode else 'OFF'}")

        if self.shuffle_mode:
            random.shuffle(self.cards)

        self.apply_filter()

    def mark_quality(self, quality: int) -> None:
        """Record a quality grade for the visible card and persist its SM-2 schedule."""
        card = self._current_card()
        if card is None:
            return

        if not self.answer.toPlainText().strip():
            return

        if quality < 0 or quality > 5:
            QMessageBox.warning(self, "Study", "Quality must be between 0 and 5.")
            return

        try:
            record = self._record_for_card(card)
            updated = self._schedule(record, quality)
            self.schedule_records[updated.card_id] = updated
            self.schedule_store.save_all(self.schedule_records)

            self._mark_current_item_reviewed()

            self.stats.studied += 1
            self.stats.updated_at = self._now()

            if quality >= 3:
                self.stats.known += 1
            else:
                self.stats.unknown += 1

            self._increment_quality_counter(quality)
            self._update_dashboard()

            logger.info(
                "SM-2 study event recorded",
                extra={
                    "context": {
                        "operation": "mark_quality",
                        "document_id": updated.document_id,
                        "card_id": updated.card_id,
                        "quality": quality,
                        "next_due": updated.next_due,
                    }
                },
            )

            if self.current_filtered_index < len(self.filtered_indexes) - 1:
                self.next_card()
            else:
                self.apply_filter()
                self.status_message.emit("End of queue reached.")

        except Exception as exc:
            context = {
                "operation": "mark_quality",
                "document_id": self.document_id,
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
            }
            self._show_error_dialog("scheduling", context)

    def _mark_current_item_reviewed(self) -> None:
        item = self.card_list.item(self.current_filtered_index)
        if item is not None:
            item.setBackground(QColor(self.COLOR_REVIEWED))

    def _increment_quality_counter(self, quality: int) -> None:
        if quality == 0:
            self.stats.q0 += 1
        elif quality == 1:
            self.stats.q1 += 1
        elif quality == 2:
            self.stats.q2 += 1
        elif quality == 3:
            self.stats.q3 += 1
        elif quality == 4:
            self.stats.q4 += 1
        elif quality == 5:
            self.stats.q5 += 1

    @Slot(int)
    def _on_card_selected(self, row: int) -> None:
        if row < 0 or row >= len(self.filtered_indexes):
            return
        self.current_filtered_index = row
        self.render_current()

    def export_flashcards(self) -> None:
        cards_to_export = self._cards_for_export()
        if not cards_to_export:
            QMessageBox.information(self, "Export", "No flashcards to export.")
            return

        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export flashcards",
            "flashcards.csv",
            "CSV (*.csv);;JSON (*.json);;Anki Package (*.apkg)",
        )

        if not path:
            return

        output_path = Path(path)

        try:
            if selected_filter.startswith("JSON") or output_path.suffix.lower() == ".json":
                output_path = output_path.with_suffix(".json")
                self._export_json(output_path, cards_to_export)
                export_format = "json"
            elif selected_filter.startswith("Anki") or output_path.suffix.lower() == ".apkg":
                output_path = output_path.with_suffix(".apkg")
                self._export_apkg(output_path, cards_to_export)
                export_format = "apkg"
            else:
                output_path = output_path.with_suffix(".csv")
                self._export_csv(output_path, cards_to_export)
                export_format = "csv"

            QMessageBox.information(self, "Export", f"Saved to:\n{output_path}")
            logger.info(
                "Flashcards exported",
                extra={
                    "context": {
                        "operation": "export_flashcards",
                        "format": export_format,
                        "path": str(output_path),
                        "count": len(cards_to_export),
                    }
                },
            )

        except Exception as exc:
            context = {
                "operation": "export_flashcards",
                "document_id": self.document_id,
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
                "path": str(output_path),
            }
            self._show_error_dialog("export", context)

    def export_analytics(self) -> None:
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export multi-document analytics",
            "study_analytics.json",
            "JSON (*.json);;CSV (*.csv)",
        )

        if not path:
            return

        output_path = Path(path)

        try:
            if selected_filter.startswith("CSV") or output_path.suffix.lower() == ".csv":
                output_path = output_path.with_suffix(".csv")
                self._export_analytics_csv(output_path)
            else:
                output_path = output_path.with_suffix(".json")
                self._export_analytics_json(output_path)

            QMessageBox.information(self, "Export", f"Saved to:\n{output_path}")
            logger.info(
                "Multi-doc analytics exported",
                extra={"context": {"operation": "export_analytics", "path": str(output_path)}},
            )

        except Exception as exc:
            context = {
                "operation": "export_analytics",
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
                "path": str(output_path),
            }
            self._show_error_dialog("export", context)

    def _export_json(self, path: Path, cards: list[Any]) -> None:
        payload = [self._card_payload(card) for card in cards]
        self._atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def _export_csv(self, path: Path, cards: list[Any]) -> None:
        fieldnames = [
            "document_id",
            "question",
            "answer",
            "source_ref",
            "confidence",
            "difficulty",
            "last_reviewed",
            "next_due",
            "repetitions",
            "interval_days",
            "ease_factor",
            "known_count",
            "unknown_count",
        ]

        def writer_fn(tmp_path: Path) -> None:
            with tmp_path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                for card in cards:
                    writer.writerow(self._card_payload(card))

        self._atomic_write_with_callback(path, writer_fn)

    def _export_apkg(self, path: Path, cards: list[Any]) -> None:
        try:
            import genanki
        except Exception as exc:
            raise RuntimeError("Anki .apkg export requires genanki.") from exc

        model = genanki.Model(
            1607392319,
            "AmbaAI SM-2 Flashcard",
            fields=[
                {"name": "Question"},
                {"name": "Answer"},
                {"name": "Metadata"},
            ],
            templates=[
                {
                    "name": "Card 1",
                    "qfmt": "{{Question}}",
                    "afmt": "{{FrontSide}}<hr id='answer'>{{Answer}}<br><br><small>{{Metadata}}</small>",
                }
            ],
        )

        deck = genanki.Deck(
            2059400110,
            f"AmbaAI Export {datetime.now(timezone.utc).strftime('%Y%m%d')}",
        )

        for card in cards:
            payload = self._card_payload(card)
            metadata = json.dumps(
                {
                    "document_id": payload["document_id"],
                    "source_ref": payload["source_ref"],
                    "difficulty": payload["difficulty"],
                    "next_due": payload["next_due"],
                    "ease_factor": payload["ease_factor"],
                },
                ensure_ascii=False,
            )
            note = genanki.Note(
                model=model,
                fields=[
                    payload["question"],
                    payload["answer"],
                    metadata,
                ],
            )
            deck.add_note(note)

        def writer_fn(tmp_path: Path) -> None:
            genanki.Package(deck).write_to_file(str(tmp_path))

        self._atomic_write_with_callback(path, writer_fn)

    def _export_analytics_json(self, path: Path) -> None:
        payload = self._analytics_payload()
        self._atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def _export_analytics_csv(self, path: Path) -> None:
        payload = self._analytics_payload()

        def writer_fn(tmp_path: Path) -> None:
            with tmp_path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["document_id", "total_cards", "due_cards", "known_count", "unknown_count"])
                for document_id, stats in payload["documents"].items():
                    writer.writerow(
                        [
                            document_id,
                            stats["total"],
                            stats["due"],
                            stats["known"],
                            stats["unknown"],
                        ]
                    )

        self._atomic_write_with_callback(path, writer_fn)

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        def writer_fn(tmp_path: Path) -> None:
            tmp_path.write_text(content, encoding="utf-8")

        StudyView._atomic_write_with_callback(path, writer_fn)

    @staticmethod
    def _atomic_write_with_callback(path: Path, writer_fn: Callable[[Path], None]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.stem}.",
            suffix=f"{path.suffix}.tmp",
            dir=str(path.parent),
        )
        tmp_path = Path(tmp_name)

        try:
            Path(tmp_name).unlink(missing_ok=True)
            writer_fn(tmp_path)
            tmp_path.replace(path)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            finally:
                raise
        finally:
            try:
                import os

                os.close(fd)
            except Exception:
                pass

    def _cards_for_export(self) -> list[Any]:
        scope = self.export_scope.currentText().lower()

        if scope == self.EXPORT_SCOPE_CURRENT_FILTER:
            return [self.cards[index] for index in self.filtered_indexes]

        selected: list[Any] = []
        for card in self.cards:
            record = self._record_for_card(card)
            if scope == self.EXPORT_SCOPE_ALL:
                selected.append(card)
            elif scope == self.EXPORT_SCOPE_KNOWN and record.known_count > record.unknown_count:
                selected.append(card)
            elif (
                scope == self.EXPORT_SCOPE_UNKNOWN
                and record.unknown_count >= record.known_count
                and (record.known_count + record.unknown_count) > 0
            ):
                selected.append(card)
            elif scope == self.EXPORT_SCOPE_DUE and self._is_due(record):
                selected.append(card)

        return selected

    def _card_payload(self, card: Any) -> dict[str, Any]:
        record = self._record_for_card(card)
        return {
            "document_id": record.document_id,
            "question": self._get_question(card),
            "answer": self._get_answer(card),
            "source_ref": self._get_source_ref(card),
            "confidence": record.confidence,
            "difficulty": record.difficulty,
            "last_reviewed": record.last_reviewed,
            "next_due": record.next_due,
            "repetitions": record.repetitions,
            "interval_days": record.interval_days,
            "ease_factor": record.ease_factor,
            "known_count": record.known_count,
            "unknown_count": record.unknown_count,
        }

    def _analytics_payload(self) -> dict[str, Any]:
        global_due = sum(1 for record in self.schedule_records.values() if self._is_due(record))
        documents: dict[str, Any] = {}

        for record in self.schedule_records.values():
            document_id = str(record.document_id)
            if document_id not in documents:
                documents[document_id] = {
                    "total": 0,
                    "due": 0,
                    "known": 0,
                    "unknown": 0,
                }

            documents[document_id]["total"] += 1

            if self._is_due(record):
                documents[document_id]["due"] += 1

            documents[document_id]["known"] += record.known_count
            documents[document_id]["unknown"] += record.unknown_count

        return {
            "exported_at": self._now(),
            "global_session": asdict(self.stats),
            "global_due_count": global_due,
            "global_total_cards": len(self.schedule_records),
            "documents": documents,
        }

    def _ensure_schedule_records(self) -> None:
        changed = False
        now = self._now()

        for card in self.cards:
            card_id = self._card_id(card)
            if card_id not in self.schedule_records:
                self.schedule_records[card_id] = ScheduleRecord(
                    card_id=card_id,
                    document_id=self._get_card_doc_id(card),
                    question=self._get_question(card),
                    answer=self._get_answer(card),
                    source_ref=self._get_source_ref(card),
                    created_at=now,
                    next_due=now,
                    tags=[],
                )
                changed = True

        if changed:
            self.schedule_store.save_all(self.schedule_records)

    def _record_for_card(self, card: Any) -> ScheduleRecord:
        card_id = self._card_id(card)
        if card_id not in self.schedule_records:
            now = self._now()
            self.schedule_records[card_id] = ScheduleRecord(
                card_id=card_id,
                document_id=self._get_card_doc_id(card),
                question=self._get_question(card),
                answer=self._get_answer(card),
                source_ref=self._get_source_ref(card),
                created_at=now,
                next_due=now,
                tags=[],
            )
            self.schedule_store.save_all(self.schedule_records)

        return self.schedule_records[card_id]

    def _schedule(self, record: ScheduleRecord, quality: int) -> ScheduleRecord:
        """Apply the SuperMemo-2 scheduling algorithm to a reviewed card.

        The SM-2 quality score must be between 0 and 5. Scores below 3 reset
        repetitions and schedule a short retry. Scores from 3 to 5 increase the
        repetition count and calculate the next interval using the ease factor.
        The ease factor is bounded at 1.3 to avoid collapse, while the resulting
        interval is capped by MAX_INTERVAL_DAYS to prevent unrealistic review
        dates far in the future.
        """
        bounded_quality = max(0, min(5, int(quality)))
        now_dt = datetime.now(timezone.utc)

        record.ease_factor = record.ease_factor + (
            0.1 - (5 - bounded_quality) * (0.08 + (5 - bounded_quality) * 0.02)
        )
        record.ease_factor = max(1.3, record.ease_factor)

        if bounded_quality < 3:
            record.repetitions = 0
            record.interval_days = 1
        else:
            record.repetitions += 1
            if record.repetitions == 1:
                record.interval_days = 1
            elif record.repetitions == 2:
                record.interval_days = 6
            else:
                base_interval = max(1, record.interval_days)
                record.interval_days = int(round(base_interval * record.ease_factor))

        record.interval_days = max(1, min(self.MAX_INTERVAL_DAYS, record.interval_days))
        record.last_reviewed = now_dt.isoformat()
        record.next_due = (now_dt + timedelta(days=record.interval_days)).isoformat()
        record.confidence = str(bounded_quality)

        if bounded_quality >= 3:
            record.known_count += 1
            if bounded_quality >= 5:
                record.difficulty = "easy"
            elif bounded_quality == 4:
                record.difficulty = "medium"
            else:
                record.difficulty = "known"
        else:
            record.unknown_count += 1
            if bounded_quality == 2:
                record.difficulty = "hard"
            elif bounded_quality == 1:
                record.difficulty = "wrong"
            else:
                record.difficulty = "blackout"

        return record

    def _is_due(self, record: ScheduleRecord) -> bool:
        if not record.next_due:
            return True

        try:
            due = datetime.fromisoformat(record.next_due)
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            return due <= datetime.now(timezone.utc)
        except Exception:
            return True

    def _current_card(self) -> Any | None:
        if not self.cards or not self.filtered_indexes:
            return None

        self.current_filtered_index = max(
            0,
            min(self.current_filtered_index, len(self.filtered_indexes) - 1),
        )
        return self.cards[self.filtered_indexes[self.current_filtered_index]]

    @staticmethod
    def _tooltip_for(record: ScheduleRecord) -> str:
        return (
            f"Doc ID: {record.document_id}\n"
            f"Difficulty: {record.difficulty}\n"
            f"Next due: {record.next_due or 'Now'}\n"
            f"Ease Factor: {record.ease_factor:.2f}\n"
            f"Repetitions: {record.repetitions}"
        )

    def _update_dashboard(self) -> None:
        total = len(self.cards)
        filtered = len(self.filtered_indexes)
        due_count = (
            sum(1 for card in self.cards if self._is_due(self._record_for_card(card)))
            if self.cards
            else 0
        )

        mode_text = f"Document {self.document_id}" if self.document_id else "Global Review (All Docs)"
        self.meta_label.setText(f"Mode: {mode_text} | Cards: {total} | Filtered: {filtered}")
        self.session_label.setText(f"Session: {self.stats.studied} studied")
        self.due_label.setText(f"Due: {due_count}")
        self.accuracy_label.setText(f"Accuracy: {self.stats.accuracy}%")

        if self.stats.total > 0:
            progress_value = int((self.stats.studied / self.stats.total) * 100)
            self.study_progress.setValue(min(100, max(0, progress_value)))
        else:
            self.study_progress.setValue(0)

        self.accuracy_progress.setValue(min(100, max(0, int(self.stats.accuracy))))
        self.pie.set_values(self.stats.known, self.stats.unknown)

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self.progress.setVisible(busy)

        if busy:
            self.progress.setRange(0, 0)
            if message:
                self.meta_label.setText(message)
                self.status_message.emit(message)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self._update_dashboard()

        self._set_controls_enabled(not busy)

    def _set_controls_enabled(self, enabled: bool) -> None:
        has_cards = bool(self.cards)
        has_document = self.document_id is not None

        self.btn_global_review.setEnabled(enabled)
        self.btn_generate.setEnabled(enabled and has_document)
        self.btn_export.setEnabled(enabled and has_cards)
        self.btn_export_analytics.setEnabled(enabled)
        self.btn_shuffle.setEnabled(enabled and has_cards)
        self.filter_box.setEnabled(enabled)
        self.export_scope.setEnabled(enabled and has_cards)

        self.btn_prev.setEnabled(enabled and has_cards)
        self.btn_next.setEnabled(enabled and has_cards)
        self.btn_show.setEnabled(enabled and has_cards)

        for button in self._quality_buttons():
            button.setEnabled(enabled and has_cards)

    def _show_error_dialog(
        self,
        category: str,
        context: dict[str, Any],
        retry: Callable[[], None] | None = None,
    ) -> None:
        logger.error(f"Study {category} error", extra={"context": context})

        title = {
            "generation": "Flashcard Generation Error",
            "scheduling": "Scheduling Error",
            "export": "Export Error",
        }.get(category, "Study Error")

        message = self._format_error(context)

        if retry is not None:
            result = QMessageBox.question(
                self,
                title,
                message + "\n\nRetry?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if result == QMessageBox.StandardButton.Yes:
                retry()
            return

        QMessageBox.critical(self, title, message)

    @staticmethod
    def _unwrap(raw: Any) -> WorkerResult:
        if isinstance(raw, WorkerResult):
            return raw
        return WorkerResult(task_name="unknown", result=raw, success=True)

    @staticmethod
    def _format_error(context: dict[str, Any]) -> str:
        lines = [
            f"Operation: {context.get('operation', context.get('task_name', 'unknown'))}",
            f"Message: {context.get('error_message', context.get('error', ''))}",
        ]

        if context.get("document_id"):
            lines.append(f"Document ID: {context['document_id']}")

        if context.get("traceback"):
            lines.append(f"\nTraceback:\n{str(context['traceback'])[-4000:]}")

        return "\n".join(lines)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _read_value(card: Any, keys: tuple[str, ...], default: Any = None) -> Any:
        if isinstance(card, dict):
            for key in keys:
                if key in card and card[key] not in (None, ""):
                    return card[key]
            return default

        for key in keys:
            if hasattr(card, key):
                value = getattr(card, key)
                if value not in (None, ""):
                    return value

        return default

    @classmethod
    def _get_question(cls, card: Any) -> str:
        value = cls._read_value(card, ("question", "q", "front", "prompt"), "")
        return str(value or "")

    @classmethod
    def _get_answer(cls, card: Any) -> str:
        value = cls._read_value(card, ("answer", "a", "back", "response"), "")
        return str(value or "")

    @classmethod
    def _get_source_ref(cls, card: Any) -> str | None:
        value = cls._read_value(card, ("source_ref", "source", "sourceRef", "citation"), None)
        return str(value) if value not in (None, "") else None

    def _get_card_doc_id(self, card: Any) -> str:
        value = self._read_value(card, ("document_id", "documentId", "doc_id", "docId"), None)
        if value not in (None, ""):
            return str(value)
        return str(self.document_id or "0")

    def _get_existing_card_id(self, card: Any) -> str | None:
        value = self._read_value(card, ("card_id", "cardId", "id"), None)
        return str(value) if value not in (None, "") else None

    def _card_id(self, card: Any) -> str:
        existing = self._get_existing_card_id(card)
        if existing:
            return existing

        payload = "|".join(
            [
                self._get_card_doc_id(card),
                self._get_question(card),
                self._get_answer(card),
                self._get_source_ref(card) or "",
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
