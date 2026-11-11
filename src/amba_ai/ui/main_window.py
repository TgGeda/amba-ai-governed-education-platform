from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QCoreApplication, QSettings, QSize, Qt, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from amba_ai.compute.edge_slm import OllamaClient
from amba_ai.application.service_container import ApplicationServices
from amba_ai.core.agent_bridge import AgentBridge
from amba_ai.core.agent_orchestrator import AgentOrchestrator
from amba_ai.core.context_tracker import ContextTracker
from amba_ai.core.memory_manager import MemoryManager
from amba_ai.db.database import Database
from amba_ai.logger import logger
from amba_ai.services.job_service import JobService
from amba_ai.ui.common.qss_utils import load_qss_text
from amba_ai.ui.common.ui_icons_utils import clear_icon_cache, icon
from amba_ai.ui.features.equity_switch import EquitySwitchWidget
from amba_ai.ui.features.ingest import IngestWidget
from amba_ai.ui.features.library import LibraryWidget
from amba_ai.ui.features.notes import NotesWidget
from amba_ai.ui.features.study import StudyWidget
from amba_ai.ui.features.summarizer import SummarizerWidget
from amba_ai.ui.features.tutor import TutorWidget
from amba_ai.ui.features.governance_review import GovernanceReviewWidget
from amba_ai.ui.features.governance.main_window_integration import install_submission_workspaces

try:
    from amba_ai.ui.ambient_overlay import AmbientOverlay
except ImportError:
    AmbientOverlay = None

try:
    from amba_ai.services.voice_service import VoiceService
except ImportError:
    VoiceService = None


