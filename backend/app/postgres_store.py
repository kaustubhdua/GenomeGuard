"""PostgreSQL-backed implementation of the Store contract.

This adapter deliberately reuses the domain/store methods in app.store.Store while replacing
SQLite's connection semantics with PostgreSQL, an explicit schema migration, and transactional
writes. It is opt-in via GG_DATABASE_URL; no database is created or provisioned by this module.
"""
from __future__ import annotations

import re
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.core.audit_chain import GENESIS, entry_hash, jsonable
from app.store import Store, now_iso

_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def _translate(sql: str) -> str:
    """Translate the small, known SQLite SQL subset used by Store into PostgreSQL SQL."""
    statement = sql.strip()
    if statement.upper().startswith("INSERT OR REPLACE INTO DECISIONS"):
        match = re.match(
            r"INSERT OR REPLACE INTO decisions\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
            statement, re.IGNORECASE,
        )
        if not match:
            raise ValueError("unsupported decisions upsert statement")
        columns = [c.strip() for c in match.group(1).split(",")]
        updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in columns if c != "request_id")
        statement = (f"INSERT INTO decisions ({', '.join(columns)}) VALUES ({match.group(2)}) "
                     f"ON CONFLICT (request_id) DO UPDATE SET {updates}")
    elif statement.upper().startswith("INSERT OR REPLACE INTO EPSILON_LEDGER"):
        statement = (
            "INSERT INTO epsilon_ledger(requester_id,dataset_id,epsilon_spent,updated_at) "
            "VALUES(?,?,?,?) ON CONFLICT(requester_id,dataset_id) DO UPDATE SET "
            "epsilon_spent=EXCLUDED.epsilon_spent, updated_at=EXCLUDED.updated_at"
        )
    return statement.replace("?", "%s")


class _ConnectionCompat:
    """Minimal connection facade for the existing Store methods; SQL remains parameterized."""
    def __init__(self, connection: psycopg.Connection, store) -> None:
        self.connection = connection
        self.store = store

    def execute(self, sql: str, args: tuple = ()):
        return self.connection.execute(_translate(sql), args)

    def executemany(self, sql: str, args):
        return self.connection.cursor().executemany(_translate(sql), args)

    def commit(self) -> None:
        if self.store._transaction_depth == 0:
            self.connection.commit()


class PostgresStore(Store):
    """PostgreSQL store with serialized connection access and versioned migrations."""

    backend = "postgresql"
    durable = True  # means PostgreSQL is configured, not that provider backups are verified

    def __init__(self, database_url: str, *, connect_timeout: int = 10) -> None:
        if not database_url or not database_url.startswith(("postgres://", "postgresql://")):
            raise ValueError("GG_DATABASE_URL must be a PostgreSQL connection URL")
        self.path = "postgresql"
        self.lock = threading.RLock()
        self._transaction_depth = 0
        self.connection = psycopg.connect(
            database_url, connect_timeout=connect_timeout, row_factory=dict_row,
            application_name="GenomeGuard",
        )
        self.db = _ConnectionCompat(self.connection, self)
        try:
            self._migrate()
        except Exception:
            self.connection.close()
            raise

    def _migrate(self) -> None:
        migration = _MIGRATIONS / "001_initial_postgres.sql"
        if not migration.is_file():
            raise RuntimeError(f"PostgreSQL migration is missing: {migration.name}")
        with self.lock, self.connection.transaction():
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            applied = self.connection.execute(
                "SELECT version FROM schema_migrations WHERE version=1"
            ).fetchone()
            if applied:
                return
            # Migration files contain only DDL statements without procedural blocks.
            # Remove full-line SQL comments before splitting statements. Splitting raw SQL
            # on semicolons otherwise leaves the trailing comment text attached to the first DDL.
            sql = "\n".join(
                line for line in migration.read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("--")
            )
            for statement in sql.split(";"):
                if statement.strip():
                    self.connection.execute(statement)
            self.connection.execute("INSERT INTO schema_migrations(version) VALUES (1)")

    def q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            rows = list(self.connection.execute(_translate(sql), args).fetchall())
            if self._transaction_depth == 0:
                self.connection.commit()
            return rows

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql: str, args: tuple = ()) -> int:
        """Execute one statement atomically and return generated id where applicable."""
        with self.lock:
            statement = _translate(sql)
            insert = re.match(r"INSERT\s+INTO\s+(\w+)", statement, re.IGNORECASE)
            id_tables = {"requesters", "requests", "alerts"}
            if insert and insert.group(1).lower() in id_tables:
                statement = statement.rstrip().rstrip(";") + " RETURNING id"
                row = self.connection.execute(statement, args).fetchone()
                if self._transaction_depth == 0:
                    self.connection.commit()
                return int(row["id"]) if row else 0
            self.connection.execute(statement, args)
            if self._transaction_depth == 0:
                self.connection.commit()
            return 0


    @contextmanager
    def transaction(self):
        """Atomic unit of work; nested store calls use savepoints and do not commit early."""
        with self.lock:
            self._transaction_depth += 1
            try:
                with self.connection.transaction():
                    # Serialize mutation units across instances. This conservative lock prevents
                    # concurrent requests from racing the privacy-budget read/charge sequence.
                    self.connection.execute("SELECT pg_advisory_xact_lock(71020261026)")
                    yield
            finally:
                self._transaction_depth -= 1

    def append_audit_entry(self, actor: str, action: str, payload: Any, ts: str | None = None) -> dict:
        """Serialize audit sequence allocation across workers and commit the row atomically."""
        import json

        with self.lock, self.connection.transaction():
            # Transaction-scoped advisory lock coordinates separate workers and instances.
            self.connection.execute("SELECT pg_advisory_xact_lock(71020261025)")
            last = self.connection.execute(
                "SELECT idx, hash FROM audit_log ORDER BY idx DESC LIMIT 1"
            ).fetchone()
            idx = int(last["idx"]) + 1 if last else 1
            previous = last["hash"] if last else GENESIS
            stamp = ts or now_iso()
            safe_payload = jsonable(payload)
            entry = {
                "idx": idx, "ts": stamp, "actor": actor, "action": action,
                "payload": safe_payload, "prev_hash": previous,
                "hash": entry_hash(idx, stamp, actor, action, safe_payload, previous),
            }
            self.connection.execute(
                "INSERT INTO audit_log(idx,ts,actor,action,payload_json,prev_hash,hash) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (idx, stamp, actor, action, json.dumps(safe_payload), previous, entry["hash"]),
            )
            return entry

    def close(self) -> None:
        with self.lock:
            self.connection.close()
