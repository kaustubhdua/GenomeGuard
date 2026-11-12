"""Regression tests for the SQLite-to-PostgreSQL SQL compatibility layer."""
from app.postgres_store import _translate


def test_decision_replace_becomes_postgres_upsert():
    statement = (
        "INSERT OR REPLACE INTO decisions("
        "request_id,outcome,reasons_json,risk_json,transform_json,"
        "explanation_text,needs_human,private_json,release_json"
        ") VALUES(?,?,?,?,?,?,?,?,?)"
    )
    translated = _translate(statement)
    assert translated == (
        "INSERT INTO decisions(request_id,outcome,reasons_json,risk_json,transform_json,"
        "explanation_text,needs_human,private_json,release_json) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (request_id) DO UPDATE SET "
        "outcome=EXCLUDED.outcome, reasons_json=EXCLUDED.reasons_json, "
        "risk_json=EXCLUDED.risk_json, transform_json=EXCLUDED.transform_json, "
        "explanation_text=EXCLUDED.explanation_text, needs_human=EXCLUDED.needs_human, "
        "private_json=EXCLUDED.private_json, release_json=EXCLUDED.release_json"
    )
    assert translated.count("%s") == 9


def test_decision_replace_rejects_unexpected_columns():
    import pytest

    with pytest.raises(ValueError, match="unsupported decisions upsert"):
        _translate("INSERT OR REPLACE INTO decisions(request_id,untrusted_column) VALUES(?,?)")



def test_privacy_ledger_replace_becomes_composite_key_upsert():
    sql = _translate("INSERT OR REPLACE INTO epsilon_ledger VALUES(?,?,?,?)")
    assert "ON CONFLICT(requester_id,dataset_id)" in sql
    assert "epsilon_spent=EXCLUDED.epsilon_spent" in sql
    assert sql.count("%s") == 4


def test_parameter_placeholders_are_translated_without_interpolating_values():
    sql = _translate("SELECT * FROM requests WHERE requester_id=? AND id=? LIMIT ?")
    assert sql == "SELECT * FROM requests WHERE requester_id=%s AND id=%s LIMIT %s"


def test_unsupported_postgres_url_fails_before_connecting():
    import pytest

    from app.postgres_store import PostgresStore

    with pytest.raises(ValueError, match="GG_DATABASE_URL"):
        PostgresStore("sqlite:///not-postgres")

def test_closed_provider_connection_is_reopened_with_runtime_search_path(monkeypatch):
    from contextlib import nullcontext

    from app.postgres_store import PostgresStore, _ConnectionCompat

    class FakeConnection:
        def __init__(self, closed, broken=False):
            self.closed = closed
            self.broken = broken
            self.statements = []

        def transaction(self):
            return nullcontext()

        def execute(self, statement, args=()):
            self.statements.append((statement, args))

        def close(self):
            self.closed = 1

    old = FakeConnection(closed=1)
    replacement = FakeConnection(closed=0)
    calls = []

    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        return replacement

    monkeypatch.setattr("app.postgres_store.psycopg.connect", connect)
    store = object.__new__(PostgresStore)
    store.database_url = "postgresql://example.invalid/db"
    store.connect_timeout = 7
    store._transaction_depth = 0
    store.connection = old
    store.db = _ConnectionCompat(old, store)

    store._ensure_connection()

    assert len(calls) == 1
    assert calls[0][0] == (store.database_url,)
    assert calls[0][1]["connect_timeout"] == 7
    assert store.connection is replacement
    assert store.db.connection is replacement
    assert replacement.statements == [
        ("SET search_path TO genomeguard_runtime, public", ()),
    ]


def test_closed_provider_connection_is_not_reopened_inside_transaction(monkeypatch):
    import psycopg
    import pytest

    from app.postgres_store import PostgresStore

    class ClosedConnection:
        closed = 1
        broken = False

    store = object.__new__(PostgresStore)
    store.connection = ClosedConnection()
    store._transaction_depth = 1
    monkeypatch.setattr(
        "app.postgres_store.psycopg.connect",
        lambda *args, **kwargs: pytest.fail("must not reconnect mid-transaction"),
    )

    with pytest.raises(psycopg.OperationalError, match="closed during a transaction"):
        store._ensure_connection()


