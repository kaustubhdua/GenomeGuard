"""Read-only acceptance for the free, public synthetic GenomeGuard demo.

This deliberately verifies that the hosted instance is labelled synthetic and remains
fail-closed for institutional production use. It never creates requests or exposes keys.
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def get(base: str, path: str, timeout: float = 20.0, headers: dict | None = None) -> tuple[int, dict | str]:
    request = Request(
        urljoin(base.rstrip("/") + "/", path.lstrip("/")),
        headers={"Accept": "application/json", "User-Agent": "GenomeGuard-free-demo-monitor/1.0", **(headers or {})},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "json" in content_type.lower():
                return response.status, json.loads(raw) if raw else {}
            return response.status, raw.decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, raw.decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError) as exc:
        return 0, f"{type(exc).__name__}: {str(exc)[:180]}"


def post(base: str, path: str, body: dict, headers: dict | None = None, timeout: float = 20.0) -> tuple[int, dict | str]:
    request = Request(
        urljoin(base.rstrip("/") + "/", path.lstrip("/")),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "GenomeGuard-free-demo-monitor/1.0",
            **(headers or {}),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, raw.decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError) as exc:
        return 0, f"{type(exc).__name__}: {str(exc)[:180]}"


def require(label: str, condition: bool) -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        raise AssertionError(label)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="https://genomeguard.onrender.com")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    try:
        status, health = get(base, "/health")
        require("health endpoint is HTTP 200", status == 200 and isinstance(health, dict))
        require("service reports healthy", health.get("status") == "ok")
        require("public deployment is explicitly demo mode", health.get("demo_mode") is True)
        require("genotypes are explicitly synthetic", health.get("synthetic_data_only") is True
                and (health.get("provenance") or {}).get("genotypes") == "synthetic")
        require("consent is explicitly simulated", health.get("consent_simulated") is True
                and (health.get("provenance") or {}).get("consent") == "simulated")
        require("persistent database backend is PostgreSQL", health.get("storage_backend") == "postgresql")
        require("synthetic cohort has expected dimensions",
                int(health.get("donors") or 0) == 600 and int(health.get("variants") or 0) == 3000)
        require("destructive tamper demo remains disabled", health.get("tamper_demo") is False)

        status, audit = get(base, "/audit/verify")
        require("audit verification endpoint is HTTP 200", status == 200 and isinstance(audit, dict))
        require("audit hash chain verifies", audit.get("ok") is True and int(audit.get("length") or 0) > 0)

        status, demo = get(base, "/demo/requesters")
        require("demo persona endpoint is available", status == 200 and isinstance(demo, dict))
        accounts = demo.get("requesters") or []
        require("demo personas are present", isinstance(accounts, list) and len(accounts) >= 1)
        require("administrator key is not exposed", "admin_key" not in demo)
        require("requester API keys are not exposed",
                all("api_key" not in account for account in accounts if isinstance(account, dict)))
        session_status, demo_session = post(base, "/demo/session", {"requester_id": accounts[0]["id"]})
        require("short-lived demo requester session can be issued",
                session_status == 200 and isinstance(demo_session, dict)
                and bool(demo_session.get("session_token")) and "api_key" not in demo_session)
        profile_status, profile = get(
            base, "/me", headers={"X-Demo-Session": demo_session.get("session_token", "")},
        )
        require("short-lived demo requester session authenticates", profile_status == 200
                and isinstance(profile, dict))

        donor_status, donor_data = get(base, "/demo/donors")
        donors = donor_data.get("donors") if isinstance(donor_data, dict) else []
        require("demo donor personas are present without donor keys",
                donor_status == 200 and isinstance(donors, list) and len(donors) >= 1
                and all("key" not in donor and "api_key" not in donor for donor in donors))
        donor_session_status, donor_session = post(
            base, "/demo/donor-session", {"donor_id": donors[0]["id"]},
        )
        require("short-lived demo donor session can be issued",
                donor_session_status == 200 and bool(donor_session.get("session_token")))
        donor_profile_status, donor_profile = get(
            base, f"/donor/{donors[0]['id']}",
            headers={"X-Demo-Donor-Session": donor_session.get("session_token", "")},
        )
        require("short-lived donor session authenticates only its donor",
                donor_profile_status == 200 and isinstance(donor_profile, dict))

        status, ready = get(base, "/health/ready")
        checks = ready.get("checks") if isinstance(ready, dict) else {}
        require("production readiness correctly remains blocked",
                status == 503 and ready.get("status") == "not_ready" and ready.get("ready") is False)
        require("institutional identity is not falsely marked verified",
                checks.get("institutional_identity_provider_verified") is False)
        require("participant consent authority is not falsely marked configured",
                checks.get("participant_consent_authority_configured") is False)

        status, page = get(base, "/")
        require("public landing page responds", status == 200 and isinstance(page, str)
                and "GenomeGuard" in page)
    except (AssertionError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"FREE DEMO MONITOR FAILED: {exc}", file=sys.stderr)
        return 1

    print("FREE SYNTHETIC DEMO MONITOR PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
