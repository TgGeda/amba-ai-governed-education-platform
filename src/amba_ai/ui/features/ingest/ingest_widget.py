from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QDateTime, QSettings, QSize, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from amba_ai.ui.common.qss_utils import apply_local_qss
from amba_ai.ui.common.ui_icons_utils import icon
from .data_classes import IngestViewModel
from .ingest_manager import IngestManager


class IngestWidget(QWidget):
    documentIngested = Signal(int)
    statusMessage = Signal(str, str)
    operationStarted = Signal(str)
    operationFinished = Signal(str)

    def __init__(
        self,
        settings: QSettings,
        job_service: JobService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.settings = settings
        self.jobs = job_service
        self.ingest_manager = IngestManager(job_service, self)

        self._is_operation_active = False
        self._last_upload_dir = str(Path.home())
        self._latest_ingest: IngestViewModel | None = None
        self._equity_profile: dict[str, Any] = {}

        self.setObjectName("AmbaIngestWidgetUI")

        self._setup_ui()
        self._connect_signals()
        self._load_local_styles()
        self._post_init_setup()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(7, 7, 7, 7)
        main_layout.setSpacing(6)

        self._setup_toolbar(main_layout)
        self._setup_tabs(main_layout)
        self._setup_bottom_bar(main_layout)

    def _setup_toolbar(self, main_layout: QVBoxLayout) -> None:
        self.top_toolbar = QToolBar(self.tr("Ingest Controls"), self)
        self.top_toolbar.setObjectName("ingestToolbar")
        self.top_toolbar.setIconSize(QSize(16, 16))
        self.top_toolbar.setMovable(False)
        self.top_toolbar.setFloatable(False)

        self.upload_btn = QPushButton(icon("ingest"), self.tr("Upload File"))
        self.upload_btn.setObjectName("uploadButton")
        self.upload_btn.setProperty("priority", "primary")

        self.clear_log_btn = QPushButton(icon("clear"), self.tr("Clear Log"))
        self.clear_log_btn.setObjectName("clearLogButton")
        self.clear_log_btn.setProperty("variant", "secondary")

        self.top_toolbar.addWidget(self.upload_btn)
        self.top_toolbar.addWidget(self.clear_log_btn)

        main_layout.addWidget(self.top_toolbar)

    def _setup_tabs(self, main_layout: QVBoxLayout) -> None:
        self.content_tabs = QTabWidget()
        self.content_tabs.setIconSize(QSize(14, 14))

        self._setup_upload_tab()
        self._setup_result_tab()
        self._setup_log_tab()

        main_layout.addWidget(self.content_tabs, stretch=1)

    def _setup_upload_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.ingest_title = QLabel(self.tr("Upload learning material"))
        self.ingest_title.setObjectName("ingestTitle")
        self.ingest_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.ingest_subtitle = QLabel(
            self.tr("Ingest PDF, DOCX, PPTX, TXT, audio, or video files into the local AmbaAI learning library.")
        )
        self.ingest_subtitle.setObjectName("ingestSubtitle")
        self.ingest_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ingest_subtitle.setWordWrap(True)

        self.drop_hint = QLabel(
            self.tr("Offline-first ingestion stores content locally, creates reusable chunks, and prepares the document for curriculum-grounded retrieval.")
        )
        self.drop_hint.setObjectName("ingestDropHint")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.setWordWrap(True)
        self.drop_hint.setMinimumHeight(90)

        layout.addWidget(self.ingest_title)
        layout.addWidget(self.ingest_subtitle)
        layout.addWidget(self.drop_hint)
        layout.addStretch(1)

        self.content_tabs.addTab(tab, icon("upload"), self.tr("Upload"))

    def _setup_result_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        self.result_view = QTextBrowser()
        self.result_view.setObjectName("ingestResultView")
        self.result_view.setReadOnly(True)

        layout.addWidget(self.result_view, stretch=1)

        self.content_tabs.addTab(tab, icon("check"), self.tr("Result"))

    def _setup_log_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        self.ingest_status_label = QLabel(self.tr("Ingest Status: Idle"))
        self.ingest_status_label.setObjectName("ingestStatusLabel")
        self.ingest_status_label.setWordWrap(True)
        self.ingest_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ingest_status_label.setMinimumHeight(28)

        self.operation_log = QTextBrowser()
        self.operation_log.setObjectName("ingestOperationLog")
        self.operation_log.setReadOnly(True)
        self.operation_log.setFont(QFont("Consolas"))

        layout.addWidget(self.ingest_status_label)
        layout.addWidget(self.operation_log, stretch=1)

        self.content_tabs.addTab(tab, icon("info"), self.tr("Log & Status"))

    def _setup_bottom_bar(self, main_layout: QVBoxLayout) -> None:
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(4, 2, 4, 2)
        bottom_bar.setSpacing(5)

        self.overall_status_label = QLabel(self.tr("Ready. Upload a learning file to begin."))
        bottom_bar.addWidget(self.overall_status_label, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(220)
        self.progress_bar.setFixedHeight(18)
        bottom_bar.addWidget(self.progress_bar)

        main_layout.addLayout(bottom_bar)

    def _connect_signals(self) -> None:
        self.upload_btn.clicked.connect(self.pick_file)
        self.clear_log_btn.clicked.connect(self.clear_log)

        self.ingest_manager.ingestionStarted.connect(self._on_manager_ingestion_started)
        self.ingest_manager.ingestionFinished.connect(self._on_manager_ingestion_finished)
        self.ingest_manager.ingestionFailed.connect(self._on_manager_ingestion_failed)
        self.ingest_manager.documentIngested.connect(self.documentIngested.emit)
        self.ingest_manager.statusMessage.connect(self._append_status_message)
        self.ingest_manager.operationStarted.connect(self.operationStarted.emit)
        self.ingest_manager.operationFinished.connect(self.operationFinished.emit)

    def _post_init_setup(self) -> None:
        self._last_upload_dir = str(self.settings.value("Ingest/last_upload_dir", str(Path.home())))
        self._update_ui_for_operation_status()

    def _load_local_styles(self) -> None:
        qss_path = Path(__file__).parent / "ingest.qss"
        apply_local_qss(self, qss_path)

    @Slot(dict)
    def apply_equity_profile(self, profile: dict[str, Any]) -> None:
        self._equity_profile = dict(profile or {})
        self.ingest_manager.apply_equity_profile(self._equity_profile)
        self._append_status_message("Ingest profile updated from Equity Switch.", "INFO")

    @Slot()
    def pick_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Choose Learning File"),
            self._last_upload_dir,
            self.tr(
                "Study Files (*.pdf *.docx *.pptx *.txt *.md *.mp3 *.wav *.m4a *.mp4 *.mov *.mkv *.webm);;All Files (*)"
            ),
        )

        if not file_path:
            return

        self._last_upload_dir = str(Path(file_path).parent)
        self.settings.setValue("Ingest/last_upload_dir", self._last_upload_dir)

        self._append_status_message(f"Selected file: {file_path}", "INFO")
        self.ingest_manager.ingest_file(file_path)

    @Slot()
    def clear_log(self) -> None:
        self.operation_log.clear()
        self.result_view.clear()
        self.ingest_status_label.setText(self.tr("Ingest Status: Idle"))
        self.overall_status_label.setText(self.tr("Ready. Upload a learning file to begin."))

    @Slot(str)
    def _on_manager_ingestion_started(self, path: str) -> None:
        self._is_operation_active = True
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.ingest_status_label.setText(self.tr("Ingesting learning material..."))
        self.overall_status_label.setText(self.tr("Ingestion in progress..."))
        self.result_view.setHtml(
            f"<h2>Ingestion Started</h2><p><b>File:</b> {self._escape(path)}</p><p>Processing local learning material...</p>"
        )
        self.content_tabs.setCurrentIndex(2)
        self._update_ui_for_operation_status()

    @Slot(dict)
    def _on_manager_ingestion_finished(self, payload: dict[str, Any]) -> None:
        self._is_operation_active = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)

        ingest = IngestViewModel(
            document_id=int(payload.get("document_id") or 0),
            title=str(payload.get("title") or f"Document {payload.get('document_id', '')}"),
            kind=str(payload.get("kind") or "unknown"),
            source_path=str(payload.get("source_path") or ""),
            chunk_count=payload.get("chunk_count", "unknown"),
            text_length=payload.get("text_length", "unknown"),
            rag_indexed=bool(payload.get("rag_indexed", False)),
            metadata=dict(payload.get("metadata") or {}),
        )

        self._latest_ingest = ingest

        self.result_view.setHtml(self._result_html(ingest))
        self.content_tabs.setCurrentIndex(1)

        message = self.tr(
            f"Document {ingest.document_id} ingested. Chunks: {ingest.chunk_count}. Indexed: {ingest.indexed_label}."
        )

        self.ingest_status_label.setText(message)
        self.overall_status_label.setText(message)
        self._append_status_message(message, "INFO")

        if ingest.document_id > 0:
            self.documentIngested.emit(ingest.document_id)

        self._update_ui_for_operation_status()

    @Slot(dict)
    def _on_manager_ingestion_failed(self, error_context: dict[str, Any]) -> None:
        self._is_operation_active = False
        self.progress_bar.setVisible(False)

        message = str(error_context.get("error_message") or "Ingestion failed.")
        self.ingest_status_label.setText(message)
        self.overall_status_label.setText(message)
        self._append_status_message(message, "ERROR")
        self.content_tabs.setCurrentIndex(2)

        QMessageBox.critical(self, self.tr("Ingestion failed"), message)

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
        safe = self._escape(str(message))
        self.operation_log.append(
            f'<span style="color:#94A3B8;">[{timestamp}]</span> '
            f'<b style="color:{color};">[{level.upper()}]</b> {safe}'
        )
        self.statusMessage.emit(message, level)

    @staticmethod
    def _escape(value: str) -> str:
        return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _result_html(self, ingest: IngestViewModel) -> str:
        rows = [
            ("Document ID", str(ingest.document_id)),
            ("Title", ingest.title),
            ("Kind", ingest.kind),
            ("Chunks", str(ingest.chunk_count)),
            ("Text Length", str(ingest.text_length)),
            ("RAG Indexed", ingest.indexed_label),
            ("Source Path", ingest.source_path or "N/A"),
        ]

        rows_html = "\n".join(
            f"<tr><td class='label'>{self._escape(label)}</td><td class='value'>{self._escape(value)}</td></tr>"
            for label, value in rows
        )

        return f"""
        <html>
        <head>
        <style>
            table {{
                width: 100%;
                border-collapse: collapse;
                font-family: Segoe UI, Arial, sans-serif;
                font-size: 11pt;
            }}
            td.label {{
                font-weight: bold;
                padding: 6px 12px 6px 0;
                width: 160px;
                color: #2DD4BF;
            }}
            td.value {{
                padding: 6px 0;
                color: #E2E8F0;
            }}
            h2 {{
                color: #F8FAFC;
            }}
            p {{
                color: #A7F3D0;
            }}
        </style>
        </head>
        <body>
            <h2>Ingestion Completed</h2>
            <p>The learning material has been saved into the local AmbaAI library.</p>
            <table>{rows_html}</table>
        </body>
        </html>
        """

    def _update_ui_for_operation_status(self) -> None:
        inactive = not self._is_operation_active
        self.upload_btn.setEnabled(inactive)
        self.clear_log_btn.setEnabled(inactive)

    def cleanup_before_close(self) -> None:
        self.settings.setValue("Ingest/last_upload_dir", self._last_upload_dir)
        self.ingest_manager.cleanup_before_close()
        logger.info("IngestWidget cleanup completed.")

    def retranslateUi(self) -> None:
        self.top_toolbar.setWindowTitle(self.tr("Ingest Controls"))
        self.upload_btn.setText(self.tr("Upload File"))
        self.clear_log_btn.setText(self.tr("Clear Log"))
        self.content_tabs.setTabText(0, self.tr("Upload"))
        self.content_tabs.setTabText(1, self.tr("Result"))
        self.content_tabs.setTabText(2, self.tr("Log & Status"))
        self.ingest_title.setText(self.tr("Upload learning material"))
        self.ingest_subtitle.setText(
            self.tr("Ingest PDF, DOCX, PPTX, TXT, audio, or video files into the local AmbaAI learning library.")
        )
        self.drop_hint.setText(
            self.tr("Offline-first ingestion stores content locally, creates reusable chunks, and prepares the document for curriculum-grounded retrieval.")
        )