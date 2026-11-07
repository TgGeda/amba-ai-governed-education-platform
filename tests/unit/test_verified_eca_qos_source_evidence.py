from __future__ import annotations

import pytest

from amba_ai.governance.verified_eca_qos_source_evidence import (
    EvidenceActivationStatus,
    ECAQoSEvidenceError,
    LocatorVerificationStatus,
    assert_threshold_not_activatable,
    verified_eca_qos_source_evidence,
)


def test_eca_qos_source_boundary_is_exact() -> None:
    evidence = verified_eca_qos_source_evidence()
    assert evidence.source_id == "ETH-ECA-QOS-794-2021"
    assert evidence.version_id == "794-2021"
    assert evidence.canonical_title == (
        "Telecommunications Quality of Service Directive No. 794/2021"
    )
    assert evidence.source_class == "directive"
    assert evidence.binding_level == "directive"
    assert evidence.artifact_sha256 == (
        "3c23ba0cfeca1f0fbdf724da211164fb8bbbec75945f16d9740cb112342ea449"
    )
    assert evidence.artifact_integrity_status == "verified"
    assert evidence.pdf_magic_header_status == "verified"
    assert evidence.activation_status is EvidenceActivationStatus.VERIFIED_SOURCE_BOUNDARY
    assert evidence.locator_verification_status is LocatorVerificationStatus.NOT_ASSESSED


def test_eca_qos_unverified_fields_remain_null_or_false() -> None:
    evidence = verified_eca_qos_source_evidence()
    assert evidence.official_locator is None
    assert evidence.page_start is None and evidence.page_end is None
    assert evidence.exact_clause_verified is False
    assert evidence.exact_table_verified is False
    assert evidence.exact_source_excerpt is None
    assert evidence.exact_source_excerpt_sha256 is None
    assert evidence.exact_table_cells is None
    assert evidence.exact_table_cells_sha256 is None
    assert evidence.verified_unit is None
    assert evidence.regulated_service is None
    assert evidence.regulated_actor is None
    assert evidence.measurement_method is None
    assert evidence.applicable_date is None
    assert evidence.table_headers is None
    assert evidence.table_conditions is None
    assert evidence.table_headers_verified is False
    assert evidence.measurement_method_verified is False
    assert evidence.applicable_date_verified is False


def test_eca_qos_eligibility_and_threshold_boundaries() -> None:
    evidence = verified_eca_qos_source_evidence()
    assert evidence.eligible_for_technical_context is True
    assert evidence.eligible_for_readiness_evidence is True
    assert evidence.eligible_for_binding_technical_findings is False
    assert evidence.eligible_for_citation is False
    assert evidence.bandwidth_threshold_established is False
    assert evidence.latency_threshold_established is False
    assert evidence.packet_loss_threshold_established is False
    assert evidence.reliability_threshold_established is False
    assert evidence.threshold_activation_ready is False
    assert len(evidence.threshold_activation_requirements) == 10
    assert evidence.human_validation_required_for_threshold_activation is True


def test_eca_qos_threshold_activation_fails_closed() -> None:
    with pytest.raises(ECAQoSEvidenceError, match="all ten exact-evidence requirements"):
        assert_threshold_not_activatable(verified_eca_qos_source_evidence())
