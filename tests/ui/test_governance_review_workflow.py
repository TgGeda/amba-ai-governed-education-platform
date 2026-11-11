from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from PySide6.QtCore import QSettings
from amba_ai.governance.runtime.review_models import GovernanceReviewDecision, ReviewDisposition
from amba_ai.ui.features.governance_review import GovernanceReviewManager, GovernanceReviewWidget


class FakeReviewService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def decide(self, **kwargs: Any) -> GovernanceReviewDecision:
        self.calls.append(dict(kwargs))
        disposition = ReviewDisposition(kwargs["disposition"])
        return GovernanceReviewDecision(
            review_id="EDU-REVIEW-001",
            subject_type="chunk",
            subject_id=str(kwargs["subject_id"]),
            document_id=int(kwargs["document_id"]),
            disposition=disposition,
            reviewer_role=str(kwargs["reviewer_role"]),
            rationale=str(kwargs["rationale"]),
            redactions=tuple(kwargs.get("redactions") or ()),
            supersedes_review_id=kwargs.get("supersedes_review_id"),
            decided_at="2026-11-10T00:00:00Z",
            receipt_id="EDU-GOV-RECEIPT-001",
            published_at="2026-11-10T00:00:01Z",
            effective_text="[REDACTED]" if kwargs.get("redactions") else None,
        )


def test_manager_validates_and_calls_review_service(qtbot) -> None:
    service = FakeReviewService()
    manager = GovernanceReviewManager(
        review_service=service,
        services=SimpleNamespace(),
    )
    with qtbot.waitSignal(manager.reviewCompleted, timeout=3000):
        manager.submit_review(
            {
                "subject_id": "101",
                "document_id": 1,
                "disposition": "approve",
                "reviewer_role": "teacher",
                "rationale": "Verified for teaching",
            }
        )
    assert len(service.calls) == 1
    assert service.calls[0]["subject_type"] == "chunk"


def test_redactions_are_one_exact_string_per_line(qtbot) -> None:
    service = FakeReviewService()
    manager = GovernanceReviewManager(
        review_service=service,
        services=SimpleNamespace(),
    )
    with qtbot.waitSignal(manager.reviewCompleted, timeout=3000):
        manager.submit_review(
            {
                "subject_id": "101",
                "document_id": 1,
                "disposition": "approve_with_redactions",
                "reviewer_role": "teacher",
                "rationale": "Remove learner identifiers",
                "redactions": "learner@example.com\nStudent ID: ABC-123",
            }
        )
    assert service.calls[0]["redactions"] == (
        "learner@example.com",
        "Student ID: ABC-123",
    )


def test_manager_rejects_invalid_request_before_service_call(qtbot) -> None:
    service = FakeReviewService()
    manager = GovernanceReviewManager(
        review_service=service,
        services=SimpleNamespace(),
    )
    with qtbot.waitSignal(manager.reviewFailed, timeout=1000):
        manager.submit_review(
            {
                "subject_id": "101",
                "document_id": 1,
                "disposition": "revoke",
                "reviewer_role": "learner",
                "rationale": "",
            }
        )
    assert service.calls == []


def test_qss_uses_existing_learning_palette() -> None:
    qss = Path(
        "src/amba_ai/ui/features/governance_review/governance_review.qss"
    ).read_text(encoding="utf-8")
    for color in ("#090D16", "#0F172A", "#020617", "#334155", "#2DD4BF"):
        assert color in qss


def test_manager_has_no_direct_review_mutation() -> None:
    source = Path(
        "src/amba_ai/ui/features/governance_review/review_manager.py"
    ).read_text(encoding="utf-8")
    assert "self.review_service.decide" in source
    assert ".append_review(" not in source
    assert ".publish_review(" not in source
    assert ".unpublish_review(" not in source
