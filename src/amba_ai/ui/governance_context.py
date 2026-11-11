from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock

from amba_ai.governance.learning_operations import (
    LEARNING_METHOD_OPERATION_MAP,
    canonical_learning_operation,
)
from amba_ai.governance.models import (
    AuthorizationBasis,
    AuthorizationBasisType,
    to_canonical_json,
)
from amba_ai.services.job_governance import JobGovernanceContext

_LEARNER_MANDATE_ID = "LEARNER-EDUCATIONAL-OPERATIONS-V1"
_LEARNER_PRINCIPAL_ID = "SYNTHETIC-LEARNER-01"
_EFFECTIVE_FROM = "2026-01-01T00:00:00Z"
_EXPIRES_AT = "2027-01-01T00:00:00Z"
_OPERATION_DESTINATIONS = {
    "learning.tutor.retrieve": "internal.retrieval",
    "learning.tutor.answer": "desktop.tutor",
    "learning.summary.generate": "desktop.summary",
    "learning.notes.generate": "desktop.notes",
    "learning.flashcards.generate": "desktop.study",
    "learning.quiz.generate": "desktop.study",
    "learning.content.export": "local.export",
    "learning.content.copy": "local.clipboard",
}


def _learner_basis(operation_id: str) -> AuthorizationBasis:
    fixture = {
        "mandate_id": _LEARNER_MANDATE_ID,
        "principal_id": _LEARNER_PRINCIPAL_ID,
        "role": "learner",
        "operation_id": operation_id,
        "decision": "request_learning_operation",
        "synthetic": True,
        "legal_effect": False,
    }
    artifact_hash = hashlib.sha256(
        to_canonical_json(fixture).encode("utf-8")
    ).hexdigest()
    return AuthorizationBasis(
        basis_id=f"{_LEARNER_MANDATE_ID}:{operation_id}",
        basis_type=AuthorizationBasisType.PROJECT_FIXTURE,
        subject_category="synthetic_learner",
        authority_reference=_LEARNER_MANDATE_ID,
        purposes=(operation_id,),
        data_categories=("local_educational_content",),
        processing_operations=(operation_id,),
        effective_from=_EFFECTIVE_FROM,
        expires_at=_EXPIRES_AT,
        revoked_at=None,
        artifact_hash=artifact_hash,
        verifier_id="AMBA-DESKTOP-LEARNER-CONTEXT-V1",
        synthetic=True,
        legal_effect=False,
    )


@dataclass(slots=True)
class DesktopGovernanceContextFactory:
    session_id: str
    principal_id: str = _LEARNER_PRINCIPAL_ID
    source_node: str = "LOCAL_DESKTOP_UI"
    _lock: RLock = field(init=False, repr=False)
    _sequence: int = field(init=False, default=0, repr=False)

    def __post_init__(self) -> None:
        self.session_id = str(self.session_id).strip()
        if not self.session_id:
            raise ValueError("session_id must be non-empty")
        if self.principal_id != _LEARNER_PRINCIPAL_ID:
            raise ValueError("Desktop learner principal must match the configured mandate")
        self._lock = RLock()

    @classmethod
    def create(cls) -> "DesktopGovernanceContextFactory":
        return cls(session_id=f"desktop-{uuid.uuid4().hex}")

    def for_operation(
        self,
        operation_name: str,
        *,
        document_id: int | None = None,
    ) -> JobGovernanceContext:
        operation_id = canonical_learning_operation(operation_name)
        try:
            destination_id = _OPERATION_DESTINATIONS[operation_id]
        except KeyError as error:
            raise ValueError(
                f"Desktop learner operation has no authorized destination: {operation_id}"
            ) from error
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
        scope = (
            f"document-{int(document_id)}"
            if document_id is not None
            else "no-document"
        )
        return JobGovernanceContext(
            run_id=f"{self.session_id}:{sequence}",
            scenario_id="desktop-learning-session",
            stage_id=f"{operation_id}:{scope}",
            source_node=self.source_node,
            destination_id=destination_id,
            authorization_basis=_learner_basis(operation_id),
            approval_decision=None,
            synthetic=True,
        )


_SHARED_FACTORY = DesktopGovernanceContextFactory.create()


def desktop_governance_context(
    operation_name: str,
    *,
    document_id: int | None = None,
) -> JobGovernanceContext:
    return _SHARED_FACTORY.for_operation(
        operation_name,
        document_id=document_id,
    )


def verify_desktop_governance_contracts() -> None:
    now_iso = datetime.now(timezone.utc).isoformat()

    for method_name, expected_operation in LEARNING_METHOD_OPERATION_MAP.items():
        if expected_operation not in _OPERATION_DESTINATIONS:
            continue

        actual_operation = canonical_learning_operation(method_name)

        if actual_operation != expected_operation:
            raise RuntimeError(
                "Desktop governance operation mismatch: "
                f"{method_name} -> {actual_operation}; "
                f"expected {expected_operation}"
            )

        try:
            expected_destination = _OPERATION_DESTINATIONS[expected_operation]
        except KeyError as exc:
            raise RuntimeError(
                f"No desktop destination is configured for {expected_operation}"
            ) from exc

        context = desktop_governance_context(method_name)

        if context.destination_id != expected_destination:
            raise RuntimeError(
                "Desktop governance destination mismatch: "
                f"{expected_operation} -> {context.destination_id}; "
                f"expected {expected_destination}"
            )

        basis = context.authorization_basis

        if basis is None:
            raise RuntimeError(
                f"Missing desktop authorization basis for {expected_operation}"
            )

        if not basis.is_valid(
            purpose=expected_operation,
            operation=expected_operation,
            now_iso=now_iso,
        ):
            raise RuntimeError(
                f"Invalid or expired desktop authorization basis for {expected_operation}"
            )