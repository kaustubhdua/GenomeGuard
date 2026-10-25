#!/usr/bin/env python3
"""One-time, offline migration of GenomeGuard SQLite records into an empty PostgreSQL database.

Stop the application first and pass a consistent SQLite snapshot. This script refuses a target
with existing application rows and verifies the audit chain before and after copying. Keep the
same GG_MASTER_KEY: genotype ciphertext is copied byte-for-byte and still depends on that key.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.core.audit_chain import verify
from app.postgres_store import PostgresStore

TABLES = (
    "cohort_metadata", "donors", "genotypes", "variants", "relationships",
    "requesters", "requests", "decisions", "epsilon_ledger", "audit_log",
    "donor_access", "alerts",
)
SEQUENCES = ("relationships", "requesters", "requests", "decisions", "donor_access", "alerts")


def audit_entries(rows):
    return [{
        "idx": row["idx"], "ts": row["ts"], "actor": row["actor"], "action": row["action"],
        "payload": json.loads(row["payload_json"]), "prev_hash": row["prev_hash"],
        "hash": row["hash"],
    } for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, help="Path to a stopped-service SQLite snapshot")
    parser.add_argument("--database-url", default=os.environ.get("GG_DATABASE_URL"),
                        help="Target PostgreSQL URL (or set GG_DATABASE_URL)")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or GG_DATABASE_URL is required")
    source_path = Path(args.sqlite).resolve()
    if not source_path.is_file():
        parser.error(f"SQLite snapshot does not exist: {source_path}")

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        source_rows = {table: [dict(row) for row in source.execute(f"SELECT * FROM {table}")]
                       for table in TABLES}
    finally:
        source.close()

    source_audit = verify(audit_entries(source_rows["audit_log"]))
    if not source_audit["ok"]:
        print(f"Refusing migration: source audit chain is invalid: {source_audit}", file=sys.stderr)
        return 2

    # Runs schema migrations. No database is created by this script.
    store = PostgresStore(args.database_url)
    store.close()
    with psycopg.connect(args.database_url, row_factory=dict_row) as target:
        with target.transaction():
            for table in TABLES:
                row = target.execute(f"SELECT count(*) AS n FROM {table}").fetchone()
                if int(row["n"]) != 0:
                    raise RuntimeError(
                        f"Target table {table} is not empty; use a dedicated empty database"
                    )

            for table in TABLES:
                rows = source_rows[table]
                if not rows:
                    continue
                columns = list(rows[0].keys())
                col_sql = ", ".join(columns)
                placeholders = ", ".join(["%s"] * len(columns))
                sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
                values = [tuple(row[col] for col in columns) for row in rows]
                target.cursor().executemany(sql, values)

            for table in SEQUENCES:
                target.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                    "GREATEST(COALESCE((SELECT max(id) FROM " + table + "), 1), 1), "
                    "EXISTS (SELECT 1 FROM " + table + "))",
                    (table,),
                )

        migrated_rows = target.execute("SELECT * FROM audit_log ORDER BY idx").fetchall()
        target_audit = verify(audit_entries(migrated_rows))
        if not target_audit["ok"] or target_audit["length"] != source_audit["length"]:
            raise RuntimeError(f"Post-migration audit verification failed: {target_audit}")

        counts = {table: int(target.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"])
                  for table in TABLES}
    print(json.dumps({
        "status": "migrated",
        "source": str(source_path),
        "audit_chain": target_audit,
        "row_counts": counts,
        "note": "Keep GG_MASTER_KEY unchanged and perform a clean backup/restore drill before cutover.",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
