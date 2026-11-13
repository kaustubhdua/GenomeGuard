#!/usr/bin/env python3
"""Live contract smoke test for the GWAS Catalog REST API v2."""
from __future__ import annotations

import json
import sys

from app.literature.gwas_catalog import search_gwas_catalog


def main() -> int:
    result = search_gwas_catalog(gene_symbol="BRCA1", page=0, size=3)
    if result["provider"] != "GWAS Catalog" or result["api_version"] != "2.0":
        raise AssertionError("unexpected GWAS Catalog provider or API version")
    if not result["provenance"].get("data_release_date"):
        raise AssertionError("GWAS Catalog metadata did not include a data release date")
    if result["count"] <= 0 or not result["records"]:
        raise AssertionError("GWAS Catalog returned no associations for the public BRCA1 smoke query")
    if not any(
        str(record.get("study_accession") or "").startswith("GCST")
        and isinstance(record.get("p_value"), (int, float))
        and record.get("source_url", "").startswith("https://www.ebi.ac.uk/gwas/rest/api/v2/")
        for record in result["records"]
    ):
        raise AssertionError("GWAS Catalog associations did not include study, p-value, and source provenance")
    if result["has_more"] and not result.get("next_page_url"):
        raise AssertionError("GWAS Catalog pagination did not include a validated next link")
    print(json.dumps({
        "provider": result["provider"],
        "api_version": result["api_version"],
        "data_release_date": result["provenance"]["data_release_date"],
        "gene_build": result["provenance"]["gene_build"],
        "count": result["count"],
        "returned": result["returned"],
        "has_more": result["has_more"],
        "first_study": result["records"][0].get("study_accession"),
        "first_p_value": result["records"][0].get("p_value"),
        "retrieved_at": result["retrieved_at"],
    }, indent=2))
    print("[PASS] live GWAS Catalog REST API v2 association + metadata contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] GWAS Catalog live contract: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
