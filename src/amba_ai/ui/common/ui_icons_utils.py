from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import QCoreApplication, QSize
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QApplication, QStyle

try:
    import qtawesome as qta
    _QTA_AVAILABLE = True
except ImportError:
    qta = None
    _QTA_AVAILABLE = False

logger = logging.getLogger(__name__)

# QtAwesome icon map
_AMBAAI_QTA_MAP: dict[str, str] = {
    "app": "fa5s.graduation-cap",
    "ambaai": "fa5s.graduation-cap",
    "home": "fa5s.home",
    "dashboard": "fa5s.tachometer-alt",
    "settings": "fa5s.cogs",
    "preferences": "fa5s.cogs",
    "menu": "fa5s.bars",
    "education": "fa5s.graduation-cap",
    "learning": "fa5s.book-reader",
    "student": "fa5s.user-graduate",
    "teacher": "fa5s.chalkboard-teacher",
    "teacher-review": "fa5s.chalkboard-teacher",
    "classroom": "fa5s.chalkboard",
    "school": "fa5s.school",
    "curriculum": "fa5s.book",
    "lesson": "fa5s.book-open",
    "book": "fa5s.book",
    "library": "fa5s.book-open",
    "knowledge": "fa5s.brain",
    "ingest": "fa5s.file-upload",
    "upload": "fa5s.upload",
    "file-upload": "fa5s.file-upload",
    "import": "fa5s.file-import",
    "document": "fa5s.file-alt",
    "file": "fa5.file",
    "pdf": "fa5.file-pdf",
    "file-pdf": "fa5.file-pdf",
    "docx": "fa5.file-word",
    "word": "fa5.file-word",
    "pptx": "fa5.file-powerpoint",
    "powerpoint": "fa5.file-powerpoint",
    "audio": "fa5.file-audio",
    "video": "fa5.file-video",
    "image": "fa5s.image",
    "notes": "fa5s.sticky-note",
    "summary": "fa5s.align-left",
    "summarizer": "fa5s.align-left",
    "outline": "fa5s.list-alt",
    "study": "fa5s.book-reader",
    "study-pack": "fa5s.archive",
    "flashcards": "fa5s.clone",
    "flashcard": "fa5s.clone",
    "quiz": "fa5s.question-circle",
    "mcq": "fa5s.tasks",
    "question": "fa5s.question-circle",
    "answer": "fa5s.check-circle",
    "practice": "fa5s.pen-alt",
    "tutor": "fa5s.comments",
    "chat": "fa5s.comment-dots",
    "ask": "fa5s.paper-plane",
    "send": "fa5s.paper-plane",
    "assistant": "fa5s.robot",
    "agent": "fa5s.robot",
    "offline": "fa5s.database",
    "offline-first": "fa5s.database",
    "local": "fa5s.hdd",
    "local-database": "fa5s.database",
    "database": "fa5s.database",
    "storage": "fa5s.hdd",
    "data-sovereignty": "fa5s.lock",
    "sovereignty": "fa5s.lock",
    "privacy": "fa5s.user-shield",
    "privacy-mode": "fa5s.user-shield",
    "lock": "fa5s.lock",
    "ai": "fa5s.brain",
    "edge-ai": "fa5s.microchip",
    "edge": "fa5s.microchip",
    "cpu-mode": "fa5s.microchip",
    "model": "fa5s.robot",
    "llm": "fa5s.robot",
    "rag": "fa5s.project-diagram",
    "retrieval": "fa5s.search",
    "evidence": "fa5s.anchor",
    "source": "fa5s.link",
    "citation": "fa5s.quote-right",
    "verified": "fa5s.check-circle",
    "guardrails": "fa5s.shield-alt",
    "safety": "fa5s.shield-alt",
    "shield": "fa5s.shield-alt",
    "language": "fa5s.language",
    "language-mode": "fa5s.language",
    "translate": "fa5s.language",
    "multilingual": "fa5s.globe-africa",
    "mother-tongue": "fa5s.language",
    "globe": "fa5s.globe-africa",
    "inclusion": "fa5s.users",
    "accessibility": "fa5s.universal-access",
    "audio-learning": "fa5s.volume-up",
    "tts": "fa5s.volume-up",
    "cloud": "fa5s.cloud",
    "cloud-optional": "fa5s.cloud",
    "cloud-assist": "fa5s.cloud",
    "hybrid": "fa5s.exchange-alt",
    "equity-switch": "fa5s.toggle-on",
    "equity": "fa5s.toggle-on",
    "low-resource": "fa5s.leaf",
    "sync": "fa5s.sync-alt",
    "refresh": "fa5s.sync-alt",
    "generate": "fa5s.magic",
    "run": "fa5s.play-circle",
    "play": "fa5s.play-circle",
    "stop": "fa5s.stop-circle",
    "cancel": "fa5s.ban",
    "export": "fa5s.file-export",
    "download": "fa5s.download",
    "save": "fa5s.save",
    "copy": "fa5s.copy",
    "edit": "fa5s.edit",
    "delete": "fa5s.trash-alt",
    "trash": "fa5s.trash-alt",
    "clear": "fa5s.eraser",
    "search": "fa5s.search",
    "filter": "fa5s.filter",
    "plus": "fa5s.plus",
    "add": "fa5s.plus",
    "minus": "fa5s.minus",
    "remove": "fa5s.minus",
    "success": "fa5s.check-circle",
    "check": "fa5s.check",
    "warning": "fa5s.exclamation-triangle",
    "error": "fa5s.exclamation-circle",
    "info": "fa5s.info-circle",
    "help": "fa5s.question-circle",
    "loading": "fa5s.spinner",
    "spinner": "fa5s.spinner",
    "close": "fa5s.times",
    "times": "fa5s.times",
    "chevron-down": "fa5s.chevron-down",
    "chevron-up": "fa5s.chevron-up",
    "chevron-left": "fa5s.chevron-left",
    "chevron-right": "fa5s.chevron-right",
    "arrow-left": "fa5s.arrow-left",
    "arrow-right": "fa5s.arrow-right",
    "arrow-up": "fa5s.arrow-up",
    "arrow-down": "fa5s.arrow-down",
}

