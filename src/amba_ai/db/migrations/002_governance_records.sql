CREATE TABLE IF NOT EXISTS governance_principals (
    principal_id TEXT PRIMARY KEY,
    role TEXT NOT NULL,

    synthetic INTEGER NOT NULL
        CHECK (synthetic IN (0, 1)),

    legal_effect INTEGER NOT NULL
        CHECK (legal_effect IN (0, 1)),

    credential_digest TEXT NOT NULL,

    credential_algorithm TEXT NOT NULL
        CHECK (credential_algorithm = 'scrypt'),

    credential_salt TEXT NOT NULL,

    active_from TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    disabled_at TEXT,

    mandate_ids_json TEXT NOT NULL,

    CHECK (
        length(trim(principal_id)) > 0
    ),

    CHECK (
        length(trim(role)) > 0
    ),

    CHECK (
        NOT (
            synthetic = 1
            AND legal_effect = 1
        )
    ),

    CHECK (
        length(credential_digest) = 64
        AND credential_digest NOT GLOB '*[^0-9a-f]*'
        AND credential_digest !=
            '0000000000000000000000000000000000000000000000000000000000000000'
        AND credential_digest !=
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    ),

    CHECK (
        length(credential_salt) >= 32
        AND length(credential_salt) % 2 = 0
        AND credential_salt NOT GLOB '*[^0-9a-f]*'
    ),

    CHECK (
        length(trim(active_from)) > 0
    ),

    CHECK (
        length(trim(expires_at)) > 0
    ),

    CHECK (
        expires_at > active_from
    ),

    CHECK (
        disabled_at IS NULL
        OR disabled_at >= active_from
    )
);

CREATE TABLE IF NOT EXISTS governance_mandates (
    mandate_id TEXT PRIMARY KEY,

    principal_id TEXT NOT NULL,
    role TEXT NOT NULL,

    permitted_operations_json TEXT NOT NULL,
    permitted_decisions_json TEXT NOT NULL,

    synthetic INTEGER NOT NULL
        CHECK (synthetic IN (0, 1)),

    legal_effect INTEGER NOT NULL
        CHECK (legal_effect IN (0, 1)),

    active_from TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,

    FOREIGN KEY (principal_id)
        REFERENCES governance_principals(principal_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CHECK (
        length(trim(mandate_id)) > 0
    ),

    CHECK (
        length(trim(principal_id)) > 0
    ),

    CHECK (
        length(trim(role)) > 0
    ),

    CHECK (
        length(trim(permitted_operations_json)) > 0
    ),

    CHECK (
        length(trim(permitted_decisions_json)) > 0
    ),

    CHECK (
        NOT (
            synthetic = 1
            AND legal_effect = 1
        )
    ),

    CHECK (
        length(trim(active_from)) > 0
    ),

    CHECK (
        length(trim(expires_at)) > 0
    ),

    CHECK (
        expires_at > active_from
    ),

    CHECK (
        revoked_at IS NULL
        OR revoked_at >= active_from
    )
);

CREATE INDEX IF NOT EXISTS
    idx_governance_principals_role
ON governance_principals(role);

CREATE INDEX IF NOT EXISTS
    idx_governance_principals_active_window
ON governance_principals(
    active_from,
    expires_at,
    disabled_at
);

CREATE INDEX IF NOT EXISTS
    idx_governance_mandates_principal
ON governance_mandates(principal_id);

CREATE INDEX IF NOT EXISTS
    idx_governance_mandates_role
ON governance_mandates(role);

CREATE INDEX IF NOT EXISTS
    idx_governance_mandates_active_window
ON governance_mandates(
    active_from,
    expires_at,
    revoked_at
);