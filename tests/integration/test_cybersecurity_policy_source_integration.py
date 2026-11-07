from __future__ import annotations

import hashlib
from pathlib import Path

from amba_ai.governance.verified_cybersecurity_policy_records import (
    ARTIFACT_SHA256,
    quarantined_cybersecurity_policy_candidates,
)
from amba_ai.rag.policy_pdf_extractor import PolicyPdfExtractor

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = (
    REPOSITORY_ROOT
    / "kb"
    / "sources"
    / "ethiopia"
    / "ETH_NATIONAL_CYBERSECURITY_POLICY_2024.pdf"
)


def test_verified_source_artifact_extracts_but_does_not_promote_candidates() -> None:
    data = SOURCE_PATH.read_bytes()
    assert data[:5] == b"%PDF-"
    assert hashlib.sha256(data).hexdigest() == ARTIFACT_SHA256
    pages = PolicyPdfExtractor().extract_pages(
        SOURCE_PATH,
        remove_repeated_marginal_lines=False,
    )
    assert pages
    assert all(page.page_number >= 1 for page in pages)
    for record in quarantined_cybersecurity_policy_candidates():
        assert record.official_locator is None
        assert record.eligible_for_citation is False
        assert record.eligible_for_binding_legal_findings is False
        assert record.human_review_required is True