class ShortcutsDialog(QDialog):
    def __init__(self, actions: list[QAction], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Keyboard Shortcuts"))
        self.setMinimumSize(560, 420)
        self.setWindowIcon(icon("keyboard"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.list_widget = QListWidget()
        for action in actions:
            shortcut = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            if shortcut:
                label = (action.toolTip() or action.text()).replace("&amp;amp;", "").replace("&amp;", "").replace("&", "")
                text = f"{label} \t({shortcut})"
                item = QListWidgetItem(text)
                self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)


class MainWindow(QMainWindow):
    documentChanged = Signal(int)
    equityProfileChanged = Signal(dict)

    def __init__(self, services: ApplicationServices) -> None:
        super().__init__()
        if not isinstance(services, ApplicationServices):
            raise TypeError("services must be an ApplicationServices")
        self.services = services
        self.job_service = services.job_service

        self._load_settings()
        self._setup_services()
        self._setup_core_components()
        self._setup_status_bar()
        self._setup_tab_widgets()
        self._setup_actions()
        self._setup_menus_and_toolbars()
        self._restore_window_state()
        self._connect_all_signals()
        self._load_styles()
        self._build_agentic_runtime()
        self._restore_saved_document_context()

        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.cleanup_before_close)

        self.library_widget.refresh_documents()
        self._update_contextual_actions()
        self._update_global_status("Ready. Offline-first mode enabled.", "INFO")
        install_submission_workspaces(self)

    def _load_settings(self) -> None:
        self.settings = QSettings("AmbaAI", "AmbaAIApp")
        self._saved_geometry = self.settings.value("MainWindow/geometry")
        self._saved_state = self.settings.value("MainWindow/state")
        self.styles_dir = Path(__file__).parent / "styles"
        self.current_theme_name = str(self.settings.value("Appearance/theme", "Living Library"))
        self.available_themes: dict[str, Path] = {}
        self.theme_actions: dict[str, QAction] = {}

        self.agent_bridge: AgentBridge | None = None
        self.context_tracker: ContextTracker | None = None
        self.memory_manager: MemoryManager | None = None
        self.llm: OllamaClient | None = None
        self.orchestrator: AgentOrchestrator | None = None
        self.voice_service: Any | None = None
        self.ambient_overlay: Any | None = None

        doc_id = self.settings.value("MainWindow/current_document_id")
        if doc_id is not None:
            try:
                self.current_document_id = int(doc_id)
            except ValueError:
                self.current_document_id = None
        else:
            self.current_document_id = None

        self.current_equity_profile: dict[str, Any] = {}
        self._is_cleaned_up = False

    def _setup_services(self) -> None:
        self.db = self.services.database
        self.jobs = self.services.job_service

    def _setup_core_components(self) -> None:
        self.setWindowTitle(self.tr("AmbaAI Offline Study Assistant"))
        self.setWindowIcon(icon("ambaai"))
        self.resize(1366, 768)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.setIconSize(QSize(18, 18))
        self.setCentralWidget(self.tabs)

    def _setup_status_bar(self) -> None:
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(240)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self.document_status_label = QLabel(self.tr("Document: None"))
        self.statusBar().addWidget(self.document_status_label, 1)

        self.status_badge = QLabel(self.tr("Offline-First | Local Database Ready"))
        self.status_badge.setProperty("badge", "offline")
        self.statusBar().addPermanentWidget(self.status_badge)

    def _setup_tab_widgets(self) -> None:
        self.ingest_widget = IngestWidget(self.settings, self.jobs, self)
        self.library_widget = LibraryWidget(self.settings, self.jobs, self)
        self.summarizer_widget = SummarizerWidget(self.settings, self.jobs, self)
        self.notes_widget = NotesWidget(self.settings, self.jobs, self)
        self.study_widget = StudyWidget(self.settings, self.jobs, self)
        self.tutor_widget = TutorWidget(self.settings, self.jobs, self)
        self.equity_switch_widget = EquitySwitchWidget(self.settings, self.jobs, self)
        self.governance_review_widget = GovernanceReviewWidget(
            self.settings,
            self.services,
            self,
        )

        for widget in self._module_widgets():
            widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.tabs.addTab(self.ingest_widget, icon("ingest"), self.tr("Ingest"))
        self.tabs.addTab(self.library_widget, icon("library"), self.tr("Library"))
        self.tabs.addTab(self.summarizer_widget, icon("summarizer"), self.tr("Summarizer"))
        self.tabs.addTab(self.notes_widget, icon("notes"), self.tr("Notes"))
        self.tabs.addTab(self.study_widget, icon("study-pack"), self.tr("Study"))
        self.tabs.addTab(self.tutor_widget, icon("tutor"), self.tr("Tutor"))
        self.tabs.addTab(self.equity_switch_widget, icon("equity-switch"), self.tr("Equity Switch"))
        self.tabs.addTab(self.governance_review_widget, icon("check"), self.tr("Teacher Review"))

    def _setup_actions(self) -> None:
        self.upload_action = QAction(icon("ingest"), self.tr("&Upload Learning File..."), self)
        self.upload_action.setShortcut(QKeySequence("Ctrl+O"))
        self.upload_action.setToolTip(self.tr("Upload PDF, DOCX, PPTX, TXT, or media files into the local library"))
        self.upload_action.triggered.connect(self.pick_file)

        self.refresh_library_action = QAction(icon("refresh"), self.tr("&Refresh Library"), self)
        self.refresh_library_action.setShortcut(QKeySequence("F5"))
        self.refresh_library_action.setToolTip(self.tr("Scan and synchronize the local document database"))
        self.refresh_library_action.triggered.connect(self.refresh_library)

        self.open_library_action = QAction(icon("library"), self.tr("&Open Library"), self)
        self.open_library_action.setShortcut(QKeySequence("Ctrl+L"))
        self.open_library_action.setToolTip(self.tr("Open the local document library view"))
        self.open_library_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.library_widget))

        self.generate_summary_action = QAction(icon("summarizer"), self.tr("Generate &Summary"), self)
        self.generate_summary_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.generate_summary_action.setToolTip(self.tr("Generate an offline curriculum summary for the active document"))
        self.generate_summary_action.triggered.connect(self.generate_summary)

        self.generate_notes_action = QAction(icon("notes"), self.tr("Generate &Notes"), self)
        self.generate_notes_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.generate_notes_action.setToolTip(self.tr("Generate customized student or teacher study notes"))
        self.generate_notes_action.triggered.connect(lambda: self.generate_notes(force=False))

        self.generate_study_action = QAction(icon("study-pack"), self.tr("Generate &Study Pack"), self)
        self.generate_study_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self.generate_study_action.setToolTip(self.tr("Generate interactive flashcards and multiple-choice quizzes"))
        self.generate_study_action.triggered.connect(lambda: self.generate_study_assets(force=False))

        self.open_tutor_action = QAction(icon("tutor"), self.tr("Open &Tutor"), self)
        self.open_tutor_action.setShortcut(QKeySequence("Ctrl+T"))
        self.open_tutor_action.setToolTip(self.tr("Interact with the AI tutor grounded in your study material"))
        self.open_tutor_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.tutor_widget))

        self.open_equity_switch_action = QAction(icon("equity-switch"), self.tr("Open &Equity Switch"), self)
        self.open_equity_switch_action.setShortcut(QKeySequence("Ctrl+E"))
        self.open_equity_switch_action.setToolTip(self.tr("Configure language, offline behavior, and accessibility policies"))
        self.open_equity_switch_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.equity_switch_widget))

        self.show_ingest_tab_action = QAction(icon("ingest"), self.tr("Show Ingest"), self)
        self.show_ingest_tab_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.ingest_widget))

        self.show_library_tab_action = QAction(icon("library"), self.tr("Show Library"), self)
        self.show_library_tab_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.library_widget))

        self.show_summarizer_tab_action = QAction(icon("summarizer"), self.tr("Show Summarizer"), self)
        self.show_summarizer_tab_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.summarizer_widget))

        self.show_notes_tab_action = QAction(icon("notes"), self.tr("Show Notes"), self)
        self.show_notes_tab_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.notes_widget))

        self.show_study_tab_action = QAction(icon("study-pack"), self.tr("Show Study"), self)
        self.show_study_tab_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.study_widget))

        self.show_tutor_tab_action = QAction(icon("tutor"), self.tr("Show Tutor"), self)
        self.show_tutor_tab_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.tutor_widget))

        self.show_equity_tab_action = QAction(icon("equity-switch"), self.tr("Show Equity Switch"), self)
        self.show_equity_tab_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.equity_switch_widget))

        self.show_governance_review_tab_action = QAction(icon("check"), self.tr("Show Teacher Review"), self)
        self.show_governance_review_tab_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.governance_review_widget))

        self.shortcuts_action = QAction(icon("keyboard"), self.tr("Keyboard &Shortcuts..."), self)
        self.shortcuts_action.setShortcut(QKeySequence("Ctrl+/"))
        self.shortcuts_action.setToolTip(self.tr("Show the list of keyboard shortcut combinations"))
        self.shortcuts_action.triggered.connect(self._show_shortcuts)

        self.about_action = QAction(icon("info"), self.tr("&About AmbaAI"), self)
        self.about_action.setToolTip(self.tr("View application details, version, and credentials"))
        self.about_action.triggered.connect(self._show_about)

        self.exit_action = QAction(icon("close"), self.tr("E&xit"), self)
        self.exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.exit_action.setToolTip(self.tr("Safely save state and close the application"))
        self.exit_action.triggered.connect(self.close)

        self.all_actions_list = [
            self.upload_action,
            self.refresh_library_action,
            self.open_library_action,
            self.generate_summary_action,
            self.generate_notes_action,
            self.generate_study_action,
            self.open_tutor_action,
            self.open_equity_switch_action,
            self.shortcuts_action,
            self.about_action,
            self.exit_action,
        ]
        self._setup_theme_actions()

    def _setup_menus_and_toolbars(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu(self.tr("&File"))
        file_menu.addAction(self.upload_action)
        file_menu.addAction(self.refresh_library_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        view_menu = menubar.addMenu(self.tr("&View"))
        view_menu.addAction(self.show_ingest_tab_action)
        view_menu.addAction(self.show_library_tab_action)
        view_menu.addAction(self.show_summarizer_tab_action)
        view_menu.addAction(self.show_notes_tab_action)
        view_menu.addAction(self.show_study_tab_action)
        view_menu.addAction(self.show_tutor_tab_action)
        view_menu.addAction(self.show_equity_tab_action)
        view_menu.addAction(self.show_governance_review_tab_action)
        view_menu.addSeparator()

        self.theme_menu = view_menu.addMenu(icon("settings"), self.tr("Themes"))
        for action in self.theme_actions.values():
            self.theme_menu.addAction(action)

        view_menu.addSeparator()

        learning_menu = menubar.addMenu(self.tr("&Learning"))
        learning_menu.addAction(self.generate_summary_action)
        learning_menu.addAction(self.generate_notes_action)
        learning_menu.addAction(self.generate_study_action)
        learning_menu.addAction(self.open_tutor_action)

        tools_menu = menubar.addMenu(self.tr("&Tools"))
        tools_menu.addAction(self.open_equity_switch_action)

        help_menu = menubar.addMenu(self.tr("&Help"))
        help_menu.addAction(self.shortcuts_action)
        help_menu.addAction(self.about_action)

        self.quick_access_toolbar = QToolBar(self.tr("Quick Access"), self)
        self.quick_access_toolbar.setObjectName("quickAccessToolbar")
        self.quick_access_toolbar.setIconSize(QSize(16, 16))
        self.quick_access_toolbar.setMovable(False)
        self.quick_access_toolbar.setFloatable(False)
        self.quick_access_toolbar.addAction(self.upload_action)
        self.quick_access_toolbar.addAction(self.refresh_library_action)
        self.quick_access_toolbar.addSeparator()
        self.quick_access_toolbar.addAction(self.generate_notes_action)
        self.quick_access_toolbar.addAction(self.open_tutor_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.quick_access_toolbar)

        self.learning_workflow_toolbar = QToolBar(self.tr("Learning Workflow"), self)
        self.learning_workflow_toolbar.setObjectName("learningWorkflowToolbar")
        self.learning_workflow_toolbar.setIconSize(QSize(16, 16))
        self.learning_workflow_toolbar.setMovable(False)
        self.learning_workflow_toolbar.setFloatable(False)
        self.learning_workflow_toolbar.addAction(self.show_ingest_tab_action)
        self.learning_workflow_toolbar.addAction(self.show_library_tab_action)
        self.learning_workflow_toolbar.addAction(self.show_summarizer_tab_action)
        self.learning_workflow_toolbar.addAction(self.show_notes_tab_action)
        self.learning_workflow_toolbar.addAction(self.show_study_tab_action)
        self.learning_workflow_toolbar.addAction(self.show_tutor_tab_action)
        self.learning_workflow_toolbar.addAction(self.show_equity_tab_action)
        self.learning_workflow_toolbar.addAction(self.show_governance_review_tab_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.learning_workflow_toolbar)

        view_menu.addAction(self.quick_access_toolbar.toggleViewAction())
        view_menu.addAction(self.learning_workflow_toolbar.toggleViewAction())

    def _restore_window_state(self) -> None:
        if self._saved_geometry:
            self.restoreGeometry(self._saved_geometry)
        if self._saved_state:
            self.restoreState(self._saved_state)

    def _show_shortcuts(self) -> None:
        dialog = ShortcutsDialog(self.all_actions_list, self)
        dialog.exec()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            self.tr("About AmbaAI"),
            self.tr(
                "<h3>AmbaAI Offline Study Assistant</h3>"
                "<p>An offline-first curriculum-grounded learning application.</p>"
                "<p>Built with PySide6, Ollama, and local secure storage.</p>"
            ),
        )

    def _update_contextual_actions(self) -> None:
        has_doc = self.current_document_id is not None
        self.generate_summary_action.setEnabled(has_doc)
        self.generate_notes_action.setEnabled(has_doc)
        self.generate_study_action.setEnabled(has_doc)

        if has_doc:
            doc_title = self._current_document_title(default=str(self.current_document_id))
            self.document_status_label.setText(self.tr(f"Document: {doc_title}"))
        else:
            self.document_status_label.setText(self.tr("Document: None"))

    def _connect_all_signals(self) -> None:
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.ingest_widget.documentIngested.connect(self._on_document_ingested)

        self.library_widget.documentSelected.connect(self._on_document_selected)
        self.library_widget.documentActivated.connect(self._on_document_activated)
        self.library_widget.libraryRefreshed.connect(self._on_library_refreshed)

        self.summarizer_widget.summaryGenerated.connect(self._on_summary_generated)
        self.notes_widget.notesGenerated.connect(self._on_notes_generated)
        self.study_widget.studyAssetsGenerated.connect(self._on_study_assets_generated)
        self.tutor_widget.tutorAnswerReady.connect(self._on_tutor_answer_ready)
        self.tutor_widget.tutorError.connect(self._on_tutor_error)

        self.equity_switch_widget.equityProfileChanged.connect(self._on_equity_profile_changed)
        self.equity_switch_widget.modelModeChanged.connect(self._on_model_mode_changed)
        self.equity_switch_widget.languageModeChanged.connect(self._on_language_mode_changed)
        self.equity_switch_widget.privacyModeChanged.connect(self._on_privacy_mode_changed)
        self.equity_switch_widget.connectivityModeChanged.connect(self._on_connectivity_mode_changed)

        for widget in self._module_widgets():
            widget.statusMessage.connect(self._handle_module_status)
            widget.operationStarted.connect(self._on_module_operation_started)
            widget.operationFinished.connect(self._on_module_operation_finished)

        self.documentChanged.connect(self.summarizer_widget.set_document)
        self.documentChanged.connect(self.notes_widget.set_document)
        self.documentChanged.connect(self.study_widget.set_document)
        self.documentChanged.connect(self.tutor_widget.set_document)
        self.documentChanged.connect(self.governance_review_widget.set_document)

        self.equityProfileChanged.connect(self.ingest_widget.apply_equity_profile)
        self.equityProfileChanged.connect(self.summarizer_widget.apply_equity_profile)
        self.equityProfileChanged.connect(self.notes_widget.apply_equity_profile)
        self.equityProfileChanged.connect(self.study_widget.apply_equity_profile)
        self.equityProfileChanged.connect(self.tutor_widget.apply_equity_profile)

    def _module_widgets(self) -> list[Any]:
        return [
            self.ingest_widget,
            self.library_widget,
            self.summarizer_widget,
            self.notes_widget,
            self.study_widget,
            self.tutor_widget,
            self.equity_switch_widget,
            self.governance_review_widget,
        ]

    def _load_styles(self) -> None:
        self._apply_saved_theme()

    def _build_agentic_runtime(self) -> None:
        try:
            self.agent_bridge = AgentBridge(
                self,
                allowed_actions={
                    "switch_tab",
                    "focus_widget",
                    "open_dialog",
                    "close_dialog",
                    "load_document_assets",
                    "generate_summary",
                    "generate_notes",
                    "generate_study_assets",
                    "refresh_library",
                    "show_overlay",
                    "hide_overlay",
                    "set_overlay_state",
                },
            )

            self.context_tracker = self.services.context_tracker
            self.memory_manager = self.services.memory_service
            self.llm = self.services.model_service.get_client_for_task("tutor_chat")

            self.orchestrator = AgentOrchestrator(
                llm=self.llm,
                context_tracker=self.context_tracker,
                agent_bridge=self.agent_bridge,
                memory_manager=self.memory_manager,
                parent=self,
            )

            self.agent_bridge.ui_action_requested.connect(self.handle_agent_ui_action)
            self.agent_bridge.ui_action_rejected.connect(self.handle_agent_ui_rejected)

            self.orchestrator.response_ready.connect(self.on_agent_response_ready)
            self.orchestrator.thinking_started.connect(self.on_agent_thinking_started)
            self.orchestrator.thinking_finished.connect(self.on_agent_thinking_finished)
            self.orchestrator.error_occurred.connect(self.on_agent_error)

            self.on_tab_changed(self.tabs.currentIndex())

            if AmbientOverlay is not None and os.environ.get("AMBA_ENABLE_OVERLAY", "0") == "1":
                try:
                    self.ambient_overlay = AmbientOverlay(start_visible=False)
                except TypeError:
                    self.ambient_overlay = AmbientOverlay()
                    self.ambient_overlay.hide()
            else:
                self.ambient_overlay = None

            if VoiceService is not None:
                try:
                    self.voice_service = VoiceService()
                    self.voice_service.wake_word_detected.connect(self.on_voice_wake_word)
                    self.voice_service.listening_started.connect(self.on_voice_listening_started)
                    self.voice_service.listening_stopped.connect(self.on_voice_listening_stopped)
                    self.voice_service.transcription_ready.connect(self.on_voice_transcription_ready)
                    self.voice_service.error_occurred.connect(self.on_voice_error)

                    if os.environ.get("AMBA_ENABLE_VOICE", "0") == "1":
                        self.voice_service.start()

                except Exception:
                    logger.warning("Voice service could not be started", exc_info=True)
                    self.voice_service = None

            logger.info("Agentic runtime initialized successfully.")

        except Exception:
            logger.error("Failed to initialize agentic runtime", exc_info=True)

    @Slot(int)
    def _on_document_ingested(self, document_id: int) -> None:
        self.current_document_id = int(document_id)
        self.documentChanged.emit(self.current_document_id)
        self.library_widget.refresh_documents()
        self.tabs.setCurrentWidget(self.library_widget)
        self._update_context_from_current_ui()
        self._update_contextual_actions()
        self._update_global_status(f"Document {document_id} ingested.", "INFO")

    @Slot(int)
    def _on_document_selected(self, document_id: int) -> None:
        self.current_document_id = int(document_id)
        self.documentChanged.emit(self.current_document_id)
        self._update_context_from_current_ui()
        self._update_contextual_actions()
        self._update_global_status(f"Selected document {document_id}.", "INFO")

    @Slot(int)
    def _on_document_activated(self, document_id: int) -> None:
        self.current_document_id = int(document_id)
        self.documentChanged.emit(self.current_document_id)
        self.tabs.setCurrentWidget(self.notes_widget)
        self._update_context_from_current_ui()
        self._update_contextual_actions()
        self._update_global_status(f"Activated document {document_id}.", "INFO")

    @Slot(list)
    def _on_library_refreshed(self, documents: list) -> None:
        self._update_global_status(f"Library refreshed: {len(documents)} document(s).", "INFO")

    @Slot(int)
    def _on_summary_generated(self, document_id: int) -> None:
        self._update_global_status(f"Summary generated for document {document_id}.", "INFO")

    @Slot(int)
    def _on_notes_generated(self, document_id: int) -> None:
        self._update_global_status(f"Notes generated for document {document_id}.", "INFO")

    @Slot(int)
    def _on_study_assets_generated(self, document_id: int) -> None:
        self._update_global_status(f"Study assets generated for document {document_id}.", "INFO")

    @Slot(str)
    def _on_tutor_answer_ready(self, answer_text: str) -> None:
        self._update_global_status("Tutor answer ready.", "INFO")

    @Slot(dict)
    def _on_tutor_error(self, error_context: dict[str, Any]) -> None:
        self._update_global_status(str(error_context.get("error_message") or "Tutor error."), "ERROR")

    @Slot(dict)
    def _on_equity_profile_changed(self, profile: dict[str, Any]) -> None:
        self.current_equity_profile = dict(profile or {})
        self.equityProfileChanged.emit(self.current_equity_profile)
        self._update_global_status("Equity Switch profile applied.", "INFO")

    @Slot(str)
    def _on_model_mode_changed(self, mode: str) -> None:
        self._update_global_status(f"Model mode changed: {mode}", "INFO")

    @Slot(str)
    def _on_language_mode_changed(self, language: str) -> None:
        self._update_global_status(f"Language mode changed: {language}", "INFO")

    @Slot(str)
    def _on_privacy_mode_changed(self, mode: str) -> None:
        self._update_global_status(f"Privacy mode changed: {mode}", "INFO")

    @Slot(str)
    def _on_connectivity_mode_changed(self, mode: str) -> None:
        self._update_global_status(f"Connectivity mode changed: {mode}", "INFO")

    @Slot(str)
    def _on_module_operation_started(self, message: str) -> None:
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.statusBar().showMessage(message)

    @Slot(str)
    def _on_module_operation_finished(self, message: str) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage(message, 6000)

    @Slot(str, str)
    def _handle_module_status(self, message: str, level: str = "INFO") -> None:
        self._update_global_status(message, level)

    def _update_global_status(self, message: str, level: str = "INFO") -> None:
        self.statusBar().showMessage(message, 6000)

        upper = level.upper()
        if upper == "ERROR":
            logger.error(message)
        elif upper == "WARNING":
            logger.warning(message)
        elif upper == "DEBUG":
            logger.debug(message)
        else:
            logger.info(message)

    def pick_file(self) -> None:
        self.tabs.setCurrentWidget(self.ingest_widget)
        self.ingest_widget.pick_file()

    def refresh_library(self) -> None:
        self.library_widget.refresh_documents()

    def generate_summary(self) -> None:
        self.tabs.setCurrentWidget(self.summarizer_widget)
        self.summarizer_widget.generate_summary()

    def generate_notes(self, force: bool = False) -> None:
        self.tabs.setCurrentWidget(self.notes_widget)
        if hasattr(self.notes_widget, "force_check"):
            self.notes_widget.force_check.setChecked(force)
        self.notes_widget.generate_notes()

    def generate_study_assets(self, force: bool = False) -> None:
        self.tabs.setCurrentWidget(self.study_widget)
        if hasattr(self.study_widget, "force_combo"):
            self.study_widget.force_combo.setCurrentIndex(1 if force else 0)
        self.study_widget.generate_study_assets()

    def ask_tutor(self, question: str | None = None) -> None:
        self.tabs.setCurrentWidget(self.tutor_widget)
        if question:
            self.tutor_widget.chat_input.setText(question)
        self.tutor_widget.ask_question()

    @Slot(dict)
    def handle_agent_ui_action(self, command: dict[str, Any]) -> None:
        action = command.get("action")
        target = command.get("target")

        logger.info(
            "Handling agent UI action",
            extra={"context": {"action": action, "target": target, "command": command}},
        )

        if action == "switch_tab":
            self._agent_switch_tab(str(target or ""))
        elif action == "focus_widget":
            self._agent_focus_widget(str(target or ""))
        elif action == "load_document_assets":
            self._agent_load_document_assets()
        elif action == "generate_summary":
            self.generate_summary()
        elif action == "generate_notes":
            self.generate_notes(force=False)
        elif action == "generate_study_assets":
            self.generate_study_assets(force=False)
        elif action == "refresh_library":
            self.refresh_library()
        elif action == "show_overlay" and self.ambient_overlay is not None:
            self.ambient_overlay.show_overlay()
        elif action == "hide_overlay" and self.ambient_overlay is not None:
            self.ambient_overlay.hide_overlay()
        elif action == "set_overlay_state":
            self._agent_set_overlay_state(str(target or "idle"))
        else:
            logger.warning("Unknown agent UI action", extra={"context": {"command": command}})

    @Slot(dict)
    def handle_agent_ui_rejected(self, command: dict[str, Any]) -> None:
        logger.warning("Rejected agent UI action", extra={"context": {"command": command}})
        self.statusBar().showMessage("Rejected unsafe agent UI action", 5000)

    def _agent_switch_tab(self, target: str) -> None:
        tab_map = {
            "ingest": self.ingest_widget,
            "view_ingest": self.ingest_widget,
            "library": self.library_widget,
            "view_library": self.library_widget,
            "summarizer": self.summarizer_widget,
            "summary": self.summarizer_widget,
            "view_summarizer": self.summarizer_widget,
            "notes": self.notes_widget,
            "view_notes": self.notes_widget,
            "study": self.study_widget,
            "view_study": self.study_widget,
            "tutor": self.tutor_widget,
            "chat": self.tutor_widget,
            "view_tutor": self.tutor_widget,
            "equity": self.equity_switch_widget,
            "equity_switch": self.equity_switch_widget,
            "view_equity_switch": self.equity_switch_widget,
            "teacher_review": self.governance_review_widget,
            "governance_review": self.governance_review_widget,
            "view_governance_review": self.governance_review_widget,
        }

        widget = tab_map.get(target)
        if widget is None:
            logger.warning("Unknown tab target requested by agent", extra={"context": {"target": target}})
            return

        self.tabs.setCurrentWidget(widget)

    def _agent_focus_widget(self, target: str) -> None:
        widget_map = {
            "chat_input": getattr(self.tutor_widget, "chat_input", None),
            "library_filter": getattr(self.library_widget, "library_filter", None),
            "summary_view": getattr(self.summarizer_widget, "summary_view", None),
            "notes_view": getattr(self.notes_widget, "notes_view", None),
            "flashcards_filter": getattr(self.study_widget, "flashcards_filter", None),
            "mcqs_filter": getattr(self.study_widget, "mcqs_filter", None),
        }

        widget = widget_map.get(target)
        if widget is not None:
            widget.setFocus()

    def _agent_load_document_assets(self) -> None:
        if self.current_document_id is None:
            self.statusBar().showMessage("No document selected", 5000)
            return

        self.documentChanged.emit(self.current_document_id)
        self.tabs.setCurrentWidget(self.notes_widget)
        self.generate_summary()
        self.generate_notes(force=False)
        self.generate_study_assets(force=False)

    def _agent_set_overlay_state(self, state: str) -> None:
        overlay = self.ambient_overlay
        if overlay is None:
            return

        if state == "listening" and hasattr(overlay, "set_listening"):
            overlay.set_listening()
        elif state == "thinking" and hasattr(overlay, "set_thinking"):
            overlay.set_thinking()
        elif state == "speaking" and hasattr(overlay, "set_speaking"):
            overlay.set_speaking()
        elif state == "error" and hasattr(overlay, "set_error"):
            overlay.set_error()
        elif hasattr(overlay, "set_idle"):
            overlay.set_idle()

    @Slot(str)
    def on_agent_response_ready(self, text: str) -> None:
        cleaned = (text or "").strip()
        if cleaned and hasattr(self.tutor_widget, "_append_chat_message"):
            self.tutor_widget._append_chat_message("AmbaAI", cleaned, model_name="agent-orchestrator")
        self._on_module_operation_finished("Agent response ready")

    @Slot()
    def on_agent_thinking_started(self) -> None:
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.statusBar().showMessage("AmbaAI is thinking...")

        if self.ambient_overlay is not None and hasattr(self.ambient_overlay, "set_thinking"):
            self.ambient_overlay.set_thinking()

    @Slot()
    def on_agent_thinking_finished(self) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)

        if self.ambient_overlay is not None and hasattr(self.ambient_overlay, "set_idle"):
            self.ambient_overlay.set_idle()

    @Slot(str)
    def on_agent_error(self, message: str) -> None:
        self.progress_bar.setVisible(False)
        if hasattr(self.tutor_widget, "_append_chat_message"):
            self.tutor_widget._append_chat_message("AmbaAI error", message)

        self.statusBar().showMessage("Agent error", 6000)
        if self.ambient_overlay is not None and hasattr(self.ambient_overlay, "set_error"):
            self.ambient_overlay.set_error()

    @Slot()
    def on_voice_wake_word(self) -> None:
        self.statusBar().showMessage("Wake word detected", 3000)
        if self.ambient_overlay is not None and hasattr(self.ambient_overlay, "set_listening"):
            self.ambient_overlay.set_listening()

    @Slot()
    def on_voice_listening_started(self) -> None:
        self.statusBar().showMessage("Listening...", 3000)
        if self.ambient_overlay is not None and hasattr(self.ambient_overlay, "set_listening"):
            self.ambient_overlay.set_listening()

    @Slot()
    def on_voice_listening_stopped(self) -> None:
        self.statusBar().showMessage("Processing voice input...", 3000)
        if self.ambient_overlay is not None and hasattr(self.ambient_overlay, "set_thinking"):
            self.ambient_overlay.set_thinking()

    @Slot(str)
    def on_voice_transcription_ready(self, text: str) -> None:
        transcript = (text or "").strip()
        if not transcript:
            return

        self.tabs.setCurrentWidget(self.tutor_widget)
        if hasattr(self.tutor_widget, "_append_chat_message"):
            self.tutor_widget._append_chat_message("Student voice", transcript)

        self._update_context_from_current_ui()
        if self.orchestrator is not None:
            self.orchestrator.handle_user_input(transcript)
        else:
            self.ask_tutor(transcript)

    @Slot(str)
    def on_voice_error(self, message: str) -> None:
        logger.warning("Voice service error", extra={"context": {"error": message}})
        self.statusBar().showMessage(f"Voice error: {message}", 6000)

        if self.ambient_overlay is not None and hasattr(self.ambient_overlay, "set_error"):
            self.ambient_overlay.set_error()

    @Slot(int)
    def on_tab_changed(self, index: int) -> None:
        if self.context_tracker is None:
            return

        self.context_tracker.set_active_tab(self._tab_name_for_index(index))
        self._update_context_from_current_ui()

    def _tab_name_for_index(self, index: int) -> str:
        widget = self.tabs.widget(index)
        if widget is self.ingest_widget:
            return "view_ingest"
        if widget is self.library_widget:
            return "view_library"
        if widget is self.summarizer_widget:
            return "view_summarizer"
        if widget is self.notes_widget:
            return "view_notes"
        if widget is self.study_widget:
            return "view_study"
        if widget is self.tutor_widget:
            return "view_tutor"
        if widget is self.equity_switch_widget:
            return "view_equity_switch"
        if widget is self.governance_review_widget:
            return "view_governance_review"
        return "unknown"

    def _update_context_from_current_ui(self) -> None:
        if self.context_tracker is None:
            return

        try:
            self.context_tracker.set_active_tab(self._tab_name_for_index(self.tabs.currentIndex()))

            if self.current_document_id is not None:
                self.context_tracker.set_active_document(
                    document_id=self.current_document_id,
                    title=self._current_document_title(default=f"document_{self.current_document_id}"),
                )
            elif hasattr(self.context_tracker, "clear_active_document"):
                self.context_tracker.clear_active_document()

            flashcard_count = None
            assets = getattr(self.study_widget, "current_assets", None)
            if assets is not None:
                flashcard_count = len(getattr(assets, "flashcards", []) or [])

            self.context_tracker.set_extra_state("generated_flashcards", flashcard_count)
            self.context_tracker.set_extra_state("equity_profile", self.current_equity_profile or None)

        except Exception:
            logger.warning("Failed to update UI context", exc_info=True)

    def _current_document_title(self, *, default: str) -> str:
        if self.current_document_id is None:
            return default

        try:
            doc = self.db.get_document(self.current_document_id)
            if doc:
                title = str(dict(doc).get("title", default))
                return self._safe_filename_stem(title)
        except Exception:
            logger.exception(
                "Failed to get current document title",
                extra={
                    "context": {
                        "operation": "_current_document_title",
                        "document_id": self.current_document_id,
                    }
                },
            )

        return default

    @staticmethod
    def _safe_filename_stem(value: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
        return cleaned or "document"

    def cleanup_before_close(self) -> None:
        if getattr(self, "_is_cleaned_up", False):
            return
        self._is_cleaned_up = True

        if self.current_document_id is not None:
            self.settings.setValue("MainWindow/current_document_id", self.current_document_id)
        self.settings.setValue("MainWindow/geometry", self.saveGeometry())
        self.settings.setValue("MainWindow/state", self.saveState())
        self.settings.sync()

        for widget in self._module_widgets():
            if hasattr(widget, "cleanup_before_close"):
                try:
                    widget.cleanup_before_close()
                except Exception:
                    logger.warning(
                        "Module cleanup failed",
                        extra={"context": {"widget": type(widget).__name__}},
                        exc_info=True,
                    )

        try:
            if getattr(self, "voice_service", None) is not None:
                self.voice_service.stop()
        except Exception:
            logger.warning("Failed to stop voice service cleanly", exc_info=True)

        try:
            if getattr(self, "ambient_overlay", None) is not None:
                self.ambient_overlay.close()
        except Exception:
            logger.warning("Failed to close ambient overlay cleanly", exc_info=True)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.cleanup_before_close()
        super().closeEvent(event)

    def retranslateUi(self) -> None:
        self.setWindowTitle(self.tr("AmbaAI Offline Study Assistant"))
        self.tabs.setTabText(self.tabs.indexOf(self.ingest_widget), self.tr("Ingest"))
        self.tabs.setTabText(self.tabs.indexOf(self.library_widget), self.tr("Library"))
        self.tabs.setTabText(self.tabs.indexOf(self.summarizer_widget), self.tr("Summarizer"))
        self.tabs.setTabText(self.tabs.indexOf(self.notes_widget), self.tr("Notes"))
        self.tabs.setTabText(self.tabs.indexOf(self.study_widget), self.tr("Study"))
        self.tabs.setTabText(self.tabs.indexOf(self.tutor_widget), self.tr("Tutor"))
        self.tabs.setTabText(self.tabs.indexOf(self.equity_switch_widget), self.tr("Equity Switch"))
        self.tabs.setTabText(self.tabs.indexOf(self.governance_review_widget), self.tr("Teacher Review"))

        for widget in self._module_widgets():
            if hasattr(widget, "retranslateUi"):
                widget.retranslateUi()

    def _restore_saved_document_context(self) -> None:
        if self.current_document_id is None:
            return
        if not self._document_exists(self.current_document_id):
            self.current_document_id = None
            self._update_contextual_actions()
            return
        self.documentChanged.emit(self.current_document_id)
        self._update_contextual_actions()
        self._update_context_from_current_ui()

    def _document_exists(self, document_id: int) -> bool:
        try:
            return self.db.get_document(document_id) is not None
        except Exception:
            logger.warning("Failed to validate saved document", exc_info=True)
            return False

    def _discover_available_themes(self) -> dict[str, Path]:
        dir_to_check = self.styles_dir
        if not dir_to_check.exists():
            dir_to_check = Path("src/amba_ai/ui/styles")

        themes: dict[str, Path] = {}
        if dir_to_check.exists():
            for path in dir_to_check.glob("*.qss"):
                display_name = self._theme_display_name(path)
                themes[display_name] = path

        preferred_order = [
            "Living Library",
            "High Contrast Accessible",
            "Institutional Merit",
            "STEM Neon Lab",
            "Creative Studio",
            "Modern",
            "Light",
            "Dark",
            "Office",
            "Solarized",
            "Amba Ai",
            "Style",
            "VSCode Dark Plus",
            "JetBrains Darcula",
            "Office Fluent",
            "Slack Aubergine",
        ]
        sorted_themes: dict[str, Path] = {}
        for pref in preferred_order:
            for name, path in themes.items():
                if self._theme_key(name) == self._theme_key(pref):
                    sorted_themes[pref] = path
                    break

        for name in sorted(themes):
            if not any(self._theme_key(name) == self._theme_key(existing) for existing in sorted_themes):
                sorted_themes[name] = themes[name]

        return sorted_themes

    @staticmethod
    def _theme_display_name(path: Path) -> str:
        mapping = {
            "living_library": "Living Library",
            "high_contrast_accessible": "High Contrast Accessible",
            "institutional_merit": "Institutional Merit",
            "stem_neon_lab": "STEM Neon Lab",
            "creative_studio": "Creative Studio",
            "modern": "Modern",
            "light": "Light",
            "dark": "Dark",
            "office": "Office",
            "solarized": "Solarized",
            "amba_ai": "Amba Ai",
            "ambaai": "Ambaai",
            "style": "Style",
            "vscode_dark_plus": "VSCode Dark Plus",
            "jetbrains_darcula": "JetBrains Darcula",
            "office_fluent": "Office Fluent",
            "slack_aubergine": "Slack Aubergine",
        }
        stem = path.stem.strip().lower()
        return mapping.get(stem, path.stem.replace("_", " ").replace("-", " ").title())

    @staticmethod
    def _theme_key(name: str) -> str:
        return " ".join(str(name or "").strip().lower().replace("_", " ").replace("-", " ").split())

    def _setup_theme_actions(self) -> None:
        self.available_themes = self._discover_available_themes()
        self.theme_actions = {}
        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.setExclusive(True)

        for theme_name in self.available_themes:
            action = QAction(theme_name, self, checkable=True)
            action.setToolTip(self.tr(f"Apply {theme_name} theme"))
            action.setActionGroup(self.theme_action_group)
            action.triggered.connect(
                lambda checked, name=theme_name: self.apply_theme_and_save(name) if checked else None
            )
            self.theme_actions[theme_name] = action

        self._refresh_theme_action_checks()

    def _apply_saved_theme(self) -> None:
        saved_theme = str(self.settings.value("Appearance/theme", self.current_theme_name or "Living Library"))
        self.apply_theme_style(saved_theme)

    def apply_theme_and_save(self, theme_name: str) -> None:
        self.apply_theme_style(theme_name)
        self.settings.setValue("Appearance/theme", self.current_theme_name)
        self.settings.sync()

    def apply_theme_style(self, theme_name: str) -> None:
        if not self.available_themes:
            self.available_themes = self._discover_available_themes()

        if not self.available_themes:
            logger.warning("No QSS themes available to apply")
            return

        selected_name = None
        requested_key = self._theme_key(theme_name)

        for name in self.available_themes:
            if self._theme_key(name) == requested_key:
                selected_name = name
                break

        if selected_name is None:
            for fallback in ["Living Library", "Modern", "Light", "Amba Ai"]:
                for name in self.available_themes:
                    if self._theme_key(name) == self._theme_key(fallback):
                        selected_name = name
                        break
                if selected_name is not None:
                    break

        if selected_name is None:
            selected_name = next(iter(self.available_themes.keys()))

        selected_path = self.available_themes[selected_name]

        try:
            selected_qss = load_qss_text(selected_path)
            if not selected_qss:
                logger.warning(
                    "Selected theme QSS is empty",
                    extra={"context": {"theme_name": selected_name, "theme_path": str(selected_path)}},
                )
                return

            self._clear_module_stylesheet_overrides()
            self.setStyleSheet(selected_qss)

            self.current_theme_name = selected_name
            clear_icon_cache()
            self._refresh_theme_action_checks()

            self.statusBar().showMessage(self.tr(f"Theme applied: {selected_name}"), 5000)
            logger.info(f"Theme applied: {selected_name} ({selected_path})")

        except Exception:
            logger.warning(
                "Failed to apply theme",
                extra={"context": {"theme_name": selected_name, "theme_path": str(selected_path)}},
                exc_info=True,
            )

    def _refresh_theme_action_checks(self) -> None:
        current_key = self._theme_key(self.current_theme_name)

        for name, action in self.theme_actions.items():
            action.blockSignals(True)
            action.setChecked(self._theme_key(name) == current_key)
            action.blockSignals(False)

    def _clear_module_stylesheet_overrides(self) -> None:
        for widget in self._module_widgets():
            try:
                widget.setStyleSheet("")
                if hasattr(widget, "apply_feature_style"):
                    widget.apply_feature_style()
            except Exception:
                logger.warning(
                    "Failed to clear module stylesheet override",
                    extra={"context": {"widget": type(widget).__name__}},
                    exc_info=True,
                )