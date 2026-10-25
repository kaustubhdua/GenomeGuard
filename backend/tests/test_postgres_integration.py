"""Real PostgreSQL integration tests. CI provides an isolated disposable PostgreSQL service."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.audit_chain import AuditChain
from app.postgres_store import PostgresStore
from app.store import AuditStore


@pytest.fixture
def pg_store():
    url = os.environ.get("GG_TEST_DATABASE_URL")
    if not url:
        pytest.skip("GG_TEST_DATABASE_URL is not configured")
    store = PostgresStore(url)
    # This fixture must only ever point to a disposable test database.
    with store.lock, store.connection.transaction():
        store.connection.execute(
            "TRUNCATE audit_log, donor_access, epsilon_ledger, decisions, requests, "
            "requesters, alerts, genotypes, donors, variants, relationships, cohort_metadata "
            "RESTART IDENTITY CASCADE"
        )
    try:
        yield store
    finally:
        store.close()


def test_postgres_persists_request_decision_budget_and_audit(pg_store):
    requester_id = pg_store.add_requester(
        "Integration Researcher", "researcher", "standard", "test-institution", "hash-test-key"
    )
    request_id = pg_store.add_request(
        requester_id, "2026-10-25T00:00:00+00:00",
        {"purpose": "research", "disease": None, "is_commercial": False,
         "data_level": "frequency", "cohort_filter": {}, "variant_filter": {}},
    )
    pg_store.save_decision(request_id, {
        "outcome": "release", "reasons": ["test-policy"], "risk": {"level": "low"},
        "transform": {"method": "aggregate"}, "explanation": "integration-test decision",
        "needs_human": False, "private": {"internal": True},
        "release": {"count": 3},
    })
    pg_store.set_eps_spent(requester_id, "test-dataset", 0.25)

    audit = AuditChain(AuditStore(pg_store))
    audit.append("integration-test", "request.created", {"request_id": request_id})
    audit.append("integration-test", "decision.recorded", {"request_id": request_id})

    decision = pg_store.decision(request_id)
    assert decision is not None
    assert decision["requester_id"] == requester_id
    assert decision["outcome"] == "release"
    assert decision["release"] == {"count": 3}
    assert pg_store.eps_spent(requester_id, "test-dataset") == pytest.approx(0.25)
    assert audit.verify()["ok"] is True
    assert audit.verify()["length"] == 2


def test_postgres_concurrent_audit_appends_have_unique_contiguous_sequence(pg_store):
    audit = AuditChain(AuditStore(pg_store))
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda i: audit.append("worker", "concurrent.test", {"i": i}), range(100)))
    result = audit.verify()
    assert result["ok"] is True
    assert result["length"] == 100
    assert [entry["idx"] for entry in audit.entries()] == list(range(1, 101))


def test_postgres_store_survives_connection_reopen(pg_store):
    url = os.environ["GG_TEST_DATABASE_URL"]
    requester_id = pg_store.add_requester(
        "Persistence Researcher", "researcher", "standard", "test-institution", "persist-test-key"
    )
    pg_store.close()
    reopened = PostgresStore(url)
    try:
        assert reopened.requester(requester_id)["name"] == "Persistence Researcher"
    finally:
        reopened.close()


def test_postgres_unit_of_work_rolls_back_all_store_writes(pg_store):
    with pytest.raises(RuntimeError, match="injected failure"):
        with pg_store.transaction():
            pg_store.add_requester(
                "Rollback Researcher", "researcher", "standard", "test-institution", "rollback-test-key"
            )
            raise RuntimeError("injected failure")
    assert pg_store.one("SELECT id FROM requesters WHERE name=?", ("Rollback Researcher",)) is None
