from __future__ import annotations

import hashlib

from amba_ai.governance.models import (
    ActivationStatus,
    BindingLevel,
    LocatorVerificationStatus,
)
from amba_ai.governance.record_registry import PolicyRecordRegistry
from amba_ai.governance.verified_policy_records import (
    register_verified_itu_y3172_records,
    verified_itu_y3172_records,
)


def test_verified_y3172_record_set_has_exact_known_locators() -> None:
    records = verified_itu_y3172_records()
    assert len(records) == 5
    assert {record.official_locator for record in records} == {
        "Clause 3.2.6",
        "Clause 7.4",
        "Clause 8.1",
        "Clauses 8.1 and 8.2",
        "Clause 9",
    }


def test_verified_y3172_records_are_supporting_architecture_evidence_only() -> None:
    for record in verified_itu_y3172_records():
        assert record.binding_level is BindingLevel.TECHNICAL_STANDARD
        assert record.activation_status is ActivationStatus.ACTIVE
        assert record.locator_verification_status is LocatorVerificationStatus.VERIFIED_STRUCTURAL
        assert record.artifact_sha256 == "e42f9a3be3f951d3e19b9007f876f0b389c81b4693f0d8576e18185a1acfe67b"
        assert record.national_binding_status is False
        assert record.legal_effect is False
        assert record.eligible_for_project_enforcement is False
        assert record.eligible_for_national_legal_finding is False
        assert record.eligible_for_citation is True
        assert record.conditions["formal_conformance_claim"] is False
        assert record.conditions["ethiopian_legal_authority"] is False
        assert record.normative_unit_sha256 == hashlib.sha256(record.normative_text.encode("utf-8")).hexdigest()


def test_verified_y3172_records_register_without_identity_conflicts() -> None:
    registry = PolicyRecordRegistry()
    records = register_verified_itu_y3172_records(registry)
    assert len(records) == 5
    for record in records:
        assert registry.require(record.identity) == record
        assert registry.eligible_for_citation(record.identity) is True
