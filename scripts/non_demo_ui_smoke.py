"""Browser smoke test for the non-demo sign-in experience using mocked API responses.

This test exercises UI behavior only. It does not claim that mocked credentials, identity,
consent, or data represent a real deployment. Run against the local UI server started by make.
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8767")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    eval_calls: list[str] = []

    health = {
        "status": "ok",
        "demo_mode": False,
        "synthetic_data_only": False,
        "provenance_known": True,
        "consent_simulated": False,
        "tamper_demo": False,
        "donors": 44,
        "variants": 50,
        "provenance": {
            "genotypes": "real_vcf",
            "genotypes_label": "Real VCF genotypes (operator-declared source: fixture; source not independently authenticated)",
            "consent": "source_records",
            "consent_label": "Operator-supplied source-matched consent records",
            "relatives_label": "Relative exposure is a model",
            "agents_label": "Agents: built-in templates",
            "encryption": "AES-256-GCM at rest",
        },
    }

    def fulfill(route, status: int, payload: dict) -> None:
        route.fulfill(status=status, content_type="application/json",
                      body=json.dumps(payload))

    def mock_api(route) -> None:
        req = route.request
        parsed = urlparse(req.url)
        path = parsed.path
        if path == "/" or path.startswith("/static/"):
            return route.continue_()
        headers = {k.lower(): v for k, v in req.headers.items()}
        if path == "/health":
            return fulfill(route, 200, health)
        if path in ("/demo/requesters", "/demo/donors"):
            return fulfill(route, 404, {"error": "not_found", "message": "demo mode is off"})
        if path == "/me":
            if headers.get("x-api-key") == "valid-researcher-key":
                return fulfill(route, 200, {"id": 17, "name": "Researcher", "tier": "registered"})
            return fulfill(route, 401, {"error": "unauthorized", "message": "requester key required"})
        if path == "/anomalies":
            if headers.get("x-admin-key") == "valid-steward-key":
                return fulfill(route, 200, {"length": 0, "head_hash": "0" * 64})
            return fulfill(route, 401, {"error": "unauthorized", "message": "steward key required"})
        if path == "/audit/verify":
            if headers.get("x-admin-key") == "valid-steward-key":
                return fulfill(route, 200, {"ok": True, "length": 0, "head_hash": "0" * 64})
            return fulfill(route, 401, {"error": "unauthorized", "message": "steward key required"})
        if path == "/requests":
            if req.method == "GET":
                if headers.get("x-api-key") == "valid-researcher-key" or headers.get("x-admin-key") == "valid-steward-key":
                    return fulfill(route, 200, {"requests": []})
                return fulfill(route, 401, {"error": "unauthorized", "message": "API key required"})
            return fulfill(route, 201, {"id": 100, "outcome": "permit_with_transform", "status": "released"})
        if path == "/consent/summary":
            if headers.get("x-api-key") == "valid-researcher-key":
                return fulfill(route, 200, {"considered": 44, "eligible": 44, "excluded_by_reason": {}})
            return fulfill(route, 401, {"error": "unauthorized", "message": "API key required"})
        if path == "/eval/results":
            eval_calls.append(req.url)
            return fulfill(route, 200, {"meta": {"dataset": "synthetic"}, "differencing": {}})
        # The remaining overview calls are irrelevant to the sign-in assertions.
        return fulfill(route, 200, {})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.route("**/*", mock_api)
        page.goto(base + "/#/overview", wait_until="domcontentloaded")
        page.locator("#auth-panel").wait_for(state="visible", timeout=15000)
        page.locator("#view h1").wait_for(state="visible", timeout=15000)
        check("non-demo mode shows credential sign-in", not page.locator("#auth-panel").is_hidden())
        check("demo persona selector is hidden", page.locator("#who").is_hidden())
        check("participant/demo-only links are hidden",
              page.locator('nav a[href="#/donor"], nav a[href="#/redteam"], nav a[href="#/federated"]').count() == 0)
        check("synthetic evaluation is not fetched in non-demo overview", not eval_calls)

        page.locator("#api-key-input").fill("valid-researcher-key")
        page.locator("#connect-key").click()
        page.get_by_text("Connected. This key stays in memory", exact=False).wait_for(timeout=5000)
        check("researcher key is accepted", "active in memory" in page.locator("#who-note").inner_text())
        check("real credentials are not persisted to localStorage",
              page.evaluate("localStorage.getItem('gg_who')") is None)

        page.goto(base + "/#/requests", wait_until="domcontentloaded")
        page.locator("#view h1").wait_for(state="visible", timeout=15000)
        check("real-mode request form is usable", page.locator("#purpose").count() == 1)
        check("real-mode form omits planted demo variants", page.locator("#pl").count() == 0)
        check("real-mode form omits demo preset buttons",
              page.get_by_role("button", name="Diabetes frequency study").count() == 0)
        check("real-mode form omits the synthetic probing sequence",
              page.get_by_role("button", name="Run probe sequence").count() == 0)
        check("disease field is free text for source-specific terms",
              page.locator("input#disease").count() == 1 and page.locator("select#disease").count() == 0)

        page.locator("#auth-kind").select_option("steward")
        page.locator("#api-key-input").fill("invalid-steward-key")
        page.locator("#connect-key").click()
        page.get_by_text("The key was rejected", exact=False).wait_for(timeout=5000)
        check("invalid steward key is rejected", page.locator('nav a[href="#/audit"]').count() == 0)
        page.locator("#api-key-input").fill("valid-steward-key")
        page.locator("#connect-key").click()
        page.get_by_text("Connected. This key stays in memory", exact=False).wait_for(timeout=5000)
        check("steward key is accepted", "Steward credentials are active" in page.locator("#who-note").inner_text())
        check("steward navigation appears after authentication",
              page.locator('nav a[href="#/audit"]').count() == 1)
        check("steward key is not persisted to localStorage",
              page.evaluate("localStorage.getItem('gg_who')") is None)

        page.locator("#disconnect-key").click()
        check("disconnect clears active credentials",
              "Disconnected." in page.locator("#auth-status").inner_text())
        check("steward navigation is removed after disconnect",
              page.locator('nav a[href="#/audit"]').count() == 0)
        check("demo evaluation remains unfetched", not eval_calls)
        context.close()
        browser.close()

    print("\\n" + ("NON-DEMO UI SMOKE PASSED" if not FAILURES
                     else f"NON-DEMO UI SMOKE FAILED ({len(FAILURES)} checks)"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
