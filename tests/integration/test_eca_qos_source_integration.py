from __future__ import annotations

import hashlib
from pathlib import Path

from amba_ai.governance.verified_eca_qos_source_evidence import (
    ARTIFACT_SHA256,
    verified_eca_qos_source_evidence,
)
from amba_ai.rag.policy_pdf_extractor import PolicyPdfExtractor

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = (
    REPOSITORY_ROOT
    / "kb"
    / "sources"
    / "ethiopia"
    / "ETH_ECA_QOS_794_2021.pdf"
)


def test_verified_eca_qos_artifact_extracts_without_inventing_thresholds() -> None:
    data = SOURCE_PATH.read_bytes()
    assert data[:5] == b"%PDF-"
    assert hashlib.sha256(data).hexdigest() == ARTIFACT_SHA256
    pages = PolicyPdfExtractor().extract_pages(
        SOURCE_PATH,
        remove_repeated_marginal_lines=False,
    )
    assert pages
    assert all(page.page_number >= 1 for page in pages)
    evidence = verified_eca_qos_source_evidence()
    assert evidence.exact_clause_verified is False
    assert evidence.exact_table_verified is False
    assert evidence.threshold_activation_ready is False
    assert evidence.eligible_for_binding_technical_findings is False
    assert evidence.eligible_for_citation is False
