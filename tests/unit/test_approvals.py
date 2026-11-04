from __future__ import annotations

import hashlib
from pathlib import Path
import secrets
import sqlite3
import tempfile
from typing import Callable

import pytest

from amba_ai.db.approval_repository import ApprovalRepository
from amba_ai.db.governance_repository import GovernanceRepository
from amba_ai.governance.approvals import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalService,
    ApprovalStatus,
)
from amba_ai.governance.mandates import MandateDefinition, MandateRegistry
from amba_ai.governance.models import (
    GovernanceConfigurationError,
    SequentialIdentifierProvider,
)
from amba_ai.governance.principals import (
    FixedClock,
    PrincipalCredential,
    PrincipalRegistry,
    hash_secret_scrypt,
)


MIGRATION_002 = Path("src/amba_ai/db/migrations/002_governance_records.sql")
MIGRATION_003 = Path("src/amba_ai/db/migrations/003_approval_execution_audit.sql")
FIXED_NOW = "2026-06-01T12:00:00Z"


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def make_request(
    *,
    request_id: str = "REQ-001",
    event_id: str = "EVT-001",
    recommendation_id: str = "REC-001",
    requested_decision: str = "approve_review_queue",
    context_digest: str | None = None,
    expires_at: str = "2026-06-01T13:00:00Z",
    idempotency_key: str = "IDEM-001",
    synthetic: bool = True,
    legal_effect: bool = False,
) -> ApprovalRequest:
    return ApprovalRequest.create(
        request_id=request_id,
        event_id=event_id,
        recommendation_id=recommendation_id,
        operation_id="commercial_purchase_request",
        requested_decision=requested_decision,
        target_role="school_administrator",
        mandate_id="MANDATE-01",
        context_digest=context_digest or sha256(b"context-evidence"),
        created_at="2026-06-01T11:50:00Z",
        expires_at=expires_at,
        idempotency_key=idempotency_key,
        synthetic=synthetic,
        legal_effect=legal_effect,
    )


def make_decision(
    request: ApprovalRequest,
    *,
    decision_id: str = "DEC-001",
    request_id: str | None = None,
    mandate_id: str | None = None,
    request_digest: str | None = None,
    approved: bool = True,
    synthetic: bool = True,
    legal_effect: bool = False,
) -> ApprovalDecision:
    return ApprovalDecision.create(
        decision_id=decision_id,
        request_id=request_id or request.request_id,
        principal_id="PRINCIPAL-01",
        mandate_id=mandate_id or request.mandate_id,
        approved=approved,
        rationale="Repository test decision",
        decided_at=FIXED_NOW,
        request_digest=request_digest or request.request_digest,
        synthetic=synthetic,
        legal_effect=legal_effect,
    )


@pytest.fixture
def approval_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_approvals.db"
        governance_repository = GovernanceRepository(db_path)
        governance_repository.apply_migration_file(MIGRATION_002)
        governance_repository.apply_migration_file(MIGRATION_003)

        salt = secrets.token_hex(16)
        secret = "PrincipalSecret123!"
        principals = PrincipalRegistry()
        principals.register(
            PrincipalCredential(
                principal_id="PRINCIPAL-01",
                role="school_administrator",
                synthetic=True,
                legal_effect=False,
                credential_digest=hash_secret_scrypt(secret, salt),
                credential_algorithm="scrypt",
                credential_salt=salt,
                active_from="2026-01-01T00:00:00Z",
                expires_at="2027-01-01T00:00:00Z",
                disabled_at=None,
                mandate_ids=("MANDATE-01",),
            )
        )
        mandates = MandateRegistry()
        mandates.register(
            MandateDefinition(
                mandate_id="MANDATE-01",
                principal_id="PRINCIPAL-01",
                role="school_administrator",
                permitted_operations=("commercial_purchase_request",),
                permitted_decisions=(
                    "approve_review_queue",
                    "deny_commercial_purchase",
                ),
                synthetic=True,
                legal_effect=False,
                active_from="2026-01-01T00:00:00Z",
                expires_at="2027-01-01T00:00:00Z",
                revoked_at=None,
            )
        )
        repository = ApprovalRepository(db_path)
        service = ApprovalService(
            principals,
            mandates,
            repository,
            SequentialIdentifierProvider(),
            FixedClock(FIXED_NOW),
        )
        yield {
            "db_path": db_path,
            "repository": repository,
            "service": service,
            "secret": secret,
        }


