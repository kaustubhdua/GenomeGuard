#!/usr/bin/env python3
"""Browser acceptance for GenomeGuard's department and symptom literature search.

The provider is intercepted with source-shaped fixtures here so the UI test is
deterministic. A separate CI smoke test exercises the real Europe PMC service.
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

PAGE_SIZE = 20


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--timeout", type=int, default=20_000)
    args = parser.parse_args()
    requests: list[dict[str, str]] = []
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
        if not ok:
            failures.append(label)

    def response_record(page: int, index: int) -> dict:
        suffix = "one" if page == 1 else "two"
        return {
            "title": f"Verified provider-shaped publication {suffix}-{index + 1}",
            "authorString": "Example Research Group",
            "journalTitle": "Journal of Biomedical Research",
            "firstPublicationDate": "2026-01-15",
            "pmid": str(12345678 + page * 100 + index),
            "doi": f"10.1000/genomeguard.{suffix}.{index + 1}",
            "isOpenAccess": "Y",
            "abstractText": "A test fixture used only to verify the publication display contract.",
        }

    def handle_provider(route) -> None:
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        page = int(query.get("page", ["1"])[0])
        requests.append({"query": query.get("query", [""])[0], "page": str(page)})
        records = ([response_record(1, index) for index in range(PAGE_SIZE)]
                   if page == 1 else [response_record(2, 0)])
        body = {
            "hitCount": PAGE_SIZE + 1,
            "resultList": {"result": records},
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_default_timeout(args.timeout)
        page.route("https://www.ebi.ac.uk/europepmc/webservices/rest/search**", handle_provider)
        page.goto(args.base.rstrip("/") + "/#/research", wait_until="domcontentloaded")
        page.get_by_role("heading", name="Research discovery").wait_for()
        page.get_by_role("link", name="Oncology Browse publications →").click()
        page.locator(".research-paper").first.wait_for()
        check("department hyperlink immediately performs a literature search",
              len(requests) == 1 and "oncology" in requests[0]["query"].lower(), str(requests))
        check("department search renders source metadata",
              page.locator(".research-paper h3").first.inner_text() == "Verified provider-shaped publication one-1")
        check("first result page renders all 20 returned records",
              page.locator(".research-paper").count() == PAGE_SIZE)
        page.get_by_role("button", name="Load more publications").click()
        page.locator(".research-paper").nth(PAGE_SIZE).wait_for()
        check("pagination appends the next provider page",
              len(requests) == 2 and requests[1]["page"] == "2"
              and page.locator(".research-paper").count() == PAGE_SIZE + 1, str(requests))

        page.get_by_label("Research question or symptom description").fill("BRCA1 ovarian cancer symptoms")
        page.get_by_label("Research department").select_option("oncology")
        page.get_by_role("button", name="Search publications").click()
        page.locator(".research-paper").first.wait_for()
        latest = requests[-1]["query"].lower()
        check("symptom/question search combines the selected department and user query",
              "oncology" in latest and "brca1 ovarian cancer symptoms" in latest, latest)
        check("publication links use HTTPS and open safely",
              page.locator(".research-paper a").first.get_attribute("href", timeout=args.timeout).startswith("https://")
              and page.locator(".research-paper a").first.get_attribute("rel") == "noopener noreferrer")
        browser.close()

    print("\n" + ("RESEARCH UI SMOKE PASSED" if not failures else f"RESEARCH UI SMOKE FAILED ({len(failures)} checks)"))
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