def test_broken_provider_session_is_reopened_even_before_closed_flag_changes(monkeypatch):
    from contextlib import nullcontext

    from app.postgres_store import PostgresStore, _ConnectionCompat

    class FakeConnection:
        def __init__(self, closed, broken):
            self.closed = closed
            self.broken = broken
            self.statements = []

        def transaction(self):
            return nullcontext()

        def execute(self, statement, args=()):
            self.statements.append((statement, args))

        def close(self):
            self.closed = 1

    old = FakeConnection(closed=0, broken=True)
    replacement = FakeConnection(closed=0, broken=False)
    monkeypatch.setattr("app.postgres_store.psycopg.connect", lambda *args, **kwargs: replacement)

    store = object.__new__(PostgresStore)
    store.database_url = "postgresql://example.invalid/db"
    store.connect_timeout = 7
    store._transaction_depth = 0
    store.connection = old
    store.db = _ConnectionCompat(old, store)

    store._ensure_connection()

    assert store.connection is replacement
    assert store.db.connection is replacement
    assert replacement.statements == [
        ("SET search_path TO genomeguard_runtime, public", ()),
    ]

def test_read_query_reconnects_before_using_broken_provider_session(monkeypatch):
    import threading
    from contextlib import nullcontext

    from app.postgres_store import PostgresStore, _ConnectionCompat

    class Cursor:
        def fetchall(self):
            return [{"ok": True}]

    class FakeConnection:
        def __init__(self, *, broken=False):
            self.closed = 0
            self.broken = broken
            self.statements = []

        def execute(self, statement, args=()):
            self.statements.append((statement, args))
            return Cursor()

        def commit(self):
            pass

        def close(self):
            self.closed = 1

        def transaction(self):
            return nullcontext()

    first = FakeConnection(broken=True)
    second = FakeConnection()
    calls = []

    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        return second

    monkeypatch.setattr("app.postgres_store.psycopg.connect", connect)

    store = object.__new__(PostgresStore)
    store.database_url = "postgresql://example.invalid/db"
    store.connect_timeout = 7
    store._transaction_depth = 0
    store.lock = threading.RLock()
    store.connection = first
    store.db = _ConnectionCompat(first, store)

    assert store.q("SELECT 1") == [{"ok": True}]
    assert first.closed == 0
    assert len(calls) == 1
    assert store.connection is second
    assert store.db.connection is second
    assert second.statements == [
        ("SET search_path TO genomeguard_runtime, public", ()),
        ("SELECT 1", ()),
    ]



def test_runtime_and_migration_connections_are_separated(monkeypatch):
    from contextlib import nullcontext

    from app.postgres_store import PostgresStore

    class FakeConnection:
        def __init__(self, url):
            self.url = url
            self.closed = False
            self.statements = []

        def transaction(self):
            return nullcontext()

        def execute(self, statement, args=()):
            self.statements.append((statement, args))
            class Cursor:
                def fetchone(self_inner):
                    if "SELECT current_user AS role" in statement:
                        return {"role": "runtime" if self.url.startswith("postgresql://runtime") else "owner"}
                    if "SELECT EXISTS" in statement and "genomeguard_runtime" in statement:
                        return {"present": True}
                    return None
            return Cursor()

        def close(self):
            self.closed = True

    connections = []

    def connect(url, **kwargs):
        connection = FakeConnection(url)
        connections.append(connection)
        return connection

    monkeypatch.setattr("app.postgres_store.psycopg.connect", connect)
    monkeypatch.setattr(PostgresStore, "_migrate", lambda self: None)

    store = PostgresStore(
        "postgresql://runtime.invalid/db",
        migration_database_url="postgresql://owner.invalid/db",
    )

    assert len(connections) == 2
    assert store.connection is connections[0]
    assert connections[0].url == "postgresql://runtime.invalid/db"
    assert connections[1].url == "postgresql://owner.invalid/db"
    assert connections[0].closed is False
    assert connections[1].closed is True
    assert all("CREATE SCHEMA" not in statement for statement, _ in connections[0].statements)
    assert any("SELECT EXISTS" in statement and "genomeguard_runtime" in statement
               for statement, _ in connections[1].statements)
    assert any("SET search_path TO genomeguard_runtime, public" in statement
               for statement, _ in connections[1].statements)
    assert store.migration_connection is None
    store.close()


