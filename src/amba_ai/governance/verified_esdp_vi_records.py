from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from types import MappingProxyType
from typing import Any, Mapping

SOURCE_ID = "ETH-ESDP-VI-2021"
VERSION_ID = "2021"
PROGRAMME_PERIOD = "2020/21–2024/25"
CURRENT_CLASSIFICATION = "historical_or_completed"
SOURCE_CLASS = "sector_strategy"
BINDING_LEVEL = "national_policy"
ARTIFACT_SHA256 = "f77622ff64c29d03d1e090f5c401880e3b8cda6015f6379d2afb707a0a9c7678"
DOCUMENT_TITLE = "Education Sector Development Programme VI"


class ESDPVIRecordError(ValueError):
    pass


class CandidateRecordStatus(str, Enum):
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class CandidateLocatorStatus(str, Enum):
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class QuarantinedESDPVICandidate:
    """Historical/context candidate awaiting deterministic source verification.

    This is intentionally not a PolicyRecord. Artifact integrity establishes
    the source file, but does not establish an exact provision, current-policy
    status, legal applicability, or citation eligibility.
    """

    candidate_id: str
    source_id: str
    version_id: str
    document_title: str
    programme_period: str
    current_classification: str
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
    eligible_for_historical_context: bool
    eligible_for_policy_context: bool
    eligible_for_readiness_evidence: bool
    eligible_for_current_programme_claim: bool
    eligible_for_binding_legal_findings: bool
    eligible_for_project_enforcement: bool
    eligible_for_citation: bool
    national_binding_status: bool
    legal_effect: bool
    human_review_required: bool
    historical_qualification_required: bool
    current_after_2024_25: bool
    verified_successor_identified: bool
    establishes_current_national_education_programme: bool
    establishes_binding_legal_obligation: bool
    establishes_statutory_offence: bool
    establishes_statutory_penalty: bool
    establishes_automatic_project_authorization: bool
    establishes_automatic_project_block: bool

    def __post_init__(self) -> None:
        if not self.candidate_id.startswith("ETH-ESDP-VI-"):
            raise ESDPVIRecordError("candidate_id must use the ESDP VI namespace")
        if self.source_id != SOURCE_ID or self.version_id != VERSION_ID:
            raise ESDPVIRecordError("candidate source identity is invalid")
        if self.document_title != DOCUMENT_TITLE:
            raise ESDPVIRecordError("candidate document title is invalid")
        if self.programme_period != PROGRAMME_PERIOD:
            raise ESDPVIRecordError("candidate programme period is invalid")
        if self.current_classification != CURRENT_CLASSIFICATION:
            raise ESDPVIRecordError("candidate current classification is invalid")
        if self.source_class != SOURCE_CLASS or self.binding_level != BINDING_LEVEL:
            raise ESDPVIRecordError("candidate classification is invalid")
        if self.artifact_sha256 != ARTIFACT_SHA256:
            raise ESDPVIRecordError("candidate artifact digest is invalid")
        try:
            if len(self.artifact_sha256) != 64:
                raise ValueError
            int(self.artifact_sha256, 16)
        except ValueError as error:
            raise ESDPVIRecordError(
                "artifact_sha256 must be a 64-character hexadecimal digest"
            ) from error
        if not self.theme.strip() or not self.reviewed_factual_boundary.strip():
            raise ESDPVIRecordError("theme and factual boundary must be non-empty")
        if self.record_status is not CandidateRecordStatus.HUMAN_REVIEW_REQUIRED:
            raise ESDPVIRecordError("candidate must remain human_review_required")
        if self.locator_status is not CandidateLocatorStatus.UNRESOLVED:
            raise ESDPVIRecordError("candidate locator must remain unresolved")
        for value in (
            self.official_locator,
            self.page_start,
            self.page_end,
            self.exact_source_excerpt,
            self.exact_source_excerpt_sha256,
        ):
            if value is not None:
                raise ESDPVIRecordError(
                    "unverified locator and excerpt fields must remain null"
                )
        required_true = (
            self.eligible_for_historical_context,
            self.eligible_for_policy_context,
            self.eligible_for_readiness_evidence,
            self.human_review_required,
            self.historical_qualification_required,
        )
        if any(value is not True for value in required_true):
            raise ESDPVIRecordError(
                "historical context, policy context, readiness evidence, human review, "
                "and historical qualification must remain enabled"
            )
        required_false = (
            self.eligible_for_current_programme_claim,
            self.eligible_for_binding_legal_findings,
            self.eligible_for_project_enforcement,
            self.eligible_for_citation,
            self.national_binding_status,
            self.legal_effect,
            self.current_after_2024_25,
            self.verified_successor_identified,
            self.establishes_current_national_education_programme,
            self.establishes_binding_legal_obligation,
            self.establishes_statutory_offence,
            self.establishes_statutory_penalty,
            self.establishes_automatic_project_authorization,
            self.establishes_automatic_project_block,
        )
        if any(value is not False for value in required_false):
            raise ESDPVIRecordError(
                "current-programme, binding, citation, legal-effect, successor, and automatic-action claims must remain false"
            )

    @property
    def boundary_sha256(self) -> str:
        return hashlib.sha256(
            self.reviewed_factual_boundary.encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_id": self.source_id,
            "version_id": self.version_id,
            "document_title": self.document_title,
            "programme_period": self.programme_period,
            "current_classification": self.current_classification,
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
            "eligible_for_historical_context": self.eligible_for_historical_context,
            "eligible_for_policy_context": self.eligible_for_policy_context,
            "eligible_for_readiness_evidence": self.eligible_for_readiness_evidence,
            "eligible_for_current_programme_claim": self.eligible_for_current_programme_claim,
            "eligible_for_binding_legal_findings": self.eligible_for_binding_legal_findings,
            "eligible_for_project_enforcement": self.eligible_for_project_enforcement,
            "eligible_for_citation": self.eligible_for_citation,
            "national_binding_status": self.national_binding_status,
            "legal_effect": self.legal_effect,
            "human_review_required": self.human_review_required,
            "historical_qualification_required": self.historical_qualification_required,
            "current_after_2024_25": self.current_after_2024_25,
            "verified_successor_identified": self.verified_successor_identified,
            "prohibited_claims": {
                "current_national_education_programme": self.establishes_current_national_education_programme,
                "binding_legal_obligation": self.establishes_binding_legal_obligation,
                "statutory_offence": self.establishes_statutory_offence,
                "statutory_penalty": self.establishes_statutory_penalty,
                "automatic_project_authorization": self.establishes_automatic_project_authorization,
                "automatic_project_block": self.establishes_automatic_project_block,
            },
        }


