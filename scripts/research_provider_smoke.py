#!/usr/bin/env python3
"""Live contract smoke test for the public Europe PMC search API.

This deliberately checks the real provider from CI. It uses only a public biomedical
query, stores no search history, and never sends participant or patient information.
"""
from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
QUERY = "BRCA1 AND breast cancer sort_date:y"


def fetch(page: int) -> dict:
    url = API + "?" + urlencode({
        "query": QUERY,
        "format": "json",
        "resultType": "core",
        "pageSize": 3,
        "page": page,
    })
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "GenomeGuard-research-discovery-smoke/1.0"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                if response.status != 200:
                    raise RuntimeError(f"Europe PMC returned HTTP {response.status}")
                payload = json.loads(response.read(2_000_001).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Europe PMC response is not a JSON object")
                return payload
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Europe PMC unavailable after 3 attempts: {last_error}") from last_error


def validate(payload: dict, page: int) -> list[dict]:
    results = payload.get("resultList", {}).get("result")
    if not isinstance(results, list):
        raise AssertionError(f"page {page}: resultList.result is not an array")
    try:
        hits = int(payload["hitCount"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AssertionError("hitCount is missing or invalid") from exc
    if hits <= 3:
        raise AssertionError(f"expected a broad BRCA1 literature result set, got {hits} hits")
    for record in results:
        if not isinstance(record, dict) or not isinstance(record.get("title"), str) or not record["title"].strip():
            raise AssertionError(f"page {page}: record is missing a source-provided title")
        for field in ("authorString", "journalTitle", "firstPublicationDate", "pmid", "pmcid", "doi", "abstractText"):
            value = record.get(field)
            if value is not None and not isinstance(value, str):
                raise AssertionError(f"page {page}: {field} is not a string")
    return results


def main() -> int:
    first = validate(fetch(1), 1)
    second = validate(fetch(2), 2)
    if not first:
        raise AssertionError("Europe PMC returned no first-page records for the smoke query")
    if not second:
        raise AssertionError("Europe PMC returned no second-page records; pagination contract failed")
    first_ids = {r.get("pmid") or r.get("doi") for r in first}
    second_ids = {r.get("pmid") or r.get("doi") for r in second}
    first_ids.discard(None)
    second_ids.discard(None)
    if first_ids and second_ids and first_ids.intersection(second_ids):
        raise AssertionError("Europe PMC returned duplicate identifiers across pages")
    print(f"[PASS] Europe PMC live search returned {len(first)} first-page and {len(second)} second-page records")
    print("[PASS] source metadata types and pagination contract validated")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] Europe PMC live contract: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
