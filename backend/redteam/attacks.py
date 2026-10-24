"""Red-team attacks used by `make eval`. Every function is seeded and returns plain numbers.

They run against the real GenomeGuard code (transform ladder, anomaly monitor, service), on the
SYNTHETIC cohort. What they do NOT show is in docs/eval-results.md: synthetic data, simplified
attackers, no real-world linkage data.
"""

from __future__ import annotations

import math
import statistics

import numpy as np

from app.core.anomaly import AnomalyConfig, AnomalyMonitor, QueryEvent
from app.core.dataset import Dataset
from app.core.params import DEFAULT, Params
from app.core.transform import TransformPlan, materialize, run_ladder


# ----------------------------------------------------------------------------- statistics
def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """P(score_member > score_non_member), ties count half (Mann-Whitney U)."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    allv = np.concatenate([pos, neg])
    ranks = np.empty(len(allv))
    order = np.argsort(allv, kind="mergesort")
    sorted_v = allv[order]
    i = 0
    while i < len(sorted_v):  # average ranks over ties
        j = i
        while j + 1 < len(sorted_v) and sorted_v[j + 1] == sorted_v[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg)))


def mean_ci(xs: list[float]) -> tuple[float, float]:
    """Mean and 95% half-width (normal approximation across independent trials)."""
    if len(xs) < 2:
        return (xs[0] if xs else float("nan")), float("nan")
    return statistics.fmean(xs), 1.96 * statistics.stdev(xs) / math.sqrt(len(xs))


# ----------------------------------------------------------------------------- 1. differencing
def differencing_attack(ds: Dataset, trials: int = 40, seed: int = 1, n: int = 60,
                        n_vars: int = 10, p: Params = DEFAULT) -> dict:
    """Tracker attack: query A = cohort of n donors containing the target, query B = the same
    cohort without the target; subtracting the two answers reveals the target's genotype.

    configs: no protection | DP noise only (eps=1) | ladder only | ladder + differencing guard.
    Success = share of the target's genotypes (0/1/2 per variant) recovered exactly. `baseline`
    is the accuracy of just guessing the most likely genotype from allele frequency."""
    rng = np.random.default_rng(seed)
    G = ds.genotypes
    common = np.where(ds.maf >= 0.15)[0]
    res = {k: [] for k in ("none", "dp_only", "ladder_only", "ladder_plus_guard", "baseline")}
    guard_blocked = 0
    for _ in range(trials):
        cohort = rng.choice(ds.n_donors, n, replace=False)
        target = int(cohort[0])
        a_ids = [int(i) + 1 for i in cohort]
        b_ids = a_ids[1:]
        v = rng.choice(common, n_vars, replace=False)
        truth = G[target, v].astype(int)
        base = np.array([int(np.argmax([(1 - f) ** 2, 2 * f * (1 - f), f**2]))
                         for f in ds.alt_freq[v]])
        res["baseline"].append(float((base == truth).mean()))

        def counts(ids, plan):
            out = materialize(G, ids, plan, rng)
            return np.array(out["values"], float) * 2.0 * len(ids)

        def recover(ca, cb):
            return np.clip(np.rint(ca - cb), 0, 2).astype(int)

        plain = TransformPlan("frequency", tuple(int(x) for x in v))
        res["none"].append(float((recover(counts(a_ids, plain), counts(b_ids, plain)) == truth).mean()))
        noisy = TransformPlan("frequency", tuple(int(x) for x in v), epsilon=1.0)
        res["dp_only"].append(float((recover(counts(a_ids, noisy), counts(b_ids, noisy)) == truth).mean()))

        # ladder only: whatever protection it decides for each query, applied independently
        plans = []
        for ids in (a_ids, b_ids):
            r = run_ladder(ds, ids, [int(x) for x in v], "frequency", p, build_release=False, rng=rng)
            plans.append(r.plan if r.outcome.startswith("permit") else None)
        if None in plans:
            res["ladder_only"].append(float((base == truth).mean()))
        else:
            res["ladder_only"].append(float((recover(counts(a_ids, plans[0]), counts(b_ids, plans[1]))
                                             == truth).mean()))

        # ladder + guard: the second query is blocked, so the attacker only has query A
        mon = AnomalyMonitor(AnomalyConfig.from_params(p))
        ea = QueryEvent(0.0, frozenset(int(x) for x in v), {}, frozenset(a_ids))
        eb = QueryEvent(1.0, frozenset(int(x) for x in v), {}, frozenset(b_ids))
        mon.observe(1, ea)
        blocked = mon.observe(1, eb).blocked
        guard_blocked += int(blocked)
        res["ladder_plus_guard"].append(res["ladder_only"][-1] if not blocked
                                        else float((base == truth).mean()))
    out = {k: mean_ci(vals) for k, vals in res.items()}
    return {"trials": trials, "n": n, "variants": n_vars,
            "accuracy": {k: {"mean": round(m, 4), "ci95": round(c, 4)} for k, (m, c) in out.items()},
            "guard_block_rate": round(guard_blocked / trials, 4)}


# ----------------------------------------------------------------------------- 2. membership
def _release_freqs(ds: Dataset, members: list[int], vidx: np.ndarray, bin_w, eps, rng) -> np.ndarray:
    plan = TransformPlan("frequency", tuple(int(x) for x in vidx), bin_w, eps)
    return np.array(materialize(ds.genotypes, members, plan, rng)["values"], float)


def membership_inference(ds: Dataset, n: int, V: int, bin_w: float | None, eps: float | None,
                         trials: int = 20, seed: int = 2, n_test: int = 40) -> dict:
    """Sankararaman-style likelihood-ratio test on released allele frequencies. The attacker has a
    target's genotype and a public reference panel (200 non-members) and asks 'is this person in
    the released cohort?'. AUC 0.5 = no information, 1.0 = perfect. Also reports utility: Pearson
    correlation and mean absolute error between released and true frequencies."""
    rng = np.random.default_rng(seed)
    G = ds.genotypes.astype(float)
    pool = np.where(ds.maf >= 0.02)[0]
    aucs, corrs, maes = [], [], []
    for _ in range(trials):
        perm = rng.permutation(ds.n_donors)
        S, R = perm[:n], perm[n:n + 200]
        nonmem = perm[n + 200:n + 200 + n_test]
        mem = S[:n_test]
        vidx = rng.choice(pool, min(V, len(pool)), replace=False)
        f_true = G[S][:, vidx].sum(0) / (2.0 * n)
        f_rel = _release_freqs(ds, [int(i) + 1 for i in S], vidx, bin_w, eps, rng)
        f = np.clip(f_rel, 0.005, 0.995)
        p = np.clip(G[R][:, vidx].mean(0) / 2.0, 0.005, 0.995)
        w1, w0 = np.log(f / p), np.log((1 - f) / (1 - p))

        def score(rows, vidx=vidx, w1=w1, w0=w0):
            x = G[rows][:, vidx] / 2.0
            return x @ w1 + (1 - x) @ w0

        aucs.append(auc(score(mem), score(nonmem)))
        corrs.append(float(np.corrcoef(f_rel, f_true)[0, 1]) if f_rel.std() > 0 else 0.0)
        maes.append(float(np.abs(f_rel - f_true).mean()))
    a, ac = mean_ci(aucs)
    return {"n": n, "V": V, "bin_width": bin_w, "epsilon": eps,
            "auc": round(a, 4), "auc_ci95": round(ac, 4),
            "corr": round(statistics.fmean(corrs), 4), "mae": round(statistics.fmean(maes), 4),
            "z_proxy": round(math.sqrt(V / n), 3)}


# ----------------------------------------------------------------------------- 3. triangulation
def triangulation_attack(gap_s: float, trials: int = 60, seed: int = 3, p: Params = DEFAULT,
                         monitor_on: bool = True, max_queries: int = 40) -> dict:
    """Scripted attacker shrinking a cohort toward one person with nested cohorts, changing the
    variant set slightly each time. 'Answered' = size >= k_min, not blocked, not held/frozen.
    Reports detection rate, queries until the first non-ok action / freeze, and the SMALLEST
    cohort the attacker ever got an answer for (k_min is the floor even without a monitor)."""
    rng = np.random.default_rng(seed)
    detected, until_flag, until_freeze, smallest = 0, [], [], []
    for _ in range(trials):
        mon = AnomalyMonitor(AnomalyConfig.from_params(p))
        size = int(rng.integers(300, 500))
        ids = set(range(1, size + 1))
        variants = set(int(x) for x in rng.choice(3000, 25, replace=False))
        factor = float(rng.uniform(0.6, 0.85))
        t, min_ans, flagged, frozen_at = 0.0, size, None, None
        for q in range(1, max_queries + 1):
            size = max(1, int(len(ids) * factor)) if q > 1 else len(ids)
            if q > 1:
                ids = set(list(ids)[:size])
            variants = set(variants)  # tiny changes: swap one variant
            variants.discard(next(iter(variants)))
            variants.add(int(rng.integers(3000)))
            blocked = False
            if monitor_on:
                a = mon.observe(1, QueryEvent(t, frozenset(variants), {}, frozenset(ids)))
                if a.action != "ok" and flagged is None:
                    flagged = q
                if a.action == "freeze" and frozen_at is None:
                    frozen_at = q
                blocked = a.blocked or a.action in ("throttle", "freeze")
            if len(ids) >= p.k_min and not blocked:
                min_ans = min(min_ans, len(ids))
            if blocked and monitor_on and frozen_at is not None:
                break
            t += gap_s
        detected += int(frozen_at is not None)
        if flagged:
            until_flag.append(flagged)
        if frozen_at:
            until_freeze.append(frozen_at)
        smallest.append(min_ans)
    return {"gap_s": gap_s, "monitor_on": monitor_on, "trials": trials,
            "frozen_rate": round(detected / trials, 4),
            "median_queries_until_flag": statistics.median(until_flag) if until_flag else None,
            "median_queries_until_freeze": statistics.median(until_freeze) if until_freeze else None,
            "median_smallest_answered_cohort": statistics.median(smallest)}


# ----------------------------------------------------------------------------- 4. beacon flip
def beacon_update_flip(ds: Dataset, update_size: int, mode: str, trials: int = 30, seed: int = 4,
                       base_size: int = 300, p: Params = DEFAULT) -> dict:
    """Simplified replication of the update-flip idea (arXiv:2001.08852). A beacon answers
    'does any donor carry the alt allele at v?'. The attacker snapshots it before and after
    `update_size` new donors are added and treats variants that flipped no -> yes (boolean) or
    whose count rose (count) as belonging to the victim, a random new donor. We do NOT replicate
    the paper's genome clustering, so with batches the precision here is a lower bound.

    mode: 'boolean' | 'count' | 'genomeguard' (boolean + variants with MAF < floor unanswerable +
    updates batched by the caller). Metrics vs the victim's true alt-carrying positions:
    precision = flagged positions the victim really carries; recall = victim's carried positions
    that were flagged."""
    rng = np.random.default_rng(seed)
    G = ds.genotypes
    base_size = min(base_size, ds.n_donors - update_size)  # small cohorts: keep donors to add
    prec, rec, rec_rare, flips = [], [], [], []
    for _ in range(trials):
        perm = rng.permutation(ds.n_donors)
        base, new = perm[:base_size], perm[base_size:base_size + update_size]
        victim = int(new[0])
        before, after = G[base].sum(0), G[np.concatenate([base, new])].sum(0)
        if mode == "count":
            flagged = after > before
        else:
            flagged = (before == 0) & (after > 0)
            if mode == "genomeguard":
                cohort_maf = after / (2.0 * (base_size + update_size))
                flagged &= cohort_maf >= p.maf_floor  # rare variants are not answerable
        carried = G[victim] > 0
        rare_carried = carried & (after / (2.0 * (base_size + update_size)) < p.maf_floor)
        flips.append(int(flagged.sum()))
        if rare_carried.sum():
            rec_rare.append(float((flagged & rare_carried).sum() / rare_carried.sum()))
        tp = int((flagged & carried).sum())
        prec.append(tp / flagged.sum() if flagged.sum() else float("nan"))
        rec.append(tp / carried.sum() if carried.sum() else float("nan"))
    clean_p = [x for x in prec if not math.isnan(x)]
    return {"mode": mode, "update_size": update_size, "trials": trials,
            "precision": round(statistics.fmean(clean_p), 4) if clean_p else None,
            "recall": round(statistics.fmean(rec), 4),
            "recall_of_rare_positions": round(statistics.fmean(rec_rare), 4) if rec_rare else None,
            "mean_flipped_positions": round(statistics.fmean(flips), 2),
            "no_flips_rate": round(1 - len(clean_p) / trials, 4)}
