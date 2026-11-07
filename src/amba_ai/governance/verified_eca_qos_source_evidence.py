from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

SOURCE_ID = "ETH-ECA-QOS-794-2021"
VERSION_ID = "794-2021"
CANONICAL_TITLE = "Telecommunications Quality of Service Directive No. 794/2021"
SOURCE_CLASS = "directive"
BINDING_LEVEL = "directive"
ARTIFACT_SHA256 = "3c23ba0cfeca1f0fbdf724da211164fb8bbbec75945f16d9740cb112342ea449"
SOURCE_RELATIVE_PATH = "kb/sources/ethiopia/ETH_ECA_QOS_794_2021.pdf"


class ECAQoSEvidenceError(ValueError):
    pass


class EvidenceActivationStatus(str, Enum):
    VERIFIED_SOURCE_BOUNDARY = "verified_source_boundary"


class LocatorVerificationStatus(str, Enum):
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True, slots=True)
class VerifiedECAQoSSourceEvidence:
    """Verified directive source boundary with no invented QoS threshold.

    The object records what is known about the source artifact and what remains
    required before any clause-, table-, or threshold-level evidence can be
    activated for citation or binding technical findings.
    """

    evidence_id: str
    source_id: str
    version_id: str
    canonical_title: str
    source_class: str
    binding_level: str
    source_path: str
    artifact_sha256: str
    artifact_integrity_status: str
    pdf_magic_header_status: str
    activation_status: EvidenceActivationStatus
    locator_verification_status: LocatorVerificationStatus
    official_locator: None
    page_start: None
    page_end: None
    exact_clause_verified: bool
    exact_table_verified: bool
    exact_source_excerpt: None
    exact_source_excerpt_sha256: None
    exact_table_cells: None
    exact_table_cells_sha256: None
    verified_unit: None
    regulated_service: None
    regulated_actor: None
    measurement_method: None
    applicable_date: None
    table_headers: None
    table_conditions: None
    table_headers_verified: bool
    measurement_method_verified: bool
    applicable_date_verified: bool
    eligible_for_technical_context: bool
    eligible_for_readiness_evidence: bool
    eligible_for_binding_technical_findings: bool
    eligible_for_citation: bool
    bandwidth_threshold_established: bool
    latency_threshold_established: bool
    packet_loss_threshold_established: bool
    reliability_threshold_established: bool
    human_validation_required_for_threshold_activation: bool

    def __post_init__(self) -> None:
        if self.evidence_id != "ETH-ECA-QOS-VERIFIED-SOURCE-BOUNDARY":
            raise ECAQoSEvidenceError("unexpected evidence_id")
        if self.source_id != SOURCE_ID or self.version_id != VERSION_ID:
            raise ECAQoSEvidenceError("source identity is invalid")
        if self.canonical_title != CANONICAL_TITLE:
            raise ECAQoSEvidenceError("canonical title is invalid")
        if self.source_class != SOURCE_CLASS or self.binding_level != BINDING_LEVEL:
            raise ECAQoSEvidenceError("source classification is invalid")
        if self.source_path != SOURCE_RELATIVE_PATH:
            raise ECAQoSEvidenceError("source path is invalid")
        if self.artifact_sha256 != ARTIFACT_SHA256:
            raise ECAQoSEvidenceError("artifact digest is invalid")
        try:
            if len(self.artifact_sha256) != 64:
                raise ValueError
            int(self.artifact_sha256, 16)
        except ValueError as error:
            raise ECAQoSEvidenceError(
                "artifact_sha256 must be a 64-character hexadecimal digest"
            ) from error
        if self.artifact_integrity_status != "verified":
            raise ECAQoSEvidenceError("artifact integrity must be verified")
        if self.pdf_magic_header_status != "verified":
            raise ECAQoSEvidenceError("PDF magic header must be verified")
        if self.activation_status is not EvidenceActivationStatus.VERIFIED_SOURCE_BOUNDARY:
            raise ECAQoSEvidenceError("activation status must be verified_source_boundary")
        if self.locator_verification_status is not LocatorVerificationStatus.NOT_ASSESSED:
            raise ECAQoSEvidenceError("locator verification must remain not_assessed")
        nullable_fields = (
            self.official_locator,
            self.page_start,
            self.page_end,
            self.exact_source_excerpt,
            self.exact_source_excerpt_sha256,
            self.exact_table_cells,
            self.exact_table_cells_sha256,
            self.verified_unit,
            self.regulated_service,
            self.regulated_actor,
            self.measurement_method,
            self.applicable_date,
            self.table_headers,
            self.table_conditions,
        )
        if any(value is not None for value in nullable_fields):
            raise ECAQoSEvidenceError(
                "unverified locator, excerpt, table, service, actor, method, date, and condition fields must remain null"
            )
        unverified_flags = (
            self.exact_clause_verified,
            self.exact_table_verified,
            self.table_headers_verified,
            self.measurement_method_verified,
            self.applicable_date_verified,
        )
        if any(value is not False for value in unverified_flags):
            raise ECAQoSEvidenceError("clause, table, header, method, and date verification flags must remain false")
        if self.eligible_for_technical_context is not True:
            raise ECAQoSEvidenceError("technical context eligibility must be true")
        if self.eligible_for_readiness_evidence is not True:
            raise ECAQoSEvidenceError("readiness evidence eligibility must be true")
        if self.eligible_for_binding_technical_findings is not False:
            raise ECAQoSEvidenceError("binding technical finding eligibility must be false")
        if self.eligible_for_citation is not False:
            raise ECAQoSEvidenceError("citation eligibility must be false")
        threshold_flags = (
            self.bandwidth_threshold_established,
            self.latency_threshold_established,
            self.packet_loss_threshold_established,
            self.reliability_threshold_established,
        )
        if any(value is not False for value in threshold_flags):
            raise ECAQoSEvidenceError("no QoS threshold may be established without exact verified evidence")
        if self.human_validation_required_for_threshold_activation is not True:
            raise ECAQoSEvidenceError("human validation must be required for threshold activation")

    @property
    def threshold_activation_requirements(self) -> tuple[str, ...]:
        return (
            "exact clause or table locator",
            "exact excerpt or table cells",
            "verified unit",
            "regulated service",
            "regulated actor",
            "measurement method",
            "applicable date",
            "verified table headers and conditions",
            "excerpt or table-cell SHA-256",
            "human validation",
        )

    @property
    def threshold_activation_ready(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "version_id": self.version_id,
            "canonical_title": self.canonical_title,
            "source_class": self.source_class,
            "binding_level": self.binding_level,
            "source_path": self.source_path,
            "artifact_sha256": self.artifact_sha256,
            "artifact_integrity_status": self.artifact_integrity_status,
            "pdf_magic_header_status": self.pdf_magic_header_status,
            "activation_status": self.activation_status.value,
            "locator_verification_status": self.locator_verification_status.value,
            "official_locator": self.official_locator,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "exact_clause_verified": self.exact_clause_verified,
            "exact_table_verified": self.exact_table_verified,
            "exact_source_excerpt": self.exact_source_excerpt,
            "exact_source_excerpt_sha256": self.exact_source_excerpt_sha256,
            "exact_table_cells": self.exact_table_cells,
            "exact_table_cells_sha256": self.exact_table_cells_sha256,
            "verified_unit": self.verified_unit,
            "regulated_service": self.regulated_service,
            "regulated_actor": self.regulated_actor,
            "measurement_method": self.measurement_method,
            "applicable_date": self.applicable_date,
            "table_headers": self.table_headers,
            "table_conditions": self.table_conditions,
            "table_headers_verified": self.table_headers_verified,
            "measurement_method_verified": self.measurement_method_verified,
            "applicable_date_verified": self.applicable_date_verified,
            "eligible_for_technical_context": self.eligible_for_technical_context,
            "eligible_for_readiness_evidence": self.eligible_for_readiness_evidence,
            "eligible_for_binding_technical_findings": self.eligible_for_binding_technical_findings,
            "eligible_for_citation": self.eligible_for_citation,
            "threshold_claims": {
                "bandwidth_threshold_established": self.bandwidth_threshold_established,
                "latency_threshold_established": self.latency_threshold_established,
                "packet_loss_threshold_established": self.packet_loss_threshold_established,
                "reliability_threshold_established": self.reliability_threshold_established,
            },
            "threshold_activation_requirements": list(self.threshold_activation_requirements),
            "threshold_activation_ready": self.threshold_activation_ready,
            "human_validation_required_for_threshold_activation": self.human_validation_required_for_threshold_activation,
        }


