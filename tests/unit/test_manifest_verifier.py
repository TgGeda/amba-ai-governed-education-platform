from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from amba_ai.governance.errors import GovernanceManifestError
from amba_ai.governance.manifest_verifier import (
    ManifestFailureCode,
    ManifestVerifier,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(root: Path, *lines: str) -> Path:
    path = root / "manifest.sha256"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_valid_manifest_and_require_valid(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("verified", encoding="utf-8")
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(
        _write_manifest(tmp_path, f"{_digest(artifact)}  artifact.txt")
    )
    assert result.valid is True
    assert result.verified_count == 1
    assert result.failures == ()
    result.require_valid()
    assert result.to_canonical_json() == result.to_canonical_json()


@pytest.mark.parametrize("body", ["", "# comments only\n"])
def test_empty_manifest_fails_closed(tmp_path: Path, body: str) -> None:
    manifest = tmp_path / "manifest.sha256"
    manifest.write_text(body, encoding="utf-8")
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(manifest)
    assert result.valid is False
    assert result.failures[0].code is ManifestFailureCode.EMPTY_MANIFEST
    with pytest.raises(GovernanceManifestError):
        result.require_valid()


@pytest.mark.parametrize("checksum", ["0" * 63, "G" * 64, "A" * 64])
def test_invalid_checksum_format(tmp_path: Path, checksum: str) -> None:
    (tmp_path / "artifact.txt").write_text("x", encoding="utf-8")
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(
        _write_manifest(tmp_path, f"{checksum}  artifact.txt")
    )
    assert result.failures[0].code is ManifestFailureCode.INVALID_ENTRY


def test_missing_and_mismatched_artifacts_fail(tmp_path: Path) -> None:
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(
        _write_manifest(tmp_path, f"{'0' * 64}  missing.txt")
    )
    assert result.failures[0].code is ManifestFailureCode.ARTIFACT_MISSING

    artifact = tmp_path / "artifact.txt"
    artifact.write_text("content", encoding="utf-8")
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(
        _write_manifest(tmp_path, f"{'0' * 64}  artifact.txt")
    )
    assert result.failures[0].code is ManifestFailureCode.CHECKSUM_MISMATCH


def test_duplicate_artifact_fails(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("content", encoding="utf-8")
    line = f"{_digest(artifact)}  artifact.txt"
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(
        _write_manifest(tmp_path, line, line)
    )
    assert result.verified_count == 1
    assert result.failures[0].code is ManifestFailureCode.DUPLICATE_ARTIFACT


@pytest.mark.parametrize("artifact_path", ["../escape.txt", "../../escape.txt"])
def test_path_traversal_fails(tmp_path: Path, artifact_path: str) -> None:
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(
        _write_manifest(tmp_path, f"{'0' * 64}  {artifact_path}")
    )
    assert result.failures[0].code is ManifestFailureCode.PATH_ESCAPE


def test_absolute_artifact_path_fails(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("content", encoding="utf-8")
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(
        _write_manifest(tmp_path, f"{_digest(artifact)}  {artifact}")
    )
    assert result.failures[0].code is ManifestFailureCode.ABSOLUTE_PATH_PROHIBITED


def test_manifest_outside_repository_fails(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.sha256"
    outside.write_text("0" * 64 + "  artifact.txt\n", encoding="utf-8")
    with pytest.raises(GovernanceManifestError, match="escapes"):
        ManifestVerifier(root).verify_checksum_manifest(outside)


def test_symlink_artifact_fails(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("content", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation is unavailable")
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(
        _write_manifest(tmp_path, f"{_digest(target)}  link.txt")
    )
    assert result.failures[0].code is ManifestFailureCode.PATH_ESCAPE or result.failures[0].code is ManifestFailureCode.SYMLINK_PROHIBITED


def test_directory_is_not_an_artifact(tmp_path: Path) -> None:
    (tmp_path / "directory").mkdir()
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(
        _write_manifest(tmp_path, f"{'0' * 64}  directory")
    )
    assert result.failures[0].code is ManifestFailureCode.ARTIFACT_NOT_REGULAR_FILE


def test_invalid_utf8_manifest_raises(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.sha256"
    manifest.write_bytes(b"\xff\xfe")
    with pytest.raises(GovernanceManifestError, match="UTF-8"):
        ManifestVerifier(tmp_path).verify_checksum_manifest(manifest)