@pytest.mark.parametrize(
    "dependency, message",
    [
        ("principal_registry", "principal_registry is required"),
        ("mandate_registry", "mandate_registry is required"),
        ("approval_repository", "approval_repository is required"),
        ("identifier_provider", "identifier_provider is required"),
        ("clock", "clock is required"),
    ],
)
def test_service_requires_dependencies(approval_env, dependency, message):
    service = approval_env["service"]
    arguments = {
        "principal_registry": service.principals,
        "mandate_registry": service.mandates,
        "approval_repository": service.repository,
        "identifier_provider": SequentialIdentifierProvider(),
        "clock": FixedClock(FIXED_NOW),
    }
    arguments[dependency] = None
    with pytest.raises(TypeError, match=message):
        ApprovalService(**arguments)  # type: ignore[arg-type]


def test_valid_approval_and_idempotent_replay(approval_env):
    request = make_request()
    service = approval_env["service"]
    result = service.process_approval(
        request,
        "PRINCIPAL-01",
        approval_env["secret"],
        approved=True,
        rationale="Verified educational intent",
    )
    assert result.status == ApprovalStatus.APPROVED
    assert result.decision is not None

    replay = service.process_approval(
        request,
        "PRINCIPAL-01",
        approval_env["secret"],
        approved=True,
        rationale="Verified educational intent",
    )
    assert replay.status == ApprovalStatus.DUPLICATE
    assert replay.decision == result.decision


def test_repository_round_trip_by_all_lookup_keys(approval_env):
    request = make_request(
        request_id="REQ-ROUND-TRIP",
        event_id="EVT-ROUND-TRIP",
        recommendation_id="REC-ROUND-TRIP",
        idempotency_key="IDEM-ROUND-TRIP",
    )
    result = approval_env["service"].process_approval(
        request,
        "PRINCIPAL-01",
        approval_env["secret"],
        approved=True,
        rationale="Approved round trip",
    )
    repository = approval_env["repository"]
    assert repository.get_request(request.request_id) == request
    assert repository.get_request_by_idempotency_key(request.idempotency_key) == request
    assert repository.get_decision_by_request(request.request_id) == result.decision
    assert repository.get_decision_by_idempotency_key(request.idempotency_key) == result.decision


@pytest.mark.parametrize(
    "digest, message",
    [
        ("not-a-hex-digest", "must be a 64-character lowercase SHA-256 digest"),
        (hashlib.sha256(b"").hexdigest(), "cannot use an empty-content or all-zero digest"),
        ("0" * 64, "cannot use an empty-content or all-zero digest"),
        (sha256(b"uppercase").upper(), "must be a 64-character lowercase SHA-256 digest"),
    ],
)
def test_invalid_context_digests_rejected(digest, message):
    with pytest.raises(ValueError, match=message):
        make_request(context_digest=digest)


def test_request_semantic_digest_tampering_rejected():
    valid = make_request()
    with pytest.raises(ValueError, match="request_digest does not match"):
        ApprovalRequest(
            request_id=valid.request_id,
            event_id="EVT-TAMPERED",
            recommendation_id=valid.recommendation_id,
            operation_id=valid.operation_id,
            requested_decision=valid.requested_decision,
            target_role=valid.target_role,
            mandate_id=valid.mandate_id,
            context_digest=valid.context_digest,
            request_digest=valid.request_digest,
            created_at=valid.created_at,
            expires_at=valid.expires_at,
            idempotency_key=valid.idempotency_key,
            synthetic=valid.synthetic,
            legal_effect=valid.legal_effect,
        )


