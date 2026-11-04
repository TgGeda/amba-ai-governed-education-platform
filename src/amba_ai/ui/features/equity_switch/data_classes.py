from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

from PySide6.QtCore import QSettings


def _setting_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class EquityProfile:
    profile_name: str = "Offline Classroom"
    connectivity_mode: str = "Offline Only"
    model_mode: str = "CPU Low-RAM Mode"
    cloud_assist: bool = False
    privacy_mode: str = "Local Learner Data Only"
    teacher_review_required: bool = True
    target_language: str = "English"
    simple_language: bool = True
    dyslexia_friendly: bool = False
    audio_supported_output: bool = False
    max_context_tokens: int = 2048
    preferred_model: str = "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"
    allow_external_processing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> EquityProfile:
        source = dict(data or {})
        normalized: dict[str, Any] = {}

        for f in fields(cls):
            normalized[f.name] = source.get(f.name, f.default)

        for key in [
            "cloud_assist",
            "teacher_review_required",
            "simple_language",
            "dyslexia_friendly",
            "audio_supported_output",
            "allow_external_processing",
        ]:
            normalized[key] = _setting_bool(normalized.get(key), getattr(cls, key))

        try:
            normalized["max_context_tokens"] = int(normalized.get("max_context_tokens", cls.max_context_tokens))
        except Exception:
            normalized["max_context_tokens"] = cls.max_context_tokens

        return cls(**normalized)

    @classmethod
    def from_settings(cls, settings: QSettings) -> EquityProfile:
        settings.beginGroup("EquitySwitch")
        data = {f.name: settings.value(f.name, getattr(cls, f.name)) for f in fields(cls)}
        settings.endGroup()
        return cls.from_dict(data)

    def save_to_settings(self, settings: QSettings) -> None:
        settings.beginGroup("EquitySwitch")
        for key, value in self.to_dict().items():
            settings.setValue(key, value)
        settings.endGroup()
        settings.sync()