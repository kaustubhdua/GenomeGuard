"""Read-only acceptance smoke test for a deployed GenomeGuard synthetic demo.

Usage:
    python scripts/deploy_smoke.py --base https://your-service.onrender.com

This intentionally does not submit requests, mutate consent, freeze accounts, or print demo keys.
It is a deployment sanity check, not a security audit or proof of persistence.
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def get(base: str, path: str, timeout: float) -> tuple[int, bytes, str]:
    url = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    request = Request(url, headers={"User-Agent": "GenomeGuard-deploy-smoke/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return response.status, response.read(), response.headers.get("Content-Type", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Public base URL, e.g. https://service.onrender.com")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    parsed = urlparse(args.base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        parser.error("--base must be an absolute http:// or https:// URL")
    base = args.base.rstrip("/")

    try:
        status, html, content_type = get(base, "/", args.timeout)
        text = html.decode("utf-8", errors="replace")
        check("landing page responds", status == 200 and "text/html" in content_type.lower())
        check("landing page identifies GenomeGuard", "GenomeGuard" in text and 'id="view"' in text)

        for asset in ("/static/src/style.css", "/static/src/main.js"):
            status, body, _ = get(base, asset, args.timeout)
            check(f"static asset {asset}", status == 200 and len(body) > 100)

        status, body, content_type = get(base, "/health", args.timeout)
        health = json.loads(body)
        check("health endpoint responds", status == 200 and "json" in content_type.lower())
        check("service reports healthy", health.get("status") == "ok")
        check("audit chain verifies", health.get("audit_chain_ok") is True)
        check("demo mode enabled for public smoke test", health.get("demo_mode") is True)
        check("genotypes are synthetic", health.get("synthetic_data_only") is True
              and (health.get("provenance") or {}).get("genotypes") == "synthetic")
        check("consent records are labelled simulated",
              (health.get("provenance") or {}).get("consent") == "simulated")

        status, body, _ = get(base, "/demo/requesters", args.timeout)
        demo = json.loads(body)
        accounts = demo.get("requesters")
        check("demo account list available without printing secrets",
              status == 200 and isinstance(accounts, list) and len(accounts) >= 1
              and bool(demo.get("admin_key")) and all(bool(a.get("api_key")) for a in accounts))

        status, body, content_type = get(base, "/openapi.json", args.timeout)
        spec = json.loads(body)
        paths = spec.get("endpoints", [])
        route_names = {f"{item.get('method')} {item.get('path')}" for item in paths}
        check("API documentation responds", status == 200 and "json" in content_type.lower())
        check("core routes are documented",
              {"GET /health", "POST /requests", "GET /audit/verify"} <= route_names)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        check("deployment smoke test completed", False,
              f"{type(exc).__name__}: {str(exc)[:240]}")

    print("\n" + ("DEPLOYMENT SMOKE PASSED" if not FAILURES else
                   f"DEPLOYMENT SMOKE FAILED ({len(FAILURES)} checks)"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
