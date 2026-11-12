"""Read-only acceptance checks for the isolated synthetic-only staging deployment."""
from __future__ import annotations

import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

FAILURES: list[str] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    print(f"[{'PASS' if passed else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
    if not passed:
        FAILURES.append(label)


def get_json(base: str, path: str, timeout: int) -> tuple[int, dict]:
    request = Request(base + path, headers={"Accept": "application/json"})
    try:
        response = urlopen(request, timeout=timeout)
    except HTTPError as exc:
        response = exc
    with response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError(f"{path} response exceeded the smoke-test limit")
        content_type = response.headers.get("Content-Type", "unknown")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            reason = getattr(exc, "msg", "response is not valid UTF-8 JSON")
            raise ValueError(
                f"{path} returned non-JSON HTTP {response.status} "
                f"(content-type={content_type}, bytes={len(raw)}): {reason}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(
                f"{path} returned a non-object JSON payload "
                f"(HTTP {response.status}, content-type={content_type})"
            )
        return response.status, payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--expected-commit", default="")
    parser.add_argument("--retries", type=int, default=60)
    parser.add_argument("--retry-delay", type=int, default=15)
    args = parser.parse_args()
    # This script makes outbound requests from CI. The destination is fixed in source;
    # it cannot be redirected to an arbitrary caller-supplied host.
    base = "https://genomeguard-staging-pr122.onrender.com"

    if args.expected_commit:
        deployed = None
        for attempt in range(args.retries):
            try:
                _, health_probe = get_json(base, "/health", args.timeout)
                deployed = (health_probe.get("deployment") or {}).get("git_commit")
                if deployed == args.expected_commit:
                    break
            except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
                pass
            print(f"[WAIT] staging commit {deployed or 'unavailable'}; expected {args.expected_commit} "
                  f"({attempt + 1}/{args.retries})")
            if attempt + 1 < args.retries:
                time.sleep(args.retry_delay)
        check("staging serves the exact pull-request head commit",
              deployed == args.expected_commit, f"deployed={deployed}, expected={args.expected_commit}")

    try:
        status, live = get_json(base, "/health/live", args.timeout)
        check("staging liveness", status == 200 and live.get("status") == "ok",
              f"HTTP {status}")
        status, health = get_json(base, "/health", args.timeout)
        provenance = health.get("provenance") or {}
        check("health responds", status == 200 and health.get("status") == "ok",
              f"HTTP {status}")
        check("PostgreSQL is the active staging store",
              health.get("storage_backend") == "postgresql", str(health.get("storage_backend")))
        check("only synthetic genotypes are loaded",
              health.get("synthetic_data_only") is True and provenance.get("genotypes") == "synthetic")
        check("consent is clearly simulated",
              health.get("consent_simulated") is True and provenance.get("consent") == "simulated")
        check("staging image does not claim to embed the public cohort",
              "synthetic-only cohort" in str(provenance.get("encryption", ""))
              and "public cohort artifact is plaintext" not in str(provenance.get("encryption", "")))
        check("expected synthetic fixture dimensions",
              health.get("donors") == 600 and health.get("variants") == 3000,
              f"donors={health.get('donors')}, variants={health.get('variants')}")
        check("Render commit provenance is present",
              live.get("deployment", {}).get("git_commit") is not None
              and health.get("deployment", {}).get("git_commit") is not None)

        status, readiness = get_json(base, "/health/ready", args.timeout)
        checks = readiness.get("checks") or {}
        check("readiness remains fail-closed for a synthetic demo",
              status == 503 and readiness.get("ready") is False
              and checks.get("demo_mode_disabled") is False,
              f"HTTP {status}")

        status, demo = get_json(base, "/demo/requesters", args.timeout)
        accounts = demo.get("requesters")
        check("public demo endpoint never exposes administrator credentials",
              status == 200 and "admin_key" not in demo
              and isinstance(accounts, list) and len(accounts) >= 1
              and all(bool(item.get("api_key")) for item in accounts))

        status, _ = get_json(base, "/audit", args.timeout)
        check("steward audit route rejects anonymous requests", status == 401,
              f"HTTP {status}")
        status, _ = get_json(base, "/requests", args.timeout)
        check("research request history rejects anonymous requests", status == 401,
              f"HTTP {status}")

        status, audit = get_json(base, "/audit/verify", args.timeout)
        check("public audit integrity verification", status == 200 and audit.get("ok") is True,
              f"HTTP {status}, ok={audit.get('ok')}")
        status, sources = get_json(base, "/catalogue/sources", args.timeout)
        check("public source catalogue is discovery-only",
              status == 200 and sources.get("discovery_only") is True
              and sources.get("source_count", 0) >= 1, f"HTTP {status}")
        status, datasets = get_json(base, "/catalogue/datasets", args.timeout)
        check("unapproved datasets are not listed",
              status == 200 and datasets.get("dataset_count") == 0, f"HTTP {status}")
        status, chromosomes = get_json(base, "/catalogue/chromosomes", args.timeout)
        rows = chromosomes.get("chromosomes") or []
        coverage_statuses = {
            row.get("data_coverage", {}).get("coverage_status") for row in rows
        }
        check("chromosome reference catalogue responds without inventing coverage",
              status == 200 and chromosomes.get("chromosome_count") == 25
              and len(rows) == 25 and coverage_statuses <= {"available", "unavailable"},
              f"HTTP {status}, count={len(rows)}, coverage={chromosomes.get('coverage_available')}")
        if chromosomes.get("coverage_available") is False:
            check("unavailable chromosome coverage is explicitly labelled",
                  coverage_statuses == {"unavailable"})
        else:
            check("empty staging chromosome coverage is not presented as loaded",
                  all(row.get("data_coverage", {}).get("variant_data_loaded") is False for row in rows))
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        check("staging smoke completed", False, f"{type(exc).__name__}: {str(exc)[:240]}")

    print("\n" + ("STAGING SMOKE PASSED" if not FAILURES else
                   f"STAGING SMOKE FAILED ({len(FAILURES)} checks)"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
