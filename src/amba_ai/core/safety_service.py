from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

from amba_ai.exceptions import SafetyError
from amba_ai.logger import logger


SafetyErrorType = Literal[
    "validation_error",
    "file_io_error",
    "path_resolution_error",
    "extension_disallowed",
    "extension_unsupported",
    "file_too_large",
    "not_found",
    "not_file",
    "not_directory",
    "permission_error",
    "regex_match",
    "path_escape",
    "symlink_disallowed",
    "normalization",
    "safe_filename",
    "prompt_injection",
    "pii_redaction",
]


TruncationStrategy = Literal["hard_cut", "ellipsis"]


@dataclass(frozen=True)
class SafetyDecision:
    """
    Structured safety result.

    Attributes:
        allowed: Whether the operation is allowed.
        reason: Human-readable explanation.
        error_type: Machine-readable error/category.
        metadata: Structured diagnostic information.
        value: Optional transformed output, such as redacted text, normalized
            prompt, safe filename, or resolved path.
    """

    allowed: bool
    reason: str = ""
    error_type: SafetyErrorType | str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    value: Any = None


class SafetyService:
    """
    Local safety and privacy guardrail service for AmbaAI.

    Responsibilities:
    - Validate local upload files and directories.
    - Enforce allowed/disallowed extensions.
    - Prevent path traversal outside trusted roots.
    - Normalize prompts for safe LLM routing.
    - Redact common sensitive data before persistence.
    - Generate safe filenames for exports.
    - Detect prompt-injection-like instructions.
    """

    DEFAULT_ALLOWED_EXTENSIONS = {
        ".pdf",
        ".docx",
        ".pptx",
        ".ppt",
        ".mp3",
        ".wav",
        ".m4a",
        ".mp4",
        ".mov",
        ".mkv",
        ".webm",
        ".txt",
        ".md",
        ".markdown",
    }

    DEFAULT_DISALLOWED_EXTENSIONS = {
        ".exe",
        ".bat",
        ".cmd",
        ".com",
        ".scr",
        ".msi",
        ".dll",
        ".so",
        ".dylib",
        ".sh",
        ".ps1",
        ".vbs",
        ".js",
        ".jar",
        ".app",
        ".deb",
        ".rpm",
    }

    DEFAULT_MAX_FILE_BYTES = 500 * 1024 * 1024
    DEFAULT_MAX_FILENAME_CHARS = 180

    WINDOWS_RESERVED_NAMES = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }

    PROMPT_INJECTION_PATTERNS = [
        r"ignore\s+previous\s+instructions",
        r"ignore\s+all\s+instructions",
        r"reveal\s+the\s+system\s+prompt",
        r"show\s+hidden\s+instructions",
        r"print\s+the\s+hidden\s+prompt",
        r"developer\s*:",
        r"system\s*:",
        r"assistant\s*:",
        r"jailbreak",
        r"you\s+are\s+now",
    ]

    _EMAIL_RE = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    )

    _PHONE_RE = re.compile(
        r"\b(?:\+?\d{1,3}[-.\s]?)?"
        r"(?:\(?\d{2,4}\)?[-.\s]?)?"
        r"\d{3,4}[-.\s]?\d{3,4}\b"
    )

    _CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
    _SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    _IBAN_RE = re.compile(
        r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",
        flags=re.IGNORECASE,
    )

    _API_KEY_RE = re.compile(
        r"(?i)\b("
        r"api[_-]?key|secret|access[_-]?token|refresh[_-]?token|"
        r"bearer|authorization|private[_-]?key"
        r")\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{16,}['\"]?"
    )

    _JWT_RE = re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    )

    _CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

    def __init__(
        self,
        allowed_extensions: Iterable[str] | None = None,
        disallowed_extensions: Iterable[str] | None = None,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        *,
        enable_pii_redaction: bool = True,
        enable_prompt_injection_filter: bool = True,
    ) -> None:
        self.allowed_extensions = self._normalize_extensions(
            allowed_extensions or self.DEFAULT_ALLOWED_EXTENSIONS
        )
        self.disallowed_extensions = self._normalize_extensions(
            disallowed_extensions or self.DEFAULT_DISALLOWED_EXTENSIONS
        )

        if max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be greater than zero.")

        self.max_file_bytes = int(max_file_bytes)
        self.enable_pii_redaction = enable_pii_redaction
        self.enable_prompt_injection_filter = enable_prompt_injection_filter

        self._prompt_injection_re = re.compile(
            "|".join(self.PROMPT_INJECTION_PATTERNS),
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _normalize_extensions(values: Iterable[str]) -> set[str]:
        normalized: set[str] = set()

        for value in values:
            text = str(value or "").strip().lower()
            if not text:
                continue

            if not text.startswith("."):
                text = f".{text}"

            normalized.add(text)

        return normalized

    def _context(
        self,
        *,
        operation: str,
        path: str | Path | None = None,
        extension: str | None = None,
        size: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "operation": operation,
            "max_file_bytes": self.max_file_bytes,
        }

        if path is not None:
            context["path"] = str(path)

        if extension is not None:
            context["extension"] = extension

        if size is not None:
            context["size"] = size

        context.update(extra)
        return context

    @staticmethod
    def _decision(
        *,
        allowed: bool,
        reason: str = "",
        error_type: SafetyErrorType | str | None = None,
        metadata: dict[str, Any] | None = None,
        value: Any = None,
    ) -> SafetyDecision:
        return SafetyDecision(
            allowed=allowed,
            reason=reason,
            error_type=error_type,
            metadata=metadata or {},
            value=value,
        )

    def _raise_if_needed(
        self,
        decision: SafetyDecision,
        *,
        raise_on_error: bool,
    ) -> SafetyDecision:
        if decision.allowed or not raise_on_error:
            return decision

        context = {
            **decision.metadata,
            "error_type": decision.error_type,
            "allowed": decision.allowed,
        }

        try:
            raise SafetyError(
                decision.reason or "Safety validation failed.",
                context=context,
            )
        except TypeError as exc:
            message = f"{decision.reason or 'Safety validation failed.'} | context={context}"
            raise SafetyError(message) from exc

    def validate_file(
        self,
        file_path: str | Path,
        *,
        raise_on_error: bool = True,
    ) -> SafetyDecision:
        """
        Validate file existence, type, extension, and size.
        """
        context = self._context(operation="validate_file", path=file_path)
        logger.info("File validation started", extra={"context": context})

        if not file_path or not str(file_path).strip():
            decision = self._decision(
                allowed=False,
                reason="File path is empty.",
                error_type="validation_error",
                metadata=context,
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        path = Path(file_path).expanduser()

        try:
            full_path = path.resolve(strict=False)
        except OSError as exc:
            decision = self._decision(
                allowed=False,
                reason="File path cannot be resolved.",
                error_type="path_resolution_error",
                metadata={**context, "error": str(exc)},
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        extension = full_path.suffix.lower()
        file_context = self._context(
            operation="validate_file",
            path=full_path,
            extension=extension,
        )

        if extension in self.disallowed_extensions:
            decision = self._decision(
                allowed=False,
                reason=f"Disallowed file type: {extension}",
                error_type="extension_disallowed",
                metadata=file_context,
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        if extension not in self.allowed_extensions:
            decision = self._decision(
                allowed=False,
                reason=f"Unsupported file type: {extension}",
                error_type="extension_unsupported",
                metadata=file_context,
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        if not full_path.exists():
            decision = self._decision(
                allowed=False,
                reason="File does not exist.",
                error_type="not_found",
                metadata=file_context,
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        if not full_path.is_file():
            decision = self._decision(
                allowed=False,
                reason="Path is not a file.",
                error_type="not_file",
                metadata=file_context,
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        try:
            size = full_path.stat().st_size
        except OSError as exc:
            decision = self._decision(
                allowed=False,
                reason="Cannot read file metadata.",
                error_type="file_io_error",
                metadata={**file_context, "error": str(exc)},
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        final_context = {
            **file_context,
            "size": size,
            "max_file_bytes": self.max_file_bytes,
        }

        if size > self.max_file_bytes:
            decision = self._decision(
                allowed=False,
                reason="File exceeds maximum allowed size.",
                error_type="file_too_large",
                metadata=final_context,
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        decision = self._decision(
            allowed=True,
            reason="File is safe.",
            metadata=final_context,
            value=full_path,
        )

        logger.info("File validation completed", extra={"context": final_context})
        return decision

    def validate_upload_path(
        self,
        path: str | Path,
        *,
        raise_on_error: bool = True,
    ) -> SafetyDecision:
        """
        Backward-compatible alias for validate_file.
        """
        return self.validate_file(path, raise_on_error=raise_on_error)

    def validate_directory(
        self,
        directory_path: str | Path,
        *,
        require_writable: bool = False,
        raise_on_error: bool = False,
    ) -> SafetyDecision:
        context = self._context(
            operation="validate_directory",
            path=directory_path,
            require_writable=require_writable,
        )

        logger.info("Directory validation started", extra={"context": context})

        if not directory_path or not str(directory_path).strip():
            decision = self._decision(
                allowed=False,
                reason="Directory path is empty.",
                error_type="validation_error",
                metadata=context,
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        path = Path(directory_path).expanduser()

        try:
            full_path = path.resolve(strict=False)
        except OSError as exc:
            decision = self._decision(
                allowed=False,
                reason="Directory path cannot be resolved.",
                error_type="path_resolution_error",
                metadata={**context, "error": str(exc)},
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        dir_context = {
            **context,
            "path": str(full_path),
        }

        if not full_path.exists():
            decision = self._decision(
                allowed=False,
                reason="Directory does not exist.",
                error_type="not_found",
                metadata=dir_context,
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        if not full_path.is_dir():
            decision = self._decision(
                allowed=False,
                reason="Path is not a directory.",
                error_type="not_directory",
                metadata=dir_context,
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        if not os.access(full_path, os.R_OK):
            decision = self._decision(
                allowed=False,
                reason="Directory is not readable.",
                error_type="permission_error",
                metadata={**dir_context, "permission": "read"},
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        if require_writable and not os.access(full_path, os.W_OK):
            decision = self._decision(
                allowed=False,
                reason="Directory is not writable.",
                error_type="permission_error",
                metadata={**dir_context, "permission": "write"},
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        decision = self._decision(
            allowed=True,
            reason="Directory is safe.",
            metadata=dir_context,
            value=full_path,
        )

        logger.info("Directory validation completed", extra={"context": dir_context})
        return decision

    def redact_sensitive_text(self, text: str) -> SafetyDecision:
        """
        Redact common sensitive data patterns from text.
        """
        if not text:
            return self._decision(
                allowed=True,
                reason="No text provided.",
                metadata={
                    "operation": "redact_sensitive_text",
                    "original_length": 0,
                    "redacted_length": 0,
                    "matches": {},
                    "total_matches": 0,
                },
                value="",
            )

        result = str(text)
        match_counts: dict[str, int] = {}

        replacements: list[tuple[str, re.Pattern[str], str]] = [
            ("email", self._EMAIL_RE, "[REDACTED_EMAIL]"),
            ("phone", self._PHONE_RE, "[REDACTED_PHONE]"),
            ("card", self._CARD_RE, "[REDACTED_CARD]"),
            ("ssn", self._SSN_RE, "[REDACTED_SSN]"),
            ("iban", self._IBAN_RE, "[REDACTED_IBAN]"),
            ("api_key", self._API_KEY_RE, "[REDACTED_TOKEN]"),
            ("jwt", self._JWT_RE, "[REDACTED_TOKEN]"),
        ]

        for label, pattern, replacement in replacements:
            result, count = pattern.subn(replacement, result)
            match_counts[label] = count

        total_matches = sum(match_counts.values())

        metadata = {
            "operation": "redact_sensitive_text",
            "original_length": len(str(text)),
            "redacted_length": len(result),
            "matches": match_counts,
            "total_matches": total_matches,
        }

        if total_matches:
            logger.info("Sensitive text redacted", extra={"context": metadata})
        else:
            logger.info("No sensitive text detected", extra={"context": metadata})

        return self._decision(
            allowed=True,
            reason="Sensitive text redaction completed.",
            error_type="pii_redaction" if total_matches else None,
            metadata=metadata,
            value=result,
        )

    def normalize_prompt(
        self,
        prompt: str,
        *,
        max_chars: int = 20_000,
        truncation_strategy: TruncationStrategy = "hard_cut",
    ) -> SafetyDecision:
        """
        Normalize prompt text for safe LLM routing.
        """
        if max_chars <= 0:
            raise ValueError("max_chars must be greater than zero.")

        if truncation_strategy not in {"hard_cut", "ellipsis"}:
            raise ValueError("truncation_strategy must be 'hard_cut' or 'ellipsis'.")

        original = "" if prompt is None else str(prompt)
        normalized = original.replace("\r\n", "\n").replace("\r", "\n")
        normalized = self._CONTROL_CHARS_RE.sub("", normalized)
        normalized = normalized.strip()

        flags: list[str] = []

        if self.enable_prompt_injection_filter and self._prompt_injection_re.search(normalized):
            normalized = self._prompt_injection_re.sub(
                "[filtered-instruction-like-text]",
                normalized,
            )
            flags.append("prompt_injection_like_text")

        if self.enable_pii_redaction:
            redacted = self.redact_sensitive_text(normalized)
            normalized = str(redacted.value)
            if redacted.metadata.get("total_matches", 0):
                flags.append("pii_redacted")

        was_truncated = len(normalized) > max_chars

        if was_truncated:
            if truncation_strategy == "ellipsis" and max_chars > 3:
                normalized = normalized[: max_chars - 3].rstrip() + "..."
            else:
                normalized = normalized[:max_chars]
            flags.append("truncated")

        metadata = {
            "operation": "normalize_prompt",
            "original_length": len(original),
            "normalized_length": len(normalized),
            "truncated": was_truncated,
            "truncated_length": len(normalized) if was_truncated else 0,
            "max_chars": max_chars,
            "truncation_strategy": truncation_strategy,
            "flags": flags,
        }

        logger.info("Prompt normalized", extra={"context": metadata})

        return self._decision(
            allowed=True,
            reason="Prompt normalized.",
            error_type="normalization",
            metadata=metadata,
            value=normalized,
        )

    def sanitize_prompt(
        self,
        prompt: str,
        *,
        max_chars: int = 20_000,
    ) -> SafetyDecision:
        """
        Backward-compatible prompt sanitizer.
        """
        return self.normalize_prompt(prompt, max_chars=max_chars)

    def validate_prompt(
        self,
        prompt: str,
        *,
        max_chars: int = 20_000,
    ) -> SafetyDecision:
        """
        Backward-compatible alias for sanitize_prompt.
        """
        return self.sanitize_prompt(prompt, max_chars=max_chars)

    def check_text(self, text: str) -> SafetyDecision:
        """
        General text safety check.
        """
        return self.sanitize_prompt(text)

    def sanitize_text(self, text: str) -> str:
        """
        Return sanitized text directly.
        """
        return str(self.sanitize_prompt(text).value)

    def is_safe(self, text: str) -> bool:
        """
        Return True if text can be sanitized and is allowed.
        """
        return self.sanitize_prompt(text).allowed

    def safe_filename(
        self,
        value: str,
        *,
        fallback: str = "export",
        max_chars: int = DEFAULT_MAX_FILENAME_CHARS,
    ) -> SafetyDecision:
        if max_chars <= 0 or max_chars > self.DEFAULT_MAX_FILENAME_CHARS:
            raise ValueError(
                f"max_chars must be between 1 and {self.DEFAULT_MAX_FILENAME_CHARS}."
            )

        original = "" if value is None else str(value).strip()
        fallback_value = fallback.strip() if fallback and fallback.strip() else "export"

        name = re.sub(r"[^\w.\- ]+", "_", original, flags=re.UNICODE)
        name = re.sub(r"\s+", " ", name).strip(" ._")

        if not name:
            name = fallback_value

        path_name = Path(name)
        stem = path_name.stem.upper()
        suffix = path_name.suffix

        if stem in self.WINDOWS_RESERVED_NAMES:
            name = f"{path_name.stem}_file{suffix}"

        if len(name) > max_chars:
            if suffix and len(suffix) < max_chars:
                stem_limit = max_chars - len(suffix)
                name = f"{Path(name).stem[:stem_limit]}{suffix}"
            else:
                name = name[:max_chars]

        name = name.strip(" ._") or fallback_value

        metadata = {
            "operation": "safe_filename",
            "original": original,
            "safe_filename": name,
            "max_chars": max_chars,
            "changed": original != name,
        }

        logger.info("Safe filename generated", extra={"context": metadata})

        return self._decision(
            allowed=True,
            reason="Safe filename generated.",
            error_type="safe_filename",
            metadata=metadata,
            value=name,
        )

    def ensure_child_path(
        self,
        root: str | Path,
        candidate: str | Path,
        *,
        allow_symlinks: bool = False,
        raise_on_error: bool = False,
    ) -> SafetyDecision:
        context = self._context(
            operation="ensure_child_path",
            path=candidate,
            root=str(root),
            allow_symlinks=allow_symlinks,
        )

        logger.info("Path safety check started", extra={"context": context})

        try:
            root_path = Path(root).expanduser().resolve(strict=False)
            candidate_path = Path(candidate).expanduser().resolve(strict=False)
        except OSError as exc:
            decision = self._decision(
                allowed=False,
                reason="Path cannot be resolved.",
                error_type="path_resolution_error",
                metadata={**context, "error": str(exc)},
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        path_context = {
            **context,
            "root_path": str(root_path),
            "candidate_path": str(candidate_path),
        }

        if not allow_symlinks:
            raw_candidate = Path(candidate).expanduser()
            try:
                if raw_candidate.is_symlink():
                    decision = self._decision(
                        allowed=False,
                        reason="Symlink paths are not allowed.",
                        error_type="symlink_disallowed",
                        metadata=path_context,
                    )
                    return self._raise_if_needed(
                        decision,
                        raise_on_error=raise_on_error,
                    )
            except OSError as exc:
                decision = self._decision(
                    allowed=False,
                    reason="Could not inspect symlink status.",
                    error_type="file_io_error",
                    metadata={**path_context, "error": str(exc)},
                )
                return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        try:
            candidate_path.relative_to(root_path)
        except ValueError:
            decision = self._decision(
                allowed=False,
                reason="Path escapes allowed root.",
                error_type="path_escape",
                metadata=path_context,
            )
            return self._raise_if_needed(decision, raise_on_error=raise_on_error)

        decision = self._decision(
            allowed=True,
            reason="Path is inside allowed root.",
            metadata=path_context,
            value=candidate_path,
        )

        logger.info("Path safety check completed", extra={"context": path_context})
        return decision