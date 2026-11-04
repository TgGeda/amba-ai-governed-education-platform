CREATE TABLE IF NOT EXISTS approval_requests (
    request_id TEXT PRIMARY KEY,

    event_id TEXT NOT NULL,
    recommendation_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    requested_decision TEXT NOT NULL,
    target_role TEXT NOT NULL,
    mandate_id TEXT NOT NULL,

    context_digest TEXT NOT NULL,
    request_digest TEXT NOT NULL,

    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,

    idempotency_key TEXT NOT NULL UNIQUE,

    synthetic INTEGER NOT NULL
        CHECK (synthetic IN (0, 1)),

    legal_effect INTEGER NOT NULL
        CHECK (legal_effect IN (0, 1)),

    CHECK (
        length(trim(request_id)) > 0
    ),

    CHECK (
        length(trim(event_id)) > 0
    ),

    CHECK (
        length(trim(recommendation_id)) > 0
    ),

    CHECK (
        length(trim(operation_id)) > 0
    ),

    CHECK (
        length(trim(requested_decision)) > 0
    ),

    CHECK (
        length(trim(target_role)) > 0
    ),

    CHECK (
        length(trim(mandate_id)) > 0
    ),

    CHECK (
        length(trim(idempotency_key)) > 0
    ),

    CHECK (
        NOT (
            synthetic = 1
            AND legal_effect = 1
        )
    ),

    CHECK (
        length(context_digest) = 64
        AND context_digest NOT GLOB '*[^0-9a-f]*'
        AND context_digest !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND context_digest !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    ),

    CHECK (
        length(request_digest) = 64
        AND request_digest NOT GLOB '*[^0-9a-f]*'
        AND request_digest !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND request_digest !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    ),

    CHECK (
        expires_at > created_at
    )
);

