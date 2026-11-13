#!/usr/bin/env python3
"""Live contract smoke test for NCBI ClinVar E-utilities.

Uses a public BRCA1 query only. It does not submit, retrieve, or store participant data.
"""
from __future__ import annotations

import json
import sys

from app.literature.clinvar import search_clinvar


def main() -> int:
    result = search_clinvar("BRCA1", classification="pathogenic", retmax=10)
    if result["provider"] != "NCBI ClinVar":
        raise AssertionError("unexpected ClinVar provider identity")
    if result["count"] <= 0 or not result["records"]:
        raise AssertionError("ClinVar returned no records for the public BRCA1 smoke query")
    if not any(
        record.get("accession", "").startswith("VCV")
        and record.get("classifications", {}).get("germline", {}).get("description")
        for record in result["records"]
    ):
        raise AssertionError("ClinVar ESummary records did not contain VCV aggregate classifications")
    for record in result["records"]:
        if not record.get("source_url", "").startswith("https://www.ncbi.nlm.nih.gov/clinvar/"):
            raise AssertionError("ClinVar record is missing its official source URL")
        for key in ("germline", "somatic_clinical_impact", "somatic_oncogenicity"):
            if key not in record.get("classifications", {}):
                raise AssertionError(f"ClinVar record is missing the {key} classification field")
    print(json.dumps({
        "provider": result["provider"],
        "query": result["query"],
        "count": result["count"],
        "returned": result["returned"],
        "has_more": result["has_more"],
        "first_accession": result["records"][0].get("accession"),
        "first_germline_review_status": (
            result["records"][0].get("classifications", {}).get("germline", {}).get("review_status")
        ),
        "retrieved_at": result["retrieved_at"],
    }, indent=2))
    print("[PASS] live ClinVar ESearch + ESummary source contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] ClinVar live contract: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
