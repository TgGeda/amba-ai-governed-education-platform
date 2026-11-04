from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ErrorContext:
    """
    Structured diagnostic context for AmbaAI exceptions.
    """

    operation: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AmbaAIError(Exception):
    """
    Base application error for AmbaAI.

    All domain-specific exceptions inherit from this class and support a
    structured context dictionary for logging, diagnostics, and UI reporting.
    """

    def __init__(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}
        self.cause = cause

    def __str__(self) -> str:
        if self.context:
            return f"{self.message} | Context: {self.context}"
        return self.message


class ConfigError(AmbaAIError):
    """Raised when configuration or environment variables are invalid."""


class StartupError(AmbaAIError):
    """Raised when application startup fails."""


class ValidationError(AmbaAIError):
    """Raised when input, paths, or arguments fail validation."""


class SafetyError(AmbaAIError):
    """Raised when safety, privacy, or path policy validation fails."""


class PermissionDeniedError(AmbaAIError):
    """Raised when a user role lacks permission for an operation."""


class DatabaseError(AmbaAIError):
    """Raised when SQLite or persistence layer operations fail."""


class IngestionError(AmbaAIError):
    """Raised when file ingestion fails."""


class PreprocessingError(AmbaAIError):
    """Raised when text cleanup, chunking, OCR cleanup, or preprocessing fails."""


class TranscriptionError(AmbaAIError):
    """Raised when audio or video transcription fails."""


class ModelUnavailableError(AmbaAIError):
    """Raised when a local or cloud model backend is unavailable."""


class ModelInferenceError(AmbaAIError):
    """Raised when model inference fails after a model is available."""


class RAGError(AmbaAIError):
    """Raised when retrieval-augmented generation fails."""


class MemoryStoreError(AmbaAIError):
    """Raised when vector memory persistence, loading, pruning, or retrieval fails."""


class JobServiceError(AmbaAIError):
    """Raised when JobService orchestration operations fail."""


class ExportError(AmbaAIError):
    """Raised when exporting notes, cards, study packs, analytics, or documents fails."""


class TranslationError(AmbaAIError):
    """Raised when translation fails."""


class VoiceServiceError(AmbaAIError):
    """Raised when voice capture, wake-word detection, or transcription fails."""


class MCPError(AmbaAIError):
    """Raised when MCP tool registration, routing, or execution fails."""


class SyncError(AmbaAIError):
    """Raised when offline/online synchronization fails."""


class FeedbackError(AmbaAIError):
    """Raised when RLHF recording, alignment scoring, or feedback storage fails."""


class UserFacingError(AmbaAIError):
    """
    Raised for errors that are safe to show directly in the UI.
    """


__all__ = [
    "AmbaAIError",
    "ConfigError",
    "DatabaseError",
    "ErrorContext",
    "ExportError",
    "FeedbackError",
    "IngestionError",
    "JobServiceError",
    "MCPError",
    "MemoryStoreError",
    "ModelInferenceError",
    "ModelUnavailableError",
    "PermissionDeniedError",
    "PreprocessingError",
    "RAGError",
    "SafetyError",
    "StartupError",
    "SyncError",
    "TranscriptionError",
    "TranslationError",
    "UserFacingError",
    "ValidationError",
    "VoiceServiceError",
]