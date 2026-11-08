from __future__ import annotations

import hashlib
from pathlib import Path

from amba_ai.governance.verified_pdpa_source_evidence import (
    ARTIFACT_SHA256,
    verified_pdpa_source_evidence,
)
from amba_ai.rag.policy_pdf_extractor import PolicyPdfExtractor

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = (
    REPOSITORY_ROOT
    / "kb"
    / "sources"
    / "ethiopia"
    / "ETH_PDPA_1321_2024.pdf"
)


def test_verified_pdpa_artifact_extracts_without_creating_legal_authority() -> None:
    data = SOURCE_PATH.read_bytes()
    assert data[:5] == b"%PDF-"
    assert hashlib.sha256(data).hexdigest() == ARTIFACT_SHA256
    pages = PolicyPdfExtractor().extract_pages(
        SOURCE_PATH,
        remove_repeated_marginal_lines=False,
    )
    assert pages
    assert all(page.page_number >= 1 for page in pages)
    evidence = verified_pdpa_source_evidence()
    assert evidence.physical_page_association_preserved is True
    assert evidence.cross_language_merge_permitted is False
    assert evidence.translation_equivalence_claimed is False
    assert evidence.eligible_for_binding_legal_findings is False
    assert evidence.eligible_for_citation is False
    assert evidence.binding_finding_activation_ready is False
