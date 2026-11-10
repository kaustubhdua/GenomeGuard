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
from app.store import CatalogueUnavailableError, Store, now_iso

_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
_VERIFIED_PUBLIC_DATASET_CTE = """
WITH measured AS (
    SELECT m.id, m.dataset_key, m.source_name, m.source_url, m.source_release,
           m.reference_assembly, m.file_sha256, m.data_use_review, m.consent_basis,
           m.import_status, m.variant_count, m.genotype_call_count, m.sample_count,
           m.imported_at, m.metadata ->> 'reuse_statement_url' AS reuse_statement_url,
           m.metadata ->> 'citation' AS citation,
           (SELECT count(*) FROM genomeguard.dataset_samples AS s
            WHERE s.dataset_id = m.id) AS measured_sample_count,
           (SELECT count(*) FROM genomeguard.dataset_variants AS v
            WHERE v.dataset_id = m.id) AS measured_variant_count,
           (SELECT count(*) FROM genomeguard.dataset_genotype_calls AS c
            WHERE c.dataset_id = m.id AND c.called_alleles > 0) AS measured_call_count
    FROM genomeguard.variant_dataset_manifest AS m
    WHERE m.data_use_review = 'approved_public_research'
      AND m.consent_basis = 'dataset_policy'
      AND m.import_status = 'loaded'
      AND m.source_url ~ '^https://'
      AND m.file_sha256 ~ '^[0-9a-f]{64}$'
      AND m.metadata ->> 'reuse_statement_url' ~ '^https://'
      AND length(trim(m.metadata ->> 'citation')) > 0
      AND m.sample_count > 0 AND m.variant_count > 0
      AND m.genotype_call_count > 0 AND m.imported_at IS NOT NULL
), verified_public_dataset AS (
    SELECT * FROM measured
    WHERE sample_count = measured_sample_count
      AND variant_count = measured_variant_count
      AND genotype_call_count = measured_call_count
)
"""


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

    def __init__(
        self, database_url: str, *, migration_database_url: str | None = None,
        connect_timeout: int = 10, run_migrations: bool = True,
    ) -> None:
        if not database_url or not database_url.startswith(("postgres://", "postgresql://")):
            raise ValueError("GG_DATABASE_URL must be a PostgreSQL runtime connection URL")
        if migration_database_url and (
            not migration_database_url.startswith(("postgres://", "postgresql://"))
            or migration_database_url == database_url
        ):
            raise ValueError("GG_MIGRATION_DATABASE_URL must be a distinct PostgreSQL owner URL")
        self.path = "postgresql"
        self.database_url = database_url
        self.connect_timeout = connect_timeout
        self.lock = threading.RLock()
        self._transaction_depth = 0
        self.connection = psycopg.connect(
            database_url, connect_timeout=connect_timeout, row_factory=dict_row,
            application_name="GenomeGuard-runtime",
        )
        self.migration_connection = (
            psycopg.connect(
                migration_database_url, connect_timeout=connect_timeout, row_factory=dict_row,
                application_name="GenomeGuard-migrations",
            ) if run_migrations and migration_database_url else (
                self.connection if run_migrations else None
            )
        )
        try:
            if self.migration_connection is not None and self.migration_connection is not self.connection:
                runtime_role = self.connection.execute(
                    "SELECT current_user AS role"
                ).fetchone()["role"]
                migration_role = self.migration_connection.execute(
                    "SELECT current_user AS role"
                ).fetchone()["role"]
                if runtime_role == migration_role:
                    raise ValueError(
                        "GG_DATABASE_URL and GG_MIGRATION_DATABASE_URL must authenticate "
                        "as different PostgreSQL roles"
                    )
            if run_migrations:
                # Only the migration principal may create schemas or run DDL. The ordinary
                # application connection receives a search_path after the owner creates it.
                with self.migration_connection.transaction():
                    self.migration_connection.execute(
                        "CREATE SCHEMA IF NOT EXISTS genomeguard_runtime"
                    )
                    self.migration_connection.execute(
                        "SET search_path TO genomeguard_runtime, public"
                    )
            else:
                # Operator tools that only provision records must never run schema DDL.
                present = self.connection.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_namespace "
                    "WHERE nspname='genomeguard_runtime') AS present"
                ).fetchone()["present"]
                if not present:
                    raise RuntimeError("GenomeGuard PostgreSQL schema is not migrated")
            with self.connection.transaction():
                self.connection.execute("SET search_path TO genomeguard_runtime, public")
            self.db = _ConnectionCompat(self.connection, self)
            if run_migrations:
                self._migrate()
        except Exception:
            self.connection.close()
            if self.migration_connection is not None and self.migration_connection is not self.connection:
                self.migration_connection.close()
            raise
        finally:
            if self.migration_connection is not None and self.migration_connection is not self.connection:
                self.migration_connection.close()
                self.migration_connection = None

    def _ensure_connection(self) -> None:
        """Reconnect after provider restarts without retrying an interrupted transaction.

        Render/Neon may terminate an otherwise healthy long-lived PostgreSQL session during
        maintenance or administrative restarts. Re-establish the runtime search_path before
        the next operation. Callers inside an active transaction must fail closed; the next
        request/transaction can then reconnect cleanly.
        """
        if not self.connection.closed and not self.connection.broken:
            return
        if self._transaction_depth:
            raise psycopg.OperationalError("PostgreSQL connection closed during a transaction")
        connection = psycopg.connect(
            self.database_url, connect_timeout=self.connect_timeout, row_factory=dict_row,
            application_name="GenomeGuard",
        )
        try:
            with connection.transaction():
                connection.execute("SET search_path TO genomeguard_runtime, public")
        except Exception:
            connection.close()
            raise
        self.connection = connection
        self.db.connection = connection

    def _migrate(self) -> None:
        """Apply numbered migrations using the privileged migration-only connection."""
        if not _MIGRATIONS.is_dir():
            raise RuntimeError(f"PostgreSQL migrations directory is missing: {_MIGRATIONS}")
        migrations = []
        for path in sorted(_MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")):
            prefix = path.name.split("_", 1)[0]
            if prefix.isdigit():
                migrations.append((int(prefix), path))
        if not migrations or migrations[0][0] != 1:
            raise RuntimeError("PostgreSQL migration 001_initial_postgres.sql is required")

        # Production must execute DDL through the separate owner credential. The runtime
        # connection is deliberately never used for schema creation or migrations.
        connection = self.migration_connection or self.connection
        with self.lock:
            for version, migration in migrations:
                with connection.transaction():
                    connection.execute(
                        "SET search_path TO genomeguard_runtime, public"
                    )
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS schema_migrations "
                        "(version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                    )
                    applied = connection.execute(
                        "SELECT version FROM schema_migrations WHERE version=%s", (version,)
                    ).fetchone()
                    if applied:
                        continue
                    sql = "\\n".join(
                        line for line in migration.read_text(encoding="utf-8").splitlines()
                        if not line.lstrip().startswith("--")
                    )
                    # Psycopg's simple-query protocol accepts the full migration script,
                    # preserving semicolons inside PL/pgSQL dollar-quoted function bodies.
                    connection.execute(sql, prepare=False)
                    connection.execute(
                        "INSERT INTO schema_migrations(version) VALUES (%s)", (version,)
                    )

    def lookup_population_frequencies(
        self, chromosome: str, position: int, reference: str, alternate: str, assembly: str,
    ) -> dict:
        """Read approved public aggregate frequencies in a read-only transaction."""
        statement = """
            SELECT
                m.dataset_key, m.source_name, m.source_release, m.source_url,
                m.file_sha256, m.reference_assembly,
                f.population, f.allele_count, f.allele_number,
                f.allele_frequency, f.homozygote_count
            FROM genomeguard.population_variant_frequency AS f
            JOIN genomeguard.population_reference_manifest AS m ON m.id = f.dataset_id
            WHERE f.chromosome = %s AND f.position = %s
              AND f.reference_allele = %s AND f.alternate_allele = %s
              AND m.reference_assembly = %s
              AND m.data_use_review = 'approved_public_research'
              AND m.import_status = 'loaded'
            ORDER BY m.source_name, m.source_release, f.population
            LIMIT 1001
        """
        try:
            with self.lock:
                self._ensure_connection()
                with self.connection.transaction():
                    self.connection.execute("SET LOCAL statement_timeout = '3000ms'")
                    rows = self.connection.execute(
                        statement, (chromosome, position, reference, alternate, assembly),
                    ).fetchall()
            truncated = len(rows) > 1000
            matches = [{
                "dataset_key": row["dataset_key"],
                "source_name": row["source_name"],
                "source_release": row["source_release"],
                "source_url": row["source_url"],
                "file_sha256": row["file_sha256"],
                "reference_assembly": row["reference_assembly"],
                "population": row["population"],
                "allele_count": int(row["allele_count"]),
                "allele_number": int(row["allele_number"]),
                "allele_frequency": float(row["allele_frequency"]),
                "homozygote_count": (
                    int(row["homozygote_count"]) if row["homozygote_count"] is not None else None
                ),
            } for row in rows[:1000]]
            return {"status": "available" if matches else "empty", "matches": matches, "truncated": truncated}
        except psycopg.Error:
            # Missing migrations/role grants or a disconnected reference database should not
            # leak credentials, SQL details, or block the metadata-only variant search.
            return {
                "status": "unavailable", "matches": [],
                "message": "Approved aggregate population-reference lookup is unavailable in this database.",
            }

    def verified_public_datasets(self) -> list[dict]:
        """Return only public manifests whose normalized rows reconcile to stored counts."""
        query = f"""{_VERIFIED_PUBLIC_DATASET_CTE}
            SELECT dataset_key, source_name, source_url, source_release, reference_assembly,
                   file_sha256, variant_count, genotype_call_count, sample_count, imported_at,
                   reuse_statement_url, citation
            FROM verified_public_dataset
            ORDER BY source_name, dataset_key
            LIMIT 1001
        """
        try:
            with self.lock:
                self._ensure_connection()
                with self.connection.transaction():
                    self.connection.execute("SET LOCAL statement_timeout = '3000ms'")
                    rows = self.connection.execute(query).fetchall()
            return [{
                "dataset_key": row["dataset_key"],
                "source_name": row["source_name"],
                "source_url": row["source_url"],
                "source_release": row["source_release"],
                "reference_assembly": row["reference_assembly"],
                "file_sha256": row["file_sha256"],
                "variant_count": int(row["variant_count"]),
                "genotype_call_count": int(row["genotype_call_count"]),
                "sample_count": int(row["sample_count"]),
                "imported_at": row["imported_at"],
                "reuse_statement_url": row["reuse_statement_url"],
                "citation": row["citation"],
            } for row in rows[:1000]]
        except psycopg.Error as error:
            raise CatalogueUnavailableError(
                "The verified public dataset catalogue is unavailable."
            ) from error

    def verified_public_chromosome_coverage(self, assembly: str) -> list[dict]:
        """Aggregate coordinates only from reconciled, approved public imports."""
        query = f"""{_VERIFIED_PUBLIC_DATASET_CTE}
            SELECT CASE WHEN normalized_chromosome = 'M' THEN 'MT'
                        ELSE normalized_chromosome END AS chromosome,
                   count(*) AS variant_count, min(position) AS first_position,
                   max(position) AS last_position
            FROM (
                SELECT CASE
                         WHEN upper(v.chromosome) LIKE 'CHR%%'
                           THEN substring(upper(v.chromosome) FROM 4)
                         ELSE upper(v.chromosome)
                       END AS normalized_chromosome,
                       v.position
                FROM genomeguard.dataset_variants AS v
                JOIN verified_public_dataset AS m ON m.id = v.dataset_id
                WHERE m.reference_assembly = %s
            ) AS coverage
            GROUP BY normalized_chromosome
            ORDER BY normalized_chromosome
        """
        try:
            with self.lock:
                self._ensure_connection()
                with self.connection.transaction():
                    self.connection.execute("SET LOCAL statement_timeout = '3000ms'")
                    rows = self.connection.execute(query, (assembly,)).fetchall()
            return [{
                "chromosome": row["chromosome"],
                "variant_count": int(row["variant_count"]),
                "first_position": int(row["first_position"]),
                "last_position": int(row["last_position"]),
            } for row in rows]
        except psycopg.Error as error:
            raise CatalogueUnavailableError(
                "Verified public chromosome coverage is unavailable."
            ) from error

    def verified_public_variant_search(
        self, chromosome: str, position: int, reference: str | None = None,
        alternate: str | None = None,
    ) -> list[dict]:
        """Find coordinate metadata only in reconciled, approved public imports."""
        query = f"""{_VERIFIED_PUBLIC_DATASET_CTE}
            SELECT m.dataset_key, m.reference_assembly, v.variant_index,
                   v.chromosome, v.position, v.reference_allele, v.alternate_allele
            FROM genomeguard.dataset_variants AS v
            JOIN verified_public_dataset AS m ON m.id = v.dataset_id
            WHERE upper(regexp_replace(v.chromosome, '^chr', '', 'i')) = %s
              AND v.position = %s
              AND (%s IS NULL OR upper(v.reference_allele) = %s)
              AND (%s IS NULL OR upper(v.alternate_allele) = %s)
            ORDER BY m.dataset_key, v.variant_index
            LIMIT 20
        """
        try:
            with self.lock:
                self._ensure_connection()
                with self.connection.transaction():
                    self.connection.execute("SET LOCAL statement_timeout = '3000ms'")
                    rows = self.connection.execute(
                        query, (chromosome, position, reference, reference, alternate, alternate),
                    ).fetchall()
            return [{
                "dataset_key": row["dataset_key"],
                "reference_assembly": row["reference_assembly"],
                "variant_id": int(row["variant_index"]) + 1,
                "chromosome": row["chromosome"],
                "position": int(row["position"]),
                "reference_allele": row["reference_allele"],
                "alternate_allele": row["alternate_allele"],
            } for row in rows]
        except psycopg.Error as error:
            raise CatalogueUnavailableError(
                "Verified public variant search is unavailable."
            ) from error

    def q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            self._ensure_connection()
            try:
                rows = list(self.connection.execute(_translate(sql), args).fetchall())
            except psycopg.OperationalError:
                # A provider restart can race the health check above. Retrying a read-only
                # query is safe only outside an application transaction.
                if self._transaction_depth or not self.connection.broken:
                    raise
                self.connection.close()
                self._ensure_connection()
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
            self._ensure_connection()
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
            self._ensure_connection()
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

        with self.lock:
            self._ensure_connection()
            with self.connection.transaction():
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

    def assert_least_privilege_runtime(self) -> None:
        """Fail closed if the connected application principal can bypass tenant controls."""
        row = self.connection.execute(
            "SELECT current_user AS role, r.rolsuper, r.rolbypassrls, r.rolcreatedb, "
            "r.rolcreaterole, "
            "has_database_privilege(current_user,current_database(),'CREATE') AS database_create, "
            "has_schema_privilege(current_user,'genomeguard_runtime','CREATE') AS runtime_create, "
            "has_schema_privilege(current_user,'genomeguard','CREATE') AS reference_create, "
            "EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname IN ('genomeguard_runtime','genomeguard') "
            "AND c.relkind IN ('r','p') AND c.relowner=(SELECT oid FROM pg_roles "
            "WHERE rolname=current_user)) AS owns_application_tables, "
            "COALESCE((SELECT pg_has_role(current_user, oid, 'MEMBER') FROM pg_roles "
            "WHERE rolname='genomeguard_owner'), false) AS owner_member, "
            "has_table_privilege(current_user,'genomeguard_runtime.requests','TRUNCATE') "
            "AS requests_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.decisions','TRUNCATE') "
            "AS decisions_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.donors','TRUNCATE') "
            "AS donors_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.variants','TRUNCATE') "
            "AS variants_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.relationships','TRUNCATE') "
            "AS relationships_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.cohort_metadata','TRUNCATE') "
            "AS metadata_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.genotypes','TRUNCATE') "
            "AS genotypes_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.epsilon_ledger','TRUNCATE') "
            "AS ledger_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.alerts','TRUNCATE') "
            "AS alerts_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.consent_events','TRUNCATE') "
            "AS consent_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.requesters','TRUNCATE') "
            "AS requesters_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.identity_bindings','TRUNCATE') "
            "AS bindings_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.audit_log','UPDATE') "
            "AS audit_update, "
            "has_table_privilege(current_user,'genomeguard_runtime.audit_log','DELETE') "
            "AS audit_delete, "
            "has_table_privilege(current_user,'genomeguard_runtime.audit_log','TRUNCATE') "
            "AS audit_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.schema_migrations','INSERT') "
            "AS migrations_insert, "
            "has_table_privilege(current_user,'genomeguard_runtime.schema_migrations','UPDATE') "
            "AS migrations_update, "
            "has_table_privilege(current_user,'genomeguard_runtime.schema_migrations','DELETE') "
            "AS migrations_delete, "
            "has_table_privilege(current_user,'genomeguard_runtime.schema_migrations','TRUNCATE') "
            "AS migrations_truncate, "
            "has_table_privilege(current_user,'genomeguard_runtime.consent_events','UPDATE') "
            "AS consent_update, "
            "has_table_privilege(current_user,'genomeguard_runtime.consent_events','DELETE') "
            "AS consent_delete "
            "FROM pg_roles r WHERE r.rolname=current_user"
        ).fetchone()
        if not row:
            raise RuntimeError("could not inspect the PostgreSQL runtime principal")
        unsafe = (
            row["role"] == "genomeguard_owner" or row["rolsuper"] or row["rolbypassrls"]
            or row["rolcreatedb"] or row["rolcreaterole"] or row["database_create"]
            or row["runtime_create"] or row["reference_create"] or row["owns_application_tables"]
            or row["owner_member"]
            or row["requests_truncate"] or row["decisions_truncate"] or row["donors_truncate"]
            or row["variants_truncate"] or row["relationships_truncate"] or row["metadata_truncate"]
            or row["genotypes_truncate"] or row["ledger_truncate"] or row["alerts_truncate"]
            or row["consent_truncate"] or row["requesters_truncate"] or row["bindings_truncate"]
            or row["audit_update"] or row["audit_delete"] or row["audit_truncate"]
            or row["migrations_insert"] or row["migrations_update"]
            or row["migrations_delete"] or row["migrations_truncate"]
            or row["consent_update"] or row["consent_delete"]
        )
        if unsafe:
            raise RuntimeError(
                "PostgreSQL runtime principal is over-privileged; use genomeguard_runtime "
                "with no BYPASSRLS, schema CREATE, or table TRUNCATE privileges"
            )

    def set_tenant(self, organization_id: str) -> None:
        """Set transaction-local tenant context after OIDC binding validation."""
        if not organization_id or self._transaction_depth < 1:
            raise RuntimeError("tenant context requires an active transaction and organization ID")
        self.connection.execute(
            "SELECT set_config('gg.organization_id', %s, true)", (organization_id,),
        )

    def set_admin_access(self) -> None:
        """Enable cross-tenant RLS access only inside an already-authenticated admin request."""
        if self._transaction_depth < 1:
            raise RuntimeError("admin context requires an active transaction")
        self.connection.execute("SELECT set_config('gg.admin_access', 'on', true)")

    def set_allow_unscoped_demo(self) -> None:
        """Allow unscoped legacy API keys only in the synthetic demo transaction."""
        if self._transaction_depth < 1:
            raise RuntimeError("demo context requires an active transaction")
        self.connection.execute("SELECT set_config('gg.allow_unscoped_demo', 'on', true)")

    def close(self) -> None:
        with self.lock:
            self.connection.close()