_THEMES: tuple[tuple[str, str, str], ...] = (
    ("EDUCATION-SECTOR-CONTEXT", "education-sector context", "ESDP VI may support historical education-sector context for the 2020/21–2024/25 programme period."),
    ("DIGITIZATION-CONTEXT", "digitization context", "ESDP VI may support historical education-sector digitization context."),
    ("QUALITY-EQUITY-ANALYSIS", "quality and equity analysis", "ESDP VI may support historical analysis of education quality and equity."),
    ("CURRICULUM-REFORM", "curriculum reform", "ESDP VI may support historical curriculum-reform context."),
    ("TEACHER-DEVELOPMENT", "teacher development", "ESDP VI may support historical teacher-development context."),
    ("INFRASTRUCTURE-ANALYSIS", "infrastructure analysis", "ESDP VI may support historical education-infrastructure analysis."),
    ("PROJECT-READINESS-EVIDENCE", "project-level readiness evidence", "ESDP VI may support project-level readiness evidence when explicitly qualified as historical or completed."),
)


def quarantined_esdp_vi_candidates() -> tuple[QuarantinedESDPVICandidate, ...]:
    records = tuple(
        QuarantinedESDPVICandidate(
            candidate_id=f"ETH-ESDP-VI-{suffix}",
            source_id=SOURCE_ID,
            version_id=VERSION_ID,
            document_title=DOCUMENT_TITLE,
            programme_period=PROGRAMME_PERIOD,
            current_classification=CURRENT_CLASSIFICATION,
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
            eligible_for_historical_context=True,
            eligible_for_policy_context=True,
            eligible_for_readiness_evidence=True,
            eligible_for_current_programme_claim=False,
            eligible_for_binding_legal_findings=False,
            eligible_for_project_enforcement=False,
            eligible_for_citation=False,
            national_binding_status=False,
            legal_effect=False,
            human_review_required=True,
            historical_qualification_required=True,
            current_after_2024_25=False,
            verified_successor_identified=False,
            establishes_current_national_education_programme=False,
            establishes_binding_legal_obligation=False,
            establishes_statutory_offence=False,
            establishes_statutory_penalty=False,
            establishes_automatic_project_authorization=False,
            establishes_automatic_project_block=False,
        )
        for suffix, theme, boundary in _THEMES
    )
    ids = tuple(record.candidate_id for record in records)
    if len(records) != 7 or len(ids) != len(set(ids)):
        raise ESDPVIRecordError("ESDP VI candidate set must contain 7 unique records")
    return records


def esdp_vi_candidates_by_id() -> Mapping[str, QuarantinedESDPVICandidate]:
    return MappingProxyType(
        {record.candidate_id: record for record in quarantined_esdp_vi_candidates()}
    )


def assert_not_promotable_to_policy_record(record: QuarantinedESDPVICandidate) -> None:
    if not isinstance(record, QuarantinedESDPVICandidate):
        raise TypeError("record must be a QuarantinedESDPVICandidate")
    raise ESDPVIRecordError(
        "ESDP VI thematic candidate cannot become a PolicyRecord until a deterministic "
        "source locator, source-derived excerpt, excerpt SHA-256, human review, and "
        "historical qualification are complete"
    )
