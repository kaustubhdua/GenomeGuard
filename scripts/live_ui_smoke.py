"""Read-only Playwright smoke checks for a deployed GenomeGuard UI.

Unlike scripts/ui_smoke.py, this never starts a local server, submits a request,
freezes an account, changes consent, or runs the guided tour. It checks routes in either demo or non-demo research mode without mutating data.

Usage: python scripts/live_ui_smoke.py --base https://actual-service.example
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

PAGES = ["#/overview", "#/requests", "#/request/1", "#/family/1", "#/anomalies",
         "#/audit", "#/donor", "#/redteam", "#/federated", "#/variants", "#/dataset-qc",
         "#/chromosomes", "#/datasets", "#/sources"]
EXPECTED_HEADINGS = {
    "#/overview": "Research access, governed with evidence.",
    "#/variants": "Locus & variant inspector",
    "#/dataset-qc": "Dataset QC & import review",
    "#/chromosomes": "Chromosome explorer",
    "#/datasets": "Dataset catalogue",
    "#/sources": "Public source discovery",
}
MOBILE_PAGES = ("#/overview", "#/chromosomes", "#/datasets", "#/sources", "#/variants")
STEWARD_ONLY_PAGES = {"#/family/1", "#/anomalies", "#/audit", "#/dataset-qc"}
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}" + (f": {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--timeout", type=int, default=20_000)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    if not base.startswith(("https://", "http://")):
        parser.error("--base must be an absolute http:// or https:// URL")
    steward_enabled = False
    try:
        with urlopen(base + "/demo/requesters", timeout=args.timeout / 1000) as response:
            demo_accounts = json.loads(response.read().decode("utf-8"))
            steward_enabled = bool(demo_accounts.get("admin_key"))
    except Exception:
        pass
    pages = PAGES if steward_enabled else [route for route in PAGES if route not in STEWARD_ONLY_PAGES]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        for theme in ("light", "dark"):
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            ctx.add_init_script(f"localStorage.setItem(\"gg_theme\", \"{theme}\")")
            page = ctx.new_page()
            page.set_default_timeout(args.timeout)
            errors: list[str] = []
            page.on("pageerror", lambda e, errs=errors: errs.append("JavaScript: " + str(e)))

            def record_http_error(response, errs=errors):
                if response.status < 400 or response.status == 403:
                    return
                path = urlparse(response.url).path
                is_json = "application/json" in response.headers.get("content-type", "")
                # Readiness is deliberately HTTP 503 until production controls are verified.
                # Only suppress that exact, machine-readable fail-closed response.
                if response.status == 503 and path == "/health/ready" and is_json:
                    try:
                        body = response.json()
                        if body.get("ready") is False and body.get("status") in ("not_ready", "migration_incomplete"):
                            return
                    except Exception:
                        pass
                # A fresh demo has no request history yet. The API intentionally returns
                # JSON 404/not_found for a request ID that does not exist; test that the
                # UI renders this empty-data state rather than treating it as a broken route.
                expected_empty_record = (
                    response.status == 404
                    and re.fullmatch(r"/requests/\d+(?:/exposure)?", path)
                    and is_json
                )
                if not expected_empty_record:
                    errs.append(f"HTTP {response.status} {response.url}")

            page.on("response", record_http_error)
            page.goto(base + "/#/overview", wait_until="domcontentloaded")
            page.locator("#view h1").wait_for(state="visible", timeout=args.timeout)
            if steward_enabled:
                page.locator("#who").select_option("steward")
            for route in pages:
                try:
                    page.goto(base + "/" + route, wait_until="domcontentloaded")
                    page.locator("#view h1").wait_for(state="visible", timeout=args.timeout)
                    content = page.locator("#view").inner_text().lower()
                    if route in ("#/request/1", "#/family/1") and ("no such request" in content or "no request #" in content):
                        check(f"{theme} {route} explicit empty-data state", True)
                    else:
                        heading = page.locator("#view h1").inner_text().strip()
                        expected = EXPECTED_HEADINGS.get(route)
                        check(f"{theme} {route}", page.locator("#view h1").count() == 1
                              and (expected is None or heading == expected),
                              "" if expected is None or heading == expected
                              else f"expected {expected!r}, got {heading!r}")
                except Exception as exc:
                    check(f"{theme} {route}", False, f"{type(exc).__name__}: {str(exc)[:160]}")
            check(f"no JavaScript errors ({theme})", not errors, "; ".join(errors)[:240])
            ctx.close()
        print("Read-only responsive checks")
        for width in (320, 375, 414):
            ctx = browser.new_context(viewport={"width": width, "height": 800})
            page = ctx.new_page()
            page.set_default_timeout(args.timeout)
            page.goto(base + "/#/overview", wait_until="domcontentloaded")
            page.locator("#view h1").wait_for(state="visible", timeout=args.timeout)
            if steward_enabled:
                page.locator("#who").select_option("steward")
            for route in MOBILE_PAGES:
                try:
                    page.goto(base + "/" + route, wait_until="domcontentloaded")
                    page.locator("#view h1").wait_for(state="visible", timeout=args.timeout)
                    heading = page.locator("#view h1").inner_text().strip()
                    expected = EXPECTED_HEADINGS[route]
                    check(f"{width}px {route} loads its expected page",
                          heading == expected, f"expected {expected!r}, got {heading!r}")
                    layout = page.evaluate("""() => ({viewport: document.documentElement.clientWidth,
                      width: document.documentElement.scrollWidth,
                      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1})""")
                    check(f"{width}px {route} has no horizontal overflow",
                          not layout["overflow"], str(layout))
                except Exception as exc:
                    check(f"{width}px {route}", False,
                          f"{type(exc).__name__}: {str(exc)[:160]}")
            ctx.close()
        browser.close()
    print("\n" + ("LIVE UI SMOKE PASSED" if not FAILURES else f"LIVE UI SMOKE FAILED ({len(FAILURES)} checks)"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
