from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from types import MappingProxyType
from typing import Any, Mapping

SOURCE_ID = "ETH-CYBERSECURITY-POLICY-2024"
VERSION_ID = "2024-06"
PUBLICATION_DATE = "June 2024"
ADMINISTERING_AUTHORITY = "Information Network Security Administration"
SOURCE_CLASS = "national_policy"
BINDING_LEVEL = "national_policy"
ARTIFACT_SHA256 = "624b0db098bff6cd075e92c2fd44e0a082b892a53bb4ea47952fb0850e12c62e"
DOCUMENT_TITLE = "The Federal Democratic Republic of Ethiopia National Cybersecurity Policy"


class CybersecurityPolicyRecordError(ValueError):
    pass


class CandidateRecordStatus(str, Enum):
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class CandidateLocatorStatus(str, Enum):
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class QuarantinedCybersecurityPolicyCandidate:
    """A policy-context/readiness candidate with no authority-bearing locator.

    The candidate is intentionally not a PolicyRecord. It cannot become
    citation-eligible or support a binding legal finding until a deterministic
    source locator, source-derived excerpt, excerpt digest, and human review
    are complete.
    """

    candidate_id: str
    source_id: str
    version_id: str
    document_title: str
    publication_date: str
    administering_authority: str
    source_class: str
    binding_level: str
    artifact_sha256: str
    theme: str
    reviewed_factual_boundary: str
    record_status: CandidateRecordStatus
    locator_status: CandidateLocatorStatus
    official_locator: None
    page_start: None
    page_end: None
    exact_source_excerpt: None
    exact_source_excerpt_sha256: None
    eligible_for_policy_context: bool
    eligible_for_readiness_evidence: bool
    eligible_for_binding_legal_findings: bool
    eligible_for_citation: bool
    national_binding_status: bool
    legal_effect: bool
    human_review_required: bool
    establishes_criminal_offence: bool
    establishes_statutory_penalty: bool
    establishes_valid_guardian_consent: bool
    establishes_binding_technical_threshold: bool
    establishes_automatic_statutory_block: bool

    def __post_init__(self) -> None:
        if not self.candidate_id.startswith("ETH-CYBERSECURITY-POLICY-"):
            raise CybersecurityPolicyRecordError("candidate_id must use the cybersecurity policy namespace")
        if self.source_id != SOURCE_ID or self.version_id != VERSION_ID:
            raise CybersecurityPolicyRecordError("candidate source identity is invalid")
        if self.document_title != DOCUMENT_TITLE:
            raise CybersecurityPolicyRecordError("candidate document title is invalid")
        if self.publication_date != PUBLICATION_DATE:
            raise CybersecurityPolicyRecordError("candidate publication date is invalid")
        if self.administering_authority != ADMINISTERING_AUTHORITY:
            raise CybersecurityPolicyRecordError("candidate administering authority is invalid")
        if self.source_class != SOURCE_CLASS or self.binding_level != BINDING_LEVEL:
            raise CybersecurityPolicyRecordError("candidate classification is invalid")
        if self.artifact_sha256 != ARTIFACT_SHA256:
            raise CybersecurityPolicyRecordError("candidate artifact digest is invalid")
        try:
            if len(self.artifact_sha256) != 64:
                raise ValueError
            int(self.artifact_sha256, 16)
        except ValueError as error:
            raise CybersecurityPolicyRecordError("artifact_sha256 must be a 64-character hexadecimal digest") from error
        if not self.theme.strip() or not self.reviewed_factual_boundary.strip():
            raise CybersecurityPolicyRecordError("theme and factual boundary must be non-empty")
        if self.record_status is not CandidateRecordStatus.HUMAN_REVIEW_REQUIRED:
            raise CybersecurityPolicyRecordError("candidate must remain human_review_required")
        if self.locator_status is not CandidateLocatorStatus.UNRESOLVED:
            raise CybersecurityPolicyRecordError("candidate locator must remain unresolved")
        for value in (
            self.official_locator,
            self.page_start,
            self.page_end,
            self.exact_source_excerpt,
            self.exact_source_excerpt_sha256,
        ):
            if value is not None:
                raise CybersecurityPolicyRecordError("unverified locator and excerpt fields must remain null")
        if self.eligible_for_policy_context is not True:
            raise CybersecurityPolicyRecordError("candidate must remain eligible for policy context")
        if self.eligible_for_readiness_evidence is not True:
            raise CybersecurityPolicyRecordError("candidate must remain eligible for readiness evidence")
        if self.eligible_for_binding_legal_findings is not False:
            raise CybersecurityPolicyRecordError("candidate cannot support binding legal findings")
        if self.eligible_for_citation is not False:
            raise CybersecurityPolicyRecordError("unlocated candidate cannot be citation eligible")
        if self.national_binding_status is not False or self.legal_effect is not False:
            raise CybersecurityPolicyRecordError("candidate cannot claim national binding status or legal effect")
        if self.human_review_required is not True:
            raise CybersecurityPolicyRecordError("candidate must require human review")
        prohibited = (
            self.establishes_criminal_offence,
            self.establishes_statutory_penalty,
            self.establishes_valid_guardian_consent,
            self.establishes_binding_technical_threshold,
            self.establishes_automatic_statutory_block,
        )
        if any(value is not False for value in prohibited):
            raise CybersecurityPolicyRecordError("prohibited legal and technical claims must remain false")

    @property
    def boundary_sha256(self) -> str:
        return hashlib.sha256(self.reviewed_factual_boundary.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_id": self.source_id,
            "version_id": self.version_id,
            "document_title": self.document_title,
            "publication_date": self.publication_date,
            "administering_authority": self.administering_authority,
            "source_class": self.source_class,
            "binding_level": self.binding_level,
            "artifact_sha256": self.artifact_sha256,
            "theme": self.theme,
            "reviewed_factual_boundary": self.reviewed_factual_boundary,
            "reviewed_factual_boundary_sha256": self.boundary_sha256,
            "record_status": self.record_status.value,
            "locator_status": self.locator_status.value,
            "official_locator": self.official_locator,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "exact_source_excerpt": self.exact_source_excerpt,
            "exact_source_excerpt_sha256": self.exact_source_excerpt_sha256,
            "eligible_for_policy_context": self.eligible_for_policy_context,
            "eligible_for_readiness_evidence": self.eligible_for_readiness_evidence,
            "eligible_for_binding_legal_findings": self.eligible_for_binding_legal_findings,
            "eligible_for_citation": self.eligible_for_citation,
            "national_binding_status": self.national_binding_status,
            "legal_effect": self.legal_effect,
            "human_review_required": self.human_review_required,
            "prohibited_claims": {
                "criminal_offence": self.establishes_criminal_offence,
                "statutory_penalty": self.establishes_statutory_penalty,
                "valid_guardian_consent": self.establishes_valid_guardian_consent,
                "binding_technical_threshold": self.establishes_binding_technical_threshold,
                "automatic_statutory_block": self.establishes_automatic_statutory_block,
            },
        }


