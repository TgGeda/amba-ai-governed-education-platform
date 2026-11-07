from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from types import MappingProxyType
from typing import Any, Mapping

SOURCE_ID = "ETH-STME-POLICY"
VERSION_ID = "undated-main-document"
DOCUMENT_TITLE = "Strategic Policy for National Science, Technology and Mathematics Education"
DOCUMENT_SUBTITLE = "Main Document"
SOURCE_CLASS = "strategic_policy_supporting_document"
BINDING_LEVEL = "policy_context"
FORMAL_ADOPTION_STATUS = "unverified"
ARTIFACT_SHA256 = "d5a6fb50ecd5b324d5d0eb1e1cb0eabd1744acd0423ff434127b76b4835e0260"


class STMEContextEvidenceError(ValueError):
    pass


class EvidenceActivationStatus(str, Enum):
    VERIFIED_CONTEXT_BOUNDARY = "verified_context_boundary"


class LocatorVerificationStatus(str, Enum):
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True, slots=True)
class VerifiedSTMEContextEvidence:
    """Verified context boundary without an invented provision-level locator.

    The object is complete for contextual use and explicitly ineligible for
    citation or binding findings until locator and excerpt verification exists.
    """

    evidence_id: str
    source_id: str
    version_id: str
    document_title: str
    document_subtitle: str
    source_class: str
    binding_level: str
    formal_adoption_status: str
    artifact_sha256: str
    theme: str
    reviewed_factual_boundary: str
    activation_status: EvidenceActivationStatus
    locator_verification_status: LocatorVerificationStatus
    official_locator: None
    page_start: None
    page_end: None
    exact_source_excerpt: None
    exact_source_excerpt_sha256: None
    eligible_for_policy_context: bool
    eligible_for_readiness_evidence: bool
    eligible_for_binding_findings: bool
    eligible_for_project_enforcement: bool
    eligible_for_citation: bool
    national_binding_status: bool
    legal_effect: bool
    formal_adoption_claimed: bool
    human_validation_required_for_locator_activation: bool

    def __post_init__(self) -> None:
        if not self.evidence_id.startswith("ETH-STME-CONTEXT-"):
            raise STMEContextEvidenceError("evidence_id must use the STME context namespace")
        if self.source_id != SOURCE_ID or self.version_id != VERSION_ID:
            raise STMEContextEvidenceError("source identity is invalid")
        if self.document_title != DOCUMENT_TITLE or self.document_subtitle != DOCUMENT_SUBTITLE:
            raise STMEContextEvidenceError("document identity is invalid")
        if self.source_class != SOURCE_CLASS or self.binding_level != BINDING_LEVEL:
            raise STMEContextEvidenceError("evidence classification is invalid")
        if self.formal_adoption_status != FORMAL_ADOPTION_STATUS:
            raise STMEContextEvidenceError("formal adoption status must remain unverified")
        if self.artifact_sha256 != ARTIFACT_SHA256:
            raise STMEContextEvidenceError("artifact digest is invalid")
        try:
            if len(self.artifact_sha256) != 64:
                raise ValueError
            int(self.artifact_sha256, 16)
        except ValueError as error:
            raise STMEContextEvidenceError("artifact_sha256 must be a 64-character hexadecimal digest") from error
        if not self.theme.strip() or not self.reviewed_factual_boundary.strip():
            raise STMEContextEvidenceError("theme and factual boundary must be non-empty")
        if self.activation_status is not EvidenceActivationStatus.VERIFIED_CONTEXT_BOUNDARY:
            raise STMEContextEvidenceError("activation status must remain verified_context_boundary")
        if self.locator_verification_status is not LocatorVerificationStatus.NOT_ASSESSED:
            raise STMEContextEvidenceError("locator verification must remain not_assessed")
        for value in (
            self.official_locator,
            self.page_start,
            self.page_end,
            self.exact_source_excerpt,
            self.exact_source_excerpt_sha256,
        ):
            if value is not None:
                raise STMEContextEvidenceError("unverified locator and excerpt fields must remain null")
        if self.eligible_for_policy_context is not True or self.eligible_for_readiness_evidence is not True:
            raise STMEContextEvidenceError("context and readiness evidence eligibility must be true")
        prohibited = (
            self.eligible_for_binding_findings,
            self.eligible_for_project_enforcement,
            self.eligible_for_citation,
            self.national_binding_status,
            self.legal_effect,
            self.formal_adoption_claimed,
        )
        if any(value is not False for value in prohibited):
            raise STMEContextEvidenceError("binding, citation, legal-effect, and adoption claims must remain false")
        if self.human_validation_required_for_locator_activation is not True:
            raise STMEContextEvidenceError("human validation is required for locator activation")

    @property
    def boundary_sha256(self) -> str:
        return hashlib.sha256(self.reviewed_factual_boundary.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "version_id": self.version_id,
            "document_title": self.document_title,
            "document_subtitle": self.document_subtitle,
            "source_class": self.source_class,
            "binding_level": self.binding_level,
            "formal_adoption_status": self.formal_adoption_status,
            "artifact_sha256": self.artifact_sha256,
            "theme": self.theme,
            "reviewed_factual_boundary": self.reviewed_factual_boundary,
            "reviewed_factual_boundary_sha256": self.boundary_sha256,
            "activation_status": self.activation_status.value,
            "locator_verification_status": self.locator_verification_status.value,
            "official_locator": self.official_locator,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "exact_source_excerpt": self.exact_source_excerpt,
            "exact_source_excerpt_sha256": self.exact_source_excerpt_sha256,
            "eligible_for_policy_context": self.eligible_for_policy_context,
            "eligible_for_readiness_evidence": self.eligible_for_readiness_evidence,
            "eligible_for_binding_findings": self.eligible_for_binding_findings,
            "eligible_for_project_enforcement": self.eligible_for_project_enforcement,
            "eligible_for_citation": self.eligible_for_citation,
            "national_binding_status": self.national_binding_status,
            "legal_effect": self.legal_effect,
            "formal_adoption_claimed": self.formal_adoption_claimed,
            "human_validation_required_for_locator_activation": self.human_validation_required_for_locator_activation,
        }


