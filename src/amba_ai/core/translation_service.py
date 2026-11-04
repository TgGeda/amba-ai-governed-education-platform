# src/amba_ai/core/translation_service.py
from __future__ import annotations

import re
import subprocess
import traceback
from dataclasses import dataclass, field
from typing import Any, Protocol, Literal

from amba_ai.logger import logger


# ---------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------

TranslationErrorType = Literal[
    "validation_error",
    "backend_error",
    "subprocess_error",
]


@dataclass(frozen=True)
class TranslationResult:
    """
    Structured result returned by TranslationService.translate().
    """

    text: str
    source_language: str
    target_language: str
    translated: bool
    error_type: TranslationErrorType | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class LocalTranslatorBackend(Protocol):
    """
    Protocol for local/offline translation backends.
    """

    @property
    def name(self) -> str: ...

    def healthcheck(self) -> bool: ...

    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str: ...


# ---------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------


class NoOpTranslatorBackend:
    """
    Fallback backend that returns text unchanged.
    """

    @property
    def name(self) -> str:
        return "noop"

    def healthcheck(self) -> bool:
        return True

    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        return text or ""


class OllamaTranslatorBackend:
    """
    Offline translation using local Ollama via subprocess.
    """

    def __init__(self, model: str = "mistral"):
        self.model = model

    @property
    def name(self) -> str:
        return "ollama"

    def healthcheck(self) -> bool:
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        prompt = (
            "Translate the text below.\n\n"
            "STRICT RULES:\n"
            "- Preserve Markdown formatting exactly.\n"
            "- Preserve LaTeX math ($$, \\( \\)) exactly.\n"
            "- Preserve code blocks and inline code exactly.\n"
            "- Do not add explanations.\n"
            "- Output ONLY the translated text.\n\n"
            f"Source language: {source_language}\n"
            f"Target language: {target_language}\n\n"
            "TEXT:\n"
            f"{text}"
        )

        result = subprocess.run(
            ["ollama", "run", self.model],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Ollama translation failed")

        return result.stdout.strip()


# Optional Argos backend (safe to keep disabled if not installed)
class ArgosTranslateBackend:
    def __init__(self):
        import argostranslate.translate  # type: ignore

        self._translate = argostranslate.translate.translate

    @property
    def name(self) -> str:
        return "argos"

    def healthcheck(self) -> bool:
        try:
            import argostranslate.translate  # noqa
            return True
        except Exception:
            return False

    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        return self._translate(text, source_language, target_language)


# ---------------------------------------------------------------------
# Translation service
# ---------------------------------------------------------------------


class TranslationService:
    """
    Orchestrates text translation with structured results and safety.
    """

    DEFAULT_MAX_CHARS = 20_000

    _CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

    def __init__(
        self,
        backend: LocalTranslatorBackend | None = None,
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> None:
        self.backend = backend or NoOpTranslatorBackend()
        self.max_chars = max_chars

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize_text(self, text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = self._CONTROL_CHARS_RE.sub("", normalized)
        return normalized.strip()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def translate(
        self,
        text: str,
        *,
        target_language: str,
        source_language: str = "auto",
    ) -> TranslationResult:
        context = {
            "operation": "translate",
            "backend": self.backend.name,
            "model": getattr(self.backend, "model", None),
            "source_language": source_language,
            "target_language": target_language,
        }

        logger.info(
            "Translation started",
            extra={
                "context": {
                    **context,
                    "text_length": len(text) if text else 0,
                }
            },
        )

        # ---------------- validation ----------------

        if not text or not text.strip():
            return TranslationResult(
                text="",
                source_language=source_language,
                target_language=target_language,
                translated=False,
                error_type="validation_error",
                metadata={
                    **context,
                    "reason": "empty_text",
                },
            )

        if not target_language or target_language.lower() in {"auto", "same", "none"}:
            return TranslationResult(
                text=text,
                source_language=source_language,
                target_language=target_language or "same",
                translated=False,
                metadata={
                    **context,
                    "reason": "no_translation_requested",
                },
            )

        if not self.backend.healthcheck():
            logger.error(
                "Translation backend unavailable",
                extra={"context": context},
            )
            return TranslationResult(
                text=text,
                source_language=source_language,
                target_language=target_language,
                translated=False,
                error_type="backend_error",
                metadata={
                    **context,
                    "reason": "backend_unavailable",
                },
            )

        # ---------------- normalization ----------------

        normalized = self._normalize_text(text)
        original_length = len(normalized)

        truncated = False
        if len(normalized) > self.max_chars:
            normalized = normalized[: self.max_chars]
            truncated = True

        # ---------------- backend call ----------------

        try:
            translated_text = self.backend.translate(
                normalized,
                source_language,
                target_language,
            )

            success = translated_text.strip() != normalized.strip()

            result = TranslationResult(
                text=translated_text,
                source_language=source_language,
                target_language=target_language,
                translated=success,
                metadata={
                    **context,
                    "backend_name": self.backend.name,
                    "model_name": getattr(self.backend, "model", None),
                    "original_length": original_length,
                    "sent_length": len(normalized),
                    "truncated": truncated,
                },
            )

            logger.info(
                "Translation completed",
                extra={
                    "context": {
                        **result.metadata,
                        "translated": success,
                    }
                },
            )

            return result

        except subprocess.SubprocessError as exc:
            logger.exception(
                "Translation subprocess failed",
                extra={"context": context},
            )
            return TranslationResult(
                text=text,
                source_language=source_language,
                target_language=target_language,
                translated=False,
                error_type="subprocess_error",
                metadata={
                    **context,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )

        except Exception as exc:
            logger.exception(
                "Translation backend error",
                extra={"context": context},
            )
            return TranslationResult(
                text=text,
                source_language=source_language,
                target_language=target_language,
                translated=False,
                error_type="backend_error",
                metadata={
                    **context,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )