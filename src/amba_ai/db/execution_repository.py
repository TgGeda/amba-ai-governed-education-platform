from __future__ import annotations

from contextlib import contextmanager
import hmac
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Callable, Iterator, Mapping

from amba_ai.db.governance_repository import create_sqlite_connection
from amba_ai.governance.execution import (
    DistributionAcknowledgment,
    ExecutionReceipt,
    ExecutionRepositoryProtocol,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ReviewQueueReceipt,
)
from amba_ai.governance.models import (
    EnforcementAction,
    GovernanceConfigurationError,
    to_canonical_json,
)
from amba_ai.governance.principals import parse_timestamp


def _rollback_if_active(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.rollback()


def _require_text(value: object, field_name: str) -> str:
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


def _strict_database_bool(value: object, field_name: str) -> bool:
    if type(value) is not int or value not in {0, 1}:
        raise GovernanceConfigurationError(
            f"Persisted {field_name} must be 0 or 1"
        )
    return value == 1


def _decode_details(raw_json: object, field_name: str) -> dict[str, Any]:
    if not isinstance(raw_json, str):
        raise GovernanceConfigurationError(
            f"Persisted {field_name} must be JSON text"
        )

    try:
        decoded = json.loads(raw_json)
    except (TypeError, ValueError) as error:
        raise GovernanceConfigurationError(
            f"Persisted {field_name} is not valid JSON"
        ) from error

    if not isinstance(decoded, dict):
        raise GovernanceConfigurationError(
            f"Persisted {field_name} must decode to a mapping"
        )

    return decoded


class ExecutionRepository(ExecutionRepositoryProtocol):
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
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
    def _validate_result(
        request: ExecutionRequest,
        result: ExecutionResult,
    ) -> None:
        if not isinstance(request, ExecutionRequest):
            raise TypeError("request must be an ExecutionRequest")
        if not isinstance(result, ExecutionResult):
            raise GovernanceConfigurationError(
                "Execution result factory returned an invalid result"
            )
        if result.request != request:
            raise GovernanceConfigurationError(
                "Execution result request does not match the persisted execution request"
            )
        if result.duplicate:
            raise GovernanceConfigurationError(
                "A newly produced execution result cannot be marked as duplicate"
            )

        execution_receipt = result.execution_receipt
        review_receipt = result.review_queue_receipt
        acknowledgment = result.distribution_acknowledgment

        if (execution_receipt is None) == (review_receipt is None):
            raise GovernanceConfigurationError(
                "Execution result must contain exactly one execution receipt or review queue receipt"
            )

        if execution_receipt is not None:
            if execution_receipt.request_id != request.request_id:
                raise GovernanceConfigurationError(
                    "Execution receipt request identifier does not match the execution request"
                )
            if execution_receipt.event_id != request.event_id:
                raise GovernanceConfigurationError(
                    "Execution receipt event identifier does not match the execution request"
                )
            if execution_receipt.operation_id != request.operation_id:
                raise GovernanceConfigurationError(
                    "Execution receipt operation identifier does not match the execution request"
                )

        if review_receipt is not None:
            if review_receipt.request_id != request.request_id:
                raise GovernanceConfigurationError(
                    "Review queue receipt request identifier does not match the execution request"
                )
            if review_receipt.event_id != request.event_id:
                raise GovernanceConfigurationError(
                    "Review queue receipt event identifier does not match the execution request"
                )

        if acknowledgment is None:
            return

        if execution_receipt is None:
            raise GovernanceConfigurationError(
                "Distribution acknowledgment requires an execution receipt"
            )
        if acknowledgment.execution_receipt_id != execution_receipt.receipt_id:
            raise GovernanceConfigurationError(
                "Distribution acknowledgment does not reference the execution receipt"
            )
        if execution_receipt.status is not ExecutionStatus.SUCCEEDED:
            raise GovernanceConfigurationError(
                "Distribution acknowledgment requires a successful execution receipt"
            )
        if execution_receipt.action_executed is not EnforcementAction.PROCEED:
            raise GovernanceConfigurationError(
                "Distribution acknowledgment is permitted only for successful delivery"
            )
        if acknowledgment.destination_id != request.destination_id:
            raise GovernanceConfigurationError(
                "Distribution acknowledgment destination does not match the execution request"
            )

    def execute_transaction(
        self,
        request: ExecutionRequest,
        result_factory: Callable[[ExecutionRequest], ExecutionResult],
    ) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            raise TypeError("request must be an ExecutionRequest")
        if not callable(result_factory):
            raise TypeError("result_factory must be callable")

        with self._lock, self._conn() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE;")
                existing_row = connection.execute(
                    """
                    SELECT request_id, request_digest, state
                    FROM execution_idempotency
                    WHERE idempotency_key = ?;
                    """,
                    (request.idempotency_key,),
                ).fetchone()

                if existing_row is not None:
                    persisted_request_id = _require_text(
                        existing_row["request_id"],
                        "persisted request_id",
                    )
                    persisted_digest = _require_text(
                        existing_row["request_digest"],
                        "persisted request_digest",
                    )
                    persisted_state = _require_text(
                        existing_row["state"],
                        "persisted execution state",
                    )

                    if not hmac.compare_digest(
                        persisted_digest,
                        request.idempotency_digest,
                    ):
                        raise GovernanceConfigurationError(
                            "Conflicting execution request under existing idempotency key"
                        )
                    if persisted_request_id != request.request_id:
                        raise GovernanceConfigurationError(
                            "Execution idempotency key is associated with a different request identifier"
                        )
                    if persisted_state != "completed":
                        raise GovernanceConfigurationError(
                            "Execution idempotency record is not completed"
                        )

                    cached = self._load_execution_result(
                        connection,
                        persisted_request_id,
                    )
                    if cached is None:
                        raise GovernanceConfigurationError(
                            "Execution idempotency claim has no recorded result"
                        )

                    connection.rollback()
                    return ExecutionResult(
                        request=cached.request,
                        execution_receipt=cached.execution_receipt,
                        review_queue_receipt=cached.review_queue_receipt,
                        distribution_acknowledgment=(
                            cached.distribution_acknowledgment
                        ),
                        duplicate=True,
                    )

                self._insert_request(connection, request)
                self._insert_idempotency_claim(connection, request)

                result = result_factory(request)
                if not isinstance(result, ExecutionResult):
                    raise GovernanceConfigurationError(
                        "Execution result factory returned an invalid result"
                    )
                self._validate_result(request, result)

                if result.execution_receipt is not None:
                    self._insert_execution_receipt(
                        connection,
                        result.execution_receipt,
                    )
                if result.review_queue_receipt is not None:
                    self._insert_review_receipt(
                        connection,
                        result.review_queue_receipt,
                    )
                if result.distribution_acknowledgment is not None:
                    self._insert_acknowledgment(
                        connection,
                        result.distribution_acknowledgment,
                    )

                if result.execution_receipt is not None:
                    completed_at = result.execution_receipt.executed_at
                else:
                    review_receipt = result.review_queue_receipt
                    if review_receipt is None:
                        raise GovernanceConfigurationError(
                            "Execution result has no completion receipt"
                        )
                    completed_at = review_receipt.enqueued_at

                updated_rows = connection.execute(
                    """
                    UPDATE execution_idempotency
                    SET state = 'completed',
                        completed_at = ?,
                        failure_code = NULL
                    WHERE idempotency_key = ?
                      AND request_id = ?
                      AND state = 'claimed';
                    """,
                    (
                        completed_at,
                        request.idempotency_key,
                        request.request_id,
                    ),
                ).rowcount

                if updated_rows != 1:
                    raise GovernanceConfigurationError(
                        "Execution idempotency state could not be completed"
                    )

                connection.commit()
                return result

            except GovernanceConfigurationError:
                _rollback_if_active(connection)
                raise
            except sqlite3.IntegrityError as error:
                _rollback_if_active(connection)
                raise GovernanceConfigurationError(
                    "Execution persistence integrity constraint violated"
                ) from error
            except sqlite3.Error as error:
                _rollback_if_active(connection)
                raise GovernanceConfigurationError(
                    "Execution transaction failed"
                ) from error
            except Exception:
                _rollback_if_active(connection)
                raise

    @staticmethod
    def _insert_request(
        connection: sqlite3.Connection,
        request: ExecutionRequest,
    ) -> None:
        connection.execute(
            """
            INSERT INTO execution_requests (
                request_id,
                event_id,
                operation_id,
                recommended_action,
                destination_id,
                precondition_digest,
                recommendation_digest,
                approval_decision_id,
                idempotency_key,
                idempotency_digest,
                created_at,
                synthetic,
                legal_effect
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                request.request_id,
                request.event_id,
                request.operation_id,
                request.recommended_action.value,
                request.destination_id,
                request.precondition_digest,
                request.recommendation_digest,
                request.approval_decision_id,
                request.idempotency_key,
                request.idempotency_digest,
                request.created_at,
                int(request.synthetic),
                int(request.legal_effect),
            ),
        )

    @staticmethod
    def _insert_idempotency_claim(
        connection: sqlite3.Connection,
        request: ExecutionRequest,
    ) -> None:
        connection.execute(
            """
            INSERT INTO execution_idempotency (
                idempotency_key,
                request_id,
                request_digest,
                state,
                claimed_at,
                completed_at,
                failure_code
            ) VALUES (?, ?, ?, 'claimed', ?, NULL, NULL);
            """,
            (
                request.idempotency_key,
                request.request_id,
                request.idempotency_digest,
                request.created_at,
            ),
        )

    @staticmethod
    def _insert_execution_receipt(
        connection: sqlite3.Connection,
        receipt: ExecutionReceipt,
    ) -> None:
        connection.execute(
            """
            INSERT INTO execution_receipts (
                receipt_id,
                request_id,
                event_id,
                operation_id,
                action_executed,
                status,
                executor_id,
                execution_effect,
                executed_at,
                receipt_digest,
                details_json,
                synthetic,
                legal_effect
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                receipt.receipt_id,
                receipt.request_id,
                receipt.event_id,
                receipt.operation_id,
                receipt.action_executed.value,
                receipt.status.value,
                receipt.executor_id,
                receipt.execution_effect,
                receipt.executed_at,
                receipt.receipt_digest,
                to_canonical_json(dict(receipt.details)),
                int(receipt.synthetic),
                int(receipt.legal_effect),
            ),
        )

    @staticmethod
    def _insert_review_receipt(
        connection: sqlite3.Connection,
        receipt: ReviewQueueReceipt,
    ) -> None:
        connection.execute(
            """
            INSERT INTO review_queue_receipts (
                receipt_id,
                request_id,
                event_id,
                queue_destination_id,
                enqueued_at,
                receipt_digest,
                reason_code,
                details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                receipt.receipt_id,
                receipt.request_id,
                receipt.event_id,
                receipt.queue_destination_id,
                receipt.enqueued_at,
                receipt.receipt_digest,
                receipt.reason_code,
                to_canonical_json(dict(receipt.details)),
            ),
        )

    @staticmethod
    def _insert_acknowledgment(
        connection: sqlite3.Connection,
        acknowledgment: DistributionAcknowledgment,
    ) -> None:
        connection.execute(
            """
            INSERT INTO distribution_acknowledgments (
                acknowledgment_id,
                execution_receipt_id,
                destination_id,
                disposition,
                acknowledged_at,
                acknowledgment_digest
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                acknowledgment.acknowledgment_id,
                acknowledgment.execution_receipt_id,
                acknowledgment.destination_id,
                acknowledgment.disposition,
                acknowledgment.acknowledged_at,
                acknowledgment.acknowledgment_digest,
            ),
        )

    def get_execution_result_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> ExecutionResult | None:
        normalized_key = _require_text(
            idempotency_key,
            "idempotency_key",
        )

        with self._lock, self._conn() as connection:
            try:
                row = connection.execute(
                    """
                    SELECT request_id, state
                    FROM execution_idempotency
                    WHERE idempotency_key = ?;
                    """,
                    (normalized_key,),
                ).fetchone()

                if row is None:
                    return None

                if row["state"] != "completed":
                    raise GovernanceConfigurationError(
                        "Execution idempotency record is not completed"
                    )

                result = self._load_execution_result(
                    connection,
                    row["request_id"],
                )
            except GovernanceConfigurationError:
                raise
            except sqlite3.Error as error:
                raise GovernanceConfigurationError(
                    "Execution-result lookup failed"
                ) from error

        if result is None:
            raise GovernanceConfigurationError(
                "Completed execution idempotency record has no persisted result"
            )

        return result

    def _load_execution_result(
        self,
        connection: sqlite3.Connection,
        request_id: str,
    ) -> ExecutionResult | None:
        normalized_request_id = _require_text(
            request_id,
            "request_id",
        )

        try:
            request_row = connection.execute(
                """
                SELECT *
                FROM execution_requests
                WHERE request_id = ?;
                """,
                (normalized_request_id,),
            ).fetchone()

            if request_row is None:
                return None

            request = ExecutionRequest(
                request_id=request_row["request_id"],
                event_id=request_row["event_id"],
                operation_id=request_row["operation_id"],
                recommended_action=EnforcementAction(
                    request_row["recommended_action"]
                ),
                destination_id=request_row["destination_id"],
                precondition_digest=request_row["precondition_digest"],
                recommendation_digest=request_row["recommendation_digest"],
                approval_decision_id=request_row["approval_decision_id"],
                idempotency_key=request_row["idempotency_key"],
                idempotency_digest=request_row["idempotency_digest"],
                created_at=request_row["created_at"],
                synthetic=_strict_database_bool(
                    request_row["synthetic"],
                    "execution_requests.synthetic",
                ),
                legal_effect=_strict_database_bool(
                    request_row["legal_effect"],
                    "execution_requests.legal_effect",
                ),
            )

            receipt_row = connection.execute(
                """
                SELECT *
                FROM execution_receipts
                WHERE request_id = ?;
                """,
                (normalized_request_id,),
            ).fetchone()

            review_row = connection.execute(
                """
                SELECT *
                FROM review_queue_receipts
                WHERE request_id = ?;
                """,
                (normalized_request_id,),
            ).fetchone()

            if receipt_row is None and review_row is None:
                return None

            if receipt_row is not None and review_row is not None:
                raise GovernanceConfigurationError(
                    "Persisted execution contains both execution and review receipts"
                )

            receipt: ExecutionReceipt | None = None
            acknowledgment: DistributionAcknowledgment | None = None

            if receipt_row is not None:
                receipt = ExecutionReceipt(
                    receipt_id=receipt_row["receipt_id"],
                    request_id=receipt_row["request_id"],
                    event_id=receipt_row["event_id"],
                    operation_id=receipt_row["operation_id"],
                    action_executed=EnforcementAction(
                        receipt_row["action_executed"]
                    ),
                    status=ExecutionStatus(
                        receipt_row["status"]
                    ),
                    executor_id=receipt_row["executor_id"],
                    execution_effect=receipt_row["execution_effect"],
                    executed_at=receipt_row["executed_at"],
                    receipt_digest=receipt_row["receipt_digest"],
                    details=_decode_details(
                        receipt_row["details_json"],
                        "execution_receipts.details_json",
                    ),
                    synthetic=_strict_database_bool(
                        receipt_row["synthetic"],
                        "execution_receipts.synthetic",
                    ),
                    legal_effect=_strict_database_bool(
                        receipt_row["legal_effect"],
                        "execution_receipts.legal_effect",
                    ),
                )

                acknowledgment_row = connection.execute(
                    """
                    SELECT *
                    FROM distribution_acknowledgments
                    WHERE execution_receipt_id = ?;
                    """,
                    (receipt.receipt_id,),
                ).fetchone()

                if acknowledgment_row is not None:
                    acknowledgment = DistributionAcknowledgment(
                        acknowledgment_id=(
                            acknowledgment_row["acknowledgment_id"]
                        ),
                        execution_receipt_id=(
                            acknowledgment_row["execution_receipt_id"]
                        ),
                        destination_id=(
                            acknowledgment_row["destination_id"]
                        ),
                        disposition=acknowledgment_row["disposition"],
                        acknowledged_at=(
                            acknowledgment_row["acknowledged_at"]
                        ),
                        acknowledgment_digest=(
                            acknowledgment_row["acknowledgment_digest"]
                        ),
                    )

            review_receipt: ReviewQueueReceipt | None = None

            if review_row is not None:
                review_receipt = ReviewQueueReceipt(
                    receipt_id=review_row["receipt_id"],
                    request_id=review_row["request_id"],
                    event_id=review_row["event_id"],
                    queue_destination_id=review_row["queue_destination_id"],
                    enqueued_at=review_row["enqueued_at"],
                    receipt_digest=review_row["receipt_digest"],
                    reason_code=review_row["reason_code"],
                    details=_decode_details(
                        review_row["details_json"],
                        "review_queue_receipts.details_json",
                    ),
                )

            result = ExecutionResult(
                request=request,
                execution_receipt=receipt,
                review_queue_receipt=review_receipt,
                distribution_acknowledgment=acknowledgment,
                duplicate=False,
            )
            self._validate_result(request, result)
            return result

        except GovernanceConfigurationError:
            raise
        except sqlite3.Error:
            raise
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise GovernanceConfigurationError(
                "Persisted execution result is invalid"
            ) from error

    def store_mitigation_state(
        self,
        event_id: str,
        mandate_id: str,
        actions: tuple[str, ...],
        executed_at: str,
        postconditions: Mapping[str, Any],
    ) -> None:
        normalized_event_id = _require_text(
            event_id,
            "event_id",
        )
        normalized_mandate_id = _require_text(
            mandate_id,
            "mandate_id",
        )

        if not isinstance(actions, tuple):
            raise TypeError("actions must be a tuple")

        normalized_actions = tuple(
            _require_text(action, "action")
            for action in actions
        )

        if not normalized_actions:
            raise GovernanceConfigurationError(
                "Mitigation actions must not be empty"
            )

        if len(normalized_actions) != len(set(normalized_actions)):
            raise GovernanceConfigurationError(
                "Mitigation actions cannot contain duplicates"
            )

        if not isinstance(postconditions, Mapping):
            raise TypeError(
                "postconditions must be a mapping"
            )

        normalized_executed_at = parse_timestamp(
            executed_at,
            "executed_at",
        ).isoformat()
        actions_json = to_canonical_json(
            list(normalized_actions)
        )
        postconditions_json = to_canonical_json(
            dict(postconditions)
        )

        with self._lock, self._conn() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE;")
                existing_row = connection.execute(
                    """
                    SELECT actions_json, executed_at, postconditions_json
                    FROM synthetic_mitigation_state
                    WHERE event_id = ? AND mandate_id = ?;
                    """,
                    (
                        normalized_event_id,
                        normalized_mandate_id,
                    ),
                ).fetchone()

                if existing_row is not None:
                    if (
                        existing_row["actions_json"] != actions_json
                        or existing_row["executed_at"]
                        != normalized_executed_at
                        or existing_row["postconditions_json"]
                        != postconditions_json
                    ):
                        raise GovernanceConfigurationError(
                            "Conflicting mitigation replay for event and mandate"
                        )
                    connection.rollback()
                    return

                connection.execute(
                    """
                    INSERT INTO synthetic_mitigation_state (
                        state_id,
                        event_id,
                        mandate_id,
                        actions_json,
                        executed_at,
                        postconditions_json
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        f"mit_{normalized_event_id}_{normalized_mandate_id}",
                        normalized_event_id,
                        normalized_mandate_id,
                        actions_json,
                        normalized_executed_at,
                        postconditions_json,
                    ),
                )
                connection.commit()

            except GovernanceConfigurationError:
                _rollback_if_active(connection)
                raise
            except sqlite3.IntegrityError as error:
                _rollback_if_active(connection)
                raise GovernanceConfigurationError(
                    "Synthetic mitigation persistence integrity constraint violated"
                ) from error
            except sqlite3.Error as error:
                _rollback_if_active(connection)
                raise GovernanceConfigurationError(
                    "Failed to persist synthetic mitigation state"
                ) from error
            except Exception:
                _rollback_if_active(connection)
                raise
