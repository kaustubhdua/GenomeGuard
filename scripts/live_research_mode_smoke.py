"""Read-only acceptance checks for the non-demo public-data research deployment."""
from __future__ import annotations

import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def call(base: str, path: str, method: str = "GET", body: dict | None = None,
         timeout: float = 20.0) -> tuple[int, dict]:
    headers = {"Accept": "application/json", "User-Agent": "GenomeGuard-live-research-smoke/1.0"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(base.rstrip("/") + "/" + path.lstrip("/"), data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {}
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__, "message": str(exc)[:200]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--retries", type=int, default=24)
    parser.add_argument("--retry-delay", type=float, default=15.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    base = args.base.rstrip("/")

    # Wait for the hosting provider to finish its auto-deploy and wake a free instance.
    health_status, health = 0, {}
    for attempt in range(max(1, args.retries)):
        health_status, health = call(base, "/health", timeout=args.timeout)
        if (health_status == 200 and health.get("status") == "ok"
                and health.get("demo_mode") is False
                and (health.get("provenance") or {}).get("consent") == "source_policy"):
            break
        if attempt + 1 < args.retries:
            time.sleep(args.retry_delay)
    check("public application starts and health is HTTP 200",
          health_status == 200 and health.get("status") == "ok",
          f"HTTP {health_status}: {health}")

    if health_status != 200 or health.get("status") != "ok":
        print("\nLIVE RESEARCH MODE SMOKE FAILED (application unavailable)")
        return 1

    provenance = health.get("provenance") or {}
    check("demo mode is disabled", health.get("demo_mode") is False)
    check("genotypes are real public-source data",
          provenance.get("genotypes") == "real_vcf" and health.get("synthetic_data_only") is False,
          str(provenance.get("genotypes_label")))
    check("consent is not simulated",
          health.get("consent_simulated") is False and provenance.get("consent") == "source_policy")
    policy = provenance.get("consent_policy") or {}
    check("source policy is disclosed as dataset-level, not individual consent",
          policy.get("not_individual_consent") is True
          and policy.get("scope") == "dataset"
          and policy.get("review_status") == "source_documented_not_legal_review",
          str(policy))
    check("source dataset-policy file is hashed",
          len(str(provenance.get("consent_policy_source_sha256", ""))) == 64)
    check("dataset policy is not counted as participant consent",
          int(provenance.get("consent_records_matched") or 0) == 0
          and provenance.get("consent_records_sha256") is None)
    check("dataset policy scope matches loaded cohort",
          int(provenance.get("dataset_policy_samples_scoped") or 0) == int(health.get("donors") or -1))
    check("source genotype file is hashed", len(str(provenance.get("source_vcf_sha256", ""))) == 64)
    check("real cohort has usable variants",
          int(health.get("variants") or 0) > 0 and int(health.get("donors") or 0) > 0)

    status, ready = call(base, "/health/ready", timeout=args.timeout)
    check("production readiness fails closed while infrastructure gaps remain",
          status == 503 and ready.get("ready") is False
          and ready.get("checks", {}).get("durable_storage_verified") is False
          and ready.get("checks", {}).get("external_audit_anchor_verified") is False
          and ready.get("checks", {}).get("institutional_identity_provider_verified") is False,
          f"HTTP {status}: {ready}")

    for path in ("/demo/requesters", "/demo/donors", "/federated/demo", "/federated/he",
                 "/eval/results", "/donor/1"):
        status, _ = call(base, path, timeout=args.timeout)
        check(f"synthetic/demo-only endpoint disabled: {path}", status == 404, f"HTTP {status}")
    for path, method, body in (
        ("/admin/tamper/1", "POST", {}),
        ("/admin/untamper", "POST", {}),
        ("/requests", "POST", {"purpose": "general_research", "data_level": "frequency"}),
        ("/requests", "GET", None),
        ("/audit", "GET", None),
        ("/admin/requesters", "POST", {"name": "unauthorized smoke", "institution": "test"}),
    ):
        status, _ = call(base, path, method, body, timeout=args.timeout)
        check(f"unauthenticated/disabled write is rejected: {method} {path}",
              status == (404 if path.startswith("/admin/tamper") or path == "/admin/untamper" else 401),
              f"HTTP {status}")

    status, docs = call(base, "/openapi.json", timeout=args.timeout)
    endpoints = {item.get("path") for item in docs.get("endpoints", [])}
    check("API route catalog is available", status == 200 and bool(endpoints))
    check("API catalog omits demo-only endpoints",
          not any(path and (path.startswith(("/demo/", "/donor/", "/federated/"))
                            or path in {"/eval/results", "/admin/untamper"}
                            or path.startswith("/admin/tamper/")) for path in endpoints))

    print("\n" + ("LIVE RESEARCH MODE SMOKE PASSED" if not FAILURES
                   else f"LIVE RESEARCH MODE SMOKE FAILED ({len(FAILURES)} checks)"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
