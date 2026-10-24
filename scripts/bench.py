"""`make bench`: measure what this implementation actually does, on the machine you run it on.

    PYTHONPATH=backend python scripts/bench.py [--donors 600] [--variants 3000] [--requests 300]
                                               [--write docs/bench-results.json]

Measures (all single process, SQLite on a temporary file, no network):
  1. submit() latency and throughput: the full pipeline (consent, risk, transform ladder,
     anomaly monitor, audit writes, four to five agent notes via the deterministic templates)
  2. audit-chain verification time as the log grows (it is O(n): the cost of a full re-check)
  3. audit append throughput
  4. memory held by the in-memory genotype matrix for this cohort size

Numbers depend on the hardware, so the output records the CPU count and Python version. Quote
them with that context, and re-run on your own machine before putting any figure on a slide.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="GG_MASTER_KEY")

from app.config import Settings  # noqa: E402
from app.service import bootstrap  # noqa: E402

PURPOSES = ["disease_research", "general_research", "population_genetics", "health_research"]
POPS = [None, "POP_A", "POP_B", "POP_C"]
DISEASES = ["diabetes", "cancer", "cardiovascular", None]


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def bench_submit(svc, n_requests: int) -> dict:
    """Round-robin over many accounts with simulated time spread out, so the anomaly monitor
    sees ordinary traffic and the numbers are for the normal path, not for frozen accounts."""
    reqs = [svc.authenticate(f"bench-{i}") for i in range(40)]
    for i, r in enumerate(reqs):
        if r is None:
            svc.create_requester(f"Bench {i}", "researcher", "registered", "Bench Lab",
                                 f"bench-{i}")
    reqs = [svc.authenticate(f"bench-{i}") for i in range(40)]
    lat: list[float] = []
    outcomes: dict[str, int] = {}
    t_all = time.perf_counter()
    for i in range(n_requests):
        body = {"purpose": PURPOSES[i % 4], "disease": DISEASES[i % 4],
                "data_level": "frequency", "is_commercial": False,
                "cohort_filter": {"population": POPS[i % 4]} if POPS[i % 4] else {},
                "variant_filter": {"min_maf": 0.05 + 0.01 * (i % 7), "limit": 15 + (i % 10),
                                   "include_planted": i % 2}}
        t0 = time.perf_counter()
        try:
            d = svc.submit(reqs[i % 40], body, now=1_000_000.0 + 900.0 * (i // 40) + i % 40)
            o = d["outcome"]
        except Exception as e:  # e.g. an account frozen by the monitor
            o = getattr(e, "code", "error")
        lat.append((time.perf_counter() - t0) * 1000)
        outcomes[o] = outcomes.get(o, 0) + 1
    wall = time.perf_counter() - t_all
    return {"requests": n_requests, "wall_s": round(wall, 2),
            "throughput_rps": round(n_requests / wall, 1),
            "latency_ms": {"p50": round(statistics.median(lat), 1), "p95": round(pct(lat, .95), 1),
                           "p99": round(pct(lat, .99), 1), "max": round(max(lat), 1)},
            "outcomes": outcomes}


def bench_audit(svc, sizes: list[int]) -> dict:
    rows = []
    have = svc.audit.verify()["length"]
    t0 = time.perf_counter()
    added = 0
    for target in sizes:
        while have + added < target:
            svc.audit.append("bench", "bench.event", {"i": have + added})
            added += 1
        t_v = time.perf_counter()
        v = svc.audit.verify()
        rows.append({"entries": v["length"], "verify_ms": round((time.perf_counter() - t_v) * 1000, 1),
                     "ok": v["ok"]})
    append_s = time.perf_counter() - t0
    # append time includes the verify calls above; measure append alone separately
    t1 = time.perf_counter()
    for i in range(500):
        svc.audit.append("bench", "bench.event", {"i": i})
    per_append_ms = (time.perf_counter() - t1) * 1000 / 500
    return {"verify": rows, "append_ms_each": round(per_append_ms, 2),
            "append_per_s": round(1000 / per_append_ms), "setup_s": round(append_s, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--donors", type=int, default=600)
    ap.add_argument("--variants", type=int, default=3000)
    ap.add_argument("--requests", type=int, default=300)
    ap.add_argument("--audit-sizes", default="1000,5000,20000")
    ap.add_argument("--write")
    a = ap.parse_args()

    with tempfile.TemporaryDirectory() as d:
        s = Settings()
        s.db_path = str(Path(d) / "bench.sqlite3")
        s.n_donors, s.n_variants = a.donors, a.variants
        s.n_families = max(10, a.donors // 5)
        t0 = time.perf_counter()
        svc = bootstrap(s)
        boot_s = time.perf_counter() - t0
        out = {
            "machine": {"cpus": os.cpu_count(), "python": platform.python_version(),
                        "platform": platform.platform()},
            "cohort": {"donors": svc.ds.n_donors, "variants": svc.ds.n_variants,
                       "genotype_matrix_mb": round(svc.ds.genotypes.nbytes / 1e6, 2)},
            "bootstrap_s": round(boot_s, 2),
            "submit": bench_submit(svc, a.requests),
            "audit": bench_audit(svc, [int(x) for x in a.audit_sizes.split(",")]),
        }
    print(json.dumps(out, indent=2))
    if a.write:
        Path(a.write).write_text(json.dumps(out, indent=2) + "\n")
        print(f"wrote {a.write}", file=sys.stderr)


if __name__ == "__main__":
    main()