_THEMES: tuple[tuple[str, str, str], ...] = (
    ("STEM-EDUCATION-CONTEXT", "science, technology, and mathematics education context", "The document may support science, technology, and mathematics education context."),
    ("CURRICULUM-REFORM", "curriculum-reform context", "The document may support curriculum-reform context."),
    ("TEACHER-DEVELOPMENT", "teacher-development context", "The document may support teacher-development context."),
    ("EDUCATIONAL-RESOURCES", "educational-resource analysis", "The document may support educational-resource analysis."),
    ("INCLUSION", "inclusion", "The document may support inclusion context in science, technology, and mathematics education."),
    ("MONITORING-EVALUATION", "monitoring and evaluation", "The document may support monitoring-and-evaluation context."),
    ("STAKEHOLDER-PARTNERSHIPS", "stakeholder partnerships", "The document may support stakeholder-partnership context."),
)


def verified_stme_context_evidence() -> tuple[VerifiedSTMEContextEvidence, ...]:
    records = tuple(
        VerifiedSTMEContextEvidence(
            evidence_id=f"ETH-STME-CONTEXT-{suffix}",
            source_id=SOURCE_ID,
            version_id=VERSION_ID,
            document_title=DOCUMENT_TITLE,
            document_subtitle=DOCUMENT_SUBTITLE,
            source_class=SOURCE_CLASS,
            binding_level=BINDING_LEVEL,
            formal_adoption_status=FORMAL_ADOPTION_STATUS,
            artifact_sha256=ARTIFACT_SHA256,
            theme=theme,
            reviewed_factual_boundary=boundary,
            activation_status=EvidenceActivationStatus.VERIFIED_CONTEXT_BOUNDARY,
            locator_verification_status=LocatorVerificationStatus.NOT_ASSESSED,
            official_locator=None,
            page_start=None,
            page_end=None,
            exact_source_excerpt=None,
            exact_source_excerpt_sha256=None,
            eligible_for_policy_context=True,
            eligible_for_readiness_evidence=True,
            eligible_for_binding_findings=False,
            eligible_for_project_enforcement=False,
            eligible_for_citation=False,
            national_binding_status=False,
            legal_effect=False,
            formal_adoption_claimed=False,
            human_validation_required_for_locator_activation=True,
        )
        for suffix, theme, boundary in _THEMES
    )
    ids = tuple(record.evidence_id for record in records)
    if len(records) != 7 or len(ids) != len(set(ids)):
        raise STMEContextEvidenceError("STME context evidence must contain 7 unique records")
    return records


def stme_context_evidence_by_id() -> Mapping[str, VerifiedSTMEContextEvidence]:
    return MappingProxyType({record.evidence_id: record for record in verified_stme_context_evidence()})


def assert_not_eligible_for_policy_record_activation(record: VerifiedSTMEContextEvidence) -> None:
    if not isinstance(record, VerifiedSTMEContextEvidence):
        raise TypeError("record must be VerifiedSTMEContextEvidence")
    raise STMEContextEvidenceError(
        "STME context evidence cannot be activated as a citation PolicyRecord until a deterministic "
        "source locator, source-derived excerpt, excerpt SHA-256, and human validation are complete"
    )