def test_decision_semantic_digest_tampering_rejected():
    request = make_request()
    valid = make_decision(request)
    with pytest.raises(ValueError, match="decision_digest does not match"):
        ApprovalDecision(
            decision_id=valid.decision_id,
            request_id=valid.request_id,
            principal_id=valid.principal_id,
            mandate_id=valid.mandate_id,
            approved=False,
            rationale=valid.rationale,
            decided_at=valid.decided_at,
            request_digest=valid.request_digest,
            decision_digest=valid.decision_digest,
            synthetic=valid.synthetic,
            legal_effect=valid.legal_effect,
        )


def test_expiration_changes_semantic_digest():
    first = make_request(expires_at="2026-06-01T13:00:00Z")
    second = make_request(expires_at="2026-06-01T14:00:00Z")
    assert first.request_digest != second.request_digest


def test_conflicting_idempotency_retry_rejected(approval_env):
    first = make_request(request_id="REQ-A", event_id="EVT-A", idempotency_key="IDEM-CONFLICT")
    second = make_request(request_id="REQ-B", event_id="EVT-B", idempotency_key="IDEM-CONFLICT")
    service = approval_env["service"]
    service.process_approval(first, "PRINCIPAL-01", approval_env["secret"], True, "Pass")
    with pytest.raises(GovernanceConfigurationError, match="Conflicting approval request"):
        service.process_approval(second, "PRINCIPAL-01", approval_env["secret"], True, "Conflict")


def test_empty_rationale_returns_configuration_failure(approval_env):
    result = approval_env["service"].process_approval(
        make_request(),
        "PRINCIPAL-01",
        approval_env["secret"],
        True,
        "   ",
    )
    assert result.status == ApprovalStatus.CONFIGURATION_FAILURE
    assert result.reason_code == "RATIONALE_REQUIRED"
    assert result.decision is None


def test_authentication_failure_persists_nothing(approval_env):
    request = make_request(request_id="REQ-AUTH", idempotency_key="IDEM-AUTH")
    result = approval_env["service"].process_approval(
        request,
        "PRINCIPAL-01",
        "WrongSecret!",
        True,
        "Failed attempt",
    )
    repository = approval_env["repository"]
    assert result.status == ApprovalStatus.CONFIGURATION_FAILURE
    assert repository.get_request(request.request_id) is None
    assert repository.get_request_by_idempotency_key(request.idempotency_key) is None
    assert repository.get_decision_by_request(request.request_id) is None


def test_denial_is_persisted(approval_env):
    request = make_request(
        request_id="REQ-DENIAL",
        requested_decision="deny_commercial_purchase",
        idempotency_key="IDEM-DENIAL",
    )
    result = approval_env["service"].process_approval(
        request,
        "PRINCIPAL-01",
        approval_env["secret"],
        False,
        "Commercial purchase denied",
    )
    assert result.status == ApprovalStatus.DENIED
    assert result.decision is not None
    assert result.decision.approved is False
    assert approval_env["repository"].get_decision_by_request(request.request_id) == result.decision


@pytest.mark.parametrize(
    "mutator, message",
    [
        (lambda request: make_decision(request, request_id="OTHER"), "request identifier does not match"),
        (lambda request: make_decision(request, request_digest=sha256(b"other")), "request digest does not match"),
        (lambda request: make_decision(request, mandate_id="OTHER"), "mandate does not match"),
        (lambda request: make_decision(request, synthetic=False), "synthetic boundary does not match"),
    ],
)
def test_repository_rejects_mismatched_pair(
    approval_env,
    mutator: Callable[[ApprovalRequest], ApprovalDecision],
    message: str,
):
    request = make_request(request_id="REQ-PAIR", idempotency_key="IDEM-PAIR")
    with pytest.raises(GovernanceConfigurationError, match=message):
        approval_env["repository"].store_request_and_decision(request, mutator(request))
    assert approval_env["repository"].get_request(request.request_id) is None


