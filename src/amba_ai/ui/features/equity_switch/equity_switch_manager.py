from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QSettings, Signal, Slot

from amba_ai.logger import logger
from .data_classes import EquityProfile


class EquitySwitchManager(QObject):
    profileLoaded = Signal(dict)
    profileChanged = Signal(dict)
    modelModeChanged = Signal(str)
    languageModeChanged = Signal(str)
    privacyModeChanged = Signal(str)
    connectivityModeChanged = Signal(str)
    statusMessage = Signal(str, str)

    def __init__(self, settings: QSettings, job_service: Any | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.jobs = job_service
        self._profile = EquityProfile.from_settings(settings)

    @property
    def profile(self) -> EquityProfile:
        return self._profile

    @Slot()
    def load_profile(self) -> None:
        self._profile = EquityProfile.from_settings(self.settings)
        payload = self._profile.to_dict()
        self.profileLoaded.emit(payload)
        self.profileChanged.emit(payload)
        self.statusMessage.emit("Equity profile loaded.", "INFO")

    @Slot(dict)
    def apply_profile(self, data: dict[str, Any]) -> None:
        previous = self._profile
        profile = EquityProfile.from_dict(data)
        profile.save_to_settings(self.settings)
        self._profile = profile

        payload = profile.to_dict()

        if previous.model_mode != profile.model_mode:
            self.modelModeChanged.emit(profile.model_mode)
        if previous.target_language != profile.target_language:
            self.languageModeChanged.emit(profile.target_language)
        if previous.privacy_mode != profile.privacy_mode:
            self.privacyModeChanged.emit(profile.privacy_mode)
        if previous.connectivity_mode != profile.connectivity_mode:
            self.connectivityModeChanged.emit(profile.connectivity_mode)

        self.profileChanged.emit(payload)

        if hasattr(self.jobs, "apply_equity_profile"):
            try:
                self.jobs.apply_equity_profile(payload)
            except Exception as exc:
                logger.warning(
                    "JobService equity profile hook failed",
                    extra={
                        "context": {
                            "operation": "apply_equity_profile",
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                        }
                    },
                    exc_info=True,
                )

        self.statusMessage.emit("Equity profile applied.", "INFO")

    @Slot()
    def reset_default_profile(self) -> None:
        self.apply_profile(EquityProfile().to_dict())

    def _update_field(self, key: str, value: Any) -> None:
        data = self._profile.to_dict()
        data[key] = value
        self.apply_profile(data)

    @Slot(str)
    def set_model_mode(self, mode: str) -> None:
        self._update_field("model_mode", mode)

    @Slot(str)
    def set_language_mode(self, language: str) -> None:
        self._update_field("target_language", language)

    @Slot(str)
    def set_privacy_mode(self, mode: str) -> None:
        self._update_field("privacy_mode", mode)

    def cleanup_before_close(self) -> None:
        try:
            self._profile.save_to_settings(self.settings)
            self.statusMessage.emit("Equity Switch settings saved.", "INFO")
        except Exception as exc:
            logger.error(
                "Failed to save Equity Switch settings",
                extra={
                    "context": {
                        "operation": "cleanup_before_close",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                },
                exc_info=True,
            )