#!/usr/bin/env python3
"""Browser acceptance for GenomeGuard's department and symptom literature search.

The provider is intercepted with source-shaped fixtures here so the UI test is
deterministic. A separate CI smoke test exercises the real Europe PMC service.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
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
    pubmed_requests: list[dict[str, object]] = []
    provider_outages = {"europe": False, "pubmed": False}

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
        if provider_outages["europe"]:
            route.fulfill(status=503, content_type="application/json", body=json.dumps({"error": "fixture outage"}))
            return
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        cursor = query.get("cursorMark", ["*"])[0]
        page = 1 if cursor == "*" else 2
        requests.append({"query": query.get("query", [""])[0], "cursorMark": cursor})
        records = ([response_record(1, index) for index in range(PAGE_SIZE)]
                   if page == 1 else [response_record(2, 0)])
        body = {
            "hitCount": PAGE_SIZE + 1,
            "nextCursorMark": "cursor-page-2" if page == 1 else "cursor-page-2",
            "resultList": {"result": records},
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def handle_pubmed(route) -> None:
        if provider_outages["pubmed"]:
            route.fulfill(status=503, content_type="application/json", body=json.dumps({"error": "fixture outage"}))
            return
        payload = json.loads(route.request.post_data or "{}")
        pubmed_requests.append(payload)
        if int(payload.get("retstart", 0)) == 0:
            papers = [
                {"source": "PubMed", "pmid": "12345778", "title": "Duplicate PubMed title one",
                 "authors": ["PubMed Test Author"], "journal": "PubMed Journal",
                 "publication_date": "2026", "doi": "10.1000/genomeguard.one",
                 "abstract": None, "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345778/"},
                {"source": "PubMed", "pmid": "12345779", "title": "Duplicate PubMed title two",
                 "authors": ["PubMed Test Author"], "journal": "PubMed Journal",
                 "publication_date": "2026", "doi": "10.1000/genomeguard.two",
                 "abstract": None, "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345779/"},
                {"source": "PubMed", "pmid": "99999999", "title": "PubMed-only verified publication",
                 "authors": ["NCBI Author"], "journal": "NCBI Journal",
                 "publication_date": "2026", "doi": "10.1000/genomeguard.pubmed",
                 "abstract": None, "source_url": "https://pubmed.ncbi.nlm.nih.gov/99999999/"},
            ]
            body = {"provider": "PubMed", "count": 4, "retstart": 0, "retmax": PAGE_SIZE,
                    "returned": 3, "has_more": True, "papers": papers}
        else:
            papers = [{
                "source": "PubMed", "pmid": "12345878", "title": "Duplicate second-page publication",
                "authors": ["NCBI Author"], "journal": "NCBI Journal", "publication_date": "2026",
                "doi": "10.1000/genomeguard.page2", "abstract": None,
                "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345878/"
            }]
            body = {"provider": "PubMed", "count": 4, "retstart": 3, "retmax": PAGE_SIZE,
                    "returned": 1, "has_more": False, "papers": papers}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_default_timeout(args.timeout)
        page.route("https://www.ebi.ac.uk/europepmc/webservices/rest/search**", handle_provider)
        page.route("**/literature/pubmed/search", handle_pubmed)
        page.goto(args.base.rstrip("/") + "/#/research", wait_until="domcontentloaded")
        page.get_by_role("heading", name="Research discovery").wait_for()
        page.get_by_role("link", name="Oncology Browse publications →").click()
        page.locator(".research-paper").first.wait_for()
        check("department hyperlink immediately performs a literature search",
              len(requests) == 1 and "oncology" in requests[0]["query"].lower()
              and len(pubmed_requests) == 1 and "oncology" in str(pubmed_requests[0].get("q", "")).lower(),
              str({"europe_pmc": requests, "pubmed": pubmed_requests}))
        check("department search renders source metadata",
              page.locator(".research-paper h3").first.inner_text() == "Verified provider-shaped publication one-1")
        check("first result page renders all 20 returned records",
              page.locator(".research-paper").count() == PAGE_SIZE + 1)
        page.get_by_role("button", name="Load more publications").click()
        page.locator(".research-paper").nth(PAGE_SIZE).wait_for()
        check("pagination appends the next provider page",
              len(requests) == 2 and requests[1]["cursorMark"] == "cursor-page-2"
              and len(pubmed_requests) == 2 and pubmed_requests[1].get("retstart") == 3
              and page.locator(".research-paper").count() == PAGE_SIZE + 2,
              str({"europe_pmc": requests, "pubmed": pubmed_requests}))

        page.get_by_label("Research question or symptom description").fill("BRCA1 ovarian cancer symptoms")
        page.get_by_label("Research department", exact=True).select_option("oncology")
        page.get_by_role("button", name="Search publications").click()
        page.locator(".research-paper").first.wait_for()
        latest = requests[-1]["query"].lower()
        check("symptom/question search combines the selected department and user query",
              "oncology" in latest and "brca1 ovarian cancer symptoms" in latest, latest)
        check("publication links use HTTPS and open safely",
              page.locator(".research-paper a").first.get_attribute("href", timeout=args.timeout).startswith("https://")
              and page.locator(".research-paper a").first.get_attribute("rel") == "noopener noreferrer")

        page.get_by_label("Publication sources").select_option("pubmed")
        page.locator(".research-paper").first.wait_for()
        check("source selector can restrict results to PubMed",
              page.locator(".research-paper .tag").first.inner_text() == "PubMed"
              and page.locator(".research-paper").count() == 3)

        provider_outages["pubmed"] = True
        page.get_by_label("Publication sources").select_option("both")
        page.locator(".research-paper").first.wait_for()
        partial_status = page.locator("#research-status").inner_text()
        check("one-provider outage preserves the other provider's results",
              page.locator(".research-paper").count() == PAGE_SIZE
              and "One source was unavailable" in partial_status
              and "Europe PMC" in partial_status, partial_status)

        provider_outages["europe"] = True
        page.get_by_role("button", name="Search publications").click()
        page.get_by_text("No sample or fabricated papers are shown", exact=False).wait_for()
        check("both-provider outage shows an explicit failure and no fabricated records",
              page.locator(".research-paper").count() == 0
              and "No sample or fabricated papers are shown" in page.locator("#research-status").inner_text())

        provider_outages["europe"] = False
        provider_outages["pubmed"] = False

        screenshot_dir = Path(os.environ.get("UI_SCREENSHOT_DIR", "/tmp/genomeguard-ui-screenshots"))
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_dir / "research-desktop.png"), full_page=True)

        mobile = browser.new_page(viewport={"width": 375, "height": 812})
        mobile.set_default_timeout(args.timeout)
        mobile.route("https://www.ebi.ac.uk/europepmc/webservices/rest/search**", handle_provider)
        mobile.route("**/literature/pubmed/search", handle_pubmed)
        mobile.goto(args.base.rstrip("/") + "/#/research", wait_until="domcontentloaded")
        mobile.get_by_role("heading", name="Research discovery").wait_for()
        no_horizontal_overflow = mobile.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth + 1"
        )
        check("research discovery has no horizontal overflow at 375px", no_horizontal_overflow)
        mobile.get_by_label("Research question or symptom description").fill(
            "BRCA1 ovarian cancer symptoms"
        )
        mobile.get_by_label("Research department", exact=True).select_option("oncology")
        mobile.get_by_role("button", name="Search publications").click()
        mobile.locator(".research-paper").first.wait_for()
        check("mobile research search renders live-provider-shaped results",
              mobile.locator(".research-paper").count() == PAGE_SIZE + 1)
        mobile.screenshot(path=str(screenshot_dir / "research-mobile-375.png"), full_page=True)
        browser.close()

    print("\n" + ("RESEARCH UI SMOKE PASSED" if not failures else f"RESEARCH UI SMOKE FAILED ({len(failures)} checks)"))
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
