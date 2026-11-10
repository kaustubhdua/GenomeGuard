"""Real PostgreSQL integration tests. CI provides an isolated disposable PostgreSQL service."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from app.core.audit_chain import AuditChain
from app.postgres_store import (
    PostgresStore,
    _ensure_migration_schema_access,
    _ensure_runtime_schema_exists,
)
from app.store import AuditStore


@pytest.fixture
def pg_store():
    url = os.environ.get("GG_TEST_DATABASE_URL")
    if not url:
        pytest.skip("GG_TEST_DATABASE_URL is not configured")
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(
            "DO $ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles "
            "WHERE rolname='genomeguard_runtime') THEN "
            "CREATE ROLE genomeguard_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS "
            "NOCREATEDB NOCREATEROLE; END IF; END $"
        )
        admin.execute("CREATE SCHEMA IF NOT EXISTS genomeguard_runtime")
        admin.execute("GRANT USAGE ON SCHEMA genomeguard_runtime TO genomeguard_runtime")
        admin.execute(
            "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA genomeguard_runtime "
            "GRANT ALL ON TABLES TO genomeguard_runtime"
        )
        admin.execute(
            "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA genomeguard_runtime "
            "GRANT ALL ON SEQUENCES TO genomeguard_runtime"
        )
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



def test_postgres_synthetic_cohort_seed_round_trips_with_tenant_columns(pg_store):
    from app.data.synth import generate

    master = b"g" * 32
    cohort = generate(
        n_donors=12, n_variants=24, n_populations=2, n_families=3,
        seed=17, n_planted=2, rare_maf=0.01,
    )
    pg_store.save_cohort(
        cohort, master, "integration-synthetic",
        metadata={"source": "integration test synthetic generator",
                  "genotypes_real": False, "consent_simulated": True},
    )
    loaded = pg_store.load_dataset(master, "integration-synthetic")
    assert loaded.genotypes.shape == (12, 24)
    assert len(loaded.donors) == 12
    assert loaded.n_variants == 24
    assert pg_store.one(
        "SELECT organization_id FROM donors ORDER BY id LIMIT 1"
    )["organization_id"] is None
    assert pg_store.one(
        "SELECT organization_id FROM genotypes LIMIT 1"
    )["organization_id"] is None
    assert pg_store.one(
        "SELECT dataset_id FROM cohort_metadata WHERE id=1"
    )["dataset_id"] == "integration-synthetic"



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
    assert versions == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
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


def test_postgres_audit_log_is_append_only(pg_store):
    audit = AuditChain(AuditStore(pg_store))
    audit.append("integration-test", "audit.appended", {"synthetic": True})
    with pytest.raises(psycopg.Error, match="append-only"):
        with pg_store.transaction():
            pg_store.x("UPDATE audit_log SET action='rewritten' WHERE idx=1")
    with pytest.raises(psycopg.Error, match="append-only"):
        with pg_store.transaction():
            pg_store.x("DELETE FROM audit_log WHERE idx=1")




def test_postgres_provisioned_schema_does_not_require_database_create(pg_store):
    connection = pg_store.connection
    with pg_store.transaction():
        connection.execute("SET ROLE genomeguard_owner")
        can_create_database = connection.execute(
            "SELECT has_database_privilege(current_user,current_database(),'CREATE') AS allowed"
        ).fetchone()["allowed"]
        if not can_create_database:
            _ensure_runtime_schema_exists(connection)
        assert connection.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_namespace "
            "WHERE nspname='genomeguard_runtime') AS present"
        ).fetchone()["present"] is True
        connection.execute("RESET ROLE")



def test_postgres_migration_bootstrap_handles_runtime_owned_legacy_schema(pg_store):
    connection = pg_store.connection
    owner_exists = connection.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='genomeguard_owner') AS present"
    ).fetchone()["present"]
    owner_was_runtime_member = connection.execute(
        "SELECT pg_has_role('genomeguard_owner','genomeguard_runtime','SET') AS present"
    ).fetchone()["present"]
    original_schema_owner = connection.execute(
        "SELECT nspowner::regrole::text AS owner FROM pg_namespace "
        "WHERE nspname='genomeguard_runtime'"
    ).fetchone()["owner"]
    if not owner_exists:
        connection.execute(
            "CREATE ROLE genomeguard_owner NOLOGIN NOSUPERUSER NOBYPASSRLS "
            "NOCREATEDB NOCREATEROLE"
        )
    if not owner_was_runtime_member:
        connection.execute(
            "GRANT genomeguard_runtime TO genomeguard_owner WITH INHERIT FALSE, SET TRUE"
        )
    connection.execute("ALTER SCHEMA genomeguard_runtime OWNER TO genomeguard_runtime")
    connection.execute("REVOKE CREATE ON SCHEMA genomeguard_runtime FROM genomeguard_owner")
    connection.commit()
    try:
        connection.execute("SET ROLE genomeguard_owner")
        connection.commit()
        _ensure_migration_schema_access(connection)
        assert connection.execute("SELECT current_user AS role").fetchone()["role"] == "genomeguard_owner"
        assert connection.execute(
            "SELECT has_schema_privilege(current_user,'genomeguard_runtime','CREATE') AS can_create"
        ).fetchone()["can_create"] is True
    finally:
        connection.execute("RESET ROLE")
        connection.execute(
            f"ALTER SCHEMA genomeguard_runtime OWNER TO {original_schema_owner}"
        )
        connection.execute("REVOKE CREATE ON SCHEMA genomeguard_runtime FROM genomeguard_owner")
        if not owner_was_runtime_member:
            connection.execute("REVOKE genomeguard_runtime FROM genomeguard_owner")
        if not owner_exists:
            connection.execute("DROP ROLE genomeguard_owner")
        connection.commit()



def test_postgres_runtime_role_cannot_mutate_audit_or_migration_ledgers(pg_store):
    with pg_store.transaction():
        pg_store.connection.execute("SET ROLE genomeguard_runtime")
        pg_store.assert_least_privilege_runtime()
        privileges = pg_store.q(
            "SELECT "
            "has_table_privilege(current_user,'genomeguard_runtime.audit_log','INSERT') AS audit_insert, "
            "has_table_privilege(current_user,'genomeguard_runtime.audit_log','UPDATE') AS audit_update, "
            "has_table_privilege(current_user,'genomeguard_runtime.audit_log','DELETE') AS audit_delete, "
            "has_table_privilege(current_user,'genomeguard_runtime.audit_log','TRUNCATE') AS audit_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.schema_migrations','SELECT') AS migrations_select, "
            "has_table_privilege(current_user,'genomeguard_runtime.schema_migrations','INSERT') AS migrations_insert, "
            "has_table_privilege(current_user,'genomeguard_runtime.consent_events','SELECT') AS consent_select, "
            "has_table_privilege(current_user,'genomeguard_runtime.consent_events','INSERT') AS consent_insert, "
            "has_table_privilege(current_user,'genomeguard_runtime.consent_events','UPDATE') AS consent_update, "
            "has_table_privilege(current_user,'genomeguard_runtime.consent_events','DELETE') AS consent_delete, "
            "has_table_privilege(current_user,'genomeguard_runtime.consent_events','TRUNCATE') AS consent_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.donors','SELECT') AS donors_select, "
            "has_table_privilege(current_user,'genomeguard_runtime.donors','INSERT') AS donors_insert, "
            "has_table_privilege(current_user,'genomeguard_runtime.donors','UPDATE') AS donors_update, "
            "has_table_privilege(current_user,'genomeguard_runtime.donors','DELETE') AS donors_delete, "
            "has_table_privilege(current_user,'genomeguard_runtime.variants','INSERT') AS variants_insert, "
            "has_table_privilege(current_user,'genomeguard_runtime.variants','UPDATE') AS variants_update, "
            "has_table_privilege(current_user,'genomeguard_runtime.variants','DELETE') AS variants_delete, "
            "has_table_privilege(current_user,'genomeguard_runtime.genotypes','INSERT') AS genotypes_insert, "
            "has_table_privilege(current_user,'genomeguard_runtime.genotypes','UPDATE') AS genotypes_update, "
            "has_table_privilege(current_user,'genomeguard_runtime.genotypes','DELETE') AS genotypes_delete, "
            "has_table_privilege(current_user,'genomeguard_runtime.relationships','INSERT') AS relationships_insert, "
            "has_table_privilege(current_user,'genomeguard_runtime.relationships','UPDATE') AS relationships_update, "
            "has_table_privilege(current_user,'genomeguard_runtime.relationships','DELETE') AS relationships_delete, "
            "has_table_privilege(current_user,'genomeguard_runtime.cohort_metadata','INSERT') AS metadata_insert, "
            "has_table_privilege(current_user,'genomeguard_runtime.cohort_metadata','UPDATE') AS metadata_update, "
            "has_table_privilege(current_user,'genomeguard_runtime.cohort_metadata','DELETE') AS metadata_delete, "
            "has_table_privilege(current_user,'genomeguard_runtime.donor_access','INSERT') AS donor_access_insert, "
            "has_table_privilege(current_user,'genomeguard_runtime.donor_access','UPDATE') AS donor_access_update, "
            "has_table_privilege(current_user,'genomeguard_runtime.donor_access','DELETE') AS donor_access_delete, "
            "has_table_privilege(current_user,'genomeguard_runtime.alerts','INSERT') AS alerts_insert, "
            "has_table_privilege(current_user,'genomeguard_runtime.alerts','UPDATE') AS alerts_update, "
            "has_table_privilege(current_user,'genomeguard_runtime.alerts','DELETE') AS alerts_delete"
        )[0]
        assert privileges == {
            "audit_insert": True, "audit_update": False, "audit_delete": False,
            "audit_truncate": False, "migrations_select": True, "migrations_insert": False,
            "consent_select": True, "consent_insert": True, "consent_update": False,
            "consent_delete": False, "consent_truncate": False,
            "donors_select": True, "donors_insert": False, "donors_update": True, "donors_delete": False,
            "variants_insert": False, "variants_update": False, "variants_delete": False,
            "genotypes_insert": False, "genotypes_update": False, "genotypes_delete": False,
            "relationships_insert": False, "relationships_update": False, "relationships_delete": False,
            "metadata_insert": False, "metadata_update": False, "metadata_delete": False,
            "donor_access_insert": True, "donor_access_update": False, "donor_access_delete": False,
            "alerts_insert": True, "alerts_update": False, "alerts_delete": False,
        }
        pg_store.connection.execute("RESET ROLE")




def test_postgres_unscoped_demo_requester_requires_explicit_demo_context(pg_store):
    connection = pg_store.connection
    with pg_store.transaction():
        connection.execute("SET ROLE genomeguard_runtime")
        pg_store.set_allow_unscoped_demo()
        requester_id = pg_store.add_requester(
            "Synthetic Demo Researcher", "researcher", "standard",
            "GenomeGuard demo", "demo-bootstrap-key", organization_id=None,
        )
        assert pg_store.requester(requester_id)["name"] == "Synthetic Demo Researcher"
        connection.execute("RESET ROLE")
    pg_store.x("DELETE FROM requesters WHERE name=?", ("Synthetic Demo Researcher",))
    connection.commit()



def test_postgres_donor_consent_updates_require_admin_scope(pg_store):
    connection = pg_store.connection
    donor_id = 999999
    connection.execute(
        "INSERT INTO donors(id,cohort_id,population,consent_json) VALUES (%s,%s,%s,%s)",
        (donor_id, "rls-test", "TST", "{}"),
    )
    connection.commit()
    try:
        with pg_store.transaction():
            connection.execute("SET ROLE genomeguard_runtime")
            blocked = connection.execute(
                "UPDATE donors SET withdrawn_at='2026-11-10T00:00:00Z' WHERE id=%s",
                (donor_id,),
            )
            assert blocked.rowcount == 0
            connection.execute("SELECT set_config('gg.admin_access','on',true)")
            allowed = connection.execute(
                "UPDATE donors SET withdrawn_at='2026-11-10T00:00:00Z' WHERE id=%s",
                (donor_id,),
            )
            assert allowed.rowcount == 1
            connection.execute("RESET ROLE")
    finally:
        connection.execute("DELETE FROM donors WHERE id=%s", (donor_id,))
        connection.commit()




def test_postgres_cohort_rows_are_tenant_scoped_and_foreign_keys_prevent_cross_tenant_links(pg_store):
    from uuid import uuid4

    role = "gg_cohort_rls_" + uuid4().hex[:12]
    connection = pg_store.connection
    connection.execute(f'CREATE ROLE "{role}" NOLOGIN')
    connection.execute(
        f'GRANT USAGE ON SCHEMA genomeguard_runtime TO "{role}"'
    )
    connection.execute(
        f'GRANT SELECT ON donors, genotypes, variants, relationships, cohort_metadata, donor_access TO "{role}"'
    )
    connection.execute(
        f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA genomeguard_runtime TO "{role}"'
    )
    connection.commit()

    try:
        with pg_store.transaction():
            pg_store.x(
                "INSERT INTO cohort_metadata(id,dataset_id,metadata_json) VALUES(1,?,?)",
                ("shared-synthetic", "{}"),
            )
            pg_store.x(
                "INSERT INTO donors(id,cohort_id,population,consent_json,organization_id) "
                "VALUES(?,?,?,?,?)",
                (990001, "tenant-a-cohort", "TST", "{}", "tenant-a"),
            )
            pg_store.x(
                "INSERT INTO donors(id,cohort_id,population,consent_json,organization_id) "
                "VALUES(?,?,?,?,?)",
                (990002, "tenant-b-cohort", "TST", "{}", "tenant-b"),
            )
            pg_store.x(
                "INSERT INTO donors(id,cohort_id,population,consent_json,organization_id) "
                "VALUES(?,?,?,?,?)",
                (990003, "public-synthetic", "TST", "{}", None),
            )
            pg_store.x(
                "INSERT INTO genotypes(donor_id,genotype_blob,organization_id) VALUES(?,?,?)",
                (990001, b"tenant-a-genotype", "tenant-a"),
            )
            pg_store.x(
                "INSERT INTO genotypes(donor_id,genotype_blob,organization_id) VALUES(?,?,?)",
                (990002, b"tenant-b-genotype", "tenant-b"),
            )
            pg_store.x(
                "INSERT INTO genotypes(donor_id,genotype_blob,organization_id) VALUES(?,?,?)",
                (990003, b"public-genotype", None),
            )
            pg_store.x(
                "INSERT INTO variants(id,chrom,pos,ref,alt,organization_id) VALUES(?,?,?,?,?,?)",
                (880001, "1", 100, "A", "T", "tenant-a"),
            )
            pg_store.x(
                "INSERT INTO variants(id,chrom,pos,ref,alt,organization_id) VALUES(?,?,?,?,?,?)",
                (880002, "1", 200, "C", "G", "tenant-b"),
            )
            pg_store.x(
                "INSERT INTO variants(id,chrom,pos,ref,alt,organization_id) VALUES(?,?,?,?,?,?)",
                (880003, "1", 300, "G", "A", None),
            )
            pg_store.x(
                "INSERT INTO relationships(donor_a,donor_b,relation,organization_id) "
                "VALUES(?,?,?,?)",
                (990001, 990001, "self", "tenant-a"),
            )
            pg_store.x(
                "INSERT INTO relationships(donor_a,donor_b,relation,organization_id) "
                "VALUES(?,?,?,?)",
                (990002, 990002, "self", "tenant-b"),
            )
            pg_store.x(
                "INSERT INTO donor_access(donor_id,purpose,organization_id) VALUES(?,?,?)",
                (990001, "tenant-a-access", "tenant-a"),
            )
            pg_store.x(
                "INSERT INTO donor_access(donor_id,purpose,organization_id) VALUES(?,?,?)",
                (990002, "tenant-b-access", "tenant-b"),
            )

        connection.execute(f'SET ROLE "{role}"')
        connection.commit()
        with pg_store.transaction():
            pg_store.set_tenant("tenant-a")
            assert {r["id"] for r in pg_store.q("SELECT id FROM donors")} == {990001, 990003}
            assert {r["donor_id"] for r in pg_store.q("SELECT donor_id FROM genotypes")} == {990001, 990003}
            assert {r["id"] for r in pg_store.q("SELECT id FROM variants")} == {880001, 880003}
            assert {r["donor_a"] for r in pg_store.q("SELECT donor_a FROM relationships")} == {990001}
            assert {r["id"] for r in pg_store.q("SELECT id FROM cohort_metadata")} == {1}
            assert {r["purpose"] for r in pg_store.q("SELECT purpose FROM donor_access")} == {"tenant-a-access"}

        with pg_store.transaction():
            pg_store.set_tenant("tenant-b")
            assert {r["id"] for r in pg_store.q("SELECT id FROM donors")} == {990002, 990003}
            assert {r["donor_id"] for r in pg_store.q("SELECT donor_id FROM genotypes")} == {990002, 990003}
            assert {r["id"] for r in pg_store.q("SELECT id FROM variants")} == {880002, 880003}
            assert {r["donor_a"] for r in pg_store.q("SELECT donor_a FROM relationships")} == {990002}
            assert {r["id"] for r in pg_store.q("SELECT id FROM cohort_metadata")} == {1}
            assert {r["purpose"] for r in pg_store.q("SELECT purpose FROM donor_access")} == {"tenant-b-access"}

        with pg_store.transaction():
            assert {r["id"] for r in pg_store.q("SELECT id FROM donors")} == {990003}
            assert {r["donor_id"] for r in pg_store.q("SELECT donor_id FROM genotypes")} == {990003}
            assert {r["id"] for r in pg_store.q("SELECT id FROM variants")} == {880003}
            assert pg_store.q("SELECT id FROM relationships") == []
            assert {r["id"] for r in pg_store.q("SELECT id FROM cohort_metadata")} == {1}
            assert pg_store.q("SELECT purpose FROM donor_access") == []

        with pytest.raises(psycopg.Error):
            with pg_store.transaction():
                pg_store.set_tenant("tenant-a")
                pg_store.x(
                    "INSERT INTO relationships(donor_a,donor_b,relation,organization_id) "
                    "VALUES(?,?,?,?)",
                    (990001, 990002, "cross-tenant", "tenant-a"),
                )

        connection.execute("RESET ROLE")
        connection.commit()

        # The application role's default organization column binds donor-access events
        # to the active tenant, and the composite FK rejects another tenant's donor.
        with pg_store.transaction():
            connection.execute("SET ROLE genomeguard_runtime")
            pg_store.set_tenant("tenant-a")
            row = pg_store.connection.execute(
                "INSERT INTO donor_access(donor_id,purpose) VALUES(990001,'runtime-access') "
                "RETURNING organization_id"
            ).fetchone()
            assert row["organization_id"] == "tenant-a"
        with pytest.raises(psycopg.Error):
            with pg_store.transaction():
                connection.execute("SET ROLE genomeguard_runtime")
                pg_store.set_tenant("tenant-a")
                connection.execute(
                    "INSERT INTO donor_access(donor_id,purpose) VALUES(990002,'cross-tenant')"
                )
    finally:
        connection.execute("RESET ROLE")
        connection.commit()
        pg_store.x("DELETE FROM donor_access WHERE donor_id BETWEEN 990001 AND 990003")
        pg_store.x("DELETE FROM relationships WHERE donor_a BETWEEN 990001 AND 990003")
        pg_store.x("DELETE FROM genotypes WHERE donor_id BETWEEN 990001 AND 990003")
        pg_store.x("DELETE FROM variants WHERE id BETWEEN 880001 AND 880003")
        pg_store.x("DELETE FROM cohort_metadata WHERE id=1")
        pg_store.x("DELETE FROM donors WHERE id BETWEEN 990001 AND 990003")
        connection.execute(f'DROP OWNED BY "{role}"')
        connection.execute(f'DROP ROLE IF EXISTS "{role}"')
        connection.commit()



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
        assert versions == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
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
            f'GRANT SELECT ON requesters, identity_bindings, consent_events TO "{role}"'
        )
        pg_store.connection.execute(
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA genomeguard_runtime TO "{role}"'
        )

        pg_store.x(
            "INSERT INTO donors(id,cohort_id,population,consent_json,family_id,withdrawn_at) "
            "VALUES(?,?,?,?,?,?)",
            (998, "test", "TEST", "{}", 998, None),
        )
        with pg_store.transaction():
            pg_store.set_admin_access()
            pg_store.record_consent_event(
                "00000000-0000-4000-8000-000000000002", 998, "test-dataset", "withdrawn",
                b"encrypted-consent-payload", "https://consent.example.edu", "b" * 64,
                "2026-11-10T00:00:00Z",
            )
        ids = {}
        with pg_store.transaction():
            pg_store.set_admin_access()
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
            assert {row["organization_id"] for row in pg_store.q(
                "SELECT organization_id FROM requesters"
            )} == {"tenant-a"}
            assert {row["subject"] for row in pg_store.q(
                "SELECT subject FROM identity_bindings"
            )} == {"subject-tenant-a"}

        with pg_store.transaction():
            # No organization context is default-deny for tenant-owned rows.
            assert pg_store.q("SELECT id FROM requests") == []
            assert pg_store.q("SELECT id FROM requesters") == []
            assert pg_store.q("SELECT subject FROM identity_bindings") == []
            assert pg_store.q("SELECT event_id FROM consent_events") == []
            assert pg_store.q(
                "SELECT has_table_privilege(current_user,'requests','TRUNCATE') AS can_truncate"
            )[0]["can_truncate"] is False

        with pg_store.transaction():
            pg_store.set_admin_access()
            assert {row["id"] for row in pg_store.q("SELECT id FROM requests")} == set(ids.values())
            assert {row["organization_id"] for row in pg_store.q(
                "SELECT organization_id FROM requesters"
            )} == {"tenant-a", "tenant-b"}
            assert {row["subject"] for row in pg_store.q(
                "SELECT subject FROM identity_bindings"
            )} == {"subject-tenant-a", "subject-tenant-b"}
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
    with pg_store.transaction():
        pg_store.set_admin_access()
        pg_store.record_consent_event(
            "00000000-0000-4000-8000-000000000001", 999, "test-dataset", "withdrawn",
            b"encrypted-consent-payload", "https://consent.example.edu", "a" * 64,
            "2026-11-10T00:00:00Z",
        )
    with pytest.raises(psycopg.Error, match="append-only"):
        with pg_store.transaction():
            pg_store.set_admin_access()
            pg_store.x(
                "UPDATE consent_events SET event_type='consent_updated' "
                "WHERE event_id=?",
                ("00000000-0000-4000-8000-000000000001",),
            )
    with pytest.raises(psycopg.Error, match="append-only"):
        with pg_store.transaction():
            pg_store.set_admin_access()
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
        pg_store.connection.execute(
            f'REVOKE TRUNCATE ON TABLE genomeguard_runtime.requests FROM "{role}"'
        )
        pg_store.connection.execute(
            f'GRANT UPDATE ON TABLE genomeguard_runtime.audit_log TO "{role}"'
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



def test_postgres_rejects_distinct_urls_for_the_same_runtime_and_migration_role():
    url = os.environ["GG_TEST_DATABASE_URL"]
    with pytest.raises(ValueError, match="different PostgreSQL roles"):
        PostgresStore(
            url,
            migration_database_url=url + "?application_name=misleading-distinct-url",
        )