def test_repository_rejects_legal_effect_boundary_mismatch(approval_env):
    request = make_request(
        request_id="REQ-LEGAL",
        idempotency_key="IDEM-LEGAL",
        synthetic=False,
        legal_effect=False,
    )
    decision = make_decision(
        request,
        synthetic=False,
        legal_effect=True,
    )
    with pytest.raises(GovernanceConfigurationError, match="legal-effect boundary does not match"):
        approval_env["repository"].store_request_and_decision(request, decision)


def test_repository_rolls_back_request_when_decision_insert_fails(approval_env):
    repository = approval_env["repository"]
    first_request = make_request(request_id="REQ-FIRST", idempotency_key="IDEM-FIRST")
    repository.store_request_and_decision(
        first_request,
        make_decision(first_request, decision_id="DEC-DUPLICATE"),
    )
    second_request = make_request(request_id="REQ-ROLLBACK", idempotency_key="IDEM-ROLLBACK")
    with pytest.raises(GovernanceConfigurationError, match="persistence integrity constraint"):
        repository.store_request_and_decision(
            second_request,
            make_decision(second_request, decision_id="DEC-DUPLICATE"),
        )
    assert repository.get_request(second_request.request_id) is None
    assert repository.get_request_by_idempotency_key(second_request.idempotency_key) is None


@pytest.mark.parametrize(
    "lookup",
    [
        lambda repository: repository.get_request(" "),
        lambda repository: repository.get_request_by_idempotency_key(" "),
        lambda repository: repository.get_decision_by_request(" "),
        lambda repository: repository.get_decision_by_idempotency_key(" "),
    ],
)
def test_repository_rejects_empty_lookup_values(approval_env, lookup):
    with pytest.raises(GovernanceConfigurationError, match="must not be empty"):
        lookup(approval_env["repository"])


def test_foreign_keys_are_enabled(
    approval_env,
) -> None:
    database_path = approval_env["db_path"]

    raw_connection = sqlite3.connect(
        str(database_path)
    )

    try:
        raw_enabled = raw_connection.execute(
            "PRAGMA foreign_keys;"
        ).fetchone()[0]
    finally:
        raw_connection.close()

    assert raw_enabled == 0

    repository = approval_env["repository"]

    with repository._conn() as connection:
        repository_enabled = connection.execute(
            "PRAGMA foreign_keys;"
        ).fetchone()[0]

    assert repository_enabled == 1


def test_corrupted_request_row_is_reported_as_governance_error(approval_env):
    repository = approval_env["repository"]
    request = make_request(request_id="REQ-CORRUPT", idempotency_key="IDEM-CORRUPT")
    repository.store_request_and_decision(request, make_decision(request))
    with repository._conn() as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON;")
        connection.execute(
            "UPDATE approval_requests SET request_digest = ? WHERE request_id = ?;",
            (sha256(b"wrong"), request.request_id),
        )
    with pytest.raises(GovernanceConfigurationError, match="Persisted approval request is invalid"):
        repository.get_request(request.request_id)


def test_corrupted_decision_row_is_reported_as_governance_error(approval_env):
    repository = approval_env["repository"]
    request = make_request(request_id="REQ-CORRUPT-DEC", idempotency_key="IDEM-CORRUPT-DEC")
    decision = make_decision(request, decision_id="DEC-CORRUPT")
    repository.store_request_and_decision(request, decision)
    with repository._conn() as connection:
        connection.execute(
            "UPDATE approval_decisions SET request_digest = ? WHERE decision_id = ?;",
            (sha256(b"corrupted"), decision.decision_id),
        )
    with pytest.raises(GovernanceConfigurationError, match="Persisted approval decision is invalid"):
        repository.get_decision_by_request(request.request_id)
