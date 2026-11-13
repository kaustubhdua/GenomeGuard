#!/usr/bin/env python3
"""Live contract smoke test for EMBL-EBI OLS4 MONDO/HPO/DOID search."""
from __future__ import annotations

import json
import sys

from app.literature.ontology import search_ontology


def main() -> int:
    result = search_ontology("ataxia", ontology="all", page=0, size=5)
    if result["provider"] != "EMBL-EBI Ontology Lookup Service":
        raise AssertionError("unexpected OLS provider")
    if not result["terms"] or result["returned"] <= 0:
        raise AssertionError("OLS4 returned no terms for the public ataxia smoke query")
    if any(term["ontology"] not in {"mondo", "hp", "doid"} for term in result["terms"]):
        raise AssertionError("OLS4 returned a term outside the configured ontology allowlist")
    if not all(term["label"] and term["iri"] and term["source_url"] for term in result["terms"]):
        raise AssertionError("OLS4 terms are missing source identifiers or links")
    print(json.dumps({
        "provider": result["provider"],
        "query": result["query"],
        "returned": result["returned"],
        "total": result["total"],
        "ontologies": sorted({term["ontology"] for term in result["terms"]}),
        "retrieved_at": result["retrieved_at"],
    }, indent=2))
    print("[PASS] live OLS4 MONDO/HPO/DOID search contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] OLS4 live contract: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
