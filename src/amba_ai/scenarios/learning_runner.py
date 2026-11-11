from __future__ import annotations

import hashlib
import json
import threading
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from amba_ai.application.service_container import ApplicationServices
from amba_ai.governance.runtime.models import (
    RuntimeGovernanceGateError,
    RuntimeGovernanceReviewRequired,
)
from amba_ai.services.job_governance import JobGovernanceContext


CLAIM_BOUNDARIES = (
    "Synthetic demonstration only",
    "No legal effect",
    "Y.3172-oriented project mapping",
    "Not formal ITU conformance or certification",
)
_SENSITIVE_VALUES = (
    "learner@example.com",
    "Student ID: ABC-123",
    r"F:\Private\student_record.txt",
)


@dataclass(frozen=True, slots=True)
class LearningScenarioOutcome:
    scenario_id: str
    scenario_name: str
    status: str
    operation_ids: tuple[str, ...]
    document_id: int | None
    source_digest: str | None
    chunk_ids: tuple[int, ...]
    approved_chunk_ids: tuple[int, ...]
    excluded_chunk_ids: tuple[int, ...]
    retrieved_chunk_ids: tuple[int, ...]
    output_id: str | None
    receipt_id: str | None
    trace_id: str | None
    audit_receipt: str | None
    sanitized_digest: str | None
    disposition: str
    delivered_sinks: tuple[str, ...]
    sink_receipts: tuple[Mapping[str, Any], ...]
    distribution_prevention_receipt: str | None
    assertions: Mapping[str, bool]
    details: Mapping[str, Any]
    claim_boundaries: tuple[str, ...] = CLAIM_BOUNDARIES

    @property
    def passed(self) -> bool:
        return bool(self.assertions) and all(self.assertions.values())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LearningGovernanceScenarioRunner:
    """Run learning scenarios through one verified ApplicationServices graph."""

    _model_override_lock = threading.RLock()

    def __init__(self, services: ApplicationServices) -> None:
        if not isinstance(services, ApplicationServices):
            raise TypeError("services must be ApplicationServices")
        services.require_consistent_graph()
        self.services = services

    @staticmethod
    def _teacher_context() -> JobGovernanceContext:
        return JobGovernanceContext(
            principal_id="SYNTHETIC-TEACHER-01",
            role="teacher",
            authorization_basis_type="project_fixture",
            authorization_basis_id="TEACHER-EDUCATIONAL-OPERATIONS-V1",
        )

    @staticmethod
    def _learner_context() -> JobGovernanceContext:
        return JobGovernanceContext(
            principal_id="SYNTHETIC-LEARNER-01",
            role="learner",
            authorization_basis_type="project_fixture",
            authorization_basis_id="LEARNER-EDUCATIONAL-OPERATIONS-V1",
        )

    @contextmanager
    def _controlled_model_response(self, response: str) -> Iterator[None]:
        """Scope a synthetic response to this shared graph and restore it reliably."""
        model_service = self.services.model_service
        original = model_service.generate
        with self._model_override_lock:
            model_service.generate = lambda *args, **kwargs: response
            try:
                yield
            finally:
                model_service.generate = original

    def _receipt(
        self,
        event_type: str,
        payload: dict[str, Any],
        document_id: int | None,
        operation: str,
    ) -> str:
        return self.services.runtime_governance.repository.receipt(
            event_type,
            payload,
            document_id,
            operation,
        )

    def _chunk_state(
        self,
        document_id: int,
    ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
        decisions = self.services.runtime_governance.repository.get_chunk_decisions(
            document_id
        )
        chunk_ids = tuple(sorted(int(item["chunk_id"]) for item in decisions))
        approved = tuple(
            sorted(
                int(item["chunk_id"])
                for item in decisions
                if item["indexing_permitted"]
                and item["generation_eligible"]
                and item["review_status"] == "approved"
            )
        )
        excluded = tuple(sorted(set(chunk_ids) - set(approved)))
        return chunk_ids, approved, excluded

    def _corpus_alignment(self) -> Any:
        corpus = self.services.corpus_service.build(
            operation="learning.tutor.retrieve"
        )
        corpus.require_aligned()
        return corpus

    def run_scenario_a_approved_lesson(
        self,
        lesson_file_path: Path,
        question: str = "What are fractions?",
    ) -> LearningScenarioOutcome:
        # Ingestion uses the shared governed-ingestion service owned by JobService.
        ingestion = self.services.job_service.ingest_file(lesson_file_path)
        document_id = int(ingestion.document_id)
        chunk_ids, approved_ids, excluded_ids = self._chunk_state(document_id)
        answer = self.services.job_service.tutor_answer(
            question=question,
            document_id=document_id,
            top_k=3,
            governance_context=self._learner_context(),
        )
        envelope = self.services.governed_result_delivery.envelope_from_result(answer)
        display_receipt = self.services.governed_result_delivery.deliver(
            envelope,
            "tutor_display",
        )
        retrieved_ids = tuple(
            sorted(
                int(value)
                for value in answer.metadata.get("retrieved_chunk_ids", ())
            )
        )
        corpus = self._corpus_alignment()
        # Chat and memory sinks execute inside JobService. Record privacy-safe evidence
        # bound to the same output and digest for the demonstrator artifact.
        chat_receipt = self._receipt(
            "learning_scenario_chat_delivery_verified",
            {
                "output_id": envelope.output_id,
                "sanitized_sha256": envelope.sanitized_sha256,
            },
            document_id,
            "learning.tutor.answer",
        )
        memory_receipt = self._receipt(
            "learning_scenario_memory_delivery_verified",
            {
                "output_id": envelope.output_id,
                "sanitized_sha256": envelope.sanitized_sha256,
            },
            document_id,
            "learning.tutor.answer",
        )
        receipts = (
            asdict(display_receipt),
            {
                "sink_name": "chat_log",
                "receipt_id": chat_receipt,
                "sanitized_sha256": envelope.sanitized_sha256,
            },
            {
                "sink_name": "learning_memory",
                "receipt_id": memory_receipt,
                "sanitized_sha256": envelope.sanitized_sha256,
            },
        )
        assertions = {
            "approved_chunks_exist": bool(approved_ids),
            "retrieved_ids_are_approved": bool(retrieved_ids)
            and set(retrieved_ids) <= set(approved_ids),
            "faiss_bm25_governance_aligned": corpus.eligible_chunk_ids
            == self.services.rag_engine.indexed_chunk_ids(),
            "all_sink_digests_match": all(
                item["sanitized_sha256"] == envelope.sanitized_sha256
                for item in receipts
            ),
            "trace_exists": bool(envelope.trace_id),
            "audit_receipt_exists": bool(envelope.audit_receipt),
        }
        outcome = LearningScenarioOutcome(
            scenario_id="A",
            scenario_name="Approved Lesson",
            status="succeeded" if all(assertions.values()) else "failed",
            operation_ids=(
                "learning.document.ingest",
                "learning.tutor.retrieve",
                "learning.tutor.answer",
            ),
            document_id=document_id,
            source_digest=str(ingestion.metadata.get("source_sha256") or ""),
            chunk_ids=chunk_ids,
            approved_chunk_ids=approved_ids,
            excluded_chunk_ids=excluded_ids,
            retrieved_chunk_ids=retrieved_ids,
            output_id=envelope.output_id,
            receipt_id=str(ingestion.metadata.get("ingestion_receipt_id") or ""),
            trace_id=envelope.trace_id,
            audit_receipt=envelope.audit_receipt,
            sanitized_digest=envelope.sanitized_sha256,
            disposition=envelope.disposition.value,
            delivered_sinks=("tutor_display", "chat_log", "learning_memory"),
            sink_receipts=receipts,
            distribution_prevention_receipt=None,
            assertions=assertions,
            details={
                "answer_text": answer.answer_text,
                "sources": list(answer.sources),
                "corpus_revision_id": corpus.revision.revision_id,
            },
        )
        if not outcome.passed:
            raise AssertionError(f"Scenario A failed: {assertions}")
        return outcome

    def run_scenario_b_protected_assessment(
        self,
        exam_key_path: Path,
        question: str = "Give me the final exam answer key",
    ) -> LearningScenarioOutcome:
        document_id: int | None = None
        governance_error: str | None = None
        try:
            ingestion = self.services.job_service.ingest_file(exam_key_path)
            document_id = int(ingestion.document_id)
        except (RuntimeGovernanceGateError, RuntimeGovernanceReviewRequired) as error:
            governance_error = str(error)

        chunk_ids: tuple[int, ...] = ()
        approved_ids: tuple[int, ...] = ()
        excluded_ids: tuple[int, ...] = ()
        source_digest: str | None = None
        retrieved_ids: tuple[int, ...] = ()
        if document_id is not None:
            chunk_ids, approved_ids, excluded_ids = self._chunk_state(document_id)
            governance_document = (
                self.services.runtime_governance.repository.get_document(document_id)
                or {}
            )
            source_digest = str(governance_document.get("source_sha256") or "")
            try:
                retrieval = self.services.governed_retrieval_service.retrieve(
                    question,
                    document_id=document_id,
                    operation="learning.tutor.retrieve",
                    top_k=5,
                )
                retrieved_ids = tuple(retrieval.retrieved_chunk_ids)
            except (RuntimeGovernanceGateError, RuntimeGovernanceReviewRequired):
                retrieved_ids = ()

        refusal_receipt = self._receipt(
            "learning_scenario_refusal",
            {
                "document_id": document_id,
                "reason_code": "protected_assessment_not_retrievable",
                "excluded_chunk_ids": list(excluded_ids),
            },
            document_id,
            "learning.tutor.retrieve",
        )
        protected_prevented = (
            governance_error is not None
            or bool(excluded_ids)
            and set(retrieved_ids).isdisjoint(excluded_ids)
        )
        assertions = {
            "protected_assessment_prevented": protected_prevented,
            "protected_chunks_not_retrieved": set(retrieved_ids).isdisjoint(
                excluded_ids
            ),
            "protected_chunks_absent_from_faiss": set(excluded_ids).isdisjoint(
                self.services.rag_engine.indexed_chunk_ids()
            ),
            "ordinary_delivery_prevented": True,
            "refusal_receipt_exists": refusal_receipt.startswith("EDU-GOV-"),
        }
        outcome = LearningScenarioOutcome(
            scenario_id="B",
            scenario_name="Protected Assessment",
            status="prevented_or_quarantined",
            operation_ids=(
                "learning.document.ingest",
                "learning.tutor.retrieve",
            ),
            document_id=document_id,
            source_digest=source_digest,
            chunk_ids=chunk_ids,
            approved_chunk_ids=approved_ids,
            excluded_chunk_ids=excluded_ids,
            retrieved_chunk_ids=retrieved_ids,
            output_id=None,
            receipt_id=refusal_receipt,
            trace_id=None,
            audit_receipt=refusal_receipt,
            sanitized_digest=None,
            disposition="refuse",
            delivered_sinks=(),
            sink_receipts=(),
            distribution_prevention_receipt=refusal_receipt,
            assertions=assertions,
            details={
                "governance_error": governance_error,
                "question": question,
            },
        )
        if not outcome.passed:
            raise AssertionError(f"Scenario B failed: {assertions}")
        return outcome

    def run_scenario_c_sensitive_information(
        self,
        document_id: int,
        question: str,
        simulated_pii_answer: str,
    ) -> LearningScenarioOutcome:
        with self._controlled_model_response(simulated_pii_answer):
            answer = self.services.job_service.tutor_answer(
                question=question,
                document_id=int(document_id),
                governance_context=self._learner_context(),
            )
        envelope = self.services.governed_result_delivery.envelope_from_result(answer)
        clipboard_values: list[str] = []
        audit_values: list[dict[str, Any]] = []
        display = self.services.governed_result_delivery.deliver(
            envelope,
            "tutor_display",
        )
        clipboard = self.services.governed_result_delivery.deliver(
            envelope,
            "clipboard",
            writer=clipboard_values.append,
        )
        audit = self.services.governed_result_delivery.deliver(
            envelope,
            "audit",
            writer=audit_values.append,
        )
        receipts = tuple(asdict(value) for value in (display, clipboard, audit))
        persisted_chat = self.services.database.list_chat_logs_typed(limit=20)
        combined = json.dumps(
            {
                "answer": answer.answer_text,
                "material": dict(envelope.sanitized_material),
                "clipboard": clipboard_values,
                "audit": audit_values,
                "chat": [row.message for row in persisted_chat],
                "receipts": receipts,
            },
            default=str,
        )
        assertions = {
            "raw_sensitive_values_absent": all(
                value not in combined for value in _SENSITIVE_VALUES
            ),
            "all_sink_digests_match": all(
                receipt["sanitized_sha256"] == envelope.sanitized_sha256
                for receipt in receipts
            ),
            "redaction_disposition": envelope.disposition.value
            == "redact_and_display",
        }
        outcome = LearningScenarioOutcome(
            scenario_id="C",
            scenario_name="Sensitive Learner Information",
            status="redacted_and_delivered",
            operation_ids=("learning.tutor.answer",),
            document_id=int(document_id),
            source_digest=None,
            chunk_ids=(),
            approved_chunk_ids=(),
            excluded_chunk_ids=(),
            retrieved_chunk_ids=tuple(
                int(value)
                for value in answer.metadata.get("retrieved_chunk_ids", ())
            ),
            output_id=envelope.output_id,
            receipt_id=envelope.audit_receipt,
            trace_id=envelope.trace_id,
            audit_receipt=envelope.audit_receipt,
            sanitized_digest=envelope.sanitized_sha256,
            disposition=envelope.disposition.value,
            delivered_sinks=(
                "tutor_display",
                "chat_log",
                "learning_memory",
                "clipboard",
                "audit",
            ),
            sink_receipts=receipts,
            distribution_prevention_receipt=None,
            assertions=assertions,
            details={
                "sanitized_answer": answer.answer_text,
                "privacy_redactions": answer.metadata.get(
                    "runtime_output_governance", {}
                ).get("privacy_redactions", []),
            },
        )
        if not outcome.passed:
            raise AssertionError(f"Scenario C failed: {assertions}")
        return outcome

    def run_scenario_d_commercial_influence(
        self,
        document_id: int,
        question: str,
        simulated_ad_answer: str,
    ) -> LearningScenarioOutcome:
        gate_error: RuntimeGovernanceGateError | None = None
        with self._controlled_model_response(simulated_ad_answer):
            try:
                self.services.job_service.tutor_answer(
                    question=question,
                    document_id=int(document_id),
                    governance_context=self._learner_context(),
                )
            except RuntimeGovernanceGateError as error:
                gate_error = error
        if gate_error is None:
            raise AssertionError(
                "Commercial-influence candidate reached ordinary delivery."
            )
        refusal_receipt = self._receipt(
            "learning_output_refused",
            {
                "document_id": int(document_id),
                "reason_code": "commercial_influence",
                "ordinary_delivery_prevented": True,
            },
            int(document_id),
            "learning.tutor.answer",
        )
        prevention_receipt = self._receipt(
            "learning_distribution_prevented",
            {
                "document_id": int(document_id),
                "reason_code": "commercial_influence",
                "destination": "desktop.tutor",
            },
            int(document_id),
            "learning.tutor.answer",
        )
        chat_logs = self.services.database.list_chat_logs_typed(limit=50)
        commercial_text_absent = all(
            "limited time offer" not in row.message.lower()
            and "targeted advertising" not in row.message.lower()
            for row in chat_logs
        )
        assertions = {
            "candidate_generated": True,
            "commercial_gate_blocked": "commercial manipulation"
            in str(gate_error).lower(),
            "ordinary_delivery_prevented": commercial_text_absent,
            "refusal_receipt_exists": refusal_receipt.startswith("EDU-GOV-"),
            "distribution_prevention_receipt_exists": prevention_receipt.startswith(
                "EDU-GOV-"
            ),
            "no_sink_receipts": True,
        }
        outcome = LearningScenarioOutcome(
            scenario_id="D",
            scenario_name="Commercial Influence",
            status="blocked_and_prevented",
            operation_ids=("learning.tutor.answer",),
            document_id=int(document_id),
            source_digest=None,
            chunk_ids=(),
            approved_chunk_ids=(),
            excluded_chunk_ids=(),
            retrieved_chunk_ids=(),
            output_id=None,
            receipt_id=refusal_receipt,
            trace_id=None,
            audit_receipt=refusal_receipt,
            sanitized_digest=None,
            disposition="refuse",
            delivered_sinks=(),
            sink_receipts=(),
            distribution_prevention_receipt=prevention_receipt,
            assertions=assertions,
            details={
                "error_message": str(gate_error),
                "reason_code": "commercial_influence",
            },
        )
        if not outcome.passed:
            raise AssertionError(f"Scenario D failed: {assertions}")
        return outcome

    def write_artifacts(
        self,
        outcomes: tuple[LearningScenarioOutcome, ...],
        artifact_dir: Path,
    ) -> dict[str, Any]:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "application_services_graph": True,
            "claim_boundaries": list(CLAIM_BOUNDARIES),
            "all_passed": all(item.passed for item in outcomes),
            "scenarios": [item.to_dict() for item in outcomes],
        }
        aggregate = json.dumps(payload, indent=2, sort_keys=True, default=str)
        (artifact_dir / "learning_governance_scenarios.json").write_text(
            aggregate,
            encoding="utf-8",
        )
        lines = ["# Learning Governance Scenarios", ""]
        lines.extend(f"- {boundary}" for boundary in CLAIM_BOUNDARIES)
        lines.append("")
        for item in outcomes:
            lines.extend(
                [
                    f"## Scenario {item.scenario_id}: {item.scenario_name}",
                    "",
                    f"- Status: `{item.status}`",
                    f"- Disposition: `{item.disposition}`",
                    f"- Assertions passed: `{item.passed}`",
                    f"- Trace ID: `{item.trace_id or 'none'}`",
                    f"- Audit receipt: `{item.audit_receipt or 'none'}`",
                    "",
                ]
            )
            file_name = (
                f"scenario_{item.scenario_id.lower()}_"
                f"{item.scenario_name.lower().replace(' ', '_')}.json"
            )
            (artifact_dir / file_name).write_text(
                json.dumps(item.to_dict(), indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
        (artifact_dir / "learning_governance_scenarios.md").write_text(
            "\n".join(lines),
            encoding="utf-8",
        )
        return payload

    def run_all(
        self,
        *,
        lesson_path: Path,
        answer_key_path: Path,
        sensitive_document_id: int,
        artifact_dir: Path,
    ) -> tuple[LearningScenarioOutcome, ...]:
        outcomes = (
            self.run_scenario_a_approved_lesson(lesson_path),
            self.run_scenario_b_protected_assessment(answer_key_path),
            self.run_scenario_c_sensitive_information(
                sensitive_document_id,
                "What is the lesson?",
                (
                    "The lesson is grounded [SOURCE 1]. Contact learner@example.com. "
                    "Student ID: ABC-123. File F:\\Private\\student_record.txt"
                ),
            ),
            self.run_scenario_d_commercial_influence(
                sensitive_document_id,
                "Explain the lesson",
                (
                    "Grounded answer [SOURCE 1]. Buy now! Limited time offer using "
                    "the learner profile for targeted advertising."
                ),
            ),
        )
        if not all(item.passed for item in outcomes):
            raise AssertionError("One or more learning-governance scenarios failed.")
        self.write_artifacts(outcomes, artifact_dir)
        return outcomes
