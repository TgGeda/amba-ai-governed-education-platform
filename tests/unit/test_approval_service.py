from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

import pytest

from amba_ai.governance.approvals import (
    ApprovalProcessingResult,
    ApprovalRequest,
    ApprovalStatus,
)
from amba_ai.governance.models import GovernanceConfigurationError
from amba_ai.services.approval_service import ApprovalService


def make_request() -> ApprovalRequest:
    return ApprovalRequest.create(
        request_id="SYNTHETIC-APPROVAL-REQUEST",
        event_id="SYNTHETIC-EVENT",
        recommendation_id="SYNTHETIC-RECOMMENDATION",
        operation_id="commercial_purchase_request",
        requested_decision="approve_review_queue",
        target_role="school_administrator",
        mandate_id="SYNTHETIC-MANDATE",
        context_digest=hashlib.sha256(b"synthetic-context").hexdigest(),
        created_at="2026-06-01T11:50:00Z",
        expires_at="2026-06-01T13:00:00Z",
        idempotency_key="SYNTHETIC-APPROVAL-IDEMPOTENCY",
    )


@dataclass
class StaticApprovalProcessor:
    result: object
    call_count: int = 0
    received: dict[str, Any] | None = None

    def process_approval(
        self,
        request: ApprovalRequest,
        principal_id: str,
        plaintext_secret: str,
        approved: bool,
        rationale: str,
    ) -> Any:
        self.call_count += 1
        self.received = {
            "request": request,
            "principal_id": principal_id,
            "plaintext_secret": plaintext_secret,
            "approved": approved,
            "rationale": rationale,
        }
        return self.result


def make_result(request: ApprovalRequest) -> ApprovalProcessingResult:
    return ApprovalProcessingResult(
        status=ApprovalStatus.PENDING,
        request=request,
        decision=None,
        reason_code="SYNTHETIC_PENDING",
    )


@pytest.mark.parametrize("value", [None, object()])
def test_constructor_rejects_invalid_processor(value: object) -> None:
    with pytest.raises(TypeError, match="approval_processor"):
        ApprovalService(value)  # type: ignore[arg-type]


def test_process_validates_inputs_before_delegation() -> None:
    request = make_request()
    processor = StaticApprovalProcessor(make_result(request))
    service = ApprovalService(processor)

    with pytest.raises(TypeError, match="ApprovalRequest"):
        service.process(  # type: ignore[arg-type]
            object(),
            principal_id="principal",
            plaintext_secret="secret",
            approved=True,
            rationale="approved",
        )
    with pytest.raises(ValueError, match="principal_id"):
        service.process(
            request,
            principal_id=" ",
            plaintext_secret="secret",
            approved=True,
            rationale="approved",
        )
    with pytest.raises(ValueError, match="plaintext_secret"):
        service.process(
            request,
            principal_id="principal",
            plaintext_secret="",
            approved=True,
            rationale="approved",
        )
    with pytest.raises(TypeError, match="strict Boolean"):
        service.process(
            request,
            principal_id="principal",
            plaintext_secret="secret",
            approved=1,  # type: ignore[arg-type]
            rationale="approved",
        )
    with pytest.raises(ValueError, match="rationale"):
        service.process(
            request,
            principal_id="principal",
            plaintext_secret="secret",
            approved=True,
            rationale=" ",
        )

    assert processor.call_count == 0


def test_process_delegates_once_and_normalizes_public_text() -> None:
    request = make_request()
    expected = make_result(request)
    processor = StaticApprovalProcessor(expected)
    service = ApprovalService(processor)

    result = service.process(
        request,
        principal_id=" principal ",
        plaintext_secret="secret",
        approved=True,
        rationale=" approved for synthetic review ",
    )

    assert result is expected
    assert processor.call_count == 1
    assert processor.received == {
        "request": request,
        "principal_id": "principal",
        "plaintext_secret": "secret",
        "approved": True,
        "rationale": "approved for synthetic review",
    }


def test_process_rejects_invalid_processor_result() -> None:
    request = make_request()
    service = ApprovalService(StaticApprovalProcessor(object()))

    with pytest.raises(
        GovernanceConfigurationError,
        match="invalid processing result",
    ):
        service.process(
            request,
            principal_id="principal",
            plaintext_secret="secret",
            approved=True,
            rationale="approved",
        )


def test_process_rejects_result_for_different_request() -> None:
    request = make_request()
    other = ApprovalRequest.create(
        request_id="OTHER-REQUEST",
        event_id=request.event_id,
        recommendation_id=request.recommendation_id,
        operation_id=request.operation_id,
        requested_decision=request.requested_decision,
        target_role=request.target_role,
        mandate_id=request.mandate_id,
        context_digest=request.context_digest,
        created_at=request.created_at,
        expires_at=request.expires_at,
        idempotency_key="OTHER-IDEMPOTENCY",
    )
    service = ApprovalService(
        StaticApprovalProcessor(make_result(other))
    )

    with pytest.raises(
        GovernanceConfigurationError,
        match="does not match input request",
    ):
        service.process(
            request,
            principal_id="principal",
            plaintext_secret="secret",
            approved=True,
            rationale="approved",
        )
