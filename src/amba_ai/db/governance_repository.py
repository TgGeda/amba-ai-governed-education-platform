from __future__ import annotations

from pathlib import Path
import sqlite3
import threading

from amba_ai.governance.models import GovernanceConfigurationError


SQLITE_TIMEOUT_SECONDS = 30.0
SQLITE_BUSY_TIMEOUT_MS = 30_000


def _close_quietly(
    connection: sqlite3.Connection,
) -> None:
    try:
        connection.close()
    except sqlite3.Error:
        pass


def _configure_connection(
    connection: sqlite3.Connection,
) -> None:
    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON;"
    )

    foreign_keys_enabled = connection.execute(
        "PRAGMA foreign_keys;"
    ).fetchone()[0]

    if foreign_keys_enabled != 1:
        raise GovernanceConfigurationError(
            "SQLite foreign-key enforcement "
            "could not be enabled"
        )

    connection.execute(
        f"PRAGMA busy_timeout = "
        f"{SQLITE_BUSY_TIMEOUT_MS};"
    )

    journal_mode = connection.execute(
        "PRAGMA journal_mode = WAL;"
    ).fetchone()[0]

    if str(journal_mode).lower() != "wal":
        raise GovernanceConfigurationError(
            "SQLite WAL journal mode "
            "could not be enabled"
        )

    connection.execute(
        "PRAGMA synchronous = NORMAL;"
    )


def create_sqlite_connection(
    db_path: Path | str,
) -> sqlite3.Connection:
    path = Path(db_path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        connection = sqlite3.connect(
            str(path),
            timeout=SQLITE_TIMEOUT_SECONDS,
            isolation_level=None,
        )

        _configure_connection(connection)

        return connection

    except GovernanceConfigurationError:
        if "connection" in locals():
            _close_quietly(connection)

        raise

    except (OSError, sqlite3.Error) as error:
        if "connection" in locals():
            _close_quietly(connection)

        raise GovernanceConfigurationError(
            "SQLite governance connection "
            "could not be created"
        ) from error


class GovernanceRepository:
    def __init__(
        self,
        db_path: Path | str,
    ) -> None:
        self.db_path = Path(db_path)

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._lock = threading.RLock()

        self._initialize_database()

    def _initialize_database(self) -> None:
        connection = self.get_connection()

        try:
            connection.execute("SELECT 1;")
        except sqlite3.Error as error:
            raise GovernanceConfigurationError(
                "SQLite governance database "
                "initialization failed"
            ) from error
        finally:
            _close_quietly(connection)

    def get_connection(
        self,
    ) -> sqlite3.Connection:
        return create_sqlite_connection(
            self.db_path
        )

    def apply_migration_file(
        self,
        migration_path: Path | str,
    ) -> None:
        path = Path(migration_path)

        if not path.is_file():
            raise GovernanceConfigurationError(
                "Migration script file does not exist"
            )

        try:
            sql = path.read_text(
                encoding="utf-8"
            )
        except (
            OSError,
            UnicodeError,
        ) as error:
            raise GovernanceConfigurationError(
                "Migration script file "
                "could not be read"
            ) from error

        if not sql.strip():
            raise GovernanceConfigurationError(
                "Migration script file is empty"
            )

        script = (
            "BEGIN IMMEDIATE;\n"
            + sql
            + "\nCOMMIT;"
        )

        with self._lock:
            connection = self.get_connection()

            try:
                connection.executescript(script)

            except sqlite3.Error as error:
                if connection.in_transaction:
                    connection.rollback()

                raise GovernanceConfigurationError(
                    "Failed to apply governance "
                    "migration script"
                ) from error

            finally:
                connection.close()