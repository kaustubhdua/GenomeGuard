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
    edge_calls: list[dict] = []
    review_state = {"status": "pending_review", "history": []}
    submitted_request: dict = {}

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
            "encryption": "AES-256-GCM protects selected application records; public cohort artifact is plaintext in the image. Private or controlled-access data are not supported by this deployment.",
        },
    }

    def fulfill(route, status: int, payload: dict) -> None:
        route.fulfill(status=status, content_type="application/json",
                      body=json.dumps(payload))

    def mock_api(route) -> None:
        req = route.request
        parsed = urlparse(req.url)
        path = parsed.path
        if parsed.netloc == "hkyieaovolkethovyenb.supabase.co":
            if path == "/auth/v1/token" and req.method == "POST":
                payload = req.post_data_json or {}
                email = payload.get("email", "")
                token = "reviewer-token" if email.startswith("reviewer") else (
                    "unprovisioned-token" if email.startswith("pending") else "researcher-token")
                return fulfill(route, 200, {
                    "access_token": token, "refresh_token": token + "-refresh",
                    "token_type": "bearer", "expires_in": 3600,
                    "user": {"id": "auth-" + token, "email": email,
                             "user_metadata": {"full_name": "Smoke Test User"}},
                })
            if path == "/auth/v1/signup" and req.method == "POST":
                payload = req.post_data_json or {}
                return fulfill(route, 200, {"user": {"id": "new-auth-user", "email": payload.get("email")}, "session": None})
            if path == "/auth/v1/logout" and req.method == "POST":
                return fulfill(route, 200, {})
            if path.startswith("/functions/v1/genomeguard-api/"):
                edge_path = path.split("/functions/v1/genomeguard-api", 1)[1]
                headers = {k.lower(): v for k, v in req.headers.items()}
                token = headers.get("authorization", "").replace("Bearer ", "")
                edge_calls.append({"path": edge_path, "method": req.method, "token": token,
                                   "body": req.post_data_json if req.method == "POST" else None})
                if edge_path == "/me" and req.method == "GET":
                    if token == "unprovisioned-token":
                        access = {"access_status": "no_membership", "memberships": [],
                                  "active_membership_count": 0, "membership_count": 0}
                    else:
                        role = "reviewer" if token == "reviewer-token" else "researcher"
                        access = {"access_status": "active", "memberships": [{
                            "organization_id": "org-1", "organization": "Research Institute",
                            "organization_status": "active", "role": role, "status": "active",
                        }], "active_membership_count": 1, "membership_count": 1}
                    return fulfill(route, 200, {"user": {"id": "auth-" + token, "email": token + "@example.org"}, "access": access})
                if edge_path == "/requests" and req.method == "GET":
                    return fulfill(route, 200, {"requests": []})
                if edge_path == "/requests" and req.method == "POST":
                    submitted_request.update(req.post_data_json or {})
                    review_state["status"] = "pending_review"
                    review_state["history"] = []
                    return fulfill(route, 201, {"id": 501, "status": "pending_review", "message": "Stored for review"})
                if edge_path == "/requests/501" and req.method == "GET":
                    request_data = {
                        "id": 501, "created_at": "2026-11-03T10:00:00Z",
                        "purpose": submitted_request.get("purpose", "general_research"),
                        "disease": submitted_request.get("disease"),
                        "is_commercial": submitted_request.get("is_commercial", False),
                        "data_level": submitted_request.get("data_level", "aggregate"),
                        "status": review_state["status"], "organization_id": "org-1",
                    }
                    decision = None if not review_state["history"] else {
                        "outcome": review_state["history"][-1]["outcome"],
                        "explanation": review_state["history"][-1]["reason"],
                        "reasons": [review_state["history"][-1]["reason"]],
                    }
                    return fulfill(route, 200, {"request": request_data, "decision": decision,
                                                "review_history": review_state["history"], "history": []})
                if edge_path == "/steward/requests" and req.method == "GET":
                    items = [] if review_state["status"] not in ("pending_review", "needs_more_information") else [{
                        "id": 501, "ts": "2026-11-03T10:00:00Z", "status": review_state["status"],
                        "requester": "Test Researcher", "institution": "Research Institute",
                        "request": {"purpose": submitted_request.get("purpose", "general_research"),
                                    "disease": submitted_request.get("disease"),
                                    "is_commercial": False, "data_level": submitted_request.get("data_level", "aggregate")},
                        "outcome": "pending", "needs_human": True,
                    }]
                    return fulfill(route, 200, {"requests": items, "total_count": len(items), "limit": 50, "offset": 0})
                if edge_path == "/requests/501/review" and req.method == "POST":
                    payload = req.post_data_json or {}
                    status = {"approved": "approved_pending_release", "denied": "denied",
                              "needs_more_information": "needs_more_information"}.get(payload.get("outcome"))
                    if not status or len(payload.get("reason", "")) < 3:
                        return fulfill(route, 400, {"error": "invalid_review"})
                    review_state["status"] = status
                    review_state["history"].append({"outcome": payload["outcome"], "reason": payload["reason"],
                                                     "created_at": "2026-11-03T10:05:00Z"})
                    return fulfill(route, 200, {"request_id": 501, "outcome": payload["outcome"], "status": status})
                if edge_path == "/sources" and req.method == "GET":
                    return fulfill(route, 200, {"sources": [{
                        "source_id": "igsr-1000-genomes-phase-3", "name": "1000 Genomes Project Phase 3",
                        "provider": "IGSR", "release": "Phase 3", "data_type": "Sample-level VCF",
                        "assembly": "GRCh37", "summary": "Public source discovery only.",
                        "reuse_review": "Review exact-artifact terms.", "source_url": "https://www.internationalgenome.org/",
                        "terms_url": "https://www.internationalgenome.org/IGSR_disclaimer/",
                        "lifecycle_status": {"discovered": "complete"},
                    }], "source_count": 1, "discovery_only": True, "provenance_note": "Discovery only."})
                if edge_path == "/datasets" and req.method == "GET":
                    return fulfill(route, 200, {"datasets": [], "dataset_count": 0, "provenance_note": "No verified imports."})
                if edge_path == "/chromosomes" and req.method == "GET":
                    return fulfill(route, 200, {"reference_assembly": "GRCh38", "chromosomes": [{
                        "chromosome": "1", "kind": "autosome", "length_bp": 248956422,
                        "data_coverage": {"variant_data_loaded": False, "variant_count": 0},
                    }], "provenance_note": "Reference metadata only."})
                return fulfill(route, 404, {"error": "not_found"})
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
        if path == "/admin/requesters" and req.method == "POST":
            if headers.get("x-admin-key") == "valid-steward-key":
                payload = json.loads(req.post_data or "{}")
                return fulfill(route, 201, {"id": 18, "name": payload.get("name"),
                    "institution": payload.get("institution"), "credential_level": payload.get("credential_level"),
                    "api_key": "one-time-issued-researcher-key", "shown_once": True})
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
        check("steward can open researcher provisioning form",
              page.locator("#new-requester-name").count() == 1)
        page.locator("#new-requester-name").fill("New Researcher")
        page.locator("#new-requester-institution").fill("Research Institute")
        page.locator("#issue-researcher-title + p")  # ensure the access section is rendered
        page.get_by_role("button", name="Issue researcher key").click()
        page.get_by_label("New researcher API key").wait_for(timeout=5000)
        check("one-time researcher key is displayed after provisioning",
              page.locator('input[aria-label="New researcher API key"]').input_value()
              == "one-time-issued-researcher-key")
        check("issued researcher key is not persisted to localStorage",
              page.evaluate("localStorage.getItem('gg_who')") is None)

        page.locator("#disconnect-key").click()
        check("disconnect clears active credentials",
              "Disconnected." in page.locator("#auth-status").inner_text())
        check("steward navigation is removed after disconnect",
              page.locator('nav a[href="#/audit"]').count() == 0)
        check("Supabase Auth panel is available in non-demo mode",
              not page.locator("#supabase-auth-panel").is_hidden())

        # Supabase Auth sign-in is mocked; no real account is created and no email is sent.
        page.locator("#supabase-email").fill("researcher@example.org")
        page.locator("#supabase-password").fill("correct-horse-battery")
        page.locator("#supabase-signin").click()
        page.get_by_text("Your organization membership is active", exact=False).wait_for(timeout=5000)
        check("Supabase researcher sign-in obtains verified membership status",
              "Research Institute (researcher)" in page.locator("#who-note").inner_text())
        check("legacy API-key panel hides after Supabase sign-in", page.locator("#auth-panel").is_hidden())
        check("Supabase credentials are not persisted to browser storage",
              page.evaluate("localStorage.getItem('gg_who')") is None)

        page.goto(base + "/#/requests", wait_until="domcontentloaded")
        page.locator("#name").wait_for(state="visible", timeout=5000)
        check("Supabase request form uses supported data levels",
              page.locator("#level").input_value() == "aggregate")
        check("Supabase request form has no synthetic planted-variant field",
              page.locator("#pl").count() == 0)
        page.locator("#name").fill("Test Researcher")
        page.get_by_role("button", name="Send request").click()
        page.get_by_text("Waiting for steward review", exact=False).wait_for(timeout=5000)
        check("Supabase request submission sends organization and researcher identity",
              submitted_request.get("name") == "Test Researcher" and
              submitted_request.get("institution") == "Research Institute" and
              submitted_request.get("data_level") == "aggregate")
        check("Supabase request detail does not claim data release",
              page.get_by_text("No genomic data has been released", exact=False).count() == 1)

        page.goto(base + "/#/sources", wait_until="domcontentloaded")
        page.get_by_text("1000 Genomes Project Phase 3", exact=False).wait_for(timeout=5000)
        check("public source discovery uses Supabase Edge API",
              any(call["path"] == "/sources" for call in edge_calls))
        page.goto(base + "/#/datasets", wait_until="domcontentloaded")
        page.get_by_text("No dataset has been verified yet", exact=False).wait_for(timeout=5000)
        check("empty verified dataset catalogue is shown honestly",
              any(call["path"] == "/datasets" for call in edge_calls))

        # Sign-up without a returned session must explain email verification and membership provisioning.
        page.locator("#supabase-signout").click()
        page.locator("#supabase-email").fill("new-user@example.org")
        page.locator("#supabase-password").fill("correct-horse-battery")
        page.locator("#supabase-full-name").fill("New User")
        page.locator("#supabase-signup").click()
        page.get_by_text("Check your email for the verification link", exact=False).wait_for(timeout=5000)
        check("new account is not treated as authorized before verification and membership", page.locator("#supabase-signout").is_hidden())

        # An authenticated but unprovisioned account must not see a request form.
        page.locator("#supabase-email").fill("pending@example.org")
        page.locator("#supabase-password").fill("correct-horse-battery")
        page.locator("#supabase-signin").click()
        page.get_by_text("not yet authorized for research workflows", exact=False).wait_for(timeout=5000)
        page.goto(base + "/#/requests", wait_until="domcontentloaded")
        page.get_by_text("no active organization membership", exact=False).wait_for(timeout=5000)
        check("unprovisioned Supabase user is blocked from request submission",
              page.locator("#purpose").count() == 0)

        # A reviewer sees only their organization's queue and can record a reasoned decision.
        page.locator("#supabase-signout").click()
        page.locator("#supabase-email").fill("reviewer@example.org")
        page.locator("#supabase-password").fill("correct-horse-battery")
        page.locator("#supabase-signin").click()
        page.get_by_text("Your organization membership is active", exact=False).wait_for(timeout=5000)
        page.goto(base + "/#/requests", wait_until="domcontentloaded")
        page.get_by_text("Test Researcher", exact=False).wait_for(timeout=5000)
        check("reviewer role shows steward queue, not researcher request form",
              page.locator("#purpose").count() == 0 and
              any(call["path"] == "/steward/requests" for call in edge_calls))
        page.goto(base + "/#/request/501", wait_until="domcontentloaded")
        page.locator("textarea").wait_for(state="visible", timeout=5000)
        page.locator("textarea").fill("The research purpose is sufficiently scoped; approval is for review only.")
        page.get_by_role("button", name="Approve for separate release review").click()
        page.get_by_text("No requests yet", exact=False).wait_for(timeout=5000)
        review_call = next((call for call in edge_calls if call["path"] == "/requests/501/review"), {})
        check("steward review sends a reason and preserves the in-memory session",
              review_call.get("body", {}).get("outcome") == "approved" and
              len(review_call.get("body", {}).get("reason", "")) >= 3 and
              page.locator("#supabase-signout").is_visible())
        check("approval does not release data",
              review_state["status"] == "approved_pending_release")

        page.locator("#supabase-signout").click()
        check("Supabase sign-out clears active session",
              "Signed out" in page.locator("#supabase-auth-status").inner_text())
        check("demo evaluation remains unfetched", not eval_calls)
        context.close()
        browser.close()

    print("\\n" + ("NON-DEMO UI SMOKE PASSED" if not FAILURES
                     else f"NON-DEMO UI SMOKE FAILED ({len(FAILURES)} checks)"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
