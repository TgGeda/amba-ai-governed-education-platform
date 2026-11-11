from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


_ALLOWED_DISPOSITIONS = frozenset(
    {"approve", "approve_with_redactions", "reject", "revoke"}
)
_ALLOWED_REVIEWER_ROLES = frozenset({"teacher", "school_administrator"})


@dataclass(frozen=True, slots=True)
class ReviewDecisionHistoryItem:
    review_id: str
    disposition: str
    reviewer_role: str
    rationale: str
    redactions: tuple[str, ...]
    supersedes_review_id: str | None
    decided_at: str
    receipt_id: str
    published_at: str | None
    effective_text: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReviewItemViewModel:
    document_id: int
    document_title: str
    chunk_id: int
    chunk_text: str
    source_digest: str
    risk_findings: tuple[str, ...]
    current_status: str
    permitted_operations: tuple[str, ...]
    restricted_operations: tuple[str, ...]
    proposed_redactions: tuple[str, ...]
    previous_reviews: tuple[ReviewDecisionHistoryItem, ...]
    effective_review_id: str | None
    effective_text: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReviewActionRequest:
    subject_id: str
    document_id: int
    disposition: str
    reviewer_role: str
    rationale: str
    redactions: tuple[str, ...] = ()
    supersedes_review_id: str | None = None
    operation: str = "learning.tutor.answer"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReviewActionRequest":
        raw_redactions = data.get("redactions") or ()
        if isinstance(raw_redactions, str):
            redactions = tuple(
                line.strip()
                for line in raw_redactions.splitlines()
                if line.strip()
            )
        else:
            redactions = tuple(
                str(value).strip()
                for value in raw_redactions
                if str(value).strip()
            )
        request = cls(
            subject_id=str(data["subject_id"]).strip(),
            document_id=int(data["document_id"]),
            disposition=str(data["disposition"]).strip(),
            reviewer_role=str(data["reviewer_role"]).strip(),
            rationale=str(data["rationale"]).strip(),
            redactions=redactions,
            supersedes_review_id=(
                str(data["supersedes_review_id"]).strip()
                if data.get("supersedes_review_id")
                else None
            ),
            operation=str(
                data.get("operation") or "learning.tutor.answer"
            ).strip(),
        )
        request.validate()
        return request

    def validate(self) -> None:
        if not self.subject_id:
            raise ValueError("subject_id is required")
        if self.document_id <= 0:
            raise ValueError("document_id must be positive")
        if self.disposition not in _ALLOWED_DISPOSITIONS:
            raise ValueError(f"unsupported review disposition: {self.disposition}")
        if self.reviewer_role not in _ALLOWED_REVIEWER_ROLES:
            raise ValueError("reviewer role is unauthorized")
        if not self.rationale:
            raise ValueError("rationale is required")
        if self.disposition == "approve_with_redactions" and not self.redactions:
            raise ValueError("approve_with_redactions requires exact redactions")
        if self.disposition != "approve_with_redactions" and self.redactions:
            raise ValueError(
                "redactions are valid only for approve_with_redactions"
            )
        if self.disposition == "revoke" and not self.supersedes_review_id:
            raise ValueError("revoke requires the current effective review")
        if not self.operation.startswith("learning."):
            raise ValueError("operation must be a registered learning operation")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
