#!/usr/bin/env python3
"""Guard the boundary between deterministic PR CI and live upstream-provider checks.

This is a static workflow-contract test. It never makes network requests.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
LIVE = ROOT / ".github" / "workflows" / "research-provider-live.yml"
PROVIDER_SCRIPTS = (
    "pubmed_provider_smoke.py",
    "open_targets_provider_smoke.py",
    "clinvar_provider_smoke.py",
    "gwas_catalog_provider_smoke.py",
    "ontology_provider_smoke.py",
    "research_provider_smoke.py",
    "ensembl_provider_smoke.py",
    "uniprot_provider_smoke.py",
)


def main() -> int:
    errors: list[str] = []
    for path in (CI, LIVE):
        if not path.is_file():
            errors.append(f"missing workflow: {path.relative_to(ROOT)}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    ci_text = CI.read_text(encoding="utf-8")
    live_text = LIVE.read_text(encoding="utf-8")

    for filename in PROVIDER_SCRIPTS:
        if filename in ci_text:
            errors.append(f"{filename} must not run in deterministic ci.yml")
        if filename not in live_text:
            errors.append(f"{filename} must remain in research-provider-live.yml")

    if "workflow_dispatch:" not in live_text:
        errors.append("live provider acceptance must support explicit manual dispatch")
    if "schedule:" not in live_text:
        errors.append("live provider acceptance must retain scheduled monitoring")
    if "on:" not in live_text:
        errors.append("live provider workflow is missing its trigger declaration")

    if errors:
        print("CI provider-isolation contract failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "CI provider-isolation contract passed: eight live provider smoke scripts "
        "are scheduled/manual only and absent from deterministic backend CI."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
