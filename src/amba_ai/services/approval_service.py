from __future__ import annotations

from typing import Protocol, runtime_checkable

from amba_ai.governance.approvals import (
    ApprovalDecision,
    ApprovalProcessingResult,
    ApprovalRequest,
    ApprovalStatus,
)
from amba_ai.governance.models import GovernanceConfigurationError


@runtime_checkable
class ApprovalProcessorProtocol(Protocol):
    def process_approval(
        self,
        request: ApprovalRequest,
        principal_id: str,
        plaintext_secret: str,
        approved: bool,
        rationale: str,
    ) -> ApprovalProcessingResult:
        ...


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")

    return normalized


class ApprovalService:
    """Application boundary for authenticated approval processing.

    The service delegates to the single injected governance approval processor.
    Authentication, mandate evaluation, expiry, replay protection, decision
    creation, and persistence remain authoritative in that processor. This
    boundary never creates or alters an ApprovalDecision.
    """

    _NO_DECISION_STATUSES = {
        ApprovalStatus.PENDING,
        ApprovalStatus.EXPIRED,
        ApprovalStatus.CANCELLED,
        ApprovalStatus.CONFIGURATION_FAILURE,
    }

    def __init__(self, approval_processor: ApprovalProcessorProtocol) -> None:
        if approval_processor is None:
            raise TypeError("approval_processor is required")
        if not isinstance(approval_processor, ApprovalProcessorProtocol):
            raise TypeError(
                "approval_processor must provide a callable "
                "process_approval method"
            )

        self._approval_processor = approval_processor

    @property
    def approval_processor(self) -> ApprovalProcessorProtocol:
        return self._approval_processor

    def process(
        self,
        request: ApprovalRequest,
        *,
        principal_id: str,
        plaintext_secret: str,
        approved: bool,
        rationale: str,
    ) -> ApprovalProcessingResult:
        if not isinstance(request, ApprovalRequest):
            raise TypeError("request must be an ApprovalRequest")

        normalized_principal_id = _require_text(principal_id, "principal_id")

        if not isinstance(plaintext_secret, str):
            raise TypeError("plaintext_secret must be a string")
        if not plaintext_secret:
            raise ValueError("plaintext_secret must not be empty")

        if type(approved) is not bool:
            raise TypeError("approved must be a strict Boolean")

        normalized_rationale = _require_text(rationale, "rationale")

        result = self._approval_processor.process_approval(
            request=request,
            principal_id=normalized_principal_id,
            plaintext_secret=plaintext_secret,
            approved=approved,
            rationale=normalized_rationale,
        )

        self._validate_result(request, result)
        return result

    @classmethod
    def _validate_result(
        cls,
        request: ApprovalRequest,
        result: object,
    ) -> None:
        if not isinstance(result, ApprovalProcessingResult):
            raise GovernanceConfigurationError(
                "approval_processor returned an invalid processing result"
            )
        if not isinstance(result.status, ApprovalStatus):
            raise GovernanceConfigurationError(
                "approval processing result contains an invalid status"
            )
        if not isinstance(result.request, ApprovalRequest):
            raise GovernanceConfigurationError(
                "approval processing result contains an invalid request"
            )
        if result.request.request_id != request.request_id:
            raise GovernanceConfigurationError(
                "approval result request identifier does not match input request"
            )
        if result.request.request_digest != request.request_digest:
            raise GovernanceConfigurationError(
                "approval result request digest does not match input request"
            )

        _require_text(result.reason_code, "reason_code")
        decision = result.decision

        if decision is not None and not isinstance(decision, ApprovalDecision):
            raise GovernanceConfigurationError(
                "approval processing result contains an invalid decision"
            )

        if result.status in cls._NO_DECISION_STATUSES and decision is not None:
            raise GovernanceConfigurationError(
                "approval status must not contain an ApprovalDecision"
            )

        if result.status in {ApprovalStatus.APPROVED, ApprovalStatus.DENIED}:
            if decision is None:
                raise GovernanceConfigurationError(
                    "recorded approval status requires an ApprovalDecision"
                )
            expected_approval = result.status is ApprovalStatus.APPROVED
            if decision.approved is not expected_approval:
                raise GovernanceConfigurationError(
                    "approval decision does not match processing status"
                )

        if decision is not None:
            if decision.request_id != request.request_id:
                raise GovernanceConfigurationError(
                    "approval decision request identifier does not match input request"
                )
            if decision.request_digest != request.request_digest:
                raise GovernanceConfigurationError(
                    "approval decision request digest does not match input request"
                )
