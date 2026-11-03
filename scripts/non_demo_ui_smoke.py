"""Browser smoke test for account-free guest UI against a non-demo backend.

The test verifies that signup/sign-in/email confirmation are absent and that a
non-demo deployment does not silently expose synthetic demo personas or data.
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

FAILURES: list[str] = []


def check(label: str, ok: bool) -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILURES.append(label)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8767")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    auth_calls: list[str] = []
    eval_calls: list[str] = []

    health = {
        "status": "ok", "demo_mode": False, "synthetic_data_only": False,
        "provenance_known": True, "consent_simulated": False,
        "donors": 44, "variants": 50,
        "provenance": {"genotypes_label": "Operator-declared source",
                       "consent_label": "Operator-supplied consent records"},
    }

    def fulfill(route, status: int, payload: dict) -> None:
        route.fulfill(status=status, content_type="application/json",
                      body=json.dumps(payload))

    def mock_api(route) -> None:
        req = route.request
        parsed = urlparse(req.url)
        path = parsed.path
        if parsed.netloc == "hkyieaovolkethovyenb.supabase.co" and path.startswith("/auth/v1/"):
            auth_calls.append(path)
            return fulfill(route, 500, {"error": "auth_disabled"})
        if path == "/health":
            return fulfill(route, 200, health)
        if path == "/health/ready":
            return fulfill(route, 200, {"ready": True, "checks": {}})
        if path in ("/demo/requesters", "/demo/donors"):
            return fulfill(route, 404, {"error": "demo_mode_disabled"})
        if path == "/eval/results":
            eval_calls.append(req.url)
        if path == "/" or path.startswith("/static/") or path.endswith((".js", ".css", ".svg", ".png", ".woff2")):
            return route.continue_()
        return fulfill(route, 200, {})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.route("**/*", mock_api)
        page.goto(base + "/#/overview", wait_until="domcontentloaded")
        page.locator("#view h1").wait_for(state="visible", timeout=15000)

        check("legacy API-key login panel is removed", page.locator("#auth-panel").count() == 0)
        check("legacy API-key controls are absent",
              page.locator("#api-key-input, #auth-kind, #connect-key, #disconnect-key").count() == 0)
        check("Supabase account panel and all account controls are absent",
              page.locator("#supabase-auth-panel, #supabase-email, #supabase-password, "
                           "#supabase-full-name, #supabase-signin, #supabase-signup, "
                           "#supabase-resend, #supabase-signout").count() == 0)
        check("guest-only notice is shown",
              "account creation and sign-in are disabled" in page.locator("#who-note").inner_text().lower())
        check("demo persona selector is hidden on non-demo backend", page.locator("#who").is_hidden())
        check("participant/demo-only links are hidden",
              page.locator('nav a[href="#/donor"], nav a[href="#/redteam"], nav a[href="#/federated"]').count() == 0)
        check("no Supabase Auth endpoint is called", not auth_calls)
        check("synthetic evaluation is not fetched in non-demo overview", not eval_calls)

        context.close()
        browser.close()

    print("\\n" + ("NON-DEMO UI SMOKE PASSED" if not FAILURES
                     else f"NON-DEMO UI SMOKE FAILED ({len(FAILURES)} checks)"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
