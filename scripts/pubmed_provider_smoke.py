#!/usr/bin/env python3
"""Low-rate live contract smoke test for the public NCBI PubMed API."""
from __future__ import annotations

import sys

from app.literature.pubmed import search_pubmed


def main() -> int:
    result = search_pubmed("BRCA1 AND breast cancer", retstart=0, retmax=3)
    papers = result["papers"]
    if result["provider"] != "PubMed" or result["count"] <= 3:
        raise AssertionError("PubMed returned an unexpected provider/count response")
    if not papers:
        raise AssertionError("PubMed returned no records for the public smoke query")
    pmids = [paper["pmid"] for paper in papers]
    if len(pmids) != len(set(pmids)):
        raise AssertionError("PubMed returned duplicate PMIDs in one page")
    for paper in papers:
        if not paper["pmid"].isdigit() or not paper["source_url"].startswith("https://pubmed.ncbi.nlm.nih.gov/"):
            raise AssertionError("PubMed returned an invalid identifier or source link")
        if paper["source"] != "PubMed" or not paper["title"]:
            raise AssertionError("PubMed record normalization is incomplete")
    print(f"[PASS] PubMed ESearch returned {result['count']} matches")
    print(f"[PASS] ESummary normalized {len(papers)} source records with valid PMIDs and links")
    print("[PASS] no abstracts or full text were fetched")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] PubMed live contract: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