# Theme map
_THEME_MAP: dict[str, str] = {
    "search": "edit-find",
    "settings": "preferences-system",
    "preferences": "preferences-system",
    "folder": "folder",
    "folder-open": "document-open",
    "document": "text-x-generic",
    "file": "text-x-generic",
    "pdf": "application-pdf",
    "save": "document-save",
    "export": "document-save-as",
    "upload": "document-send",
    "download": "document-revert",
    "copy": "edit-copy",
    "edit": "document-edit",
    "delete": "user-trash",
    "trash": "user-trash",
    "clear": "edit-clear",
    "refresh": "view-refresh",
    "sync": "view-refresh",
    "play": "media-playback-start",
    "run": "media-playback-start",
    "stop": "media-playback-stop",
    "cancel": "process-stop",
    "info": "dialog-information",
    "warning": "dialog-warning",
    "error": "dialog-error",
    "help": "help-faq",
    "home": "go-home",
    "check": "emblem-ok",
    "success": "emblem-ok",
    "loading": "process-working",
    "spinner": "process-working",
    "database": "document-properties",
    "local-database": "document-properties",
    "cloud": "folder-remote",
    "language": "preferences-desktop-locale",
    "accessibility": "preferences-desktop-accessibility",
}

# Fallback map
_FALLBACK_MAP: dict[str, QStyle.StandardPixmap] = {
    "file": QStyle.StandardPixmap.SP_FileIcon,
    "document": QStyle.StandardPixmap.SP_FileIcon,
    "pdf": QStyle.StandardPixmap.SP_FileIcon,
    "folder": QStyle.StandardPixmap.SP_DirIcon,
    "folder-open": QStyle.StandardPixmap.SP_DirOpenIcon,
    "upload": QStyle.StandardPixmap.SP_ArrowUp,
    "download": QStyle.StandardPixmap.SP_ArrowDown,
    "close": QStyle.StandardPixmap.SP_DialogCloseButton,
    "times": QStyle.StandardPixmap.SP_DialogCloseButton,
    "delete": QStyle.StandardPixmap.SP_TrashIcon,
    "trash": QStyle.StandardPixmap.SP_TrashIcon,
    "search": QStyle.StandardPixmap.SP_FileDialogContentsView,
    "play": QStyle.StandardPixmap.SP_MediaPlay,
    "run": QStyle.StandardPixmap.SP_MediaPlay,
    "stop": QStyle.StandardPixmap.SP_MediaStop,
    "refresh": QStyle.StandardPixmap.SP_BrowserReload,
    "sync": QStyle.StandardPixmap.SP_BrowserReload,
    "settings": QStyle.StandardPixmap.SP_ComputerIcon,
    "preferences": QStyle.StandardPixmap.SP_ComputerIcon,
    "info": QStyle.StandardPixmap.SP_MessageBoxInformation,
    "warning": QStyle.StandardPixmap.SP_MessageBoxWarning,
    "error": QStyle.StandardPixmap.SP_MessageBoxCritical,
    "help": QStyle.StandardPixmap.SP_DialogHelpButton,
    "save": QStyle.StandardPixmap.SP_DialogSaveButton,
    "home": QStyle.StandardPixmap.SP_DirHomeIcon,
    "arrow-left": QStyle.StandardPixmap.SP_ArrowLeft,
    "arrow-right": QStyle.StandardPixmap.SP_ArrowRight,
    "arrow-up": QStyle.StandardPixmap.SP_ArrowUp,
    "arrow-down": QStyle.StandardPixmap.SP_ArrowDown,
}


