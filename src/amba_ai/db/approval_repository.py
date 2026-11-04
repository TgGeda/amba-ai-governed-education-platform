from __future__ import annotations

from contextlib import contextmanager
import hmac
from pathlib import Path
import sqlite3
import threading
from typing import Iterator

from amba_ai.db.governance_repository import create_sqlite_connection
from amba_ai.governance.approvals import (
    ApprovalDecision,
    ApprovalRepositoryProtocol,
    ApprovalRequest,
)
from amba_ai.governance.models import GovernanceConfigurationError


def _rollback_if_active(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.rollback()


def _require_lookup(value: object, field_name: str) -> str:
    if not isinstance(field_name, str):
        raise TypeError("field_name must be a string")

    normalized_field_name = field_name.strip()
    if not normalized_field_name:
        raise ValueError("field_name must not be empty")

    if not isinstance(value, str):
        raise TypeError(f"{normalized_field_name} must be a string")

    normalized_value = value.strip()
    if not normalized_value:
        raise GovernanceConfigurationError(
            f"{normalized_field_name} must not be empty"
        )

    return normalized_value


def _require_persisted_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernanceConfigurationError(
            f"Persisted {field_name} must be a nonempty string"
        )
    return value.strip()


def _strict_database_bool(value: object, field_name: str) -> bool:
    if type(value) is not int or value not in {0, 1}:
        raise GovernanceConfigurationError(
            f"Persisted {field_name} must be 0 or 1"
        )
    return value == 1


class ApprovalRepository(ApprovalRepositoryProtocol):
    def __init__(self, db_path: Path | str) -> None:
        if not isinstance(db_path, (str, Path)):
            raise TypeError("db_path must be a path")

        path_text = str(db_path).strip()
        if not path_text:
            raise ValueError("db_path must not be empty")

        self.db_path = Path(path_text)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        connection = create_sqlite_connection(self.db_path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _validate_pair(
        request: ApprovalRequest,
        decision: ApprovalDecision,
    ) -> None:
        if not isinstance(request, ApprovalRequest):
            raise TypeError("request must be an ApprovalRequest")
        if not isinstance(decision, ApprovalDecision):
            raise TypeError("decision must be an ApprovalDecision")

        if decision.request_id != request.request_id:
            raise GovernanceConfigurationError(
                "Approval decision request identifier does not match "
                "the approval request"
            )

        if not hmac.compare_digest(
            decision.request_digest,
            request.request_digest,
        ):
            raise GovernanceConfigurationError(
                "Approval decision request digest does not match "
                "the approval request"
            )

        if decision.mandate_id != request.mandate_id:
            raise GovernanceConfigurationError(
                "Approval decision mandate does not match "
                "the approval request"
            )

        if decision.synthetic != request.synthetic:
            raise GovernanceConfigurationError(
                "Approval decision synthetic boundary does not match "
                "the approval request"
            )

        if decision.legal_effect != request.legal_effect:
            raise GovernanceConfigurationError(
                "Approval decision legal-effect boundary does not match "
                "the approval request"
            )

    @staticmethod
    def _validate_persisted_relationship(
        row: sqlite3.Row,
        decision: ApprovalDecision,
    ) -> None:
        try:
            persisted_request_id = _require_persisted_text(
                row["persisted_request_id"],
                "request_id",
            )
            persisted_request_digest = _require_persisted_text(
                row["persisted_request_digest"],
                "request_digest",
            )
            persisted_mandate_id = _require_persisted_text(
                row["persisted_mandate_id"],
                "mandate_id",
            )
            request_synthetic = _strict_database_bool(
                row["request_synthetic"],
                "request_synthetic",
            )
            request_legal_effect = _strict_database_bool(
                row["request_legal_effect"],
                "request_legal_effect",
            )
        except GovernanceConfigurationError:
            raise
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise GovernanceConfigurationError(
                "Persisted approval relationship metadata is invalid"
            ) from error

        if decision.request_id != persisted_request_id:
            raise GovernanceConfigurationError(
                "Persisted approval decision request identifier is inconsistent"
            )

        if not hmac.compare_digest(
            decision.request_digest,
            persisted_request_digest,
        ):
            raise GovernanceConfigurationError(
                "Persisted approval decision request digest does not match "
                "its approval request"
            )

        if decision.mandate_id != persisted_mandate_id:
            raise GovernanceConfigurationError(
                "Persisted approval decision mandate does not match "
                "its approval request"
            )

        if decision.synthetic != request_synthetic:
            raise GovernanceConfigurationError(
                "Persisted approval synthetic boundary is inconsistent"
            )

        if decision.legal_effect != request_legal_effect:
            raise GovernanceConfigurationError(
                "Persisted approval legal-effect boundary is inconsistent"
            )

    def store_request_and_decision(
        self,
        request: ApprovalRequest,
        decision: ApprovalDecision,
    ) -> None:
        self._validate_pair(request, decision)

        with self._lock, self._conn() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE;")
                connection.execute(
                    """
                    INSERT INTO approval_requests (
                        request_id,
                        event_id,
                        recommendation_id,
                        operation_id,
                        requested_decision,
                        target_role,
                        mandate_id,
                        context_digest,
                        request_digest,
                        created_at,
                        expires_at,
                        idempotency_key,
                        synthetic,
                        legal_effect
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        request.request_id,
                        request.event_id,
                        request.recommendation_id,
                        request.operation_id,
                        request.requested_decision,
                        request.target_role,
                        request.mandate_id,
                        request.context_digest,
                        request.request_digest,
                        request.created_at,
                        request.expires_at,
                        request.idempotency_key,
                        int(request.synthetic),
                        int(request.legal_effect),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO approval_decisions (
                        decision_id,
                        request_id,
                        principal_id,
                        mandate_id,
                        approved,
                        rationale,
                        decided_at,
                        request_digest,
                        decision_digest,
                        synthetic,
                        legal_effect
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        decision.decision_id,
                        decision.request_id,
                        decision.principal_id,
                        decision.mandate_id,
                        int(decision.approved),
                        decision.rationale,
                        decision.decided_at,
                        decision.request_digest,
                        decision.decision_digest,
                        int(decision.synthetic),
                        int(decision.legal_effect),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as error:
                _rollback_if_active(connection)
                raise GovernanceConfigurationError(
                    "Approval request or decision violates a persistence "
                    "integrity constraint"
                ) from error
            except sqlite3.Error as error:
                _rollback_if_active(connection)
                raise GovernanceConfigurationError(
                    "Approval transaction failed"
                ) from error
            except Exception:
                _rollback_if_active(connection)
                raise

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        normalized_id = _require_lookup(request_id, "request_id")

        with self._lock, self._conn() as connection:
            try:
                row = connection.execute(
                    """
                    SELECT *
                    FROM approval_requests
                    WHERE request_id = ?;
                    """,
                    (normalized_id,),
                ).fetchone()
            except sqlite3.Error as error:
                raise GovernanceConfigurationError(
                    "Approval request lookup failed"
                ) from error

        return None if row is None else self._row_to_request(row)

    def get_request_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> ApprovalRequest | None:
        normalized_key = _require_lookup(
            idempotency_key,
            "idempotency_key",
        )

        with self._lock, self._conn() as connection:
            try:
                row = connection.execute(
                    """
                    SELECT *
                    FROM approval_requests
                    WHERE idempotency_key = ?;
                    """,
                    (normalized_key,),
                ).fetchone()
            except sqlite3.Error as error:
                raise GovernanceConfigurationError(
                    "Approval request idempotency lookup failed"
                ) from error

        return None if row is None else self._row_to_request(row)

    def get_decision_by_request(
        self,
        request_id: str,
    ) -> ApprovalDecision | None:
        normalized_id = _require_lookup(request_id, "request_id")

        with self._lock, self._conn() as connection:
            try:
                row = connection.execute(
                    """
                    SELECT
                        d.*,
                        r.request_id AS persisted_request_id,
                        r.request_digest AS persisted_request_digest,
                        r.mandate_id AS persisted_mandate_id,
                        r.synthetic AS request_synthetic,
                        r.legal_effect AS request_legal_effect
                    FROM approval_decisions AS d
                    INNER JOIN approval_requests AS r
                        ON r.request_id = d.request_id
                    WHERE d.request_id = ?;
                    """,
                    (normalized_id,),
                ).fetchone()
            except sqlite3.Error as error:
                raise GovernanceConfigurationError(
                    "Approval decision lookup failed"
                ) from error

        if row is None:
            return None

        decision = self._row_to_decision(row)
        self._validate_persisted_relationship(row, decision)
        return decision

    def get_decision_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> ApprovalDecision | None:
        normalized_key = _require_lookup(
            idempotency_key,
            "idempotency_key",
        )

        with self._lock, self._conn() as connection:
            try:
                row = connection.execute(
                    """
                    SELECT
                        d.*,
                        r.request_id AS persisted_request_id,
                        r.request_digest AS persisted_request_digest,
                        r.mandate_id AS persisted_mandate_id,
                        r.synthetic AS request_synthetic,
                        r.legal_effect AS request_legal_effect
                    FROM approval_decisions AS d
                    INNER JOIN approval_requests AS r
                        ON r.request_id = d.request_id
                    WHERE r.idempotency_key = ?;
                    """,
                    (normalized_key,),
                ).fetchone()
            except sqlite3.Error as error:
                raise GovernanceConfigurationError(
                    "Approval decision idempotency lookup failed"
                ) from error

        if row is None:
            return None

        decision = self._row_to_decision(row)
        self._validate_persisted_relationship(row, decision)
        return decision

    @staticmethod
    def _row_to_request(row: sqlite3.Row) -> ApprovalRequest:
        try:
            return ApprovalRequest(
                request_id=_require_persisted_text(
                    row["request_id"],
                    "request_id",
                ),
                event_id=_require_persisted_text(
                    row["event_id"],
                    "event_id",
                ),
                recommendation_id=_require_persisted_text(
                    row["recommendation_id"],
                    "recommendation_id",
                ),
                operation_id=_require_persisted_text(
                    row["operation_id"],
                    "operation_id",
                ),
                requested_decision=_require_persisted_text(
                    row["requested_decision"],
                    "requested_decision",
                ),
                target_role=_require_persisted_text(
                    row["target_role"],
                    "target_role",
                ),
                mandate_id=_require_persisted_text(
                    row["mandate_id"],
                    "mandate_id",
                ),
                context_digest=_require_persisted_text(
                    row["context_digest"],
                    "context_digest",
                ),
                request_digest=_require_persisted_text(
                    row["request_digest"],
                    "request_digest",
                ),
                created_at=_require_persisted_text(
                    row["created_at"],
                    "created_at",
                ),
                expires_at=_require_persisted_text(
                    row["expires_at"],
                    "expires_at",
                ),
                idempotency_key=_require_persisted_text(
                    row["idempotency_key"],
                    "idempotency_key",
                ),
                synthetic=_strict_database_bool(
                    row["synthetic"],
                    "synthetic",
                ),
                legal_effect=_strict_database_bool(
                    row["legal_effect"],
                    "legal_effect",
                ),
            )
        except GovernanceConfigurationError:
            raise
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise GovernanceConfigurationError(
                "Persisted approval request is invalid"
            ) from error

    @staticmethod
    def _row_to_decision(row: sqlite3.Row) -> ApprovalDecision:
        try:
            return ApprovalDecision(
                decision_id=_require_persisted_text(
                    row["decision_id"],
                    "decision_id",
                ),
                request_id=_require_persisted_text(
                    row["request_id"],
                    "request_id",
                ),
                principal_id=_require_persisted_text(
                    row["principal_id"],
                    "principal_id",
                ),
                mandate_id=_require_persisted_text(
                    row["mandate_id"],
                    "mandate_id",
                ),
                approved=_strict_database_bool(
                    row["approved"],
                    "approved",
                ),
                rationale=_require_persisted_text(
                    row["rationale"],
                    "rationale",
                ),
                decided_at=_require_persisted_text(
                    row["decided_at"],
                    "decided_at",
                ),
                request_digest=_require_persisted_text(
                    row["request_digest"],
                    "request_digest",
                ),
                decision_digest=_require_persisted_text(
                    row["decision_digest"],
                    "decision_digest",
                ),
                synthetic=_strict_database_bool(
                    row["synthetic"],
                    "synthetic",
                ),
                legal_effect=_strict_database_bool(
                    row["legal_effect"],
                    "legal_effect",
                ),
            )
        except GovernanceConfigurationError:
            raise
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise GovernanceConfigurationError(
                "Persisted approval decision is invalid"
            ) from error
