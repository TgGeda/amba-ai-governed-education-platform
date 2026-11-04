from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import os
from pathlib import Path
import re
from typing import Any

from amba_ai.governance.errors import GovernanceManifestError
from amba_ai.governance.models import to_canonical_json


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
READ_BLOCK_SIZE = 1024 * 1024


class ManifestFailureCode(str, Enum):
    INVALID_ENTRY = "INVALID_ENTRY"
    DUPLICATE_ARTIFACT = "DUPLICATE_ARTIFACT"
    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    ARTIFACT_NOT_REGULAR_FILE = "ARTIFACT_NOT_REGULAR_FILE"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    PATH_ESCAPE = "PATH_ESCAPE"
    ABSOLUTE_PATH_PROHIBITED = "ABSOLUTE_PATH_PROHIBITED"
    SYMLINK_PROHIBITED = "SYMLINK_PROHIBITED"
    ARTIFACT_CHANGED = "ARTIFACT_CHANGED"
    FILE_READ_FAILED = "FILE_READ_FAILED"
    EMPTY_MANIFEST = "EMPTY_MANIFEST"


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(field_name, str):
        raise TypeError("field_name must be a string")

    normalized_field_name = field_name.strip()
    if not normalized_field_name:
        raise ValueError("field_name must not be empty")

    if not isinstance(value, str):
        raise TypeError(f"{normalized_field_name} must be a string")

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{normalized_field_name} must not be empty")

    return normalized_value


