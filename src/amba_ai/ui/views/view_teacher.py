from __future__ import annotations

import csv
import inspect
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from amba_ai.core.context_tracker import ContextTracker
from amba_ai.core.export import export_markdown, export_pdf
from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from amba_ai.ui.workers import FunctionWorker, WorkerResult


@dataclass(frozen=True)
class TeacherDocument:
    document_id: int
    title: str
    kind: str
    created_at: str
    size: int | None = None


@dataclass(frozen=True)
class LessonPackResult:
    document_id: int
    content: str
    item_count: int
    model_name: str | None
    created_at: str


@dataclass(frozen=True)
class QuizResult:
    document_id: int
    questions: list[str]
    question_count: int
    model_name: str | None
    created_at: str


@dataclass(frozen=True)
class TeachingHistoryItem:
    kind: str
    document_id: int
    created_at: str
    summary: str


class TeacherView(QWidget):
    """
    Teacher tools view for generating lesson packs, quizzes, and exports.

    This view does not call the LLM directly. It delegates all AI work to
    JobService and only updates UI state plus ContextTracker.
    """

    ACTIVE_TAB_NAME = "Teacher Tools"

    def __init__(self, job_service: JobService, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.job_service = job_service
        self.thread_pool = QThreadPool.globalInstance()
        self.context_tracker: ContextTracker | None = getattr(job_service, "context_tracker", None)

        self._documents: list[TeacherDocument] = []
        self.history: list[TeachingHistoryItem] = []

        self.header = QLabel("Teacher Tools")
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter documents by title or kind...")
        self.search.textChanged.connect(self._apply_filter)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)

        self.documents = QListWidget()
        self.documents.itemDoubleClicked.connect(self._on_document_double_click)
        self.documents.currentItemChanged.connect(lambda *_: self._update_context_from_selection())

        self.output = QTextEdit()
        self.output.setReadOnly(False)

        self.difficulty = QComboBox()
        self.difficulty.addItems(["Easy", "Medium", "Hard"])

        self.quiz_type = QComboBox()
        self.quiz_type.addItems(["Multiple Choice", "Short Answer"])

        self.btn_refresh = QPushButton("Refresh Library")
        self.btn_lesson_pack = QPushButton("Generate Lesson Pack")
        self.btn_quiz = QPushButton("Generate Quiz")
        self.btn_export_md = QPushButton("Export Markdown")
        self.btn_export_pdf = QPushButton("Export PDF")
        self.btn_export_csv = QPushButton("Export CSV")

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_lesson_pack.clicked.connect(self.generate_lesson_pack)
        self.btn_quiz.clicked.connect(self.generate_quiz)
        self.btn_export_md.clicked.connect(lambda: self.export_current("markdown"))
        self.btn_export_pdf.clicked.connect(lambda: self.export_current("pdf"))
        self.btn_export_csv.clicked.connect(lambda: self.export_current("csv"))

        controls = QHBoxLayout()
        controls.addWidget(self.btn_refresh)
        controls.addWidget(QLabel("Difficulty"))
        controls.addWidget(self.difficulty)
        controls.addWidget(QLabel("Quiz Type"))
        controls.addWidget(self.quiz_type)

        actions = QHBoxLayout()
        actions.addWidget(self.btn_lesson_pack)
        actions.addWidget(self.btn_quiz)
        actions.addWidget(self.btn_export_md)
        actions.addWidget(self.btn_export_pdf)
        actions.addWidget(self.btn_export_csv)

        layout = QVBoxLayout()
        layout.addWidget(self.header)
        layout.addWidget(self.search)
        layout.addLayout(controls)
        layout.addWidget(self.progress)
        layout.addWidget(self.documents)
        layout.addLayout(actions)
        layout.addWidget(QLabel("Output"))
        layout.addWidget(self.output)

        self.setLayout(layout)
        self._set_controls_enabled(True)
        self._set_context(active_document=None)

    @Slot()
    def refresh(self) -> None:
        self._set_busy(True, "Refreshing library...")

        worker = self._create_worker(
            self.job_service.list_documents,
            task_name="Refresh Library",
            max_retries=1,
        )
        worker.signals.finished.connect(self._on_refresh_finished)
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)

    @Slot(object)
    def _on_refresh_finished(self, raw: Any) -> None:
        self._set_busy(False)

        result = self._unwrap(raw)
        if not result.success:
            self._handle_failure(result)
            return

        self._documents = [self._document_from_any(item) for item in (result.result or [])]
        self._populate_documents(self._documents)

        logger.info(
            "Teacher library refreshed",
            extra={"context": {"document_count": len(self._documents)}},
        )

    def selected_document_id(self) -> int | None:
        item = self.documents.currentItem()
        if item is None:
            return None

        value = item.data(Qt.ItemDataRole.UserRole)
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @Slot()
    def generate_lesson_pack(self) -> None:
        document = self._selected_document()
        if document is None:
            QMessageBox.information(self, "Teacher", "Select a document first.")
            return

        difficulty = self.difficulty.currentText().lower()
        self._set_context(active_document=document, extra={"teacher_difficulty": difficulty})
        self._set_busy(True, "Generating lesson pack...")

        worker = self._create_worker(
            lambda: self._generate_lesson_pack_job(document, difficulty),
            task_name="Generate Lesson Pack",
            max_retries=1,
        )
        worker.signals.finished.connect(
            lambda raw, d=document.document_id: self._on_lesson_pack_finished(raw, d)
        )
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)

    def _generate_lesson_pack_job(
        self,
        document: TeacherDocument,
        difficulty: str,
    ) -> LessonPackResult:
        if hasattr(self.job_service, "generate_lesson_pack"):
            result = self.job_service.generate_lesson_pack(  # type: ignore[attr-defined]
                document.document_id,
                difficulty=difficulty,
            )
            if isinstance(result, LessonPackResult):
                return result
            return self._lesson_pack_from_any(result, document.document_id)

        notes = self.job_service.generate_notes_markdown(document.document_id)
        content = self._build_lesson_pack_from_notes(
            document=document,
            notes=notes,
            difficulty=difficulty,
        )

        return LessonPackResult(
            document_id=document.document_id,
            content=content,
            item_count=self._count_lesson_items(content),
            model_name="notes-derived",
            created_at=self._now_iso(),
        )

    def _on_lesson_pack_finished(self, raw: Any, document_id: int) -> None:
        self._set_busy(False)

        result = self._unwrap(raw)
        if not result.success:
            self._handle_failure(result, document_id)
            return

        pack = self._lesson_pack_from_any(result.result, document_id)
        self.output.setPlainText(pack.content)

        self.history.append(
            TeachingHistoryItem(
                kind="lesson_pack",
                document_id=document_id,
                created_at=pack.created_at,
                summary=f"{pack.item_count} items | {pack.model_name or 'unknown'}",
            )
        )

        logger.info(
            "Lesson pack generated",
            extra={
                "context": {
                    "document_id": document_id,
                    "item_count": pack.item_count,
                    "model_name": pack.model_name,
                }
            },
        )

    @Slot()
    def generate_quiz(self) -> None:
        document = self._selected_document()
        if document is None:
            QMessageBox.information(self, "Teacher", "Select a document first.")
            return

        quiz_type = self.quiz_type.currentText().lower()
        self._set_context(active_document=document, extra={"teacher_quiz_type": quiz_type})
        self._set_busy(True, "Generating quiz...")

        worker = self._create_worker(
            lambda: self._generate_quiz_job(document, quiz_type),
            task_name="Generate Quiz",
            max_retries=1,
        )
        worker.signals.finished.connect(
            lambda raw, d=document.document_id: self._on_quiz_finished(raw, d)
        )
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)

    def _generate_quiz_job(self, document: TeacherDocument, quiz_type: str) -> QuizResult:
        method = self.job_service.generate_quiz

        try:
            signature = inspect.signature(method)
            if "quiz_type" in signature.parameters:
                result = method(document.document_id, quiz_type=quiz_type, count=10)
            else:
                result = method(document.document_id, count=10)
        except TypeError:
            result = method(document.document_id)

        return self._quiz_from_any(result, document.document_id)

    def _on_quiz_finished(self, raw: Any, document_id: int) -> None:
        self._set_busy(False)

        result = self._unwrap(raw)
        if not result.success:
            self._handle_failure(result, document_id)
            return

        quiz = self._quiz_from_any(result.result, document_id)
        self.output.setPlainText("\n\n".join(quiz.questions))

        self.history.append(
            TeachingHistoryItem(
                kind="quiz",
                document_id=document_id,
                created_at=quiz.created_at,
                summary=f"{quiz.question_count} questions | {quiz.model_name or 'unknown'}",
            )
        )

        logger.info(
            "Quiz generated",
            extra={
                "context": {
                    "document_id": document_id,
                    "question_count": quiz.question_count,
                    "model_name": quiz.model_name,
                }
            },
        )

    def export_current(self, fmt: str) -> None:
        text = self.output.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Teacher", "Nothing to export.")
            return

        ext = "md" if fmt == "markdown" else fmt
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export content",
            f"teacher_export.{ext}",
            f"{ext.upper()} (*.{ext});;All Files (*)",
        )

        if not path:
            return

        output_path = Path(path).expanduser().resolve()

        try:
            if fmt == "markdown":
                result_path = self._normalize_export_result(export_markdown(str(output_path), text))
            elif fmt == "pdf":
                result_path = self._normalize_export_result(export_pdf(str(output_path), "Teacher Export", text))
            elif fmt == "csv":
                result_path = self._export_text_lines_csv(output_path.with_suffix(".csv"), text)
            else:
                raise ValueError(f"Unsupported export format: {fmt}")

            QMessageBox.information(self, "Exported", f"Saved to:\n{result_path}")

            logger.info(
                "Teacher export completed",
                extra={
                    "context": {
                        "format": fmt,
                        "path": str(result_path),
                    }
                },
            )

        except Exception as exc:
            logger.exception(
                "Teacher export failed",
                extra={"context": {"format": fmt, "path": str(output_path)}},
            )
            QMessageBox.critical(self, "Export Error", str(exc))

    def _on_document_double_click(self, _: QListWidgetItem) -> None:
        self.generate_lesson_pack()

    def _apply_filter(self, text: str) -> None:
        query = text.lower().strip()

        if not query:
            self._populate_documents(self._documents)
            return

        filtered = [
            doc
            for doc in self._documents
            if query in doc.title.lower() or query in doc.kind.lower()
        ]
        self._populate_documents(filtered)

    def _populate_documents(self, documents: list[TeacherDocument]) -> None:
        self.documents.clear()

        for doc in documents:
            item = QListWidgetItem(f"{doc.document_id}: {doc.title}")
            item.setData(Qt.ItemDataRole.UserRole, doc.document_id)
            item.setToolTip(
                f"Title: {doc.title}\n"
                f"Kind: {doc.kind}\n"
                f"Created: {doc.created_at}\n"
                f"Size: {doc.size or 'unknown'}"
            )
            self.documents.addItem(item)

    def _selected_document(self) -> TeacherDocument | None:
        document_id = self.selected_document_id()
        if document_id is None:
            return None

        return next(
            (doc for doc in self._documents if doc.document_id == document_id),
            None,
        )

    def _update_context_from_selection(self) -> None:
        self._set_context(active_document=self._selected_document())

    def _set_context(
        self,
        *,
        active_document: TeacherDocument | None,
        extra: dict[str, str] | None = None,
    ) -> None:
        if self.context_tracker is None:
            return

        self.context_tracker.set_active_tab(self.ACTIVE_TAB_NAME)

        if active_document is not None:
            self.context_tracker.set_active_document(
                document_id=active_document.document_id,
                title=active_document.title,
            )

        if extra:
            for key, value in extra.items():
                self.context_tracker.set_extra_state(key, value)

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self.progress.setVisible(busy)

        if busy:
            self.progress.setRange(0, 0)
            if message:
                self.header.setText(message)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.header.setText("Teacher Tools")

        self._set_controls_enabled(not busy)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.btn_refresh.setEnabled(enabled)
        self.btn_lesson_pack.setEnabled(enabled)
        self.btn_quiz.setEnabled(enabled)
        self.btn_export_md.setEnabled(enabled)
        self.btn_export_pdf.setEnabled(enabled)
        self.btn_export_csv.setEnabled(enabled)
        self.search.setEnabled(enabled)
        self.difficulty.setEnabled(enabled)
        self.quiz_type.setEnabled(enabled)
        self.documents.setEnabled(enabled)
        self.output.setEnabled(enabled)

    def _create_worker(
        self,
        fn: Callable[..., Any],
        *args: Any,
        task_name: str,
        max_retries: int = 0,
        **kwargs: Any,
    ) -> FunctionWorker:
        try:
            signature = inspect.signature(FunctionWorker)
            if "task_name" in signature.parameters:
                return FunctionWorker(
                    fn,
                    *args,
                    task_name=task_name,
                    max_retries=max_retries,
                    **kwargs,
                )
        except Exception:
            pass

        return FunctionWorker(fn, *args, **kwargs)

    @staticmethod
    def _unwrap(raw: Any) -> WorkerResult:
        if isinstance(raw, WorkerResult):
            return raw

        return WorkerResult(
            task_name="unknown",
            result=raw,
            success=True,
        )

    @Slot(object)
    def _on_worker_error(self, context: Any) -> None:
        self._set_busy(False)

        if isinstance(context, dict):
            metadata = context
        else:
            metadata = {"error": str(context)}

        result = WorkerResult(
            task_name=str(metadata.get("task_name") or metadata.get("operation") or "worker"),
            result=None,
            success=False,
            error=str(metadata.get("error") or metadata.get("error_message") or metadata),
            metadata=metadata,
        )
        self._handle_failure(result)

    def _handle_failure(self, result: WorkerResult, document_id: int | None = None) -> None:
        metadata = getattr(result, "metadata", {}) or {}
        context = {
            "task": getattr(result, "task_name", "unknown"),
            "document_id": document_id,
            "error": getattr(result, "error", None),
            **metadata,
        }

        logger.error("Teacher operation failed", extra={"context": context})

        retry = QMessageBox.question(
            self,
            "Teacher Error",
            self._format_error(context) + "\n\nRetry?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if retry == QMessageBox.StandardButton.Yes:
            self.refresh()

    @staticmethod
    def _format_error(context: dict[str, Any]) -> str:
        lines = [
            f"Task: {context.get('task', 'unknown')}",
            f"Document ID: {context.get('document_id', 'n/a')}",
        ]

        error = context.get("error") or context.get("error_message")
        if error:
            lines.append(f"Error: {error}")

        if context:
            lines.append(f"Context: {context}")

        return "\n".join(lines)

    @staticmethod
    def _document_from_any(doc: Any) -> TeacherDocument:
        if isinstance(doc, dict):
            return TeacherDocument(
                document_id=int(doc.get("id") or doc.get("document_id")),
                title=str(doc.get("title") or ""),
                kind=str(doc.get("kind") or ""),
                created_at=str(doc.get("created_at") or ""),
                size=doc.get("size"),
            )

        return TeacherDocument(
            document_id=int(getattr(doc, "id", getattr(doc, "document_id"))),
            title=str(getattr(doc, "title", "")),
            kind=str(getattr(doc, "kind", "")),
            created_at=str(getattr(doc, "created_at", "")),
            size=getattr(doc, "size", None),
        )

    @staticmethod
    def _lesson_pack_from_any(value: Any, document_id: int) -> LessonPackResult:
        if isinstance(value, LessonPackResult):
            return value

        if isinstance(value, dict):
            content = str(value.get("content") or value.get("markdown") or value.get("text") or "")
            return LessonPackResult(
                document_id=int(value.get("document_id") or document_id),
                content=content,
                item_count=int(value.get("item_count") or TeacherView._count_lesson_items(content)),
                model_name=value.get("model_name"),
                created_at=str(value.get("created_at") or TeacherView._now_iso()),
            )

        content = str(getattr(value, "content", getattr(value, "markdown_notes", value)))
        return LessonPackResult(
            document_id=int(getattr(value, "document_id", document_id)),
            content=content,
            item_count=int(getattr(value, "item_count", TeacherView._count_lesson_items(content))),
            model_name=getattr(value, "model_name", None),
            created_at=str(getattr(value, "created_at", TeacherView._now_iso())),
        )

    @staticmethod
    def _quiz_from_any(value: Any, document_id: int) -> QuizResult:
        if isinstance(value, QuizResult):
            return value

        if isinstance(value, dict):
            raw_questions = value.get("questions") or value.get("mcqs") or []
            questions = TeacherView._format_questions(raw_questions)
            return QuizResult(
                document_id=int(value.get("document_id") or document_id),
                questions=questions,
                question_count=len(questions),
                model_name=value.get("model_name"),
                created_at=str(value.get("created_at") or TeacherView._now_iso()),
            )

        if isinstance(value, list):
            questions = TeacherView._format_questions(value)
            return QuizResult(
                document_id=document_id,
                questions=questions,
                question_count=len(questions),
                model_name=None,
                created_at=TeacherView._now_iso(),
            )

        raw_questions = getattr(value, "questions", getattr(value, "mcqs", []))
        questions = TeacherView._format_questions(raw_questions)
        return QuizResult(
            document_id=int(getattr(value, "document_id", document_id)),
            questions=questions,
            question_count=int(getattr(value, "question_count", len(questions))),
            model_name=getattr(value, "model_name", None),
            created_at=str(getattr(value, "created_at", TeacherView._now_iso())),
        )

    @staticmethod
    def _format_questions(raw_questions: Any) -> list[str]:
        if raw_questions is None:
            return []

        formatted: list[str] = []

        for index, item in enumerate(list(raw_questions), start=1):
            if isinstance(item, str):
                formatted.append(item)
                continue

            question = getattr(item, "question", None)
            choices = getattr(item, "choices", None)
            correct_answer = getattr(item, "correct_answer", None)
            explanation = getattr(item, "explanation", None)

            if isinstance(item, dict):
                question = item.get("question", question)
                choices = item.get("choices", choices)
                correct_answer = item.get("correct_answer", correct_answer)
                explanation = item.get("explanation", explanation)

            lines = [f"{index}. {question or 'Question'}"]

            if choices:
                for choice in choices:
                    lines.append(f"   - {choice}")

            if correct_answer:
                lines.append(f"   Correct: {correct_answer}")

            if explanation:
                lines.append(f"   Explanation: {explanation}")

            formatted.append("\n".join(lines))

        return formatted

    @staticmethod
    def _build_lesson_pack_from_notes(
        *,
        document: TeacherDocument,
        notes: str,
        difficulty: str,
    ) -> str:
        clean_notes = notes.strip() or "No notes are currently available for this document."
        return (
            f"# Lesson Pack: {document.title}\n\n"
            f"**Document ID:** {document.document_id}\n"
            f"**Difficulty:** {difficulty.title()}\n"
            f"**Generated:** {TeacherView._now_iso()}\n\n"
            "## Teaching Objectives\n"
            "- Help students understand the main concepts from the source material.\n"
            "- Support classroom explanation, guided practice, and review.\n"
            "- Provide a structured reference for teacher-led instruction.\n\n"
            "## Source-Based Teaching Notes\n\n"
            f"{clean_notes}\n\n"
            "## Suggested Classroom Flow\n"
            "1. Begin with prior-knowledge questions.\n"
            "2. Explain the key ideas using the notes above.\n"
            "3. Ask students to summarize the concept in their own words.\n"
            "4. Use quiz or flashcard generation for quick assessment.\n\n"
            "## Teacher Verification\n"
            "- Review the content before classroom use.\n"
            "- Add local examples where appropriate.\n"
        )

    @staticmethod
    def _count_lesson_items(content: str) -> int:
        return sum(
            1
            for line in content.splitlines()
            if line.strip().startswith(("-", "*", "1.", "2.", "3.", "4.", "5."))
        )

    @staticmethod
    def _normalize_export_result(result: Any) -> Path:
        if isinstance(result, Path):
            return result

        path = getattr(result, "path", None)
        if path is not None:
            return Path(path)

        return Path(str(result))

    @staticmethod
    def _export_text_lines_csv(path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.stem}.",
            suffix=".csv.tmp",
            dir=str(path.parent),
        )
        tmp_path = Path(tmp_name)

        try:
            Path(tmp_name).unlink(missing_ok=True)
            with tmp_path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["line_number", "text"])
                for index, line in enumerate(text.splitlines(), start=1):
                    writer.writerow([index, line])

            tmp_path.replace(path)
            return path

        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        finally:
            try:
                import os

                os.close(fd)
            except Exception:
                pass

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()