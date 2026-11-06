"""SQLite UnitOfWork implementation.

Each instance opens its own connection, begins an IMMEDIATE transaction
on __enter__, and either commits or rolls back on __exit__. The
UnitOfWorkFactory is just a callable returning a fresh instance.
"""

from __future__ import annotations

import sqlite3
from types import TracebackType

from relayer.application.unit_of_work import UnitOfWorkFactory
from relayer.infrastructure.persistence.schema import SCHEMA_SQL
from relayer.infrastructure.persistence.sqlite_payment_repository import (
    SQLitePaymentRepository,
)


def init_schema(db_path: str) -> None:
    """Create the schema if it does not exist. Idempotent."""
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.executescript(SCHEMA_SQL)
    finally:
        conn.close()


def make_sqlite_uow_factory(db_path: str) -> UnitOfWorkFactory:
    """Return a factory producing a fresh SQLiteUnitOfWork per call."""

    def factory() -> SQLiteUnitOfWork:
        conn = sqlite3.connect(db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return SQLiteUnitOfWork(conn)

    return factory


class SQLiteUnitOfWork:
    """UnitOfWork backed by a dedicated SQLite connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._payments = SQLitePaymentRepository(conn)
        self._committed = False
        self._entered = False

    @property
    def payments(self) -> SQLitePaymentRepository:
        return self._payments

    def __enter__(self) -> "SQLiteUnitOfWork":
        self._conn.execute("BEGIN IMMEDIATE")
        self._entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if not self._committed:
                self._conn.execute("ROLLBACK")
        finally:
            self._conn.close()

    def commit(self) -> None:
        if not self._entered:
            raise RuntimeError("commit() called outside of context manager")
        if self._committed:
            raise RuntimeError("commit() called twice")
        self._conn.execute("COMMIT")
        self._committed = True

    def rollback(self) -> None:
        if not self._entered:
            raise RuntimeError("rollback() called outside of context manager")
        self._conn.execute("ROLLBACK")
