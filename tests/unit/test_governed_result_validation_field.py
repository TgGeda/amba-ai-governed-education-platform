from __future__ import annotations

from amba_ai.governance.runtime.output_guardrails import (
    GovernedOutputValidation,
    OutputDisposition,
    digest_material,
)
from amba_ai.services.governed_result_delivery import GovernedResultDeliveryService


def test_envelope_uses_validation_decision_field() -> None:
    sanitized_material = {"notes_text": "Safe notes"}
    sanitized_digest = digest_material(sanitized_material)
    validation = GovernedOutputValidation(
        output_id="EDU-OUT-TEST-1",
        document_id=1,
        operation="learning.notes.generate",
        decision=OutputDisposition.REDACT_AND_DISPLAY,
        sanitized_material=sanitized_material,
        raw_output_sha256="a" * 64,
        sanitized_output_sha256=sanitized_digest,
        source_digest_verified=True,
        retrieved_chunk_ids=(1,),
        excluded_chunk_ids=(),
        grounding_status="grounded",
        unsupported_claims=(),
        citation_status="verified",
        privacy_redactions=(),
        sensitive_child_data=False,
        assessment_integrity_status="clear",
        harm_status="clear",
        age_suitability="suitable",
        prompt_leakage_status="clear",
        commercial_influence_status="clear",
        display_status="sanitized",
        trace_id="EDU-TRACE-TEST-1",
        audit_receipt="EDU-GOV-TEST-1",
    )
    delivery = GovernedResultDeliveryService()
    envelope = delivery.envelope_from_validation(
        validation,
        operation_id="learning.notes.generate",
    )
    assert envelope.disposition is OutputDisposition.REDACT_AND_DISPLAY
    assert envelope.sanitized_sha256 == sanitized_digest
    assert dict(envelope.sanitized_material) == sanitized_material
