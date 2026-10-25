"""Read-only Playwright smoke checks for a deployed GenomeGuard UI.

Unlike scripts/ui_smoke.py, this never starts a local server, submits a request,
freezes an account, changes consent, or runs the guided tour. It is safe for a
synthetic demo deployment whose current state should be preserved.

Usage: python scripts/live_ui_smoke.py --base https://actual-service.example
"""
from __future__ import annotations

import argparse
import re
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

PAGES = ["#/overview", "#/requests", "#/request/1", "#/family/1", "#/anomalies",
         "#/audit", "#/donor", "#/redteam", "#/federated"]
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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        for theme in ("light", "dark"):
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            ctx.add_init_script("localStorage.setItem(\"gg_who\", \"steward\");"
                                f"localStorage.setItem(\"gg_theme\", \"{theme}\")")
            page = ctx.new_page()
            page.set_default_timeout(args.timeout)
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append("JavaScript: " + str(e)))

            def record_http_error(response):
                if response.status < 400 or response.status == 403:
                    return
                path = urlparse(response.url).path
                # A fresh demo has no request history yet. The API intentionally returns
                # JSON 404/not_found for a request ID that does not exist; test that the
                # UI renders this empty-data state rather than treating it as a broken route.
                expected_empty_record = (
                    response.status == 404
                    and re.fullmatch(r"/requests/\d+(?:/exposure)?", path)
                    and "application/json" in response.headers.get("content-type", "")
                )
                if not expected_empty_record:
                    errors.append(f"HTTP {response.status} {response.url}")

            page.on("response", record_http_error)
            for route in PAGES:
                try:
                    page.goto(base + "/" + route, wait_until="domcontentloaded")
                    page.locator("#view h1").wait_for(state="visible", timeout=args.timeout)
                    content = page.locator("#view").inner_text().lower()
                    if route in ("#/request/1", "#/family/1") and ("no such request" in content or "no request #" in content):
                        check(f"{theme} {route} explicit empty-data state", True)
                    else:
                        check(f"{theme} {route}", page.locator("#view h1").count() == 1)
                except Exception as exc:
                    check(f"{theme} {route}", False, f"{type(exc).__name__}: {str(exc)[:160]}")
            check(f"no JavaScript errors ({theme})", not errors, "; ".join(errors)[:240])
            ctx.close()
        print("Read-only responsive checks")
        for width in (320, 375, 414):
            ctx = browser.new_context(viewport={"width": width, "height": 800})
            ctx.add_init_script("localStorage.setItem(\"gg_who\", \"steward\")")
            page = ctx.new_page()
            page.set_default_timeout(args.timeout)
            page.goto(base + "/#/overview", wait_until="domcontentloaded")
            page.locator("#view h1").wait_for(state="visible", timeout=args.timeout)
            layout = page.evaluate("""() => ({viewport: document.documentElement.clientWidth,
              width: document.documentElement.scrollWidth,
              overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1})""")
            check(f"{width}px overview has no horizontal overflow", not layout["overflow"], str(layout))
            ctx.close()
        browser.close()
    print("\n" + ("LIVE UI SMOKE PASSED" if not FAILURES else f"LIVE UI SMOKE FAILED ({len(FAILURES)} checks)"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