def test_schema_migrations_execute_only_through_owner_connection():
    from contextlib import nullcontext
    from threading import RLock

    from app.postgres_store import PostgresStore

    class Cursor:
        def __init__(self, statement):
            self.statement = statement

        def fetchone(self):
            if "SELECT current_user AS migration_role" in self.statement:
                return {
                    "migration_role": "genomeguard_owner",
                    "schema_owner": "genomeguard_owner",
                    "can_create": True,
                    "can_set_runtime": False,
                }
            return None

    class FakeConnection:
        def __init__(self):
            self.statements = []

        def transaction(self):
            return nullcontext()

        def execute(self, statement, args=(), **kwargs):
            self.statements.append((statement, args, kwargs))
            return Cursor(statement)

    runtime = FakeConnection()
    owner = FakeConnection()
    store = object.__new__(PostgresStore)
    store.connection = runtime
    store.migration_connection = owner
    store.lock = RLock()

    store._migrate()

    assert runtime.statements == []
    assert any("CREATE TABLE IF NOT EXISTS schema_migrations" in sql
               for sql, _args, _kwargs in owner.statements)
    assert any("CREATE OR REPLACE FUNCTION" in sql
               for sql, _args, _kwargs in owner.statements)
    assert all(kwargs.get("prepare") is False for sql, _args, kwargs in owner.statements
               if "CREATE OR REPLACE FUNCTION" in sql)


def test_transaction_reconnects_if_provider_closes_session_before_transaction_starts(monkeypatch):
    import threading
    from contextlib import nullcontext

    import psycopg

    from app.postgres_store import PostgresStore, _ConnectionCompat

    class StaleTransaction:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            self.connection.broken = True
            raise psycopg.OperationalError(
                "consuming input failed: SSL connection has been closed unexpectedly"
            )

        def __exit__(self, *args):
            return False

    class FakeConnection:
        def __init__(self, *, stale=False):
            self.closed = 0
            self.broken = False
            self.stale = stale
            self.statements = []

        def transaction(self):
            return StaleTransaction(self) if self.stale else nullcontext()

        def execute(self, statement, args=()):
            self.statements.append((statement, args))

        def close(self):
            self.closed = 1

    old = FakeConnection(stale=True)
    replacement = FakeConnection()
    calls = []
    monkeypatch.setattr(
        "app.postgres_store.psycopg.connect",
        lambda *args, **kwargs: calls.append((args, kwargs)) or replacement,
    )

    store = object.__new__(PostgresStore)
    store.database_url = "postgresql://example.invalid/db"
    store.connect_timeout = 7
    store._transaction_depth = 0
    store.lock = threading.RLock()
    store.connection = old
    store.db = _ConnectionCompat(old, store)

    with store.transaction():
        assert store._transaction_depth == 1
        store.connection.execute("SELECT 42")

    assert old.closed == 1
    assert len(calls) == 1
    assert store.connection is replacement
    assert store.db.connection is replacement
    assert replacement.statements == [
        ("SET search_path TO genomeguard_runtime, public", ()),
        ("SELECT pg_advisory_xact_lock(71020261026)", ()),
        ("SELECT 42", ()),
    ]
    assert store._transaction_depth == 0


def test_transaction_never_retries_operational_error_after_application_code_started(monkeypatch):
    import threading
    from contextlib import nullcontext

    import psycopg
    import pytest

    from app.postgres_store import PostgresStore, _ConnectionCompat

    class FakeConnection:
        closed = 0
        broken = False

        def transaction(self):
            return nullcontext()

        def execute(self, statement, args=()):
            return None

        def close(self):
            self.closed = 1

    connection = FakeConnection()
    monkeypatch.setattr(
        "app.postgres_store.psycopg.connect",
        lambda *args, **kwargs: pytest.fail("application transaction must never be replayed"),
    )

    store = object.__new__(PostgresStore)
    store.database_url = "postgresql://example.invalid/db"
    store.connect_timeout = 7
    store._transaction_depth = 0
    store.lock = threading.RLock()
    store.connection = connection
    store.db = _ConnectionCompat(connection, store)

    with pytest.raises(psycopg.OperationalError, match="commit outcome is unknown"):
        with store.transaction():
            raise psycopg.OperationalError("commit outcome is unknown")

    assert connection.closed == 0
    assert store._transaction_depth == 0
