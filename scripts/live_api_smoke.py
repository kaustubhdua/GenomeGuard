"""Non-destructive live API acceptance checks for the synthetic demo.

Creates three synthetic research requests (permitted, denied, and held) to exercise
real API paths. It never changes consent, freezes accounts, or tampers with audit history.
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def call(base: str, path: str, method: str = "GET", headers: dict | None = None,
         body: dict | None = None, timeout: float = 20.0) -> tuple[int, dict]:
    request_headers = {"Accept": "application/json", "User-Agent": "GenomeGuard-live-api-smoke/1.0"}
    request_headers.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    req = Request(urljoin(base.rstrip("/") + "/", path.lstrip("/")), data=data,
                  headers=request_headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        return exc.code, payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    base = args.base.rstrip("/")

    try:
        status, health = call(base, "/health", timeout=args.timeout)
        check("health is HTTP 200 and healthy", status == 200 and health.get("status") == "ok")
        check("demo remains synthetic with simulated consent",
              health.get("synthetic_data_only") is True
              and (health.get("provenance") or {}).get("consent") == "simulated")
        check("audit chain initially verifies", health.get("audit_chain_ok") is True)
        check("destructive tamper demo is disabled", health.get("tamper_demo") is False)

        status, demo = call(base, "/demo/requesters", timeout=args.timeout)
        accounts = {r.get("name"): r for r in demo.get("requesters", [])}
        required = ("Dr. Amara Nwosu", "Public Viewer", "Controlled-Access Lab")
        check("demo persona metadata is available without credentials",
              status == 200 and all(name in accounts for name in required)
              and "admin_key" not in demo
              and all("api_key" not in account for account in accounts.values()))
        if status != 200 or not all(name in accounts for name in required):
            raise RuntimeError("demo persona endpoint unavailable; cannot run authenticated acceptance tests")

        def session_for(name: str) -> dict:
            session_status, session = call(
                base, "/demo/session", "POST",
                body={"requester_id": accounts[name]["id"]}, timeout=args.timeout,
            )
            check(f"{name} receives a short-lived demo session",
                  session_status == 200 and bool(session.get("session_token"))
                  and "api_key" not in session)
            return {"X-Demo-Session": session.get("session_token", "")}

        researcher = session_for("Dr. Amara Nwosu")
        anonymous = session_for("Public Viewer")
        controlled = session_for("Controlled-Access Lab")

        status, permit = call(base, "/requests", "POST", researcher, {
            "purpose": "disease_research", "disease": "diabetes", "data_level": "frequency",
            "cohort_filter": {}, "variant_filter": {"min_maf": 0.1, "limit": 20, "include_planted": 2}
        }, args.timeout)
        check("registered researcher receives a transformed permitted decision",
              status == 201 and permit.get("outcome") == "permit_with_transform"
              and permit.get("status") == "released")
        permit_id = permit.get("id")
        safe_blob = json.dumps(permit)
        check("requester response excludes steward-only risk details",
              all(secret_key not in safe_blob for secret_key in
                  ('"min_carriers"', '"relatives_exposed"', '"agent_agrees"')))

        status, denied = call(base, "/requests", "POST", anonymous, {
            "purpose": "disease_research", "disease": "diabetes", "data_level": "frequency",
            "cohort_filter": {}, "variant_filter": {"min_maf": 0.1, "limit": 20}
        }, args.timeout)
        check("anonymous frequency request is denied by tier policy",
              status == 201 and denied.get("outcome") == "deny"
              and "credential_insufficient" in denied.get("reasons", []))

        status, held = call(base, "/requests", "POST", controlled, {
            "purpose": "general_research", "data_level": "record",
            "variant_filter": {"min_maf": 0.2, "limit": 10}
        }, args.timeout)
        check("controlled record-level request is held for human review",
              status == 201 and held.get("outcome") == "escalate"
              and held.get("needs_human") is True and "release" not in held)
        held_id = held.get("id")

        status, _ = call(base, "/requests", timeout=args.timeout)
        check("request listing rejects unauthenticated access", status == 401)
        status, _ = call(base, "/audit", timeout=args.timeout)
        check("audit log rejects unauthenticated access", status == 401)
        status, _ = call(base, "/donor/1", timeout=args.timeout)
        check("requester session cannot impersonate a donor", status == 401)

        if held_id is not None:
            status, _ = call(base, f"/requests/{held_id}", headers=researcher, timeout=args.timeout)
            check("researcher cannot read another account's held request", status == 404)
            status, held_owner = call(base, f"/requests/{held_id}", headers=controlled, timeout=args.timeout)
            check("controlled requester can read its own held decision", status == 200
                  and held_owner.get("outcome") == "escalate")
        if permit_id is not None:
            status, permit_owner = call(base, f"/requests/{permit_id}", headers=researcher, timeout=args.timeout)
            check("researcher can read its own permitted decision", status == 200
                  and permit_owner.get("outcome") == "permit_with_transform")

        status, verification = call(base, "/audit/verify", timeout=args.timeout)
        check("audit verification endpoint succeeds after requests",
              status == 200 and verification.get("ok") is True)
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        check("live API acceptance completed", False, f"{type(exc).__name__}: {str(exc)[:240]}")

    print("\n" + ("LIVE API SMOKE PASSED" if not FAILURES
                     else f"LIVE API SMOKE FAILED ({len(FAILURES)} checks)"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
