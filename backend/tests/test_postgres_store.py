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