_THEMES: tuple[tuple[str, str, str], ...] = (
    ("CYBERSECURITY-GOVERNANCE", "cybersecurity governance", "The policy may support cybersecurity-governance context and readiness evidence."),
    ("SHARED-RESPONSIBILITY", "shared responsibility", "The policy may support shared-responsibility context and readiness evidence."),
    ("PRIVACY-SECURITY-BALANCE", "privacy and security balance", "The policy may support context about balancing privacy and security."),
    ("DATA-LIFECYCLE-GOVERNANCE", "data-lifecycle governance", "The policy may support data-lifecycle-governance context and readiness evidence."),
    ("EDUCATION-CAPACITY-BUILDING", "education and capacity building", "The policy may support education and cybersecurity-capacity-building context."),
    ("INDIGENOUS-RESEARCH", "indigenous research", "The policy may support indigenous cybersecurity research context and readiness evidence."),
    ("CRITICAL-INFRASTRUCTURE-RESILIENCE", "critical-infrastructure resilience", "The policy may support critical-infrastructure-resilience context and readiness evidence."),
    ("INSTITUTIONAL-COORDINATION", "institutional coordination", "The policy may support institutional-coordination context and readiness evidence."),
    ("MONITORING-EVALUATION", "monitoring and evaluation", "The policy may support monitoring-and-evaluation context and readiness evidence."),
)


def quarantined_cybersecurity_policy_candidates() -> tuple[QuarantinedCybersecurityPolicyCandidate, ...]:
    records = tuple(
        QuarantinedCybersecurityPolicyCandidate(
            candidate_id=f"ETH-CYBERSECURITY-POLICY-{suffix}",
            source_id=SOURCE_ID,
            version_id=VERSION_ID,
            document_title=DOCUMENT_TITLE,
            publication_date=PUBLICATION_DATE,
            administering_authority=ADMINISTERING_AUTHORITY,
            source_class=SOURCE_CLASS,
            binding_level=BINDING_LEVEL,
            artifact_sha256=ARTIFACT_SHA256,
            theme=theme,
            reviewed_factual_boundary=boundary,
            record_status=CandidateRecordStatus.HUMAN_REVIEW_REQUIRED,
            locator_status=CandidateLocatorStatus.UNRESOLVED,
            official_locator=None,
            page_start=None,
            page_end=None,
            exact_source_excerpt=None,
            exact_source_excerpt_sha256=None,
            eligible_for_policy_context=True,
            eligible_for_readiness_evidence=True,
            eligible_for_binding_legal_findings=False,
            eligible_for_citation=False,
            national_binding_status=False,
            legal_effect=False,
            human_review_required=True,
            establishes_criminal_offence=False,
            establishes_statutory_penalty=False,
            establishes_valid_guardian_consent=False,
            establishes_binding_technical_threshold=False,
            establishes_automatic_statutory_block=False,
        )
        for suffix, theme, boundary in _THEMES
    )
    ids = tuple(record.candidate_id for record in records)
    if len(records) != 9 or len(ids) != len(set(ids)):
        raise CybersecurityPolicyRecordError("cybersecurity candidate set must contain 9 unique records")
    return records


def cybersecurity_policy_candidates_by_id() -> Mapping[str, QuarantinedCybersecurityPolicyCandidate]:
    return MappingProxyType({record.candidate_id: record for record in quarantined_cybersecurity_policy_candidates()})


def assert_not_promotable_to_policy_record(record: QuarantinedCybersecurityPolicyCandidate) -> None:
    if not isinstance(record, QuarantinedCybersecurityPolicyCandidate):
        raise TypeError("record must be a QuarantinedCybersecurityPolicyCandidate")
    raise CybersecurityPolicyRecordError(
        "cybersecurity thematic candidate cannot become a PolicyRecord until a deterministic "
        "source locator, source-derived excerpt, excerpt SHA-256, and human review are complete"
    )
