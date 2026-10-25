"""Transformation ladder + epsilon ledger (section 7.4). Pure numpy.

The ladder re-runs the risk estimator after every step and STOPS at the first step that makes the
band "low". If the ladder is exhausted:  band "high" -> escalate to a human (never auto-release);
band "medium" -> release with what was applied.

  1 drop_rare_variants        drop variants with MAF below the floor
  2 downgrade_to_count        record -> count  (a record-level request never auto-releases rows)
  3 generalise_bins           round frequencies / counts into bins of `bin_width`
  3b limit_variants           only if still risky and > max_variants_noised variants: keep the first
                              N requested (noise grows linearly with #variants, so release few)
  4 laplace_noise             Laplace noise on allele counts, scale = sensitivity * m / epsilon
  5 downgrade_to_boolean      last resort: frequencies/counts -> yes/no (loses the most utility)

Deviation from the written spec, on purpose: spec lists "downgrade level" before generalising and
noising. Downgrading a frequency request to boolean destroys most of its utility, so here the
boolean downgrade is the LAST automatic step; only record -> count happens early (individual
rows must never leave without a human).

Differential-privacy notes (stated plainly):
  * Noise is added to RAW counts and binning is applied afterwards as post-processing, which is
    the order that keeps the guarantee valid.
  * One donor changes every released count by up to 2, so the L1 sensitivity of m counts is 2m and
    the Laplace scale is 2m / epsilon. Noise therefore grows with the number of variants released
    (the lesson of the DP-for-GWAS literature): release few statistics.
  * Accounting is simple sequential composition against a per-requester, per-dataset budget.
    It is NOT a formal DP accountant.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from app.core.dataset import Dataset
from app.core.params import DEFAULT, Params
from app.core.risk import Protections, estimate

LEVELS = ("boolean", "count", "frequency", "record")
SENSITIVITY = 2.0  # one donor changes a diploid allele count by at most 2


class EpsilonLedger:
    """In-memory budget ledger. The database-backed version (epsilon_ledger table) wraps the same
    three methods in step 7."""

    def __init__(self, total: float = 1.0):
        self.total = total
        self._spent: dict[tuple[int, str], float] = {}

    def spent(self, requester_id: int, dataset_id: str) -> float:
        return self._spent.get((requester_id, dataset_id), 0.0)

    def remaining(self, requester_id: int, dataset_id: str) -> float:
        return max(0.0, self.total - self.spent(requester_id, dataset_id))

    def charge(self, requester_id: int, dataset_id: str, epsilon: float) -> float:
        if epsilon < 0 or epsilon > self.remaining(requester_id, dataset_id) + 1e-12:
            raise ValueError("epsilon budget exceeded")
        key = (requester_id, dataset_id)
        self._spent[key] = self.spent(requester_id, dataset_id) + epsilon
        return self.remaining(requester_id, dataset_id)


@dataclass(frozen=True)
class TransformPlan:
    level: str
    variant_idx: tuple[int, ...]
    bin_width: float | None = None
    epsilon: float | None = None  # total epsilon spent on THIS release (split across variants)

    @property
    def noise_scale(self) -> float | None:
        if not self.epsilon:
            return None
        return SENSITIVITY * len(self.variant_idx) / self.epsilon


@dataclass
class TransformResult:
    outcome: str  # permit | permit_with_transform | escalate | deny
    plan: TransformPlan
    steps: list[dict] = field(default_factory=list)
    risk_before: dict = field(default_factory=dict)
    risk_after: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    release: dict | None = None

    @property
    def epsilon_spent(self) -> float:
        return self.plan.epsilon or 0.0 if self.outcome.startswith("permit") else 0.0

    def to_json(self) -> dict:
        return {
            "outcome": self.outcome,
            "steps": self.steps,
            "final": {"level": self.plan.level, "n_variants": len(self.plan.variant_idx),
                      "bin_width": self.plan.bin_width, "epsilon": self.plan.epsilon,
                      "noise_scale": self.plan.noise_scale},
            "risk_before": _brief(self.risk_before),
            "risk_after": _brief(self.risk_after),
            "reasons": self.reasons,
        }


def _brief(r: dict) -> dict:
    keys = ("n", "level", "n_variants", "band", "band_reasons", "uniqueness_rate", "info_bits_mean",
            "rare_variants", "rare_few_carriers", "rare_hidden", "min_carriers",
            "membership_signal")
    out = {k: r.get(k) for k in keys}
    out["relatives_exposed_total"] = (r.get("relatives_exposed") or {}).get("total")
    return out


def materialize(
    genotypes: np.ndarray, donor_ids: list[int], plan: TransformPlan, rng: np.random.Generator
) -> dict:
    """Produce the actual released numbers: raw -> noise -> bin -> level conversion."""
    rows = np.asarray(donor_ids, dtype=int) - 1
    cols = np.asarray(plan.variant_idx, dtype=int)
    sub = genotypes[np.ix_(rows, cols)]
    n = len(rows)
    if plan.level == "record":
        return {"level": "record", "values": sub.tolist()}
    counts = sub.sum(axis=0).astype(float)  # allele counts, in [0, 2n]
    if plan.level == "boolean":
        return {"level": "boolean", "values": (counts > 0).tolist()}
    if plan.noise_scale:
        counts = counts + rng.laplace(0.0, plan.noise_scale, size=counts.shape)
        counts = np.clip(np.rint(counts), 0, 2 * n)
    if plan.level == "count":
        if plan.bin_width:
            w = max(1.0, plan.bin_width * 2 * n)
            counts = np.rint(counts / w) * w
        return {"level": "count", "values": counts.astype(int).tolist()}
    freq = counts / (2.0 * n)
    if plan.bin_width:
        freq = np.rint(freq / plan.bin_width) * plan.bin_width
    return {"level": "frequency", "values": [round(float(x), 4) for x in freq]}


def run_ladder(
    ds: Dataset,
    donor_ids: list[int],
    variant_idx: list[int],
    level: str,
    p: Params = DEFAULT,
    epsilon_available: float | None = None,
    min_epsilon: float = 0.05,
    rng: np.random.Generator | None = None,
    build_release: bool = True,
) -> TransformResult:
    """Decide what transforms a release needs. Does NOT charge the ledger: the caller charges
    `result.epsilon_spent` when it actually releases."""
    rng = rng or np.random.default_rng(0)
    eps_avail = p.epsilon_budget if epsilon_available is None else epsilon_available
    maf, genotypes = ds.maf, ds.genotypes
    plan = TransformPlan(level, tuple(int(v) for v in variant_idx))

    def risk(pl: TransformPlan) -> dict:
        prot = Protections(pl.bin_width, pl.epsilon)
        return estimate(ds, donor_ids, np.asarray(pl.variant_idx, dtype=int), pl.level, prot, p)

    before = risk(plan)
    steps: list[dict] = []
    cur, cur_risk = plan, before

    def finish(outcome: str, reasons: list[str], release_ok: bool) -> TransformResult:
        res = TransformResult(outcome, cur, steps, before, cur_risk, reasons)
        if release_ok and build_release:
            res.release = materialize(genotypes, donor_ids, cur, rng)
            res.release["variant_ids"] = [int(v) + 1 for v in cur.variant_idx]
        return res

    def record(name: str, detail: str, new_plan: TransformPlan) -> None:
        nonlocal cur, cur_risk
        cur, cur_risk = new_plan, risk(new_plan)
        steps.append({"step": name, "detail": detail, "band": cur_risk["band"],
                      "level": cur.level, "n_variants": len(cur.variant_idx)})

    if before["below_k_min"]:
        return finish("deny", ["below_k_min"], False)
    if before["band"] == "low" and level != "record":
        return finish("permit", [], True)

    # 1. drop rare variants
    keep = tuple(v for v in cur.variant_idx if maf[v] >= p.maf_floor)
    if len(keep) != len(cur.variant_idx):
        dropped = len(cur.variant_idx) - len(keep)
        record("drop_rare_variants", f"dropped {dropped} variant(s) with MAF < {p.maf_floor}",
               replace(cur, variant_idx=keep))
        if not keep:
            return finish("deny", ["all_variants_below_maf_floor"], False)
    # 2. record -> count
    if cur.level == "record":  # unconditional: genotype rows are never returned by this system
        record("downgrade_to_count", "record-level rows are never auto-released",
               replace(cur, level="count"))
    # 3. generalise
    if cur_risk["band"] != "low" and cur.level in ("frequency", "count"):
        record("generalise_bins", f"round into bins of width {p.freq_bin_width}",
               replace(cur, bin_width=p.freq_bin_width))
    # 3b. noise grows with the number of variants: cap them
    if (cur_risk["band"] != "low" and cur.level in ("frequency", "count")
            and len(cur.variant_idx) > p.max_variants_noised):
        record("limit_variants", f"noise grows with #variants: kept the first "
               f"{p.max_variants_noised} of {len(cur.variant_idx)}",
               replace(cur, variant_idx=cur.variant_idx[: p.max_variants_noised]))
    # 4. Laplace noise
    if cur_risk["band"] != "low" and cur.level in ("frequency", "count"):
        eps = min(p.epsilon_per_release, eps_avail)
        if eps < min_epsilon:
            return finish("deny", ["epsilon_budget_exhausted"], False)
        scale = SENSITIVITY * len(cur.variant_idx) / eps
        record("laplace_noise", f"Laplace noise, epsilon={eps:g} split over "
               f"{len(cur.variant_idx)} variants (scale {scale:.1f} on allele counts)",
               replace(cur, epsilon=eps))
    # 5. last resort: boolean
    if cur_risk["band"] != "low" and cur.level in ("frequency", "count"):
        record("downgrade_to_boolean", "last resort: yes/no answers only",
               replace(cur, level="boolean", epsilon=None, bin_width=None))

    if cur_risk["band"] == "high":
        return finish("escalate", ["residual_high_risk"], False)
    changed = bool(steps)
    return finish("permit_with_transform" if changed else "permit", [], True)
