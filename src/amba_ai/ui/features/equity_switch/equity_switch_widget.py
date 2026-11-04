from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QDateTime, QSettings, QSize, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
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
from .data_classes import EquityProfile
from .equity_switch_manager import EquitySwitchManager


class EquitySwitchWidget(QWidget):
    equityProfileChanged = Signal(dict)
    modelModeChanged = Signal(str)
    languageModeChanged = Signal(str)
    privacyModeChanged = Signal(str)
    connectivityModeChanged = Signal(str)
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
        self.manager = EquitySwitchManager(settings, job_service, self)
        self._is_operation_active = False

        self.setObjectName("AmbaEquitySwitchWidgetUI")

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
        self.top_toolbar = QToolBar(self.tr("Equity Switch Controls"), self)
        self.top_toolbar.setObjectName("equityToolbar")
        self.top_toolbar.setIconSize(QSize(16, 16))
        self.top_toolbar.setMovable(False)
        self.top_toolbar.setFloatable(False)

        self.btn_apply_profile = QPushButton(icon("equity-switch"), self.tr("Apply Profile"))
        self.btn_apply_profile.setObjectName("applyProfileButton")
        self.btn_apply_profile.setProperty("priority", "primary")

        self.btn_reset_profile = QPushButton(icon("refresh"), self.tr("Reset Default"))
        self.btn_reset_profile.setObjectName("resetProfileButton")
        self.btn_reset_profile.setProperty("variant", "secondary")

        self.btn_show_summary = QPushButton(icon("info"), self.tr("Profile Summary"))
        self.btn_show_summary.setObjectName("summaryProfileButton")
        self.btn_show_summary.setProperty("variant", "secondary")

        self.top_toolbar.addWidget(self.btn_apply_profile)
        self.top_toolbar.addWidget(self.btn_reset_profile)
        self.top_toolbar.addWidget(self.btn_show_summary)

        main_layout.addWidget(self.top_toolbar)

    def _setup_tabs(self, main_layout: QVBoxLayout) -> None:
        self.content_tabs = QTabWidget()
        self.content_tabs.setIconSize(QSize(14, 14))

        self._setup_mode_tab()
        self._setup_language_tab()
        self._setup_privacy_tab()
        self._setup_status_tab()

        main_layout.addWidget(self.content_tabs, stretch=1)

    def _setup_mode_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        mode_group = QGroupBox(self.tr("Offline and Model Behavior"))
        form = QFormLayout(mode_group)
        form.setSpacing(8)

        self.profile_combo = QComboBox()
        self.profile_combo.addItems(
            [
                "Offline Classroom",
                "Teacher Laptop",
                "School Lab",
                "Community Hub",
                "Low-RAM CPU Demo",
                "Hybrid Optional Cloud",
            ]
        )

        self.connectivity_combo = QComboBox()
        self.connectivity_combo.addItems(
            [
                "Offline Only",
                "Local Network Only",
                "Local Model Preferred",
                "Hybrid Optional Cloud Assist",
            ]
        )

        self.model_mode_combo = QComboBox()
        self.model_mode_combo.addItems(
            [
                "CPU Low-RAM Mode",
                "Balanced Local Model",
                "Higher Quality Local Model",
                "Hybrid Model Assist",
            ]
        )

        self.preferred_model_combo = QComboBox()
        self.preferred_model_combo.setEditable(True)
        self.preferred_model_combo.addItems(
            [
                "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M",
                "qwen2.5:0.5b",
                "qwen2.5:3b",
                "llama3.2:1b",
                "mistral",
                "llama3.1",
            ]
        )

        self.context_combo = QComboBox()
        self.context_combo.addItems(["1024", "2048", "4096", "8192"])

        self.cloud_assist_check = QCheckBox(self.tr("Allow optional cloud assist when policy and connectivity permit"))
        self.external_processing_check = QCheckBox(self.tr("Allow external processing"))

        form.addRow(self.tr("Profile:"), self.profile_combo)
        form.addRow(self.tr("Connectivity:"), self.connectivity_combo)
        form.addRow(self.tr("Model Mode:"), self.model_mode_combo)
        form.addRow(self.tr("Preferred Model:"), self.preferred_model_combo)
        form.addRow(self.tr("Context Limit:"), self.context_combo)
        form.addRow("", self.cloud_assist_check)
        form.addRow("", self.external_processing_check)

        layout.addWidget(mode_group)
        layout.addStretch(1)

        self.content_tabs.addTab(tab, icon("equity-switch"), self.tr("Mode"))

    def _setup_language_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        language_group = QGroupBox(self.tr("Language and Accessibility"))
        form = QFormLayout(language_group)
        form.setSpacing(8)

        self.language_combo = QComboBox()
        self.language_combo.addItems(
            [
                "English",
                "Amharic",
                "Afaan Oromo",
                "Tigrinya",
                "Somali",
            ]
        )

        self.simple_language_check = QCheckBox(self.tr("Use simple learner-friendly language"))
        self.dyslexia_check = QCheckBox(self.tr("Use dyslexia-friendly formatting"))
        self.audio_output_check = QCheckBox(self.tr("Prefer audio-supported outputs where available"))

        form.addRow(self.tr("Language:"), self.language_combo)
        form.addRow("", self.simple_language_check)
        form.addRow("", self.dyslexia_check)
        form.addRow("", self.audio_output_check)

        layout.addWidget(language_group)
        layout.addStretch(1)

        self.content_tabs.addTab(tab, icon("language"), self.tr("Language & Accessibility"))

    def _setup_privacy_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        privacy_group = QGroupBox(self.tr("Privacy, Safety, and Teacher Governance"))
        form = QFormLayout(privacy_group)
        form.setSpacing(8)

        self.privacy_combo = QComboBox()
        self.privacy_combo.addItems(
            [
                "Local Learner Data Only",
                "School-Controlled Local Records",
                "Consent-Based Institutional Sharing",
            ]
        )

        self.teacher_review_check = QCheckBox(self.tr("Require teacher review for reusable learning assets"))

        form.addRow(self.tr("Privacy Mode:"), self.privacy_combo)
        form.addRow("", self.teacher_review_check)

        layout.addWidget(privacy_group)
        layout.addStretch(1)

        self.content_tabs.addTab(tab, icon("guardrails"), self.tr("Privacy & Safety"))

    def _setup_status_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        self.profile_status_label = QLabel(self.tr("Equity profile: not loaded"))
        self.profile_status_label.setObjectName("equityStatusLabel")
        self.profile_status_label.setWordWrap(True)

        self.operation_log = QTextBrowser()
        self.operation_log.setObjectName("equityOperationLog")
        self.operation_log.setReadOnly(True)
        self.operation_log.setFont(QFont("Consolas"))

        layout.addWidget(self.profile_status_label)
        layout.addWidget(self.operation_log, stretch=1)

        self.content_tabs.addTab(tab, icon("info"), self.tr("Status"))

    def _setup_bottom_bar(self, main_layout: QVBoxLayout) -> None:
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(4, 2, 4, 2)
        bottom_bar.setSpacing(5)

        self.overall_status_label = QLabel(self.tr("Ready. Configure AmbaAI for offline-first learning."))
        bottom_bar.addWidget(self.overall_status_label, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(220)
        self.progress_bar.setFixedHeight(18)
        bottom_bar.addWidget(self.progress_bar)

        main_layout.addLayout(bottom_bar)

    def _connect_signals(self) -> None:
        self.btn_apply_profile.clicked.connect(self.apply_current_profile)
        self.btn_reset_profile.clicked.connect(self.reset_default_profile)
        self.btn_show_summary.clicked.connect(self.show_profile_summary)

        self.manager.profileLoaded.connect(self._on_manager_profile_loaded)
        self.manager.profileChanged.connect(self._on_manager_profile_changed)
        self.manager.modelModeChanged.connect(self.modelModeChanged.emit)
        self.manager.languageModeChanged.connect(self.languageModeChanged.emit)
        self.manager.privacyModeChanged.connect(self.privacyModeChanged.emit)
        self.manager.connectivityModeChanged.connect(self.connectivityModeChanged.emit)
        self.manager.statusMessage.connect(self._append_status_message)

    def _post_init_setup(self) -> None:
        self.manager.load_profile()
        self._update_ui_for_operation_status()

    def _load_local_styles(self) -> None:
        qss_path = Path(__file__).parent / "equity_switch.qss"
        apply_local_qss(self, qss_path)

    def _profile_from_ui(self) -> EquityProfile:
        try:
            context_tokens = int(self.context_combo.currentText())
        except Exception:
            context_tokens = 2048

        return EquityProfile(
            profile_name=self.profile_combo.currentText(),
            connectivity_mode=self.connectivity_combo.currentText(),
            model_mode=self.model_mode_combo.currentText(),
            cloud_assist=self.cloud_assist_check.isChecked(),
            privacy_mode=self.privacy_combo.currentText(),
            teacher_review_required=self.teacher_review_check.isChecked(),
            target_language=self.language_combo.currentText(),
            simple_language=self.simple_language_check.isChecked(),
            dyslexia_friendly=self.dyslexia_check.isChecked(),
            audio_supported_output=self.audio_output_check.isChecked(),
            max_context_tokens=context_tokens,
            preferred_model=self.preferred_model_combo.currentText().strip() or "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M",
            allow_external_processing=self.external_processing_check.isChecked(),
        )

    def _apply_profile_to_ui(self, profile: EquityProfile) -> None:
        self._set_combo_text(self.profile_combo, profile.profile_name)
        self._set_combo_text(self.connectivity_combo, profile.connectivity_mode)
        self._set_combo_text(self.model_mode_combo, profile.model_mode)
        self._set_combo_text(self.preferred_model_combo, profile.preferred_model)
        self._set_combo_text(self.context_combo, str(profile.max_context_tokens))
        self._set_combo_text(self.language_combo, profile.target_language)
        self._set_combo_text(self.privacy_combo, profile.privacy_mode)

        self.cloud_assist_check.setChecked(profile.cloud_assist)
        self.external_processing_check.setChecked(profile.allow_external_processing)
        self.simple_language_check.setChecked(profile.simple_language)
        self.dyslexia_check.setChecked(profile.dyslexia_friendly)
        self.audio_output_check.setChecked(profile.audio_supported_output)
        self.teacher_review_check.setChecked(profile.teacher_review_required)

        self._refresh_profile_status(profile)

    @staticmethod
    def _set_combo_text(combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.isEditable():
            combo.setEditText(value)

    @Slot()
    def apply_current_profile(self) -> None:
        self._is_operation_active = True
        self._update_ui_for_operation_status()
        self.operationStarted.emit("Applying Equity Switch profile...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        try:
            profile = self._profile_from_ui()
            self.manager.apply_profile(profile.to_dict())
        finally:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_bar.setVisible(False)
            self._is_operation_active = False
            self._update_ui_for_operation_status()
            self.operationFinished.emit("Equity profile applied.")

    @Slot()
    def reset_default_profile(self) -> None:
        reply = QMessageBox.question(
            self,
            self.tr("Reset Equity Switch"),
            self.tr("Reset Equity Switch settings to the default offline classroom profile?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.manager.reset_default_profile()

    @Slot()
    def show_profile_summary(self) -> None:
        profile = self._profile_from_ui()
        QMessageBox.information(
            self,
            self.tr("Equity Profile Summary"),
            self._profile_summary_text(profile),
        )

    @Slot(dict)
    def _on_manager_profile_loaded(self, payload: dict[str, Any]) -> None:
        profile = EquityProfile.from_dict(payload)
        self._apply_profile_to_ui(profile)

    @Slot(dict)
    def _on_manager_profile_changed(self, payload: dict[str, Any]) -> None:
        profile = EquityProfile.from_dict(payload)
        self._apply_profile_to_ui(profile)
        self.equityProfileChanged.emit(payload)

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
            f'<span style="color:#94A3B8;">[{timestamp}]</span> '
            f'<b style="color:{color};">[{level.upper()}]</b> {safe}'
        )
        self.overall_status_label.setText(message)
        self.statusMessage.emit(message, level)

    def _refresh_profile_status(self, profile: EquityProfile) -> None:
        external = "Allowed" if profile.allow_external_processing else "Disabled"
        cloud = "Enabled" if profile.cloud_assist else "Disabled"
        teacher = "Required" if profile.teacher_review_required else "Optional"

        self.profile_status_label.setText(
            self.tr(
                f"<b>Profile:</b> {profile.profile_name} | "
                f"<b>Connectivity:</b> {profile.connectivity_mode} | "
                f"<b>Model:</b> {profile.preferred_model} | "
                f"<b>Cloud:</b> {cloud} | "
                f"<b>External Processing:</b> {external} | "
                f"<b>Teacher Review:</b> {teacher}"
            )
        )

    @staticmethod
    def _profile_summary_text(profile: EquityProfile) -> str:
        return "\n".join(
            [
                f"Profile: {profile.profile_name}",
                f"Connectivity: {profile.connectivity_mode}",
                f"Model Mode: {profile.model_mode}",
                f"Preferred Model: {profile.preferred_model}",
                f"Context Tokens: {profile.max_context_tokens}",
                f"Cloud Assist: {'Enabled' if profile.cloud_assist else 'Disabled'}",
                f"External Processing: {'Allowed' if profile.allow_external_processing else 'Disabled'}",
                f"Privacy Mode: {profile.privacy_mode}",
                f"Teacher Review: {'Required' if profile.teacher_review_required else 'Optional'}",
                f"Target Language: {profile.target_language}",
                f"Simple Language: {'Enabled' if profile.simple_language else 'Disabled'}",
                f"Dyslexia-Friendly Formatting: {'Enabled' if profile.dyslexia_friendly else 'Disabled'}",
                f"Audio-Supported Output: {'Enabled' if profile.audio_supported_output else 'Disabled'}",
            ]
        )

    def _update_ui_for_operation_status(self) -> None:
        enabled = not self._is_operation_active
        self.btn_apply_profile.setEnabled(enabled)
        self.btn_reset_profile.setEnabled(enabled)
        self.btn_show_summary.setEnabled(enabled)

    def cleanup_before_close(self) -> None:
        self.manager.cleanup_before_close()
        logger.info("EquitySwitchWidget cleanup completed.")

    def retranslateUi(self) -> None:
        self.top_toolbar.setWindowTitle(self.tr("Equity Switch Controls"))
        self.btn_apply_profile.setText(self.tr("Apply Profile"))
        self.btn_reset_profile.setText(self.tr("Reset Default"))
        self.btn_show_summary.setText(self.tr("Profile Summary"))
        self.content_tabs.setTabText(0, self.tr("Mode"))
        self.content_tabs.setTabText(1, self.tr("Language & Accessibility"))
        self.content_tabs.setTabText(2, self.tr("Privacy & Safety"))
        self.content_tabs.setTabText(3, self.tr("Status"))