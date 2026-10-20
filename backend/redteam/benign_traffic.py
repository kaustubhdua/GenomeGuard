"""Benign researcher traffic, used to measure FALSE POSITIVES of the anomaly monitor and the
transform ladder. Each simulated researcher runs one session through the same pipeline the
service uses (consent -> risk/transform ladder -> anomaly monitor) in simulated time.

The archetypes are deliberately the awkward ones, because they look a little like probing:
  population_comparison  same variants queried for each population (near-duplicate variant sets)
  refine_filter          cohort filter tightened step by step (cohorts shrink)
  gene_scan              several disjoint variant windows on one cohort
  single_lookup          one to three unrelated queries
  pipeline_scan          an automation script: 15-30 disjoint windows, one query every 5-15 s.
                         Benign, but fast: expected to trip the rate detector (reported openly)
We made these up from how researchers typically work; they are an assumption, not measured
traffic. Real FP rates must be re-measured on real logs (stated in docs/eval-results.md).
"""

from __future__ import annotations

import math

import numpy as np

from app.core.anomaly import AnomalyConfig, AnomalyMonitor, QueryEvent
from app.core.consent import HEALTH_PURPOSES, ConsentRequest, eligible_cohort
from app.core.dataset import Dataset
from app.core.params import DEFAULT, Params
from app.core.transform import run_ladder

ARCHETYPES = (("single_lookup", 0.30), ("population_comparison", 0.25),
              ("refine_filter", 0.20), ("gene_scan", 0.20), ("pipeline_scan", 0.05))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% interval for a proportion (better than normal near 0 or 1)."""
    if n == 0:
        return float("nan"), float("nan")
    ph = k / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return max(0.0, (c - h) / d), min(1.0, (c + h) / d)


def _plan_queries(ds: Dataset, kind: str, rng: np.random.Generator) -> list[dict]:
    common = np.where(ds.maf >= 0.10)[0]
    rare = np.where((ds.maf > 0) & (ds.maf < 0.01))[0]
    pops = sorted({d.population for d in ds.donors})
    cohorts = sorted({d.cohort_id for d in ds.donors})

    def variants(k: int) -> list[int]:
        v = [int(x) for x in rng.choice(common, k, replace=False)]
        if rng.random() < 0.10 and len(rare):  # a few researchers also ask about rare variants
            v += [int(x) for x in rng.choice(rare, 3, replace=False)]
        return v

    if kind == "single_lookup":
        return [{"variants": variants(int(rng.integers(5, 40))), "filter": {}}
                for _ in range(int(rng.integers(1, 4)))]
    if kind == "population_comparison":
        v = variants(int(rng.integers(15, 40)))
        k = int(rng.integers(2, len(pops) + 1))
        return [{"variants": v, "filter": {"population": pops[i]}} for i in range(k)]
    if kind == "refine_filter":
        v = variants(int(rng.integers(10, 30)))
        pop, coh = str(rng.choice(pops)), str(rng.choice(cohorts))
        return [{"variants": v, "filter": {}}, {"variants": v, "filter": {"cohort_id": coh}},
                {"variants": v, "filter": {"cohort_id": coh, "population": pop}}]
    order = rng.permutation(common)  # gene_scan / pipeline_scan: disjoint windows, same cohort
    w = int(rng.integers(8, 20))
    n_q = int(rng.integers(15, 31)) if kind == "pipeline_scan" else int(rng.integers(4, 9))
    n_q = min(n_q, len(order) // w)
    return [{"variants": [int(x) for x in order[i * w:(i + 1) * w]], "filter": {}}
            for i in range(n_q)]


def run_benign(ds: Dataset, sessions: int = 300, seed: int = 11, p: Params = DEFAULT) -> dict:
    rng = np.random.default_rng(seed)
    kinds, weights = zip(*ARCHETYPES, strict=True)
    diseases = sorted({d.consent["disease"] for d in ds.donors if d.consent.get("disease")})
    per_kind: dict[str, dict] = {k: {"sessions": 0, "flagged": 0, "hard": 0} for k in kinds}
    q_out = {"permit": 0, "permit_with_transform": 0, "deny": 0, "escalate": 0}
    q_total = ladder_blocked = guard_blocked = flagged = hard = 0
    served = 0
    for s in range(sessions):
        kind = str(rng.choice(kinds, p=weights))
        mon = AnomalyMonitor(AnomalyConfig.from_params(p))
        t, spent = 0.0, 0.0
        disease = str(rng.choice(diseases)) if diseases else None
        purpose = str(rng.choice(sorted(HEALTH_PURPOSES)))
        level = "frequency" if rng.random() < 0.8 else "count"
        s_flag = s_hard = False
        for q in _plan_queries(ds, kind, rng):
            if kind == "pipeline_scan":
                t += float(rng.uniform(5.0, 15.0))
            else:  # seconds between queries
                t += max(20.0, float(rng.lognormal(math.log(150.0), 0.8)))
            req = ConsentRequest(purpose, disease, False, level, None, q["filter"])
            elig = eligible_cohort(req, ds.donors)
            if elig.n == 0:
                continue
            ladder = run_ladder(ds, elig.donor_ids, q["variants"], level, p,
                                epsilon_available=max(0.0, p.epsilon_budget - spent),
                                build_release=False, rng=np.random.default_rng(s * 100 + q["variants"][0]))
            a = mon.observe(1, QueryEvent(t, frozenset(q["variants"]), q["filter"],
                                          frozenset(elig.donor_ids), ladder.epsilon_spent))
            if a.blocked and a.action != "freeze":
                outcome = "deny"
                guard_blocked += 1
            elif a.action == "freeze" or a.action == "throttle":
                outcome = "escalate"
            else:
                outcome = ladder.outcome
                if outcome in ("deny", "escalate"):
                    ladder_blocked += 1
                if outcome.startswith("permit"):
                    spent += ladder.epsilon_spent
            q_out[outcome] += 1
            q_total += 1
            served += outcome.startswith("permit")
            s_flag |= a.action != "ok" or a.blocked
            s_hard |= a.blocked or a.action in ("throttle", "freeze")
        per_kind[kind]["sessions"] += 1
        per_kind[kind]["flagged"] += s_flag
        per_kind[kind]["hard"] += s_hard
        flagged += s_flag
        hard += s_hard
    lo_f, hi_f = wilson(flagged, sessions)
    lo_h, hi_h = wilson(hard, sessions)
    lo_l, hi_l = wilson(ladder_blocked, q_total)
    return {
        "sessions": sessions, "queries": q_total, "seed": seed,
        "monitor_flag_rate": round(flagged / sessions, 4),
        "monitor_flag_ci95": [round(lo_f, 4), round(hi_f, 4)],
        "monitor_hard_fp_rate": round(hard / sessions, 4),  # throttled, frozen or guard-blocked
        "monitor_hard_fp_ci95": [round(lo_h, 4), round(hi_h, 4)],
        "ladder_refusal_rate": round(ladder_blocked / max(q_total, 1), 4),  # deny/escalate by ladder
        "ladder_refusal_ci95": [round(lo_l, 4), round(hi_l, 4)],
        "guard_block_rate": round(guard_blocked / max(q_total, 1), 4),
        "query_outcomes": {k: round(v / max(q_total, 1), 4) for k, v in q_out.items()},
        "served_rate": round(served / max(q_total, 1), 4),
        "by_archetype": {k: {"sessions": v["sessions"],
                             "flag_rate": round(v["flagged"] / max(v["sessions"], 1), 4),
                             "hard_fp_rate": round(v["hard"] / max(v["sessions"], 1), 4)}
                         for k, v in per_kind.items()},
    }
