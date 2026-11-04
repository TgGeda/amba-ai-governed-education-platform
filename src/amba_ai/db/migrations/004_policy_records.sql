-- Policy-record persistence for the authoritative governance database.
-- Transaction control is owned by GovernanceRepository.apply_migration_file().
-- Policy-record history is retained by record_id, version_id, and source_id.

CREATE TABLE IF NOT EXISTS policy_records (
    record_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    record_digest TEXT NOT NULL,
    activation_status TEXT NOT NULL,

    PRIMARY KEY (
        record_id,
        version_id,
        source_id
    ),

    CHECK (length(trim(record_id)) > 0),
    CHECK (record_id = trim(record_id)),
    CHECK (length(trim(version_id)) > 0),
    CHECK (version_id = trim(version_id)),
    CHECK (length(trim(source_id)) > 0),
    CHECK (source_id = trim(source_id)),
    CHECK (length(record_json) > 0),
    CHECK (
        length(record_digest) = 64
        AND record_digest = lower(record_digest)
        AND record_digest NOT GLOB '*[^0-9a-f]*'
    ),
    CHECK (
        activation_status IN (
            'active',
            'inactive',
            'quarantined',
            'superseded',
            'draft'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_policy_records_record_id
ON policy_records (
    record_id
);

CREATE INDEX IF NOT EXISTS idx_policy_records_source_id
ON policy_records (
    source_id
);

CREATE INDEX IF NOT EXISTS idx_policy_records_activation_status
ON policy_records (
    activation_status
);

CREATE INDEX IF NOT EXISTS idx_policy_records_record_activation
ON policy_records (
    record_id,
    activation_status
);

-- A record identifier may retain multiple historical versions, but only one
-- version may be active at a time. This reinforces fail-closed lookup behavior
-- when concurrent writers or external database tools are used.
CREATE UNIQUE INDEX IF NOT EXISTS uq_policy_records_one_active_version
ON policy_records (
    record_id
)
WHERE activation_status = 'active';
