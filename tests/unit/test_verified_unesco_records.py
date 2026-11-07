from __future__ import annotations

import hashlib

from amba_ai.governance.models import (
    ActivationStatus,
    BindingLevel,
    LocatorVerificationStatus,
)
from amba_ai.governance.record_registry import PolicyRecordRegistry
from amba_ai.governance.verified_unesco_records import (
    register_verified_unesco_ai_ethics_records,
    verified_unesco_ai_ethics_records,
)


def test_verified_unesco_record_has_exact_authoritative_boundary() -> None:
    records = verified_unesco_ai_ethics_records()
    assert len(records) == 1
    record = records[0]
    assert record.identity.record_id == "UNESCO-AI-ETHICS-PARAGRAPH-104"
    assert record.identity.source_id == "UNESCO-AI-ETHICS-2021"
    assert record.identity.version_id == "2021"
    assert record.official_locator == "Paragraph 104"
    assert record.binding_level is BindingLevel.INTERNATIONAL_GUIDANCE
    assert record.locator_verification_status is LocatorVerificationStatus.VERIFIED_STRUCTURAL
    assert record.activation_status is ActivationStatus.ACTIVE
    assert record.artifact_sha256 == "3a93a6006c591bf7600abc55e8beab883b6450b71638fea98148e4b08f005bf7"
    assert record.normative_unit_sha256 == hashlib.sha256(
        record.normative_text.encode("utf-8")
    ).hexdigest()


def test_unesco_record_is_supporting_evidence_only() -> None:
    record = verified_unesco_ai_ethics_records()[0]
    assert record.eligible_for_citation is True
    assert record.eligible_for_project_enforcement is False
    assert record.eligible_for_national_legal_finding is False
    assert record.national_binding_status is False
    assert record.legal_effect is False
    assert record.conditions["supporting_evidence_only"] is True
    assert record.conditions["independent_ethiopian_legal_violation"] is False
    assert record.conditions["exact_source_excerpt_verified"] is False
    assert record.conditions["source_page_locator_verified"] is False
    assert record.conditions["adoption_date"] == "2021-11-23"


def test_verified_unesco_record_registers_without_conflict() -> None:
    registry = PolicyRecordRegistry()
    records = register_verified_unesco_ai_ethics_records(registry)
    assert registry.require(records[0].identity) == records[0]
    assert registry.eligible_for_citation(records[0].identity) is True
