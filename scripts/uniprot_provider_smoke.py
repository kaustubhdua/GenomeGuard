#!/usr/bin/env python3
"""Live contract smoke test for reviewed human UniProtKB protein search."""
from __future__ import annotations

import sys

from app.literature.uniprot import search_proteins


def main() -> int:
    result = search_proteins("BRCA2", size=5)
    if result.get("provider") != "UniProtKB":
        raise AssertionError("UniProtKB provider identity is missing")
    if not result.get("release"):
        raise AssertionError("UniProtKB release metadata is missing")
    proteins = result.get("proteins")
    if not isinstance(proteins, list) or not proteins:
        raise AssertionError("UniProtKB returned no reviewed BRCA2 protein records")
    reviewed = [item for item in proteins if item.get("reviewed") is True]
    if not reviewed:
        raise AssertionError("UniProtKB did not return an explicitly reviewed protein")
    if not any(item.get("accession") == "P51587" for item in reviewed):
        raise AssertionError("UniProtKB reviewed BRCA2 accession P51587 was not present")
    if any("sequence" in item for item in proteins):
        raise AssertionError("protein sequences must not be included in the discovery response")
    print(f"[PASS] UniProtKB release {result['release']} returned {len(proteins)} reviewed BRCA2 records")
    print("[PASS] reviewed accession P51587 and source metadata validated")
    print("[PASS] amino-acid sequences were not returned")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] UniProtKB live contract: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
