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

    def __init__(self, database_url: str, *, connect_timeout: int = 10) -> None:
        if not database_url or not database_url.startswith(("postgres://", "postgresql://")):
            raise ValueError("GG_DATABASE_URL must be a PostgreSQL connection URL")
        self.path = "postgresql"
        self.database_url = database_url
        self.connect_timeout = connect_timeout
        self.lock = threading.RLock()
        self._transaction_depth = 0
        self.connection = psycopg.connect(
            database_url, connect_timeout=connect_timeout, row_factory=dict_row,
            application_name="GenomeGuard",
        )
        # Keep runtime tables isolated from normalized genomic reference tables.
        # The database URL is a server-side secret; never put it in frontend/Vercel public env vars.
        try:
            with self.connection.transaction():
                # Legacy service tables and normalized public references have separate
                # schemas because they intentionally use different data contracts.
                schema_exists = self.connection.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'genomeguard_runtime') AS present"
                ).fetchone()["present"]
                if not schema_exists:
                    self.connection.execute("CREATE SCHEMA genomeguard_runtime")
                self.connection.execute("SET search_path TO genomeguard_runtime, public")
        except Exception:
            self.connection.close()
            raise
        self.db = _ConnectionCompat(self.connection, self)
        try:
            self._migrate()
        except Exception:
            self.connection.close()
            raise


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
        """Apply each numbered native PostgreSQL migration exactly once."""
        if not _MIGRATIONS.is_dir():
            raise RuntimeError(f"PostgreSQL migrations directory is missing: {_MIGRATIONS}")
        migrations = []
        for path in sorted(_MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")):
            prefix = path.name.split("_", 1)[0]
            if prefix.isdigit():
                migrations.append((int(prefix), path))
        if not migrations or migrations[0][0] != 1:
            raise RuntimeError("PostgreSQL migration 001_initial_postgres.sql is required")
        with self.lock:
            for version, migration in migrations:
                with self.connection.transaction():
                    self.connection.execute(
                        "CREATE TABLE IF NOT EXISTS schema_migrations "
                        "(version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                    )
                    applied = self.connection.execute(
                        "SELECT version FROM schema_migrations WHERE version=%s", (version,)
                    ).fetchone()
                    if applied:
                        continue
                    sql = "\n".join(
                        line for line in migration.read_text(encoding="utf-8").splitlines()
                        if not line.lstrip().startswith("--")
                    )
                    for statement in sql.split(";"):
                        if statement.strip():
                            self.connection.execute(statement)
                    self.connection.execute(
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

    def close(self) -> None:
        with self.lock:
            self.connection.close()
