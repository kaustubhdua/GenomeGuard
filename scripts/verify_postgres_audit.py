#!/usr/bin/env python3
"""Read-only verification of the GenomeGuard PostgreSQL audit hash chain.

Set GG_DATABASE_URL to the PostgreSQL database to verify. The verifier opens a read-only
transaction and never runs migrations or changes application state. Optionally provide an
externally stored checkpoint JSON to detect valid-prefix truncation and rewritten history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.core.audit_chain import canonical_json, verify


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

    try:
        with psycopg.connect(
            database_url,
            connect_timeout=10,
            row_factory=dict_row,
            options="-c default_transaction_read_only=on",
        ) as connection:
            rows = connection.execute(
                "SELECT idx, ts, actor, action, payload_json, prev_hash, hash "
                "FROM genomeguard_runtime.audit_log ORDER BY idx"
            ).fetchall()
    except psycopg.Error as exc:
        print(f"Could not read GenomeGuard audit log: {exc}", file=sys.stderr)
        return 2

    entries = []
    try:
        for row in rows:
            entries.append({
                "idx": row["idx"],
                "ts": row["ts"],
                "actor": row["actor"],
                "action": row["action"],
                "payload": json.loads(row["payload_json"]),
                "prev_hash": row["prev_hash"],
                "hash": row["hash"],
            })
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Malformed audit row: {exc}", file=sys.stderr)
        return 1

    anchor = None
    if args.checkpoint:
        try:
            checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
            body = {
                "version": checkpoint.get("version", "1.0"),
                "length": checkpoint["length"],
                "head_hash": checkpoint["head_hash"],
                "timestamp": checkpoint["timestamp"],
                "signed_by": checkpoint.get("signed_by", "system"),
            }
            digest = hashlib.sha256(canonical_json(body).encode("ascii")).hexdigest()
            if digest != checkpoint.get("checkpoint_digest"):
                print(json.dumps({"ok": False, "reason": "checkpoint_digest_mismatch"}))
                return 1
            anchor = {"length": checkpoint["length"], "head_hash": checkpoint["head_hash"]}
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            print(f"Invalid audit checkpoint: {exc}", file=sys.stderr)
            return 2

    result = verify(entries, anchor=anchor)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