def verified_eca_qos_source_evidence() -> VerifiedECAQoSSourceEvidence:
    return VerifiedECAQoSSourceEvidence(
        evidence_id="ETH-ECA-QOS-VERIFIED-SOURCE-BOUNDARY",
        source_id=SOURCE_ID,
        version_id=VERSION_ID,
        canonical_title=CANONICAL_TITLE,
        source_class=SOURCE_CLASS,
        binding_level=BINDING_LEVEL,
        source_path=SOURCE_RELATIVE_PATH,
        artifact_sha256=ARTIFACT_SHA256,
        artifact_integrity_status="verified",
        pdf_magic_header_status="verified",
        activation_status=EvidenceActivationStatus.VERIFIED_SOURCE_BOUNDARY,
        locator_verification_status=LocatorVerificationStatus.NOT_ASSESSED,
        official_locator=None,
        page_start=None,
        page_end=None,
        exact_clause_verified=False,
        exact_table_verified=False,
        exact_source_excerpt=None,
        exact_source_excerpt_sha256=None,
        exact_table_cells=None,
        exact_table_cells_sha256=None,
        verified_unit=None,
        regulated_service=None,
        regulated_actor=None,
        measurement_method=None,
        applicable_date=None,
        table_headers=None,
        table_conditions=None,
        table_headers_verified=False,
        measurement_method_verified=False,
        applicable_date_verified=False,
        eligible_for_technical_context=True,
        eligible_for_readiness_evidence=True,
        eligible_for_binding_technical_findings=False,
        eligible_for_citation=False,
        bandwidth_threshold_established=False,
        latency_threshold_established=False,
        packet_loss_threshold_established=False,
        reliability_threshold_established=False,
        human_validation_required_for_threshold_activation=True,
    )


def assert_threshold_not_activatable(evidence: VerifiedECAQoSSourceEvidence) -> None:
    if not isinstance(evidence, VerifiedECAQoSSourceEvidence):
        raise TypeError("evidence must be VerifiedECAQoSSourceEvidence")
    raise ECAQoSEvidenceError(
        "QoS threshold cannot be activated until all ten exact-evidence requirements are complete"
    )
