from __future__ import annotations

import inspect
import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QThreadPool, Signal, Slot
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
    QVBoxLayout,
    QWidget,
)

from amba_ai.core.context_tracker import ContextTracker
from amba_ai.core.export import export_markdown
from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from amba_ai.ui.workers import FunctionWorker, WorkerResult


@dataclass
class LibraryDocument:
    document_id: int
    title: str
    kind: str
    created_at: str
    size: int | None = None
    tags: list[str] = field(default_factory=list)
    usage_count: int = 0
    deleted: bool = False


@dataclass(frozen=True)
class LibraryStats:
    total: int = 0
    deleted: int = 0
    total_size_bytes: int = 0
    most_used: list[int] = field(default_factory=list)


class LibraryView(QWidget):
    """
    Advanced offline library browser.

    Responsibilities:
    - Browse local documents
    - Filter and sort documents
    - Track lightweight usage heat-map state
    - Soft-delete and undo delete locally
    - Export summaries and portable JSON bundles
    - Update ContextTracker with real active UI/document state
    """

    document_selected = Signal(int)

    ACTIVE_TAB_NAME = "Library"

    def __init__(self, job_service: JobService, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.job_service = job_service
        self.thread_pool = QThreadPool.globalInstance()
        self.context_tracker: ContextTracker | None = getattr(job_service, "context_tracker", None)

        self._documents: list[LibraryDocument] = []
        self._last_deleted: list[LibraryDocument] = []

        self.header = QLabel("Library")
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search title, kind, or tag...")
        self.search.textChanged.connect(self.apply_filter)

        self.sort_by = QComboBox()
        self.sort_by.addItems(["Title", "Created Date", "Kind", "Most Used"])
        self.sort_by.currentIndexChanged.connect(self.apply_filter)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.itemDoubleClicked.connect(self.open_selected)
        self.list.currentItemChanged.connect(lambda *_: self._update_details())

        self.details = QLabel("No document selected.")

        self.tag_editor = QLineEdit()
        self.tag_editor.setPlaceholderText("Tags, comma-separated")

        self.btn_save_tags = QPushButton("Save Tags")
        self.btn_save_tags.clicked.connect(self.save_tags)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_open = QPushButton("Open")
        self.btn_delete = QPushButton("Delete")
        self.btn_undo = QPushButton("Undo Delete")
        self.btn_export = QPushButton("Export Summary")
        self.btn_bundle_export = QPushButton("Export Bundle")
        self.btn_bundle_import = QPushButton("Import Bundle")

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_open.clicked.connect(self.open_selected)
        self.btn_delete.clicked.connect(self.delete_selected)
        self.btn_undo.clicked.connect(self.undo_delete)
        self.btn_export.clicked.connect(self.export_selected)
        self.btn_bundle_export.clicked.connect(self.export_bundle)
        self.btn_bundle_import.clicked.connect(self.import_bundle)

        actions = QHBoxLayout()
        actions.addWidget(self.btn_refresh)
        actions.addWidget(self.btn_open)
        actions.addWidget(self.btn_delete)
        actions.addWidget(self.btn_undo)

        actions2 = QHBoxLayout()
        actions2.addWidget(self.btn_export)
        actions2.addWidget(self.btn_bundle_export)
        actions2.addWidget(self.btn_bundle_import)

        self.stats_label = QLabel("Documents: 0")
        self.heatmap_label = QLabel("Most used: n/a")

        layout = QVBoxLayout()
        layout.addWidget(self.header)
        layout.addWidget(self.search)
        layout.addWidget(self.sort_by)
        layout.addLayout(actions)
        layout.addLayout(actions2)
        layout.addWidget(self.progress)
        layout.addWidget(self.list)
        layout.addWidget(self.details)
        layout.addWidget(QLabel("Tags"))
        layout.addWidget(self.tag_editor)
        layout.addWidget(self.btn_save_tags)
        layout.addWidget(self.stats_label)
        layout.addWidget(self.heatmap_label)

        self.setLayout(layout)
        self._set_context(None)

    @Slot()
    def refresh(self) -> None:
        logger.info("Library refresh requested")
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

        self._documents.clear()

        for item in result.result or []:
            try:
                self._documents.append(self._document_from_any(item))
            except Exception:
                logger.warning(
                    "Invalid library document skipped",
                    extra={"context": {"item": str(item)[:500]}},
                    exc_info=True,
                )

        logger.info(
            "Library refresh completed",
            extra={"context": {"document_count": len(self._documents)}},
        )

        self.apply_filter()
        self._update_stats()

    @Slot()
    def apply_filter(self) -> None:
        needle = self.search.text().strip().lower()
        mode = self.sort_by.currentText()

        docs = [doc for doc in self._documents if not doc.deleted]

        if mode == "Title":
            docs.sort(key=lambda doc: doc.title.lower())
        elif mode == "Created Date":
            docs.sort(key=lambda doc: doc.created_at, reverse=True)
        elif mode == "Kind":
            docs.sort(key=lambda doc: doc.kind.lower())
        elif mode == "Most Used":
            docs.sort(key=lambda doc: doc.usage_count, reverse=True)

        self.list.clear()

        for doc in docs:
            haystack = f"{doc.title} {doc.kind} {' '.join(doc.tags)}".lower()
            if needle and needle not in haystack:
                continue

            item = QListWidgetItem(f"{doc.document_id}: {doc.title}")
            item.setData(Qt.ItemDataRole.UserRole, doc.document_id)
            item.setToolTip(
                f"Title: {doc.title}\n"
                f"Kind: {doc.kind}\n"
                f"Created: {doc.created_at}\n"
                f"Size: {doc.size or 'unknown'}\n"
                f"Tags: {', '.join(doc.tags) or 'none'}\n"
                f"Usage count: {doc.usage_count}"
            )
            self.list.addItem(item)

    def _update_details(self) -> None:
        ids = self.selected_document_ids()
        if len(ids) != 1:
            self.details.setText("Select exactly one document to edit tags.")
            self.tag_editor.clear()
            self._set_context(None)
            return

        doc = self._find_document(ids[0])
        if doc is None:
            self.details.setText("No document selected.")
            self.tag_editor.clear()
            self._set_context(None)
            return

        self.details.setText(
            f"{doc.title}\n"
            f"Kind: {doc.kind}\n"
            f"Created: {doc.created_at}\n"
            f"Usage count: {doc.usage_count}"
        )
        self.tag_editor.setText(", ".join(doc.tags))
        self._set_context(doc)

    @Slot()
    def save_tags(self) -> None:
        ids = self.selected_document_ids()
        if len(ids) != 1:
            QMessageBox.information(self, "Tags", "Select exactly one document.")
            return

        doc = self._find_document(ids[0])
        if doc is None:
            return

        doc.tags = [tag.strip() for tag in self.tag_editor.text().split(",") if tag.strip()]

        logger.info(
            "Tags updated",
            extra={"context": {"document_id": doc.document_id, "tags": doc.tags}},
        )

        self.apply_filter()
        self._set_context(doc)

    @Slot()
    def open_selected(self) -> None:
        ids = self.selected_document_ids()
        if not ids:
            return

        doc = self._find_document(ids[0])
        if doc is None:
            return

        doc.usage_count += 1
        self._update_stats()
        self._set_context(doc)

        logger.info(
            "Library document opened",
            extra={"context": {"document_id": doc.document_id, "usage_count": doc.usage_count}},
        )

        self.document_selected.emit(doc.document_id)

    @Slot()
    def delete_selected(self) -> None:
        ids = self.selected_document_ids()
        if not ids:
            return

        docs = [doc for doc in (self._find_document(doc_id) for doc_id in ids) if doc is not None]
        if not docs:
            return

        summary = "\n".join(f"- {doc.title} ({doc.kind})" for doc in docs)

        reply = QMessageBox.question(
            self,
            "Delete",
            f"Move {len(docs)} document(s) to recycle bin?\n\n{summary}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        for doc in docs:
            doc.deleted = True
            self._last_deleted.append(doc)

        logger.info(
            "Documents soft-deleted",
            extra={"context": {"count": len(docs), "document_ids": [doc.document_id for doc in docs]}},
        )

        self.apply_filter()
        self._update_stats()
        self._update_details()

    @Slot()
    def undo_delete(self) -> None:
        if not self._last_deleted:
            QMessageBox.information(self, "Undo", "Nothing to restore.")
            return

        for doc in self._last_deleted:
            doc.deleted = False

        restored = len(self._last_deleted)
        self._last_deleted.clear()

        logger.info("Delete undone", extra={"context": {"count": restored}})

        self.apply_filter()
        self._update_stats()

    def export_selected(self) -> None:
        ids = self.selected_document_ids()
        if not ids:
            QMessageBox.information(self, "Export", "Select at least one document.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export summaries",
            "summaries.md",
            "Markdown (*.md);;All Files (*)",
        )

        if not path:
            return

        try:
            contents: list[str] = []
            for doc_id in ids:
                doc = self._find_document(doc_id)
                title = doc.title if doc else f"Document {doc_id}"
                notes = self.job_service.get_notes(doc_id)
                contents.append(f"# {title}\n\n{notes}")

            result = export_markdown(str(path), "\n\n---\n\n".join(contents))
            output_path = self._normalize_export_result(result)

            QMessageBox.information(self, "Export", f"Saved to:\n{output_path}")

            logger.info(
                "Summaries exported",
                extra={"context": {"count": len(ids), "path": str(output_path)}},
            )

        except Exception as exc:
            logger.exception("Summary export failed")
            QMessageBox.critical(self, "Export Error", str(exc))

    def export_bundle(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export library bundle",
            "library_bundle.json",
            "JSON (*.json);;All Files (*)",
        )

        if not path:
            return

        output_path = Path(path).expanduser().resolve().with_suffix(".json")

        try:
            payload = {
                "schema": "amba_ai.library_bundle.v1",
                "exported_at": self._now_timestamp(),
                "documents": [asdict(doc) for doc in self._documents],
            }

            self._atomic_write_json(output_path, payload)

            QMessageBox.information(self, "Export Bundle", f"Saved to:\n{output_path}")

            logger.info(
                "Library bundle exported",
                extra={"context": {"path": str(output_path), "count": len(self._documents)}},
            )

        except Exception as exc:
            logger.exception("Library bundle export failed")
            QMessageBox.critical(self, "Export Error", str(exc))

    def import_bundle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import library bundle",
            "",
            "JSON (*.json);;All Files (*)",
        )

        if not path:
            return

        input_path = Path(path).expanduser().resolve()

        try:
            raw = json.loads(input_path.read_text(encoding="utf-8"))
            documents_payload = self._extract_bundle_documents(raw)

            imported = [self._document_from_bundle(item) for item in documents_payload]
            self._documents = imported
            self._last_deleted.clear()

            logger.info(
                "Library bundle imported",
                extra={"context": {"path": str(input_path), "count": len(imported)}},
            )

            self.apply_filter()
            self._update_stats()
            self._update_details()

        except Exception as exc:
            logger.exception("Library bundle import failed")
            QMessageBox.critical(self, "Import Error", str(exc))

    def _update_stats(self) -> None:
        active = [doc for doc in self._documents if not doc.deleted]
        deleted = len([doc for doc in self._documents if doc.deleted])
        total_size = sum(doc.size or 0 for doc in active)
        most_used = sorted(active, key=lambda doc: doc.usage_count, reverse=True)[:3]

        self.stats_label.setText(
            f"Documents: {len(active)} | Deleted: {deleted} | Storage: {total_size / 1024:.1f} KB"
        )

        if most_used:
            self.heatmap_label.setText(
                "Most used: "
                + ", ".join(f"{doc.title} ({doc.usage_count})" for doc in most_used)
            )
        else:
            self.heatmap_label.setText("Most used: n/a")

    def selected_document_ids(self) -> list[int]:
        ids: list[int] = []

        for item in self.list.selectedItems():
            value = item.data(Qt.ItemDataRole.UserRole)
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid selected document id ignored",
                    extra={"context": {"value": value}},
                )

        return ids

    def _find_document(self, doc_id: int) -> LibraryDocument | None:
        return next((doc for doc in self._documents if doc.document_id == doc_id), None)

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self.progress.setVisible(busy)

        if busy:
            self.progress.setRange(0, 0)
            if message:
                self.header.setText(message)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.header.setText("Library")

        self._set_controls_enabled(not busy)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.btn_refresh.setEnabled(enabled)
        self.btn_open.setEnabled(enabled)
        self.btn_delete.setEnabled(enabled)
        self.btn_undo.setEnabled(enabled)
        self.btn_export.setEnabled(enabled)
        self.btn_bundle_export.setEnabled(enabled)
        self.btn_bundle_import.setEnabled(enabled)
        self.search.setEnabled(enabled)
        self.sort_by.setEnabled(enabled)
        self.list.setEnabled(enabled)
        self.tag_editor.setEnabled(enabled)
        self.btn_save_tags.setEnabled(enabled)

    def _set_context(self, doc: LibraryDocument | None) -> None:
        if self.context_tracker is None:
            return

        self.context_tracker.set_active_tab(self.ACTIVE_TAB_NAME)

        if doc is not None:
            self.context_tracker.set_active_document(
                document_id=doc.document_id,
                title=doc.title,
            )
            self.context_tracker.set_extra_state("library_document_kind", doc.kind)
            self.context_tracker.set_extra_state("library_document_tags", ", ".join(doc.tags) or "none")
            self.context_tracker.set_extra_state("library_usage_count", doc.usage_count)

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
            error_context = context
        else:
            error_context = {"error": str(context)}

        logger.error("Library worker error", extra={"context": error_context})

        QMessageBox.critical(
            self,
            "Library Error",
            f"Operation failed.\n\n{error_context}",
        )

    def _handle_failure(self, result: WorkerResult) -> None:
        metadata = getattr(result, "metadata", {}) or {}
        context = {
            "task": getattr(result, "task_name", "unknown"),
            "error": getattr(result, "error", None),
            **metadata,
        }

        logger.error("Library operation failed", extra={"context": context})

        QMessageBox.critical(
            self,
            "Library Error",
            self._format_error(context),
        )

    @staticmethod
    def _format_error(context: dict[str, Any]) -> str:
        lines = [
            f"Task: {context.get('task', 'unknown')}",
        ]

        error = context.get("error") or context.get("error_message")
        if error:
            lines.append(f"Error: {error}")

        if context:
            lines.append(f"Context: {context}")

        return "\n".join(lines)

    @staticmethod
    def _document_from_any(item: Any) -> LibraryDocument:
        if isinstance(item, dict):
            document_id = item.get("id", item.get("document_id"))
            if document_id is None:
                raise ValueError("Document is missing id/document_id")

            return LibraryDocument(
                document_id=int(document_id),
                title=str(item.get("title") or ""),
                kind=str(item.get("kind") or ""),
                created_at=str(item.get("created_at") or ""),
                size=LibraryView._optional_int(item.get("size")),
                tags=LibraryView._normalize_tags(item.get("tags", [])),
                usage_count=int(item.get("usage_count") or 0),
                deleted=bool(item.get("deleted", False)),
            )

        document_id = getattr(item, "id", getattr(item, "document_id", None))
        if document_id is None:
            raise ValueError("Document object is missing id/document_id")

        return LibraryDocument(
            document_id=int(document_id),
            title=str(getattr(item, "title", "")),
            kind=str(getattr(item, "kind", "")),
            created_at=str(getattr(item, "created_at", "")),
            size=LibraryView._optional_int(getattr(item, "size", None)),
            tags=LibraryView._normalize_tags(getattr(item, "tags", [])),
            usage_count=int(getattr(item, "usage_count", 0) or 0),
            deleted=bool(getattr(item, "deleted", False)),
        )

    @staticmethod
    def _document_from_bundle(item: Any) -> LibraryDocument:
        if not isinstance(item, dict):
            raise ValueError("Bundle document must be an object")

        return LibraryView._document_from_any(item)

    @staticmethod
    def _extract_bundle_documents(raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, list):
            return raw

        if isinstance(raw, dict):
            documents = raw.get("documents")
            if isinstance(documents, list):
                return documents

        raise ValueError("Invalid library bundle format")

    @staticmethod
    def _normalize_tags(value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            return [tag.strip() for tag in value.split(",") if tag.strip()]

        if isinstance(value, list):
            return [str(tag).strip() for tag in value if str(tag).strip()]

        return []

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_export_result(result: Any) -> Path:
        if isinstance(result, Path):
            return result

        path = getattr(result, "path", None)
        if path is not None:
            return Path(path)

        return Path(str(result))

    @staticmethod
    def _atomic_write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.stem}.",
            suffix=".json.tmp",
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
            tmp_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _now_timestamp() -> float:
        import time

        return time.time()