def _clean_icon_name(name: str) -> str:
    text = str(name or "").strip().lower()
    if not text:
        return "file"
    if "." in text:
        return text.split(".")[-1].lower()
    return text


def _resolve_color_name(color: Optional[Union[str, QColor]]) -> str:
    if color is None:
        app = QCoreApplication.instance()
        if app is not None:
            return app.palette().text().color().name()
        return "#FFFFFF"
    if isinstance(color, QColor):
        return color.name()
    return str(color)


def _resolve_size_tuple(size: Optional[QSize]) -> tuple[int, int]:
    if isinstance(size, QSize):
        return int(size.width()), int(size.height())
    return 0, 0


def _load_local_icon(local_path: str) -> QIcon:
    if local_path and os.path.isfile(local_path):
        q_icon = QIcon(local_path)
        if not q_icon.isNull():
            return q_icon
    return QIcon()


def _resize_icon(q_icon: QIcon, width: int, height: int) -> QIcon:
    if q_icon.isNull() or width <= 0 or height <= 0:
        return q_icon
    actual_size = q_icon.actualSize(QSize(width, height))
    if actual_size.isEmpty():
        actual_size = QSize(width, height)
    return QIcon(q_icon.pixmap(actual_size))


@lru_cache(maxsize=768)
def _icon_cached(name: str, color_name: str, width: int, height: int, local_path: str) -> QIcon:
    clean_name = _clean_icon_name(name)
    local_icon = _load_local_icon(local_path)

    if not local_icon.isNull():
        return _resize_icon(local_icon, width, height)

    canonical_name = _AMBAAI_QTA_MAP.get(clean_name, name)
    q_icon = QIcon()

    if _QTA_AVAILABLE and qta is not None:
        try:
            qta_icon = qta.icon(canonical_name, color=QColor(color_name))
            if not qta_icon.isNull():
                q_icon = qta_icon
        except Exception as exc:
            logger.debug(
                "QtAwesome icon resolution failed",
                extra={
                    "context": {
                        "requested_name": name,
                        "clean_name": clean_name,
                        "canonical_name": canonical_name,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                },
            )

    if q_icon.isNull():
        theme_name = _THEME_MAP.get(clean_name)
        if theme_name and QIcon.hasThemeIcon(theme_name):
            q_icon = QIcon.fromTheme(theme_name)
        elif QIcon.hasThemeIcon(canonical_name):
            q_icon = QIcon.fromTheme(canonical_name)

    if q_icon.isNull():
        std_pixmap = _FALLBACK_MAP.get(clean_name)
        app = QApplication.instance()
        if std_pixmap is not None and app is not None:
            q_icon = app.style().standardIcon(std_pixmap)

    if q_icon.isNull():
        q_icon = QIcon.fromTheme("application-x-zerosize", QIcon())

    return _resize_icon(q_icon, width, height)


def icon(
    name: str,
    color: Optional[Union[str, QColor]] = None,
    size: Optional[QSize] = None,
    local_path: Optional[str] = None,
) -> QIcon:
    color_name = _resolve_color_name(color)
    width, height = _resolve_size_tuple(size)
    normalized_local_path = str(Path(local_path).resolve()) if local_path else ""
    return _icon_cached(str(name or "file"), color_name, width, height, normalized_local_path)


def clear_icon_cache() -> None:
    _icon_cached.cache_clear()
