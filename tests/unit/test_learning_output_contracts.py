from __future__ import annotations
import pytest
from amba_ai.governance.learning_output_contracts import local_document_citation, local_chunk_citation, normalize_learning_result_metadata
from amba_ai.governance.models import GovernanceConfigurationError

def test_summary_contract_upgrades_legacy_citation():
    metadata = normalize_learning_result_metadata({"output_type":"summary_result","document_id":1,"markdown_length":50,"citations":[{"document_id":1,"source_name":"Doc","source_type":"local_document"}],"source_document_ids":[1],"fallback":False})
    assert metadata["citations"][0]["source_id"] == "local-document:1"
    assert metadata["citations"][0]["locator"] == "document:1"

def test_notes_contract():
    metadata = normalize_learning_result_metadata({"output_type":"notes_result","document_id":2,"markdown_length":50,"citations":[local_document_citation(2,"Doc")],"source_document_ids":[2],"fallback":True})
    assert metadata["fallback"] is True

def test_study_assets_contract():
    metadata = normalize_learning_result_metadata({"output_type":"study_assets_result","document_id":1,"flashcard_count":3,"mcq_count":2,"citations":[local_document_citation(1)],"source_document_ids":[1],"fallback":False})
    assert metadata["flashcard_count"] == 3

def test_tutor_chunk_contract():
    metadata = normalize_learning_result_metadata({"output_type":"answer_result","document_id":1,"answer_length":100,"citation_count":1,"citations":[local_chunk_citation(1,42)],"source_document_ids":[1],"retrieved_chunk_ids":[42],"excluded_chunk_ids":[],"fallback":False})
    assert metadata["citations"][0]["locator"] == "chunk:42"

def test_raw_query_is_not_permitted():
    with pytest.raises(GovernanceConfigurationError, match="non-permitted"):
        normalize_learning_result_metadata({"output_type":"answer_result","answer_length":10,"citation_count":0,"query":"sensitive"})

def test_summary_contract_accepts_internal_runtime_governance_evidence():
    metadata = normalize_learning_result_metadata({
        "output_type": "summary_result",
        "document_id": 1,
        "markdown_length": 50,
        "citations": [local_document_citation(1, "Doc")],
        "source_document_ids": [1],
        "fallback": True,
        "runtime_output_governance": {
            "output_id": "OUT-PROBE",
            "decision": "proceed",
            "sanitized_output_sha256": "a" * 64,
        },
    })
    assert metadata["runtime_output_governance"]["output_id"] == "OUT-PROBE"
