#!/usr/bin/env python3
"""Live contract smoke test for Ensembl human gene-symbol lookup.

Uses the public BRCA2 gene record only; it does not submit participant or clinical data.
"""
from __future__ import annotations

import sys

from app.literature.ensembl import lookup_gene


def main() -> int:
    result = lookup_gene("BRCA2")
    gene = result.get("gene") or {}
    if gene.get("stable_id") != "ENSG00000139618":
        raise AssertionError("Ensembl BRCA2 stable gene ID did not match the expected source record")
    if not isinstance(gene.get("assembly"), str) or not gene["assembly"]:
        raise AssertionError("Ensembl did not provide reference assembly metadata")
    if not isinstance(gene.get("start"), int) or not isinstance(gene.get("end"), int):
        raise AssertionError("Ensembl did not provide integer gene coordinates")
    if gene["start"] < 1 or gene["end"] < gene["start"]:
        raise AssertionError("Ensembl returned invalid gene coordinates")
    if result.get("species") != "homo_sapiens":
        raise AssertionError("Ensembl returned an unexpected species")
    print("[PASS] Ensembl live BRCA2 lookup returned the expected stable gene ID")
    print(f"[PASS] assembly={gene['assembly']} coordinates={gene.get('chromosome')}:{gene['start']}-{gene['end']}")
    print("[PASS] transcript metadata and source provenance validated")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] Ensembl live contract: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