CREATE TABLE IF NOT EXISTS approval_decisions (
    decision_id TEXT PRIMARY KEY,

    request_id TEXT NOT NULL UNIQUE,
    principal_id TEXT NOT NULL,
    mandate_id TEXT NOT NULL,

    approved INTEGER NOT NULL
        CHECK (approved IN (0, 1)),

    rationale TEXT NOT NULL,
    decided_at TEXT NOT NULL,

    request_digest TEXT NOT NULL,
    decision_digest TEXT NOT NULL,

    synthetic INTEGER NOT NULL
        CHECK (synthetic IN (0, 1)),

    legal_effect INTEGER NOT NULL
        CHECK (legal_effect IN (0, 1)),

    FOREIGN KEY (request_id)
        REFERENCES approval_requests(request_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CHECK (
        length(trim(decision_id)) > 0
    ),

    CHECK (
        length(trim(request_id)) > 0
    ),

    CHECK (
        length(trim(principal_id)) > 0
    ),

    CHECK (
        length(trim(mandate_id)) > 0
    ),

    CHECK (
        length(trim(rationale)) > 0
    ),

    CHECK (
        NOT (
            synthetic = 1
            AND legal_effect = 1
        )
    ),

    CHECK (
        length(request_digest) = 64
        AND request_digest NOT GLOB '*[^0-9a-f]*'
        AND request_digest !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND request_digest !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    ),

    CHECK (
        length(decision_digest) = 64
        AND decision_digest NOT GLOB '*[^0-9a-f]*'
        AND decision_digest !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND decision_digest !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    )
);

CREATE INDEX IF NOT EXISTS
    idx_approval_requests_event
ON approval_requests(event_id);

CREATE INDEX IF NOT EXISTS
    idx_approval_requests_recommendation
ON approval_requests(recommendation_id);

CREATE INDEX IF NOT EXISTS
    idx_approval_requests_operation
ON approval_requests(operation_id);

CREATE INDEX IF NOT EXISTS
    idx_approval_requests_mandate
ON approval_requests(mandate_id);

CREATE INDEX IF NOT EXISTS
    idx_approval_requests_idempotency
ON approval_requests(idempotency_key);

CREATE INDEX IF NOT EXISTS
    idx_approval_decisions_principal
ON approval_decisions(principal_id);

CREATE INDEX IF NOT EXISTS
    idx_approval_decisions_mandate
ON approval_decisions(mandate_id);

CREATE TABLE IF NOT EXISTS execution_requests (
    request_id TEXT PRIMARY KEY,

    event_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,

    recommended_action TEXT NOT NULL
        CHECK (
            recommended_action IN (
                'proceed',
                'confirm',
                'hold_for_review',
                'require_approval',
                'modify',
                'block',
                'abstain'
            )
        ),

    destination_id TEXT NOT NULL,

    precondition_digest TEXT NOT NULL,
    recommendation_digest TEXT NOT NULL,

    approval_decision_id TEXT,

    idempotency_key TEXT NOT NULL UNIQUE,
    idempotency_digest TEXT NOT NULL,

    created_at TEXT NOT NULL,

    synthetic INTEGER NOT NULL
        CHECK (synthetic IN (0, 1)),

    legal_effect INTEGER NOT NULL
        CHECK (legal_effect IN (0, 1)),

    FOREIGN KEY (approval_decision_id)
        REFERENCES approval_decisions(decision_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CHECK (
        length(trim(request_id)) > 0
    ),

    CHECK (
        length(trim(event_id)) > 0
    ),

    CHECK (
        length(trim(operation_id)) > 0
    ),

    CHECK (
        length(trim(destination_id)) > 0
    ),

    CHECK (
        length(trim(idempotency_key)) > 0
    ),

    CHECK (
        NOT (
            synthetic = 1
            AND legal_effect = 1
        )
    ),

    CHECK (
        length(precondition_digest) = 64
        AND precondition_digest NOT GLOB '*[^0-9a-f]*'
        AND precondition_digest !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND precondition_digest !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    ),

    CHECK (
        length(recommendation_digest) = 64
        AND recommendation_digest NOT GLOB '*[^0-9a-f]*'
        AND recommendation_digest !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND recommendation_digest !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    ),

    CHECK (
        length(idempotency_digest) = 64
        AND idempotency_digest NOT GLOB '*[^0-9a-f]*'
        AND idempotency_digest !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND idempotency_digest !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    )
);

CREATE TABLE IF NOT EXISTS execution_idempotency (
    idempotency_key TEXT PRIMARY KEY,

    request_id TEXT NOT NULL UNIQUE,
    request_digest TEXT NOT NULL,

    state TEXT NOT NULL
        CHECK (
            state IN (
                'claimed',
                'completed',
                'failed'
            )
        ),

    claimed_at TEXT NOT NULL,
    completed_at TEXT,
    failure_code TEXT,

    FOREIGN KEY (request_id)
        REFERENCES execution_requests(request_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CHECK (
        length(trim(idempotency_key)) > 0
    ),

    CHECK (
        length(request_digest) = 64
        AND request_digest NOT GLOB '*[^0-9a-f]*'
        AND request_digest !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND request_digest !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    ),

    CHECK (
        completed_at IS NULL
        OR completed_at >= claimed_at
    ),

    CHECK (
        (
            state = 'claimed'
            AND completed_at IS NULL
            AND failure_code IS NULL
        )
        OR (
            state = 'completed'
            AND completed_at IS NOT NULL
            AND failure_code IS NULL
        )
        OR (
            state = 'failed'
            AND completed_at IS NOT NULL
            AND length(trim(failure_code)) > 0
        )
    )
);

CREATE TABLE IF NOT EXISTS execution_receipts (
    receipt_id TEXT PRIMARY KEY,

    request_id TEXT NOT NULL UNIQUE,
    event_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,

    action_executed TEXT NOT NULL
        CHECK (
            action_executed IN (
                'proceed',
                'confirm',
                'hold_for_review',
                'require_approval',
                'modify',
                'block',
                'abstain'
            )
        ),

    status TEXT NOT NULL
        CHECK (
            status IN (
                'succeeded',
                'failed',
                'not_attempted',
                'duplicate',
                'cancelled'
            )
        ),

    executor_id TEXT NOT NULL,
    execution_effect TEXT NOT NULL,
    executed_at TEXT NOT NULL,

    receipt_digest TEXT NOT NULL,
    details_json TEXT NOT NULL,

    synthetic INTEGER NOT NULL
        CHECK (synthetic IN (0, 1)),

    legal_effect INTEGER NOT NULL
        CHECK (legal_effect IN (0, 1)),

    FOREIGN KEY (request_id)
        REFERENCES execution_requests(request_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CHECK (
        length(trim(receipt_id)) > 0
    ),

    CHECK (
        length(trim(event_id)) > 0
    ),

    CHECK (
        length(trim(operation_id)) > 0
    ),

    CHECK (
        length(trim(executor_id)) > 0
    ),

    CHECK (
        length(trim(execution_effect)) > 0
    ),

    CHECK (
        NOT (
            synthetic = 1
            AND legal_effect = 1
        )
    ),

    CHECK (
        length(receipt_digest) = 64
        AND receipt_digest NOT GLOB '*[^0-9a-f]*'
        AND receipt_digest !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND receipt_digest !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    )
);

CREATE TABLE IF NOT EXISTS review_queue_receipts (
    receipt_id TEXT PRIMARY KEY,

    request_id TEXT NOT NULL UNIQUE,
    event_id TEXT NOT NULL,

    queue_destination_id TEXT NOT NULL,
    enqueued_at TEXT NOT NULL,

    receipt_digest TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    details_json TEXT NOT NULL,

    FOREIGN KEY (request_id)
        REFERENCES execution_requests(request_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CHECK (
        length(trim(receipt_id)) > 0
    ),

    CHECK (
        length(trim(event_id)) > 0
    ),

    CHECK (
        length(trim(queue_destination_id)) > 0
    ),

    CHECK (
        length(trim(reason_code)) > 0
    ),

    CHECK (
        length(receipt_digest) = 64
        AND receipt_digest NOT GLOB '*[^0-9a-f]*'
        AND receipt_digest !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND receipt_digest !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    )
);

CREATE TABLE IF NOT EXISTS distribution_acknowledgments (
    acknowledgment_id TEXT PRIMARY KEY,

    execution_receipt_id TEXT NOT NULL UNIQUE,
    destination_id TEXT NOT NULL,
    disposition TEXT NOT NULL,

    acknowledged_at TEXT NOT NULL,
    acknowledgment_digest TEXT NOT NULL,

    FOREIGN KEY (execution_receipt_id)
        REFERENCES execution_receipts(receipt_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CHECK (
        length(trim(acknowledgment_id)) > 0
    ),

    CHECK (
        length(trim(destination_id)) > 0
    ),

    CHECK (
        length(trim(disposition)) > 0
    ),

    CHECK (
        length(acknowledgment_digest) = 64
        AND acknowledgment_digest NOT GLOB '*[^0-9a-f]*'
        AND acknowledgment_digest !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND acknowledgment_digest !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    )
);

CREATE TRIGGER IF NOT EXISTS
    trg_distribution_ack_requires_successful_proceed
BEFORE INSERT ON distribution_acknowledgments
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NOT EXISTS (
            SELECT 1
            FROM execution_receipts
            WHERE receipt_id = NEW.execution_receipt_id
              AND status = 'succeeded'
              AND action_executed = 'proceed'
        )
        THEN RAISE(
            ABORT,
            'distribution acknowledgment requires successful proceed receipt'
        )
    END;
END;

CREATE TABLE IF NOT EXISTS synthetic_mitigation_state (
    state_id TEXT PRIMARY KEY,

    event_id TEXT NOT NULL,
    mandate_id TEXT NOT NULL,

    actions_json TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    postconditions_json TEXT NOT NULL,

    CHECK (
        length(trim(state_id)) > 0
    ),

    CHECK (
        length(trim(event_id)) > 0
    ),

    CHECK (
        length(trim(mandate_id)) > 0
    ),

    CHECK (
        length(trim(actions_json)) > 0
    ),

    CHECK (
        length(trim(postconditions_json)) > 0
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS
    idx_synthetic_mitigation_event_mandate
ON synthetic_mitigation_state(
    event_id,
    mandate_id
);

CREATE INDEX IF NOT EXISTS
    idx_execution_requests_event
ON execution_requests(event_id);

CREATE INDEX IF NOT EXISTS
    idx_execution_requests_operation
ON execution_requests(operation_id);

CREATE INDEX IF NOT EXISTS
    idx_execution_requests_destination
ON execution_requests(destination_id);

CREATE INDEX IF NOT EXISTS
    idx_execution_requests_approval
ON execution_requests(approval_decision_id);

CREATE INDEX IF NOT EXISTS
    idx_execution_idempotency_state
ON execution_idempotency(state);

CREATE INDEX IF NOT EXISTS
    idx_execution_receipts_event
ON execution_receipts(event_id);

CREATE INDEX IF NOT EXISTS
    idx_review_queue_receipts_event
ON review_queue_receipts(event_id);

CREATE TABLE IF NOT EXISTS governance_audit_blocks (
    run_id TEXT NOT NULL,

    block_index INTEGER NOT NULL
        CHECK (block_index > 0),

    audit_event_id TEXT NOT NULL,

    scenario_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,

    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    schema_version TEXT NOT NULL,

    payload_json TEXT NOT NULL,

    previous_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    block_hash TEXT NOT NULL,

    PRIMARY KEY (
        run_id,
        block_index
    ),

    UNIQUE (
        run_id,
        audit_event_id
    ),

    CHECK (
        length(trim(run_id)) > 0
    ),

    CHECK (
        length(trim(audit_event_id)) > 0
    ),

    CHECK (
        length(trim(scenario_id)) > 0
    ),

    CHECK (
        length(trim(stage_id)) > 0
    ),

    CHECK (
        length(trim(event_id)) > 0
    ),

    CHECK (
        length(trim(operation_id)) > 0
    ),

    CHECK (
        length(trim(event_type)) > 0
    ),

    CHECK (
        length(trim(schema_version)) > 0
    ),

    CHECK (
        length(trim(payload_json)) > 0
    ),

    CHECK (
        length(previous_hash) = 64
        AND previous_hash NOT GLOB '*[^0-9a-f]*'
        AND previous_hash !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND previous_hash !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    ),

    CHECK (
        length(payload_hash) = 64
        AND payload_hash NOT GLOB '*[^0-9a-f]*'
        AND payload_hash !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND payload_hash !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    ),

    CHECK (
        length(block_hash) = 64
        AND block_hash NOT GLOB '*[^0-9a-f]*'
        AND block_hash !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND block_hash !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    )
);

CREATE INDEX IF NOT EXISTS
    idx_governance_audit_run
ON governance_audit_blocks(
    run_id,
    block_index
);

CREATE INDEX IF NOT EXISTS
    idx_governance_audit_event
ON governance_audit_blocks(
    event_id,
    operation_id
);

CREATE INDEX IF NOT EXISTS
    idx_governance_audit_scenario_stage
ON governance_audit_blocks(
    scenario_id,
    stage_id
);