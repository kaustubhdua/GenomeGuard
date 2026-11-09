"""Regression tests for the SQLite-to-PostgreSQL SQL compatibility layer."""
from app.postgres_store import _translate


def test_decision_replace_becomes_postgres_upsert():
    sql = _translate(
        "INSERT OR REPLACE INTO decisions(request_id,outcome,reasons_json) VALUES(?,?,?)"
    )
    assert "ON CONFLICT (request_id) DO UPDATE SET" in sql
    assert "outcome=EXCLUDED.outcome" in sql
    assert "reasons_json=EXCLUDED.reasons_json" in sql
    assert "?" not in sql


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
    from contextlib import nullcontext
    import threading

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
