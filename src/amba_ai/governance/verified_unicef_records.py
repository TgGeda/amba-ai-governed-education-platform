from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from types import MappingProxyType
from typing import Any, Mapping


SOURCE_ID = "UNICEF-AI-CHILDREN-3.0"
VERSION_ID = "3.0"
PUBLICATION_DATE = "December 2025"
SOURCE_CLASS = "international_guidance"
BINDING_LEVEL = "international_guidance"
ARTIFACT_SHA256 = "1d218b79b894402bda57d97527ef7ea015b0642003ba582d6259b050d0a548ea"
DOCUMENT_TITLE = "Guidance on AI and Children 3.0"


class UNICEFRecordError(ValueError):
    pass


class CandidateRecordStatus(str, Enum):
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class CandidateLocatorStatus(str, Enum):
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class QuarantinedUNICEFSupportingEvidenceRecord:
    """A non-citable thematic candidate awaiting deterministic source location.

    This is deliberately not a PolicyRecord. Promotion to PolicyRecord is
    prohibited until a deterministic source locator is established and the
    candidate passes human review.
    """

    candidate_id: str
    source_id: str
    version_id: str
    document_title: str
    publication_date: str
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
    national_binding_status: bool
    eligible_for_binding_findings: bool
    eligible_for_supporting_evidence: bool
    eligible_for_citation: bool
    independent_ethiopian_legal_violation: bool
    human_review_required: bool

    def __post_init__(self) -> None:
        if not self.candidate_id.startswith("UNICEF-AI-CHILDREN-"):
            raise UNICEFRecordError("candidate_id must use the UNICEF candidate namespace")
        if self.source_id != SOURCE_ID or self.version_id != VERSION_ID:
            raise UNICEFRecordError("candidate source identity is invalid")
        if self.artifact_sha256 != ARTIFACT_SHA256:
            raise UNICEFRecordError("candidate artifact digest is invalid")
        if len(self.artifact_sha256) != 64:
            raise UNICEFRecordError("artifact_sha256 must contain 64 hexadecimal characters")
        try:
            int(self.artifact_sha256, 16)
        except ValueError as error:
            raise UNICEFRecordError("artifact_sha256 must be hexadecimal") from error
        if not self.theme.strip() or not self.reviewed_factual_boundary.strip():
            raise UNICEFRecordError("theme and factual boundary must be non-empty")
        if self.record_status is not CandidateRecordStatus.HUMAN_REVIEW_REQUIRED:
            raise UNICEFRecordError("candidate must remain human_review_required")
        if self.locator_status is not CandidateLocatorStatus.UNRESOLVED:
            raise UNICEFRecordError("candidate locator must remain unresolved")
        for value in (
            self.official_locator,
            self.page_start,
            self.page_end,
            self.exact_source_excerpt,
            self.exact_source_excerpt_sha256,
        ):
            if value is not None:
                raise UNICEFRecordError("unverified locator and excerpt fields must remain null")
        if self.national_binding_status is not False:
            raise UNICEFRecordError("national_binding_status must be false")
        if self.eligible_for_binding_findings is not False:
            raise UNICEFRecordError("eligible_for_binding_findings must be false")
        if self.eligible_for_citation is not False:
            raise UNICEFRecordError("unlocated candidate must not be citation eligible")
        if self.eligible_for_supporting_evidence is not True:
            raise UNICEFRecordError("candidate must remain eligible for future supporting evidence")
        if self.independent_ethiopian_legal_violation is not False:
            raise UNICEFRecordError("candidate cannot establish an Ethiopian legal violation")
        if self.human_review_required is not True:
            raise UNICEFRecordError("candidate must require human review")

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
            "national_binding_status": self.national_binding_status,
            "eligible_for_binding_findings": self.eligible_for_binding_findings,
            "eligible_for_supporting_evidence": self.eligible_for_supporting_evidence,
            "eligible_for_citation": self.eligible_for_citation,
            "independent_ethiopian_legal_violation": self.independent_ethiopian_legal_violation,
            "human_review_required": self.human_review_required,
        }


_THEMES: tuple[tuple[str, str, str], ...] = (
    ("CHILD-CENTRED-SAFEGUARDS", "child-centred AI safeguards", "The guidance may support child-centred AI safeguards."),
    ("PRIVACY-DATA-GOVERNANCE", "privacy and data governance", "The guidance may support privacy and data-governance safeguards for children."),
    ("HUMAN-OVERSIGHT", "human oversight", "The guidance may support meaningful human oversight of AI affecting children."),
    ("COMMERCIAL-EXPLOITATION", "protection against commercial exploitation", "The guidance may support protection of children against commercial exploitation."),
    ("INCLUSION", "inclusion", "The guidance may support inclusive AI design and access for children."),
    ("EDTECH-ASSESSMENT", "EdTech assessment", "The guidance may support assessment of educational technology affecting children."),
    ("LOCAL-OFFLINE-OPERATION", "local and offline operation", "The guidance may support local and offline operation where appropriate for children and their contexts."),
    ("CHILD-PARTICIPATION", "child participation", "The guidance may support participation of children in decisions about AI that affects them."),
)


def quarantined_unicef_supporting_evidence_records() -> tuple[QuarantinedUNICEFSupportingEvidenceRecord, ...]:
    records = tuple(
        QuarantinedUNICEFSupportingEvidenceRecord(
            candidate_id=f"UNICEF-AI-CHILDREN-{suffix}",
            source_id=SOURCE_ID,
            version_id=VERSION_ID,
            document_title=DOCUMENT_TITLE,
            publication_date=PUBLICATION_DATE,
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
            national_binding_status=False,
            eligible_for_binding_findings=False,
            eligible_for_supporting_evidence=True,
            eligible_for_citation=False,
            independent_ethiopian_legal_violation=False,
            human_review_required=True,
        )
        for suffix, theme, boundary in _THEMES
    )
    ids = tuple(record.candidate_id for record in records)
    if len(ids) != 8 or len(ids) != len(set(ids)):
        raise UNICEFRecordError("UNICEF candidate record set must contain 8 unique records")
    return records


def unicef_candidate_records_by_id() -> Mapping[str, QuarantinedUNICEFSupportingEvidenceRecord]:
    return MappingProxyType(
        {record.candidate_id: record for record in quarantined_unicef_supporting_evidence_records()}
    )


def assert_not_promotable_to_policy_record(
    record: QuarantinedUNICEFSupportingEvidenceRecord,
) -> None:
    if not isinstance(record, QuarantinedUNICEFSupportingEvidenceRecord):
        raise TypeError("record must be a QuarantinedUNICEFSupportingEvidenceRecord")
    raise UNICEFRecordError(
        "UNICEF thematic candidate cannot become a PolicyRecord until a deterministic "
        "source locator, source-derived excerpt, excerpt digest, and human review are complete"
    )