@dataclass(frozen=True, slots=True)
class ManifestFailure:
    line_number: int | None
    artifact_path: str | None
    code: ManifestFailureCode
    message: str

    def __post_init__(self) -> None:
        if self.line_number is not None:
            if (
                isinstance(self.line_number, bool)
                or not isinstance(self.line_number, int)
            ):
                raise TypeError("line_number must be an integer or None")
            if self.line_number < 1:
                raise ValueError("line_number must be strictly positive")

        artifact_path = self.artifact_path
        if artifact_path is not None:
            artifact_path = _require_text(artifact_path, "artifact_path")

        if not isinstance(self.code, ManifestFailureCode):
            raise TypeError("code must be a ManifestFailureCode")

        message = _require_text(self.message, "message")

        object.__setattr__(self, "artifact_path", artifact_path)
        object.__setattr__(self, "message", message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_number": self.line_number,
            "artifact_path": self.artifact_path,
            "code": self.code.value,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ManifestVerificationResult:
    valid: bool
    verified_count: int
    failures: tuple[ManifestFailure, ...]

    def __post_init__(self) -> None:
        if type(self.valid) is not bool:
            raise TypeError("valid must be a strict Boolean")
        if (
            isinstance(self.verified_count, bool)
            or not isinstance(self.verified_count, int)
        ):
            raise TypeError("verified_count must be an integer")
        if self.verified_count < 0:
            raise ValueError("verified_count cannot be negative")
        if not isinstance(self.failures, tuple):
            raise TypeError("failures must be a tuple")
        if any(not isinstance(failure, ManifestFailure) for failure in self.failures):
            raise TypeError("failures must contain only ManifestFailure values")
        if self.valid and self.failures:
            raise ValueError("A valid manifest result cannot contain failures")
        if self.valid and self.verified_count == 0:
            raise ValueError(
                "A valid manifest result requires at least one verified artifact"
            )
        if not self.valid and not self.failures:
            raise ValueError(
                "An invalid manifest result requires at least one failure"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "verified_count": self.verified_count,
            "failures": [failure.to_dict() for failure in self.failures],
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())

    def require_valid(self) -> None:
        if self.valid:
            return
        failure_codes = ", ".join(
            failure.code.value for failure in self.failures
        )
        raise GovernanceManifestError(
            f"Manifest verification failed: {failure_codes}"
        )


class ManifestVerifier:
    def __init__(self, repository_root: Path | str) -> None:
        root = Path(repository_root)
        if not root.exists():
            raise GovernanceManifestError("Repository root does not exist")
        if root.is_symlink():
            raise GovernanceManifestError(
                "Repository root must not be a symlink"
            )
        if not root.is_dir():
            raise GovernanceManifestError(
                "Repository root must be a directory"
            )
        self._repository_root = root.resolve(strict=True)

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    def verify_checksum_manifest(
        self,
        manifest_path: Path | str,
    ) -> ManifestVerificationResult:
        manifest = self._resolve_manifest_path(manifest_path)
        if not manifest.exists():
            raise GovernanceManifestError("Checksum manifest does not exist")
        if not manifest.is_file():
            raise GovernanceManifestError(
                "Checksum manifest must be a regular file"
            )

        try:
            manifest_text = manifest.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise GovernanceManifestError(
                "Checksum manifest could not be read as UTF-8"
            ) from error

        failures: list[ManifestFailure] = []
        verified_count = 0
        entry_count = 0
        seen_paths: set[str] = set()

        for line_number, raw_line in enumerate(
            manifest_text.splitlines(),
            start=1,
        ):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            entry_count += 1
            parsed = self._parse_entry(line=line, line_number=line_number)
            if isinstance(parsed, ManifestFailure):
                failures.append(parsed)
                continue

            expected_checksum, artifact_text = parsed
            try:
                artifact = self._resolve_repository_path(
                    artifact_text,
                    field_name="artifact_path",
                )
            except GovernanceManifestError as error:
                failures.append(
                    ManifestFailure(
                        line_number=line_number,
                        artifact_path=artifact_text,
                        code=ManifestFailureCode.PATH_ESCAPE,
                        message=str(error),
                    )
                )
                continue

            normalized_artifact = artifact.relative_to(
                self.repository_root
            ).as_posix()
            artifact_identity = os.path.normcase(str(artifact))

            if artifact_identity in seen_paths:
                failures.append(
                    ManifestFailure(
                        line_number=line_number,
                        artifact_path=normalized_artifact,
                        code=ManifestFailureCode.DUPLICATE_ARTIFACT,
                        message="Artifact appears more than once in the manifest",
                    )
                )
                continue
            seen_paths.add(artifact_identity)

            if not artifact.exists():
                failures.append(
                    ManifestFailure(
                        line_number=line_number,
                        artifact_path=normalized_artifact,
                        code=ManifestFailureCode.ARTIFACT_MISSING,
                        message="Artifact does not exist",
                    )
                )
                continue
            if not artifact.is_file():
                failures.append(
                    ManifestFailure(
                        line_number=line_number,
                        artifact_path=normalized_artifact,
                        code=ManifestFailureCode.ARTIFACT_NOT_REGULAR_FILE,
                        message="Artifact must be a regular file",
                    )
                )
                continue

            try:
                actual_checksum = self._sha256_stable_file(artifact)
            except GovernanceManifestError as error:
                message = str(error)
                code = (
                    ManifestFailureCode.ARTIFACT_CHANGED
                    if "changed while being hashed" in message
                    else ManifestFailureCode.FILE_READ_FAILED
                )
                failures.append(
                    ManifestFailure(
                        line_number=line_number,
                        artifact_path=normalized_artifact,
                        code=code,
                        message=message,
                    )
                )
                continue

            if actual_checksum != expected_checksum:
                failures.append(
                    ManifestFailure(
                        line_number=line_number,
                        artifact_path=normalized_artifact,
                        code=ManifestFailureCode.CHECKSUM_MISMATCH,
                        message="Artifact checksum does not match the manifest",
                    )
                )
                continue

            verified_count += 1

        if entry_count == 0:
            failures.append(
                ManifestFailure(
                    line_number=None,
                    artifact_path=None,
                    code=ManifestFailureCode.EMPTY_MANIFEST,
                    message="Checksum manifest contains no artifact entries",
                )
            )

        return ManifestVerificationResult(
            valid=not failures,
            verified_count=verified_count,
            failures=tuple(failures),
        )

    def _resolve_manifest_path(self, manifest_path: Path | str) -> Path:
        if not isinstance(manifest_path, (str, Path)):
            raise TypeError("manifest_path must be a path")

        raw_text = str(manifest_path).strip()
        if not raw_text:
            raise ValueError("manifest_path must not be empty")
        if "\x00" in raw_text:
            raise GovernanceManifestError("manifest_path contains a null byte")

        supplied_path = Path(raw_text)
        unresolved_candidate = (
            supplied_path
            if supplied_path.is_absolute()
            else self.repository_root / supplied_path
        )
        self._reject_symlink_path(unresolved_candidate)
        candidate = unresolved_candidate.resolve(strict=False)
        self._require_within_repository(candidate, "manifest_path")
        return candidate

    def _resolve_repository_path(
        self,
        path_value: Path | str,
        *,
        field_name: str,
    ) -> Path:
        if not isinstance(path_value, (str, Path)):
            raise TypeError(f"{field_name} must be a path")

        raw_text = str(path_value).strip()
        if not raw_text:
            raise ValueError(f"{field_name} must not be empty")
        if "\x00" in raw_text:
            raise GovernanceManifestError(
                f"{field_name} contains a null byte"
            )

        candidate_input = Path(raw_text)
        if candidate_input.is_absolute():
            raise GovernanceManifestError(
                f"{field_name} must be relative to the repository root"
            )

        unresolved_candidate = self.repository_root / candidate_input
        self._require_within_repository(unresolved_candidate, field_name)
        self._reject_symlink_path(unresolved_candidate)
        candidate = unresolved_candidate.resolve(strict=False)
        self._require_within_repository(candidate, field_name)
        return candidate

    def _require_within_repository(
        self,
        candidate: Path,
        field_name: str,
    ) -> None:
        try:
            candidate.relative_to(self.repository_root)
        except ValueError as error:
            raise GovernanceManifestError(
                f"{field_name} escapes the repository root"
            ) from error

    def _reject_symlink_path(self, candidate: Path) -> None:
        self._require_within_repository(candidate, "path")
        relative = candidate.relative_to(self.repository_root)
        current = self.repository_root
        for component in relative.parts:
            current = current / component
            if current.is_symlink():
                raise GovernanceManifestError("Symlink paths are prohibited")

    @staticmethod
    def _parse_entry(
        *,
        line: str,
        line_number: int,
    ) -> tuple[str, str] | ManifestFailure:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            return ManifestFailure(
                line_number=line_number,
                artifact_path=None,
                code=ManifestFailureCode.INVALID_ENTRY,
                message=(
                    "Manifest entry must contain a checksum and artifact path"
                ),
            )

        expected_checksum, artifact_text = parts
        if not SHA256_PATTERN.fullmatch(expected_checksum):
            return ManifestFailure(
                line_number=line_number,
                artifact_path=artifact_text.strip() or None,
                code=ManifestFailureCode.INVALID_ENTRY,
                message=(
                    "Manifest checksum must be exactly 64 lowercase "
                    "hexadecimal characters"
                ),
            )

        artifact_text = artifact_text.lstrip()
        if artifact_text.startswith("*"):
            artifact_text = artifact_text[1:]
        artifact_text = artifact_text.strip()
        if not artifact_text:
            return ManifestFailure(
                line_number=line_number,
                artifact_path=None,
                code=ManifestFailureCode.INVALID_ENTRY,
                message="Manifest artifact path must not be empty",
            )

        if Path(artifact_text).is_absolute():
            return ManifestFailure(
                line_number=line_number,
                artifact_path=artifact_text,
                code=ManifestFailureCode.ABSOLUTE_PATH_PROHIBITED,
                message="Absolute artifact paths are prohibited",
            )

        return expected_checksum, artifact_text

    @staticmethod
    def _sha256_stable_file(path: Path) -> str:
        try:
            before = path.stat()
        except OSError as error:
            raise GovernanceManifestError(
                "Artifact metadata could not be read"
            ) from error

        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for block in iter(
                    lambda: stream.read(READ_BLOCK_SIZE),
                    b"",
                ):
                    digest.update(block)
        except OSError as error:
            raise GovernanceManifestError("Artifact could not be read") from error

        try:
            after = path.stat()
        except OSError as error:
            raise GovernanceManifestError(
                "Artifact metadata could not be read after hashing"
            ) from error

        before_identity = (
            before.st_size,
            before.st_mtime_ns,
            getattr(before, "st_ino", None),
            getattr(before, "st_dev", None),
        )
        after_identity = (
            after.st_size,
            after.st_mtime_ns,
            getattr(after, "st_ino", None),
            getattr(after, "st_dev", None),
        )
        if before_identity != after_identity:
            raise GovernanceManifestError("Artifact changed while being hashed")

        return digest.hexdigest()
