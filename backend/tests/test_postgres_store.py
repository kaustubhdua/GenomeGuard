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
        def __init__(self, closed):
            self.closed = closed
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
    import pytest
    import psycopg

    from app.postgres_store import PostgresStore

    class ClosedConnection:
        closed = 1

    store = object.__new__(PostgresStore)
    store.connection = ClosedConnection()
    store._transaction_depth = 1
    monkeypatch.setattr(
        "app.postgres_store.psycopg.connect",
        lambda *args, **kwargs: pytest.fail("must not reconnect mid-transaction"),
    )

    with pytest.raises(psycopg.OperationalError, match="closed during a transaction"):
        store._ensure_connection()

