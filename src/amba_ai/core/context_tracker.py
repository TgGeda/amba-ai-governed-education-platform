from __future__ import annotations

import platform
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from PySide6.QtCore import QObject, Signal

from amba_ai.logger import logger

try:
    import psutil
except Exception:
    psutil = None


@dataclass(frozen=True)
class BatterySnapshot:
    available: bool
    percent: Optional[float] = None
    plugged: Optional[bool] = None
    seconds_left: Optional[int] = None
    warning: Optional[str] = None


@dataclass(frozen=True)
class UIContextSnapshot:
    active_tab: str = "Unknown"
    active_document_title: Optional[str] = None
    active_document_id: Optional[str] = None
    due_flashcards: Optional[int] = None
    extra_state: Optional[dict[str, str]] = None


@dataclass(frozen=True)
class RuntimeContextSnapshot:
    current_datetime: str
    timezone_name: str
    location: str
    os_name: str
    machine: str
    battery: BatterySnapshot
    ui: UIContextSnapshot

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContextTracker(QObject):
    context_updated = Signal(dict)

    DEFAULT_LOCATION = "Debre Tabor, Ethiopia"
    DEFAULT_TIMEZONE = "Africa/Addis_Ababa"
    LOW_BATTERY_THRESHOLD = 20.0
    CRITICAL_BATTERY_THRESHOLD = 10.0
    MAX_EXTRA_STATE_ITEMS = 32
    MAX_TEXT_VALUE_LENGTH = 240

    def __init__(
        self,
        parent: Optional[QObject] = None,
        *,
        location: str = DEFAULT_LOCATION,
        timezone_name: str = DEFAULT_TIMEZONE,
        active_tab: str = "Unknown",
    ) -> None:
        super().__init__(parent)
        self._lock = threading.RLock()
        self.location = self._clean_text(location, self.DEFAULT_LOCATION)
        self.timezone_name = self._clean_text(timezone_name, self.DEFAULT_TIMEZONE)
        self._active_tab = self._clean_text(active_tab, "Unknown")
        self._active_document_title: Optional[str] = None
        self._active_document_id: Optional[str] = None
        self._due_flashcards: Optional[int] = None
        self._extra_state: dict[str, str] = {}

    def set_location(self, location: str) -> None:
        with self._lock:
            self.location = self._clean_text(location, self.DEFAULT_LOCATION)
            self._emit_context_updated_locked()

    def set_timezone(self, timezone_name: str) -> None:
        with self._lock:
            self.timezone_name = self._clean_text(timezone_name, self.DEFAULT_TIMEZONE)
            self._emit_context_updated_locked()

    def set_active_tab(self, active_tab: str) -> None:
        with self._lock:
            self._active_tab = self._clean_text(active_tab, "Unknown")
            self._emit_context_updated_locked()

    def set_active_document(
        self,
        *,
        document_id: int | str | None = None,
        title: str | None = None,
    ) -> None:
        with self._lock:
            self._active_document_id = (
                self._truncate(str(document_id).strip())
                if document_id is not None and str(document_id).strip()
                else None
            )
            self._active_document_title = (
                self._truncate(title.strip())
                if isinstance(title, str) and title.strip()
                else None
            )
            self._emit_context_updated_locked()

    def clear_active_document(self) -> None:
        with self._lock:
            self._active_document_id = None
            self._active_document_title = None
            self._emit_context_updated_locked()

    def set_due_flashcards(self, due_count: int | None) -> None:
        with self._lock:
            if due_count is None:
                self._due_flashcards = None
            else:
                self._due_flashcards = max(0, int(due_count))
            self._emit_context_updated_locked()

    def set_extra_state(self, key: str, value: str | int | float | bool | None) -> None:
        clean_key = self._clean_key(key)
        if not clean_key:
            return

        with self._lock:
            if value is None:
                self._extra_state.pop(clean_key, None)
                self._emit_context_updated_locked()
                return

            if clean_key not in self._extra_state and len(self._extra_state) >= self.MAX_EXTRA_STATE_ITEMS:
                oldest_key = next(iter(self._extra_state))
                self._extra_state.pop(oldest_key, None)

            self._extra_state[clean_key] = self._truncate(str(value).strip())
            self._emit_context_updated_locked()

    def remove_extra_state(self, key: str) -> None:
        clean_key = self._clean_key(key)
        if not clean_key:
            return

        with self._lock:
            self._extra_state.pop(clean_key, None)
            self._emit_context_updated_locked()

    def clear_extra_state(self) -> None:
        with self._lock:
            self._extra_state.clear()
            self._emit_context_updated_locked()

    def snapshot(self) -> RuntimeContextSnapshot:
        with self._lock:
            now = self._now_local_locked()
            battery = self._battery_snapshot()
            ui = UIContextSnapshot(
                active_tab=self._active_tab,
                active_document_title=self._active_document_title,
                active_document_id=self._active_document_id,
                due_flashcards=self._due_flashcards,
                extra_state=dict(self._extra_state),
            )

            return RuntimeContextSnapshot(
                current_datetime=now.strftime("%A, %B %d, %Y, %I:%M %p"),
                timezone_name=self.timezone_name,
                location=self.location,
                os_name=platform.system() or "Unknown",
                machine=platform.machine() or "Unknown",
                battery=battery,
                ui=ui,
            )

    def to_dict(self) -> dict[str, Any]:
        return self.snapshot().to_dict()

    def generate_system_prompt(self) -> str:
        context = self.snapshot()

        lines = [
            "Runtime context for AmbaAI:",
            f"- Current local date and time: {context.current_datetime}",
            f"- Timezone: {context.timezone_name}",
            f"- Location: {context.location}",
            f"- Operating system: {context.os_name} ({context.machine})",
            f"- Active UI tab: {context.ui.active_tab}",
        ]

        if context.ui.active_document_title:
            lines.append(f"- Active document title: {context.ui.active_document_title}")

        if context.ui.active_document_id:
            lines.append(f"- Active document ID: {context.ui.active_document_id}")

        if context.ui.due_flashcards is not None:
            lines.append(f"- Due flashcards: {context.ui.due_flashcards}")

        if context.battery.available:
            battery_status = "charging or plugged in" if context.battery.plugged else "not plugged in"
            percent = context.battery.percent if context.battery.percent is not None else 0.0
            lines.append(f"- Battery: {percent:.0f}% and {battery_status}")

            if context.battery.warning:
                lines.append(f"- Battery warning: {context.battery.warning}")
        else:
            lines.append("- Battery: unavailable")

        if context.ui.extra_state:
            lines.append("- Additional UI state:")
            for key, value in sorted(context.ui.extra_state.items()):
                lines.append(f"  - {key}: {value}")

        lines.extend(
            [
                "",
                "Instruction:",
                "Use this context silently to make responses timely, helpful, and relevant.",
                "Do not mention this runtime context unless it directly helps the student.",
                "If battery is low, keep responses concise and avoid suggesting long-running tasks unless necessary.",
                "Maintain AmbaAI's offline-first privacy posture.",
            ]
        )

        return "\n".join(lines).strip()

    def _emit_context_updated_locked(self) -> None:
        try:
            self.context_updated.emit(self.snapshot().to_dict())
        except RecursionError:
            logger.debug("Context update signal recursion avoided", exc_info=True)
        except Exception:
            logger.debug("Context update signal failed", exc_info=True)

    def _battery_snapshot(self) -> BatterySnapshot:
        if psutil is None:
            return BatterySnapshot(
                available=False,
                warning="Battery information unavailable because psutil is not installed.",
            )

        try:
            battery = psutil.sensors_battery()
        except Exception:
            logger.debug("Battery lookup failed", exc_info=True)
            return BatterySnapshot(
                available=False,
                warning="Battery information could not be read.",
            )

        if battery is None:
            return BatterySnapshot(available=False)

        percent = float(battery.percent)
        plugged = bool(battery.power_plugged)
        seconds_left = self._normalize_seconds_left(getattr(battery, "secsleft", None))
        warning = self._battery_warning(percent=percent, plugged=plugged)

        return BatterySnapshot(
            available=True,
            percent=percent,
            plugged=plugged,
            seconds_left=seconds_left,
            warning=warning,
        )

    def _battery_warning(self, *, percent: float, plugged: bool) -> Optional[str]:
        if plugged:
            return None

        if percent <= self.CRITICAL_BATTERY_THRESHOLD:
            return (
                "Battery is critically low. Recommend saving work, avoiding heavy model tasks, "
                "and connecting power."
            )

        if percent <= self.LOW_BATTERY_THRESHOLD:
            return "Battery is low. Prefer short responses and avoid long transcription or generation tasks."

        return None

    def _now_local_locked(self) -> datetime:
        try:
            return datetime.now(ZoneInfo(self.timezone_name))
        except Exception:
            logger.debug(
                "Invalid timezone; falling back to system local time",
                extra={"context": {"timezone_name": self.timezone_name}},
                exc_info=True,
            )
            return datetime.now()

    @classmethod
    def _clean_text(cls, value: str, fallback: str) -> str:
        if not isinstance(value, str):
            return fallback

        cleaned = value.strip()
        if not cleaned:
            return fallback

        return cls._truncate(cleaned)

    @classmethod
    def _clean_key(cls, key: str) -> str:
        if not isinstance(key, str):
            return ""

        cleaned = key.strip().replace(" ", "_")
        cleaned = "".join(ch for ch in cleaned if ch.isalnum() or ch in {"_", "-", "."})
        return cls._truncate(cleaned, 64)

    @classmethod
    def _truncate(cls, value: str, limit: Optional[int] = None) -> str:
        max_length = limit or cls.MAX_TEXT_VALUE_LENGTH

        if len(value) <= max_length:
            return value

        return value[: max_length - 1].rstrip() + "…"

    @staticmethod
    def _normalize_seconds_left(value: Any) -> Optional[int]:
        try:
            seconds = int(value)
        except Exception:
            return None

        if seconds < 0:
            return None

        return seconds