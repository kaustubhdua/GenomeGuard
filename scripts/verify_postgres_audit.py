#!/usr/bin/env python3
"""Verify the GenomeGuard PostgreSQL audit chain without mutating the database.

Set GG_DATABASE_URL to a read-only-capable connection URL for the restored/runtime database.
Optionally provide a previously exported checkpoint JSON to detect valid-prefix truncation or
rewritten history. The checkpoint must be stored outside the database being verified.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from app.core.audit_chain import AuditChain
from app.postgres_store import PostgresStore
from app.store import AuditStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help="previously exported external audit checkpoint JSON",
    )
    args = parser.parse_args()
    database_url = os.environ.get("GG_DATABASE_URL", "").strip()
    if not database_url:
        parser.error("GG_DATABASE_URL must point to the PostgreSQL database to verify")

    store = PostgresStore(database_url)
    try:
        chain = AuditChain(AuditStore(store))
        result = chain.verify()
        if args.checkpoint:
            try:
                checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"Could not read audit checkpoint: {exc}", file=sys.stderr)
                return 2
            anchored = chain.verify_checkpoint(checkpoint)
            if not anchored.get("valid"):
                print(json.dumps(anchored, sort_keys=True))
                return 1
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("ok") else 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
