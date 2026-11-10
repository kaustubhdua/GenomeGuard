#!/usr/bin/env python3
"""Offline Ed25519 signer for an exported GenomeGuard audit checkpoint.

Keep the private key on a separately controlled signing host or HSM-backed workflow. The
application server should export unsigned checkpoints but must not receive this private key.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.audit_chain import canonical_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="unsigned /audit/checkpoint JSON")
    parser.add_argument("--output", required=True, type=Path, help="signed checkpoint output")
    parser.add_argument("--private-key-file", required=True, type=Path,
                        help="offline file containing base64-encoded 32-byte Ed25519 private key")
    parser.add_argument("--key-id", required=True, help="public key registry identifier")
    args = parser.parse_args()

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    if (
        not isinstance(raw, dict)
        or isinstance(raw.get("length"), bool)
        or not isinstance(raw.get("length"), int)
        or raw["length"] < 0
        or not isinstance(raw.get("head_hash"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", raw["head_hash"])
        or not isinstance(raw.get("timestamp"), str)
        or not raw["timestamp"]
    ):
        parser.error("input is not a valid unsigned GenomeGuard checkpoint")
    if not args.key_id.strip() or len(args.key_id) > 128:
        parser.error("--key-id must contain 1 to 128 characters")

    try:
        private_bytes = base64.b64decode(args.private_key_file.read_text().strip(), validate=True)
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    except (OSError, ValueError) as exc:
        parser.error(f"cannot load Ed25519 private key: {exc}")

    body = {
        "version": "2.0",
        "length": raw["length"],
        "head_hash": raw["head_hash"],
        "timestamp": raw["timestamp"],
        "key_id": args.key_id,
        "signature_algorithm": "Ed25519",
    }
    signature = private_key.sign(canonical_json(body).encode("ascii"))
    signed = {
        **body,
        "signature": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }
    args.output.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Signed checkpoint written to {args.output} (key_id={args.key_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
