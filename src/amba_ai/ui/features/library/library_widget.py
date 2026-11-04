from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import (
    QModelIndex,
    QPoint,
    QSettings,
    QSize,
    QSortFilterProxyModel,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
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
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from amba_ai.ui.common.qss_utils import apply_local_qss
from amba_ai.ui.common.ui_icons_utils import icon
from .data_classes import LibraryDocument
from .library_manager import LibraryManager


class LibraryFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._text_filter = ""
        self._kind_filter = "All"
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_text_filter(self, text: str) -> None:
        normalized = str(text or "").strip().lower()
        if self._text_filter != normalized:
            self._text_filter = normalized
            self.invalidateFilter()

    def set_kind_filter(self, kind: str) -> None:
        normalized = str(kind or "All").strip()
        if self._kind_filter != normalized:
            self._kind_filter = normalized
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if not isinstance(model, QStandardItemModel):
            return super().filterAcceptsRow(source_row, source_parent)

        if self._kind_filter != "All":
            kind_index = model.index(source_row, LibraryWidget.COL_KIND, source_parent)
            kind_val = str(model.data(kind_index, Qt.ItemDataRole.DisplayRole) or "")
            if kind_val.lower() != self._kind_filter.lower():
                return False

        if not self._text_filter:
            return True

        # Search only safe non-path user-visible columns
        searchable_columns = [
            LibraryWidget.COL_ID,
            LibraryWidget.COL_TITLE,
            LibraryWidget.COL_KIND,
            LibraryWidget.COL_ORIGIN,
        ]

        for col in searchable_columns:
            index = model.index(source_row, col, source_parent)
            val = model.data(index, Qt.ItemDataRole.DisplayRole)
            if val and self._text_filter in str(val).lower():
                return True

        return False


class LibraryWidget(QWidget):
    documentSelected = Signal(int)
    documentActivated = Signal(int)
    libraryRefreshed = Signal(list)
    statusMessage = Signal(str, str)
    operationStarted = Signal(str)
    operationFinished = Signal(str)

    COL_ID = 0
    COL_TITLE = 1
    COL_KIND = 2
    COL_STATUS = 3
    COL_CHUNKS = 4
    COL_ORIGIN = 5
    COL_CREATED = 6
    MODEL_TOTAL_COLUMNS = 7

    def __init__(
        self,
        settings: QSettings,
        job_service: JobService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.settings = settings
        self.jobs = job_service
        self.library_manager = LibraryManager(job_service, self)
        self._is_operation_active = False
        self._documents: list[LibraryDocument] = []
        self._selected_doc: LibraryDocument | None = None

        self.results_model = QStandardItemModel(0, self.MODEL_TOTAL_COLUMNS, self)
        self.proxy_model = LibraryFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.results_model)

        self.setObjectName("AmbaLibraryWidgetUI")

        self._setup_ui()
        self._connect_signals()
        self._load_local_styles()
        self._post_init_setup()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self._setup_action_bar(main_layout)
        self._setup_master_detail_workspace(main_layout)
        self._setup_bottom_bar(main_layout)
        self._setup_model_headers()
        self._configure_tree_columns()

    def _setup_action_bar(self, main_layout: QVBoxLayout) -> None:
        control_card = QFrame()
        control_card.setObjectName("controlCard")
        bar_layout = QHBoxLayout(control_card)
        bar_layout.setContentsMargins(8, 6, 8, 6)
        bar_layout.setSpacing(10)

        # Search field
        self.library_filter = QLineEdit()
        self.library_filter.setObjectName("libraryFilter")
        self.library_filter.setPlaceholderText(self.tr("Search library by title, type, or origin..."))
        self.library_filter.setClearButtonEnabled(True)
        bar_layout.addWidget(self.library_filter, stretch=2)

        # Kind filter dropdown
        lbl_kind = QLabel(self.tr("Type:"))
        lbl_kind.setStyleSheet("color: #94A3B8; font-weight: 600;")
        bar_layout.addWidget(lbl_kind)

        self.kind_filter_combo = QComboBox()
        self.kind_filter_combo.setObjectName("kindFilterCombo")
        self.kind_filter_combo.addItem("All")
        bar_layout.addWidget(self.kind_filter_combo)

        bar_layout.addStretch(1)

        # Buttons
        self.refresh_btn = QPushButton(icon("refresh"), self.tr("Refresh"))
        self.refresh_btn.setObjectName("refreshLibraryButton")
        self.refresh_btn.setProperty("variant", "secondary")

        self.open_notes_btn = QPushButton(icon("notes"), self.tr("Study Notes"))
        self.open_notes_btn.setObjectName("openNotesButton")
        self.open_notes_btn.setProperty("priority", "primary")

        bar_layout.addWidget(self.refresh_btn)
        bar_layout.addWidget(self.open_notes_btn)
        main_layout.addWidget(control_card)

    def _setup_master_detail_workspace(self, main_layout: QVBoxLayout) -> None:
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("mainSplitter")

        # Left: Interactive Table
        list_container = QFrame()
        list_container.setObjectName("containerFrame")
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)

        self.documents_tree = QTreeView()
        self.documents_tree.setObjectName("libraryDocumentsTree")
        self.documents_tree.setModel(self.proxy_model)
        self.documents_tree.setAlternatingRowColors(True)
        self.documents_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.documents_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.documents_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.documents_tree.setSortingEnabled(True)
        self.documents_tree.setUniformRowHeights(True)

        list_layout.addWidget(self.documents_tree)
        self.splitter.addWidget(list_container)

        # Right: Clean Inspector & Metadata Card
        self.inspector_card = QFrame()
        self.inspector_card.setObjectName("inspectorCard")
        inspector_layout = QVBoxLayout(self.inspector_card)
        inspector_layout.setContentsMargins(12, 12, 12, 12)
        inspector_layout.setSpacing(10)

        inspector_header = QLabel(self.tr("Document Inspector"))
        inspector_header.setStyleSheet("font-weight: 700; color: #2DD4BF; font-size: 11pt;")
        inspector_layout.addWidget(inspector_header)

        self.inspector_browser = QTextBrowser()
        self.inspector_browser.setObjectName("inspectorDisplay")
        self.inspector_browser.setOpenExternalLinks(False)
        self.inspector_browser.setHtml(
            "<div style='margin-top:40px; text-align:center; color:#64748B;'>"
            "<i>Select a document from the list to view study statistics and structure.</i>"
            "</div>"
        )
        inspector_layout.addWidget(self.inspector_browser, stretch=1)

        # Quick action inside inspector
        self.inspector_notes_btn = QPushButton(icon("notes"), self.tr("Open Interactive Study Notes"))
        self.inspector_notes_btn.setEnabled(False)
        self.inspector_notes_btn.setProperty("priority", "primary")
        self.inspector_notes_btn.clicked.connect(self._emit_document_activated)
        inspector_layout.addWidget(self.inspector_notes_btn)

        self.splitter.addWidget(self.inspector_card)
        self.splitter.setSizes([680, 320])
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)

        main_layout.addWidget(self.splitter, stretch=1)

    def _setup_bottom_bar(self, main_layout: QVBoxLayout) -> None:
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(4, 2, 4, 2)
        bottom_bar.setSpacing(6)

        self.overall_status_label = QLabel(self.tr("Library ready."))
        self.overall_status_label.setObjectName("footerStatusLabel")
        bottom_bar.addWidget(self.overall_status_label, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setFixedHeight(16)
        bottom_bar.addWidget(self.progress_bar)

        main_layout.addLayout(bottom_bar)

    def _setup_model_headers(self) -> None:
        headers = [
            self.tr("ID"),
            self.tr("Title"),
            self.tr("Format"),
            self.tr("AI Knowledge Index"),
            self.tr("Units/Chunks"),
            self.tr("Origin Source"),
            self.tr("Date Ingested"),
        ]
        self.results_model.setHorizontalHeaderLabels(headers)

    def _configure_tree_columns(self) -> None:
        header = self.documents_tree.header()
        header.setMinimumSectionSize(28)
        header.setSectionResizeMode(self.COL_ID, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_KIND, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_CHUNKS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_TITLE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_ORIGIN, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(self.COL_CREATED, QHeaderView.ResizeMode.Interactive)
        self.documents_tree.setColumnWidth(self.COL_ORIGIN, 160)
        self.documents_tree.setColumnWidth(self.COL_CREATED, 150)

    def _connect_signals(self) -> None:
        self.refresh_btn.clicked.connect(self.refresh_documents)
        self.open_notes_btn.clicked.connect(self._emit_document_activated)
        self.library_filter.textChanged.connect(self.proxy_model.set_text_filter)
        self.kind_filter_combo.currentTextChanged.connect(self.proxy_model.set_kind_filter)

        self.documents_tree.doubleClicked.connect(self._on_document_double_clicked)
        self.documents_tree.customContextMenuRequested.connect(self._show_context_menu)

        selection_model = self.documents_tree.selectionModel()
        if selection_model is not None:
            selection_model.currentChanged.connect(self._on_tree_selection_changed)

        self.library_manager.libraryRefreshStarted.connect(self._on_manager_refresh_started)
        self.library_manager.libraryRefreshFinished.connect(self._on_manager_refresh_finished)
        self.library_manager.libraryRefreshFailed.connect(self._on_manager_refresh_failed)
        self.library_manager.statusMessage.connect(self.statusMessage.emit)
        self.library_manager.operationStarted.connect(self.operationStarted.emit)
        self.library_manager.operationFinished.connect(self.operationFinished.emit)

    def _load_local_styles(self) -> None:
        qss_path = Path(__file__).parent / "library.qss"
        apply_local_qss(self, qss_path)

    def _post_init_setup(self) -> None:
        self._update_ui_for_operation_status()

    @Slot()
    def refresh_documents(self) -> None:
        self.library_manager.refresh_documents()

    @Slot()
    def _on_manager_refresh_started(self) -> None:
        self._is_operation_active = True
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.overall_status_label.setText(self.tr("Refreshing document library..."))
        self._update_ui_for_operation_status()

    @Slot(list)
    def _on_manager_refresh_finished(self, documents: list[Any]) -> None:
        self._is_operation_active = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)

        normalized = [doc for item in documents if (doc := LibraryDocument.from_any(item))]
        self._documents = normalized
        self._populate_kind_filter()
        self._display_documents(normalized)

        msg = self.tr(f"Library synchronized: {len(normalized)} resource(s) loaded.")
        self.overall_status_label.setText(msg)
        self.libraryRefreshed.emit([d.to_dict() for d in normalized])
        self._update_ui_for_operation_status()

    @Slot(dict)
    def _on_manager_refresh_failed(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        self.progress_bar.setVisible(False)
        msg = str(error_context.get("error_message") or "Library refresh failed.")
        self.overall_status_label.setText(msg)
        self._update_ui_for_operation_status()

    def _populate_kind_filter(self) -> None:
        current = self.kind_filter_combo.currentText()
        kinds = sorted({doc.kind for doc in self._documents if doc.kind})

        self.kind_filter_combo.blockSignals(True)
        self.kind_filter_combo.clear()
        self.kind_filter_combo.addItem("All")
        self.kind_filter_combo.addItems(kinds)

        idx = self.kind_filter_combo.findText(current)
        if idx >= 0:
            self.kind_filter_combo.setCurrentIndex(idx)
        self.kind_filter_combo.blockSignals(False)

    def _display_documents(self, documents: list[LibraryDocument]) -> None:
        self.documents_tree.setSortingEnabled(False)
        self.results_model.removeRows(0, self.results_model.rowCount())

        root = self.results_model.invisibleRootItem()
        for doc in documents:
            root.appendRow(self._create_document_row(doc))

        self.documents_tree.setSortingEnabled(True)
        if self.results_model.rowCount() > 0:
            self.documents_tree.sortByColumn(self.COL_ID, Qt.SortOrder.DescendingOrder)

    def _create_document_row(self, doc: LibraryDocument) -> list[QStandardItem]:
        row = [QStandardItem() for _ in range(self.MODEL_TOTAL_COLUMNS)]

        # ID
        row[self.COL_ID].setText(f"#{doc.document_id}")
        row[self.COL_ID].setData(doc, Qt.ItemDataRole.UserRole)
        row[self.COL_ID].setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Title
        row[self.COL_TITLE].setText(f"📄 {doc.title}")
        row[self.COL_TITLE].setToolTip(doc.title)
        row[self.COL_TITLE].setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))

        # Kind
        row[self.COL_KIND].setText(doc.kind)
        row[self.COL_KIND].setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        # Knowledge Index Status Badge
        status_text = "● Ready" if doc.rag_indexed else "○ Unindexed"
        status_item = row[self.COL_STATUS]
        status_item.setText(status_text)
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if doc.rag_indexed:
            status_item.setForeground(QColor("#2DD4BF"))
        else:
            status_item.setForeground(QColor("#94A3B8"))

        # Chunk Count
        row[self.COL_CHUNKS].setText(str(doc.chunk_count))
        row[self.COL_CHUNKS].setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        # Privacy Safe Origin (FILENAME ONLY, NO DIRECTORY PATHS)
        row[self.COL_ORIGIN].setText(doc.safe_filename)
        row[self.COL_ORIGIN].setToolTip(self.tr("Sanitized document source"))

        # Created Date
        row[self.COL_CREATED].setText(doc.created_at or "-")

        for item in row:
            item.setEditable(False)

        return row

    @Slot(QModelIndex, QModelIndex)
    def _on_tree_selection_changed(self, current_proxy: QModelIndex, previous_proxy: QModelIndex) -> None:
        if not current_proxy.isValid():
            self._selected_doc = None
            self.inspector_browser.setHtml(
                "<div style='text-align:center; color:#64748B; margin-top:40px;'>"
                "<i>Select a document from the list to view statistics.</i>"
                "</div>"
            )
            self._update_ui_for_operation_status()
            return

        source_idx = self.proxy_model.mapToSource(current_proxy)
        id_item = self.results_model.item(source_idx.row(), self.COL_ID)
        if not id_item:
            return

        doc = id_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(doc, LibraryDocument):
            return

        self._selected_doc = doc
        self._render_inspector_card(doc)
        self.documentSelected.emit(doc.document_id)
        self.overall_status_label.setText(self.tr(f"Loaded: {doc.title}"))
        self._update_ui_for_operation_status()

    def _render_inspector_card(self, doc: LibraryDocument) -> None:
        """Presents rich metadata and study metrics without leaking internal host paths."""
        metadata = doc.sanitized_metadata
        meta_snippet = ""
        if metadata:
            meta_snippet = (
                f"<div style='margin-top:12px; font-weight:600; color:#38BDF8;'>Configuration & Tags</div>"
                f"<pre style='background-color:#020617; padding:8px; border-radius:6px; font-size:8.5pt; color:#CBD5E1;'>"
                f"{escape(json.dumps(metadata, indent=2))}</pre>"
            )

        rag_badge = (
            "<span style='background:#134E4A; color:#2DD4BF; padding:2px 8px; border-radius:10px; font-weight:600;'>Synchronized</span>"
            if doc.rag_indexed
            else "<span style='background:#334155; color:#94A3B8; padding:2px 8px; border-radius:10px;'>Offline Store</span>"
        )

        html = f"""
        <html>
        <body style="font-family:'Segoe UI', sans-serif; color:#E2E8F0; font-size:9.5pt;">
            <div style="font-size:12pt; font-weight:700; color:#F8FAFC; margin-bottom:4px;">{escape(doc.title)}</div>
            <div style="color:#94A3B8; margin-bottom:12px;">Format: <b>{escape(doc.kind)}</b> • {rag_badge}</div>

            <table style="width:100%; border-collapse:collapse; margin-top:8px;">
                <tr><td style="color:#94A3B8; padding:4px 0;">Document Ref:</td><td style="font-weight:600;">#{doc.document_id}</td></tr>
                <tr><td style="color:#94A3B8; padding:4px 0;">Reading Time:</td><td style="color:#38BDF8; font-weight:600;">{doc.estimated_read_time}</td></tr>
                <tr><td style="color:#94A3B8; padding:4px 0;">Knowledge Units:</td><td>{doc.chunk_count} chunks</td></tr>
                <tr><td style="color:#94A3B8; padding:4px 0;">Text Volume:</td><td>{doc.text_length:,} characters</td></tr>
                <tr><td style="color:#94A3B8; padding:4px 0;">Origin Reference:</td><td style="color:#A7F3D0;">{escape(doc.safe_filename)}</td></tr>
                <tr><td style="color:#94A3B8; padding:4px 0;">Date Added:</td><td>{escape(doc.created_at or 'Recently')}</td></tr>
            </table>

            {meta_snippet}
        </body>
        </html>
        """
        self.inspector_browser.setHtml(html)

    @Slot(QModelIndex)
    def _on_document_double_clicked(self, proxy_index: QModelIndex) -> None:
        if not proxy_index.isValid():
            return
        source_idx = self.proxy_model.mapToSource(proxy_index)
        id_item = self.results_model.item(source_idx.row(), self.COL_ID)
        if id_item:
            doc = id_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(doc, LibraryDocument):
                self._selected_doc = doc
                self.documentActivated.emit(doc.document_id)

    @Slot()
    def _emit_document_activated(self) -> None:
        if self._selected_doc is None:
            QMessageBox.information(self, self.tr("No Selection"), self.tr("Please select a document first."))
            return
        self.documentActivated.emit(self._selected_doc.document_id)

    @Slot(QPoint)
    def _show_context_menu(self, pos: QPoint) -> None:
        proxy_idx = self.documents_tree.indexAt(pos)
        if not proxy_idx.isValid():
            return
        source_idx = self.proxy_model.mapToSource(proxy_idx)
        id_item = self.results_model.item(source_idx.row(), self.COL_ID)
        if not id_item:
            return

        doc = id_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(doc, LibraryDocument):
            return

        menu = QMenu(self.documents_tree)
        act_open = menu.addAction(icon("notes"), self.tr("Study Notes"))
        act_open.triggered.connect(lambda: self.documentActivated.emit(doc.document_id))

        act_select = menu.addAction(icon("check"), self.tr("Select Resource"))
        act_select.triggered.connect(lambda: self.documentSelected.emit(doc.document_id))

        menu.addSeparator()
        menu.addAction(self.tr("Copy Title"), lambda: QApplication.clipboard().setText(doc.title))
        menu.addAction(self.tr("Copy ID"), lambda: QApplication.clipboard().setText(str(doc.document_id)))

        menu.exec(self.documents_tree.viewport().mapToGlobal(pos))

    def _update_ui_for_operation_status(self) -> None:
        inactive = not self._is_operation_active
        has_sel = self._selected_doc is not None
        self.refresh_btn.setEnabled(inactive)
        self.open_notes_btn.setEnabled(inactive and has_sel)
        self.inspector_notes_btn.setEnabled(inactive and has_sel)
        self.library_filter.setEnabled(inactive)
        self.kind_filter_combo.setEnabled(inactive)

    def selected_document_id(self) -> int | None:
        return self._selected_doc.document_id if self._selected_doc else None

    def cleanup_before_close(self) -> None:
        self.library_manager.cleanup_before_close()
        logger.info("LibraryWidget cleanup completed.")
