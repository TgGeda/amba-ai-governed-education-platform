from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from amba_ai.application.service_container import ApplicationServices
from amba_ai.application.providers import ProviderRegistry
from amba_ai.governance.execution_context import GovernanceExecutionContext
from amba_ai.services.governed_learning_trace_service import (
    GovernedLearningTraceService,
    REQUIRED_EVENT_TYPES,
)


class FakeServices(ApplicationServices):
    pass


def _services() -> ApplicationServices:
    shared = object()
    review = SimpleNamespace(runtime_governance=shared, rag_engine=shared)
    lifecycle = SimpleNamespace(db=shared, runtime_governance=shared, rag_engine=shared)
    ingestion = SimpleNamespace(db=shared, runtime_governance=shared, rag_engine=shared)
    retrieval = SimpleNamespace(runtime_governance=shared, rag_engine=shared)
    grounded = SimpleNamespace(model_service=shared)
    job = SimpleNamespace(
        db=shared,
        runtime_governance=shared,
        governance_coordinator=shared,
        rag=shared,
        memory=shared,
        context_tracker=shared,
        governed_ingestion=ingestion,
        governed_retrieval=retrieval,
        grounded_answer=grounded,
        result_delivery=shared,
        document_lifecycle=lifecycle,
    )
    corpus = SimpleNamespace(rag_engine=shared, runtime_governance=shared)
    return ApplicationServices(
        providers=ProviderRegistry(),
        database=shared,
        model_service=shared,
        memory_service=shared,
        context_tracker=shared,
        runtime_governance=shared,
        governance_coordinator=shared,
        rag_engine=shared,
        corpus_service=corpus,
        governed_ingestion_service=ingestion,
        governed_retrieval_service=retrieval,
        grounded_answer_service=grounded,
        governed_result_delivery=shared,
        governance_review_service=review,
        document_lifecycle_service=lifecycle,
        job_service=job,
        governance_service=shared,
        approval_service=shared,
        execution_service=shared,
        distribution_service=shared,
        trace_coordinator=shared,
        audit_service=shared,
    )


def test_complete_user_action_to_audit_chain(tmp_path: Path) -> None:
    services = _services()
    trace = GovernedLearningTraceService(services)
    context = GovernanceExecutionContext.create(
        session_id="SESSION-1",
        principal_id="SYNTHETIC-LEARNER-01",
        operation_id="learning.tutor.answer",
        document_id=7,
        runtime_request_id="EDU-REQUEST-1",
    )
    source_digest = "a" * 64
    sanitized_digest = "b" * 64
    events = (
        ("user_action", {"status": "requested"}),
        ("operation_authorization", {"decision": "authorized", "receipt_id": "AUTH-1"}),
        ("source_digest_verified", {"source_sha256": source_digest}),
        ("chunk_decisions_recorded", {"chunk_ids": [11], "approved_chunk_ids": [11], "excluded_chunk_ids": []}),
        ("index_revision_published", {"revision_id": "REV-1", "approved_chunk_ids": [11]}),
        ("retrieval_receipt_created", {"retrieval_receipt": "RET-1", "retrieved_chunk_ids": [11]}),
        ("generation_requested", {"generation_request_id": "GEN-1"}),
        ("output_validated", {"output_id": "OUT-1", "sanitized_sha256": sanitized_digest, "disposition": "display"}),
        ("sink_receipt_created", {"sink_name": "tutor_display", "receipt_id": "SINK-1", "sanitized_sha256": sanitized_digest}),
        ("distribution_completed_or_prevented", {"status": "completed", "receipt_id": "DIST-1"}),
        ("trace_completed", {"receipt_id": "TRACE-RECEIPT-1"}),
        ("audit_block_verified", {"audit_receipt": "AUDIT-1", "status": "verified"}),
    )
    matrix = {"test_complete_governed_learning_chain.py": "Full user-action-to-audit chain"}
    record = trace.build_record(
        context=context,
        event_details=events,
        scenario_ids=("A",),
        test_matrix=matrix,
        source_inventory_sha256="c" * 64,
        audit_verified=True,
    )
    trace.verify_record(record)
    json_path = tmp_path / "governed_learning_evidence_chain.json"
    md_path = tmp_path / "governed_learning_evidence_chain.md"
    trace.write_artifacts(record=record, json_path=json_path, markdown_path=md_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert tuple(event["event_type"] for event in payload["events"]) == REQUIRED_EVENT_TYPES
    assert payload["execution_context"]["correlation_id"] == context.correlation_id
    assert payload["missing_required_events"] == []
    assert payload["audit_verified"] is True


def test_evidence_chain_rejects_sensitive_raw_values() -> None:
    trace = GovernedLearningTraceService(_services())
    context = GovernanceExecutionContext.create(
        session_id="SESSION-1",
        principal_id="SYNTHETIC-LEARNER-01",
        operation_id="learning.tutor.answer",
    )
    with pytest.raises(ValueError, match="sensitive"):
        trace.event(
            sequence=1,
            event_type="user_action",
            context=context,
            details={"status": "learner@example.com"},
            previous_event_sha256=None,
        )


def test_evidence_chain_tampering_is_detected() -> None:
    trace = GovernedLearningTraceService(_services())
    context = GovernanceExecutionContext.create(
        session_id="SESSION-1",
        principal_id="SYNTHETIC-LEARNER-01",
        operation_id="learning.tutor.answer",
    )
    record = trace.build_record(
        context=context,
        event_details=((event, {"status": "verified"}) for event in REQUIRED_EVENT_TYPES),
        scenario_ids=("A", "B", "C", "D"),
        test_matrix={},
        source_inventory_sha256="d" * 64,
        audit_verified=True,
    )
    object.__setattr__(record.events[2], "details_sha256", "0" * 64)
    with pytest.raises(ValueError, match="digest"):
        trace.verify_record(record)
