from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from amba_ai.db.governance_repository import (
    SQLITE_BUSY_TIMEOUT_MS,
    GovernanceRepository,
    create_sqlite_connection,
)
from amba_ai.governance.models import GovernanceConfigurationError


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "nested" / "governance.db"


@pytest.fixture
def repository(database_path: Path) -> GovernanceRepository:
    return GovernanceRepository(database_path)


def write_migration(
    path: Path,
    sql: str,
) -> Path:
    path.write_text(sql, encoding="utf-8")
    return path


def table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?;
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def test_repository_creates_parent_directory_and_database(
    database_path: Path,
):
    assert not database_path.parent.exists()

    repository = GovernanceRepository(database_path)

    assert database_path.parent.is_dir()
    assert database_path.is_file()

    with repository.get_connection() as connection:
        assert connection.execute("SELECT 1;").fetchone()[0] == 1


def test_connection_uses_sqlite_row_factory(database_path: Path):
    with create_sqlite_connection(database_path) as connection:
        row = connection.execute(
            "SELECT 7 AS test_value;"
        ).fetchone()

    assert isinstance(row, sqlite3.Row)
    assert row["test_value"] == 7


def test_connection_enables_foreign_keys(database_path: Path):
    with create_sqlite_connection(database_path) as connection:
        enabled = connection.execute(
            "PRAGMA foreign_keys;"
        ).fetchone()[0]

    assert enabled == 1


def test_connection_enables_wal_mode(database_path: Path):
    with create_sqlite_connection(database_path) as connection:
        journal_mode = connection.execute(
            "PRAGMA journal_mode;"
        ).fetchone()[0]

    assert str(journal_mode).lower() == "wal"


def test_connection_configures_busy_timeout(database_path: Path):
    with create_sqlite_connection(database_path) as connection:
        busy_timeout = connection.execute(
            "PRAGMA busy_timeout;"
        ).fetchone()[0]

    assert busy_timeout == SQLITE_BUSY_TIMEOUT_MS


def test_connection_configures_normal_synchronous_mode(
    database_path: Path,
):
    with create_sqlite_connection(database_path) as connection:
        synchronous = connection.execute(
            "PRAGMA synchronous;"
        ).fetchone()[0]

    assert synchronous == 1


def test_repository_rejects_missing_migration_file(
    repository: GovernanceRepository,
    tmp_path: Path,
):
    missing = tmp_path / "missing.sql"

    with pytest.raises(
        GovernanceConfigurationError,
        match="Migration script file does not exist",
    ):
        repository.apply_migration_file(missing)


def test_repository_rejects_empty_migration_file(
    repository: GovernanceRepository,
    tmp_path: Path,
):
    migration = write_migration(
        tmp_path / "empty.sql",
        "   ",
    )

    with pytest.raises(
        GovernanceConfigurationError,
        match="Migration script file is empty",
    ):
        repository.apply_migration_file(migration)


def test_repository_applies_valid_migration_atomically(
    repository: GovernanceRepository,
    tmp_path: Path,
):
    migration = write_migration(
        tmp_path / "001_valid.sql",
        """
        CREATE TABLE governance_test_records (
            record_id TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        INSERT INTO governance_test_records (
            record_id,
            value
        ) VALUES (
            'REC-001',
            'persisted'
        );
        """,
    )

    repository.apply_migration_file(migration)

    with repository.get_connection() as connection:
        row = connection.execute(
            """
            SELECT record_id, value
            FROM governance_test_records
            WHERE record_id = ?;
            """,
            ("REC-001",),
        ).fetchone()

    assert row is not None
    assert row["record_id"] == "REC-001"
    assert row["value"] == "persisted"


def test_failed_migration_rolls_back_all_prior_statements(
    repository: GovernanceRepository,
    tmp_path: Path,
):
    migration = write_migration(
        tmp_path / "002_invalid.sql",
        """
        CREATE TABLE migration_should_rollback (
            record_id TEXT PRIMARY KEY
        );

        INSERT INTO migration_should_rollback (
            record_id
        ) VALUES (
            'REC-ROLLBACK'
        );

        THIS IS INVALID SQL;
        """,
    )

    with pytest.raises(
        GovernanceConfigurationError,
        match="Failed to apply governance migration script",
    ):
        repository.apply_migration_file(migration)

    with repository.get_connection() as connection:
        assert not table_exists(
            connection,
            "migration_should_rollback",
        )


def test_migration_with_integrity_failure_rolls_back_schema_and_data(
    repository: GovernanceRepository,
    tmp_path: Path,
):
    migration = write_migration(
        tmp_path / "003_integrity_failure.sql",
        """
        CREATE TABLE migration_integrity_test (
            record_id TEXT PRIMARY KEY,
            value TEXT NOT NULL UNIQUE
        );

        INSERT INTO migration_integrity_test (
            record_id,
            value
        ) VALUES (
            'REC-001',
            'duplicate-value'
        );

        INSERT INTO migration_integrity_test (
            record_id,
            value
        ) VALUES (
            'REC-002',
            'duplicate-value'
        );
        """,
    )

    with pytest.raises(
        GovernanceConfigurationError,
        match="Failed to apply governance migration script",
    ):
        repository.apply_migration_file(migration)

    with repository.get_connection() as connection:
        assert not table_exists(
            connection,
            "migration_integrity_test",
        )


def test_idempotent_migration_can_be_reapplied(
    repository: GovernanceRepository,
    tmp_path: Path,
):
    migration = write_migration(
        tmp_path / "004_idempotent.sql",
        """
        CREATE TABLE IF NOT EXISTS idempotent_records (
            record_id TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS
            idx_idempotent_records_value
        ON idempotent_records(value);
        """,
    )

    repository.apply_migration_file(migration)
    repository.apply_migration_file(migration)

    with repository.get_connection() as connection:
        assert table_exists(connection, "idempotent_records")
        index_row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'index' AND name = ?;
            """,
            ("idx_idempotent_records_value",),
        ).fetchone()

    assert index_row is not None


def test_foreign_key_constraints_are_enforced(
    repository: GovernanceRepository,
    tmp_path: Path,
):
    migration = write_migration(
        tmp_path / "005_foreign_keys.sql",
        """
        CREATE TABLE parent_records (
            parent_id TEXT PRIMARY KEY
        );

        CREATE TABLE child_records (
            child_id TEXT PRIMARY KEY,
            parent_id TEXT NOT NULL,
            FOREIGN KEY (parent_id)
                REFERENCES parent_records(parent_id)
        );
        """,
    )
    repository.apply_migration_file(migration)

    with repository.get_connection() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO child_records (
                    child_id,
                    parent_id
                ) VALUES (?, ?);
                """,
                ("CHILD-001", "MISSING-PARENT"),
            )


def test_separate_connections_receive_the_same_configuration(
    repository: GovernanceRepository,
):
    first = repository.get_connection()
    second = repository.get_connection()

    try:
        first_settings = (
            first.execute("PRAGMA foreign_keys;").fetchone()[0],
            str(first.execute("PRAGMA journal_mode;").fetchone()[0]).lower(),
            first.execute("PRAGMA busy_timeout;").fetchone()[0],
        )
        second_settings = (
            second.execute("PRAGMA foreign_keys;").fetchone()[0],
            str(second.execute("PRAGMA journal_mode;").fetchone()[0]).lower(),
            second.execute("PRAGMA busy_timeout;").fetchone()[0],
        )
    finally:
        first.close()
        second.close()

    assert first_settings == (
        1,
        "wal",
        SQLITE_BUSY_TIMEOUT_MS,
    )
    assert second_settings == first_settings
