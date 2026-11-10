"""Real PostgreSQL integration tests. CI provides an isolated disposable PostgreSQL service."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import psycopg
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
            "TRUNCATE audit_log, donor_access, consent_events, identity_bindings, "
            "epsilon_ledger, decisions, requests, requesters, alerts, genotypes, donors, "
            "variants, relationships, cohort_metadata "
            "RESTART IDENTITY CASCADE"
        )
    try:
        yield store
    finally:
        store.close()


def test_postgres_store_uses_schema_separate_from_normalized_supabase_tables(pg_store):
    assert pg_store.one("SELECT current_schema() AS schema")["schema"] == "genomeguard_runtime"


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

    pg_store.set_request_status(request_id, "released")
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


def test_postgres_mutation_lock_prevents_concurrent_budget_lost_updates(pg_store):
    url = os.environ["GG_TEST_DATABASE_URL"]
    requester_id = pg_store.add_requester(
        "Budget Researcher", "researcher", "standard", "test-institution", "budget-test-key"
    )
    stores = [pg_store] + [PostgresStore(url) for _ in range(3)]
    try:
        def charge(i):
            store = stores[i % len(stores)]
            with store.transaction():
                spent = store.eps_spent(requester_id, "budget-dataset")
                store.set_eps_spent(requester_id, "budget-dataset", spent + 0.1)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(charge, range(20)))
        assert pg_store.eps_spent(requester_id, "budget-dataset") == pytest.approx(2.0)
    finally:
        for store in stores[1:]:
            store.close()


def test_postgres_bootstrap_installs_standalone_reference_schema(pg_store):
    versions = [row["version"] for row in pg_store.q(
        "SELECT version FROM schema_migrations ORDER BY version"
    )]
    assert versions == [1, 2, 3, 4, 5, 6, 7]
    tables = {
        row["table_name"] for row in pg_store.q(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='genomeguard' AND table_type='BASE TABLE'"
        )
    }
    assert {
        "variant_dataset_manifest", "dataset_samples", "dataset_variants",
        "dataset_genotype_calls", "population_reference_manifest",
        "population_variant_frequency",
    } <= tables


def test_postgres_empty_population_reference_lookup_is_truthful(pg_store):
    result = pg_store.lookup_population_frequencies("1", 12345, "A", "T", "GRCh38")
    assert result == {"status": "empty", "matches": [], "truncated": False}


def test_postgres_empty_public_chromosome_coverage_is_available(pg_store):
    assert pg_store.verified_public_chromosome_coverage("GRCh38") == []
    assert pg_store.verified_public_datasets() == []


def test_postgres_native_migrations_are_idempotent(pg_store):
    url = os.environ["GG_TEST_DATABASE_URL"]
    reopened = PostgresStore(url)
    try:
        versions = [row["version"] for row in reopened.q(
            "SELECT version FROM schema_migrations ORDER BY version"
        )]
        assert versions == [1, 2, 3, 4, 5, 6, 7]
    finally:
        reopened.close()



def test_postgres_rls_isolates_tenants_and_requires_explicit_admin_context(pg_store):
    from uuid import uuid4

    role = "gg_test_rls_" + uuid4().hex[:12]
    pg_store.connection.execute(f'CREATE ROLE "{role}" NOLOGIN')
    try:
        pg_store.connection.execute(
            f'GRANT USAGE ON SCHEMA genomeguard_runtime TO "{role}"'
        )
        pg_store.connection.execute(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON requests, decisions, epsilon_ledger, alerts '
            f'TO "{role}"'
        )
        pg_store.connection.execute(
            f'GRANT SELECT ON requesters, consent_events TO "{role}"'
        )
        pg_store.connection.execute(
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA genomeguard_runtime TO "{role}"'
        )

        pg_store.x(
            "INSERT INTO donors(id,cohort_id,population,consent_json,family_id,withdrawn_at) "
            "VALUES(?,?,?,?,?,?)",
            (998, "test", "TEST", "{}", 998, None),
        )
        pg_store.record_consent_event(
            "00000000-0000-4000-8000-000000000002", 998, "test-dataset", "withdrawn",
            b"encrypted-consent-payload", "https://consent.example.edu", "b" * 64,
            "2026-11-10T00:00:00Z",
        )
        ids = {}
        for org in ("tenant-a", "tenant-b"):
            rid = pg_store.add_requester(
                f"Researcher {org}", "researcher", "registered", org, f"hash-{org}",
            )
            pg_store.add_identity_binding(
                rid, "https://id.example.edu", f"subject-{org}", org,
            )
            req_id = pg_store.add_request(
                rid, "2026-11-10T00:00:00Z",
                {"purpose": "research", "disease": None, "is_commercial": False,
                 "data_level": "frequency", "cohort_filter": {}, "variant_filter": {}},
            )
            pg_store.save_decision(req_id, {
                "outcome": "deny", "reasons": ["test"], "risk": {}, "transform": {},
                "explanation": "test", "needs_human": False, "private": {}, "release": None,
            })
            ids[org] = req_id

        pg_store.connection.execute(f'SET ROLE "{role}"')
        pg_store.connection.commit()
        with pg_store.transaction():
            pg_store.set_tenant("tenant-a")
            visible = {row["id"] for row in pg_store.q("SELECT id FROM requests")}
            assert visible == {ids["tenant-a"]}
            decisions = {row["request_id"] for row in pg_store.q("SELECT request_id FROM decisions")}
            assert decisions == {ids["tenant-a"]}

        with pg_store.transaction():
            # No organization context is default-deny for tenant-owned rows.
            assert pg_store.q("SELECT id FROM requests") == []
            assert pg_store.q("SELECT event_id FROM consent_events") == []
            assert pg_store.q(
                "SELECT has_table_privilege(current_user,'requests','TRUNCATE') AS can_truncate"
            )[0]["can_truncate"] is False

        with pg_store.transaction():
            pg_store.set_admin_access()
            assert {row["id"] for row in pg_store.q("SELECT id FROM requests")} == set(ids.values())
            assert pg_store.q("SELECT event_id FROM consent_events") == [
                {"event_id": "00000000-0000-4000-8000-000000000002"},
            ]

        with pytest.raises(psycopg.Error):
            with pg_store.transaction():
                pg_store.set_tenant("tenant-a")
                pg_store.x(
                    "INSERT INTO requests(requester_id,organization_id,ts,purpose,disease,"
                    "is_commercial,data_level,cohort_filter_json,variant_filter_json,status) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (1, "tenant-b", "2026-11-10T00:00:00Z", "research", None, 0,
                     "frequency", "{}", "{}", "pending"),
                )
        pg_store.connection.execute("RESET ROLE")
        pg_store.connection.commit()
    finally:
        pg_store.connection.execute("RESET ROLE")
        pg_store.connection.execute(f'DROP OWNED BY "{role}"')
        pg_store.connection.execute(f'DROP ROLE IF EXISTS "{role}"')



def test_postgres_consent_event_ledger_rejects_update_and_delete(pg_store):
    pg_store.x(
        "INSERT INTO donors(id,cohort_id,population,consent_json,family_id,withdrawn_at) "
        "VALUES(?,?,?,?,?,?)",
        (999, "test", "TEST", "{}", 999, None),
    )
    pg_store.record_consent_event(
        "00000000-0000-4000-8000-000000000001", 999, "test-dataset", "withdrawn",
        b"encrypted-consent-payload", "https://consent.example.edu", "a" * 64,
        "2026-11-10T00:00:00Z",
    )
    with pytest.raises(psycopg.Error, match="append-only"):
        with pg_store.transaction():
            pg_store.x(
                "UPDATE consent_events SET event_type='consent_updated' "
                "WHERE event_id=?",
                ("00000000-0000-4000-8000-000000000001",),
            )
    with pytest.raises(psycopg.Error, match="append-only"):
        with pg_store.transaction():
            pg_store.x(
                "DELETE FROM consent_events WHERE event_id=?",
                ("00000000-0000-4000-8000-000000000001",),
            )



def test_runtime_privilege_assertion_rejects_table_wide_truncate(pg_store):
    from uuid import uuid4

    role = "gg_test_runtime_" + uuid4().hex[:12]
    pg_store.connection.execute(
        f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE'
    )
    pg_store.connection.execute(
        f'GRANT USAGE ON SCHEMA genomeguard_runtime TO "{role}"'
    )
    pg_store.connection.commit()
    try:
        pg_store.connection.execute(f'SET ROLE "{role}"')
        pg_store.connection.commit()
        pg_store.assert_least_privilege_runtime()
        pg_store.connection.execute("RESET ROLE")
        pg_store.connection.commit()

        pg_store.connection.execute(
            f'GRANT TRUNCATE ON TABLE genomeguard_runtime.requests TO "{role}"'
        )
        pg_store.connection.commit()
        pg_store.connection.execute(f'SET ROLE "{role}"')
        pg_store.connection.commit()
        with pytest.raises(RuntimeError, match="over-privileged"):
            pg_store.assert_least_privilege_runtime()
        pg_store.connection.execute("RESET ROLE")
        pg_store.connection.commit()
    finally:
        pg_store.connection.execute("RESET ROLE")
        pg_store.connection.execute(f'DROP OWNED BY "{role}"')
        pg_store.connection.execute(f'DROP ROLE IF EXISTS "{role}"')
