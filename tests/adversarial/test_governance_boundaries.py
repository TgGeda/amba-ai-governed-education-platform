from __future__ import annotations

import hashlib
from pathlib import Path
import pytest

from amba_ai.governance.distribution import DistributionBlockExecutor, ReviewQueueExecutor
from amba_ai.governance.errors import GovernanceManifestError
from amba_ai.governance.manifest_verifier import ManifestVerifier


def test_path_traversal_cannot_escape_repository(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.sha256"
    manifest.write_text(f"{'0' * 64}  ../outside.txt\n", encoding="utf-8")
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(manifest)
    assert result.valid is False
    with pytest.raises(GovernanceManifestError):
        result.require_valid()


def test_symlink_cannot_be_used_as_verified_evidence(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("content", encoding="utf-8")
    link = tmp_path / "evidence.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.sha256"
    manifest.write_text(f"{digest}  evidence.txt\n", encoding="utf-8")
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(manifest)
    assert result.valid is False


def test_wrong_checksum_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "artifact.txt").write_text("content", encoding="utf-8")
    manifest = tmp_path / "manifest.sha256"
    manifest.write_text(f"{'0' * 64}  artifact.txt\n", encoding="utf-8")
    result = ManifestVerifier(tmp_path).verify_checksum_manifest(manifest)
    assert result.valid is False
    with pytest.raises(GovernanceManifestError):
        result.require_valid()


def test_prevention_and_review_never_claim_delivery() -> None:
    blocked = DistributionBlockExecutor().execute("destination", {"sensitive": "value"})
    queued = ReviewQueueExecutor().execute("review", {"sensitive": "value"})
    assert blocked.delivered is False
    assert queued.delivered is False
    assert blocked.details["distribution_prevented"] is True
    assert queued.details["queued_for_review"] is True


def test_kb_mappings_forbid_binding_claims_from_guidance() -> None:
    mapping = Path("kb/mappings/policy_rule_mapping.yaml")
    if not mapping.is_file():
        pytest.skip("Competition KB mapping not installed")
    text = mapping.read_text(encoding="utf-8").lower()
    assert "guidance_cannot_be_presented_as_ethiopian_binding_law: true" in text
    assert "quarantined_sources_cannot_support_binding_findings: true" in text
    assert "fabricated_citations_fail: true" in text
