"""Privacy-risk estimator (section 7.3). Pure numpy: no database, no web, no config import.

Given a candidate release (donors x variants at a data level) it reports, with plain numbers:

  n                  cohort size. Below k_min the release is never allowed (`below_k_min`).
  uniqueness_rate    share of donors whose genotype vector over the released variants is unique
                     in the cohort. Only a real risk when INDIVIDUAL rows leave the system
                     (data_level == "record"); for aggregate levels it is reported as a
                     worst-case indicator but does not drive the band.
  info_bits          mean over donors of sum_j -log2 P(genotype_ij) under Hardy-Weinberg
                     (record level only). Compare with log2(n): once bits >> log2(n), a donor's
                     row identifies them inside this cohort. (~33 bits single out one person
                     among 8 billion.)
  rare_variants      released variants with MAF < rare_maf, and `min_carriers` = fewest carriers
                     of any such variant that is actually present in the cohort. Fewer than
                     min_carriers_high carriers means a count/frequency/boolean answer can
                     reveal membership, so the band becomes "high" - UNLESS the variant is
                     masked by the transform (frequency rounded to 0 in its bin, or Laplace
                     noise scale >= carrier count, a documented heuristic: the real guarantee is
                     epsilon, and the evaluation measures the actual attack AUC).
  relatives_exposed  SIMULATED MODEL: registry relatives (up to third cousins) of released
                     donors who are not themselves in the release, with expected shared DNA.
                     These are people who never had a say in this request.

Band = worst of: size (n < k_min -> high), uniqueness (record level only), rare-variant carriers,
and kin-linked rare variants (a released carrier with a close relative outside the release ->
at least medium). All thresholds live in RiskThresholds (mirrors config.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

BAND_ORDER = {"low": 0, "medium": 1, "high": 2}
AGGREGATE_LEVELS = ("boolean", "count", "frequency")


@dataclass(frozen=True)
class RiskThresholds:
    k_min: int = 20
    uniqueness_medium: float = 0.01
    uniqueness_high: float = 0.10
    min_carriers_high: int = 5
    rare_maf: float = 0.01
    max_meioses: int = 8
    min_shared: float = 0.0078  # ignore relatives expected to share less than ~0.8%
    close_shared: float = 0.25  # "close" relative: expected sharing >= 25%

    @classmethod
    def from_settings(cls) -> RiskThresholds:
        from app.config import settings as s

        return cls(s.k_min, s.uniqueness_medium, s.uniqueness_high, s.min_carriers_high,
                   s.rare_maf, s.max_relative_meioses, s.exposure_min_shared)


def _worst(*bands: str) -> str:
    return max(bands, key=BAND_ORDER.__getitem__)


def uniqueness_rate(sub: np.ndarray) -> float:
    """Share of rows (donors) whose vector appears exactly once. sub: (n, m) int array."""
    n = sub.shape[0]
    if n == 0:
        return 0.0
    if sub.shape[1] == 0:
        return 1.0 if n == 1 else 0.0
    _, counts = np.unique(sub, axis=0, return_counts=True)
    return float((counts == 1).sum() / n)


def information_bits(sub: np.ndarray, maf: np.ndarray) -> float:
    """Mean over donors of sum_j -log2 P(g_ij) with genotype g in {0,1,2} minor-allele copies,
    assuming Hardy-Weinberg at the stored frequency."""
    if sub.size == 0:
        return 0.0
    p = np.clip(maf, 1e-6, 0.5)
    probs = np.stack([(1 - p) ** 2, 2 * p * (1 - p), p**2])  # (3, m)
    cols = np.arange(sub.shape[1])
    bits = -np.log2(probs[sub.astype(int), cols])  # (n, m)
    return float(bits.sum(axis=1).mean())


def relative_exposure(
    released_ids: set[int], relationships: list[dict], t: RiskThresholds
) -> dict:
    """SIMULATED MODEL. Relatives of released donors who are outside the release, counted once
    each at their closest relationship. `relationships` rows: donor_a, donor_b, relation,
    meioses, shared (expected average; real sharing varies, especially for distant cousins)."""
    best: dict[int, tuple[float, str]] = {}
    inside_pairs = 0
    for r in relationships:
        if r["meioses"] > t.max_meioses or r["shared"] < t.min_shared:
            continue
        a, b = r["donor_a"], r["donor_b"]
        for me, other in ((a, b), (b, a)):
            if me in released_ids:
                if other in released_ids:
                    inside_pairs += 1
                    continue
                if other not in best or r["shared"] > best[other][0]:
                    best[other] = (r["shared"], r["relation"])
    by_relation: dict[str, int] = {}
    for _, name in best.values():
        by_relation[name] = by_relation.get(name, 0) + 1
    return {
        "total": len(best),
        "by_relation": dict(sorted(by_relation.items(), key=lambda kv: -kv[1])),
        "close_total": sum(1 for s, _ in best.values() if s >= t.close_shared),
        "expected_shared_sum": round(sum(s for s, _ in best.values()), 4),
        "exposed_ids": sorted(best),  # internal; API layers must not return these
        "model": "simulated; expected averages, real sharing varies",
    }


def estimate_risk(
    genotypes: np.ndarray,
    maf: np.ndarray,
    donor_ids: list[int],
    variant_idx: list[int] | np.ndarray,
    data_level: str,
    relationships: list[dict] | None = None,
    thresholds: RiskThresholds | None = None,
    bin_width: float | None = None,
    noise_scale: float | None = None,
) -> dict:
    """Risk of releasing `variant_idx` for `donor_ids` (1-based ids; row = id - 1) at
    `data_level`. `bin_width` / `noise_scale` describe transforms ALREADY applied so the
    estimator can credit them (see module docstring)."""
    t = thresholds or RiskThresholds()
    relationships = relationships or []
    ids = list(donor_ids)
    vidx = np.asarray(list(variant_idx), dtype=int)
    n = len(ids)
    sub = genotypes[np.ix_(np.asarray(ids, dtype=int) - 1, vidx)] if n and len(vidx) else \
        np.zeros((n, len(vidx)), dtype=np.int8)
    m = len(vidx)
    vmaf = maf[vidx] if m else np.array([])
    record = data_level == "record"

    uniq = uniqueness_rate(sub)
    bits = information_bits(sub, vmaf) if record else None

    # ---- rare variants (carrier counts are WITHIN the released cohort) ----
    carriers = (sub > 0).sum(axis=0) if n and m else np.zeros(m, dtype=int)
    is_rare = vmaf < t.rare_maf
    present_rare = is_rare & (carriers > 0)
    freq = sub.sum(axis=0) / (2.0 * n) if n and m else np.zeros(m)
    masked = np.zeros(m, dtype=bool)
    if bin_width:  # frequency rounds to the zero bin: nothing visible
        masked |= present_rare & (freq < bin_width / 2.0)
    if noise_scale:  # signal (carrier count) no larger than the Laplace scale
        masked |= present_rare & (carriers <= noise_scale)
    exposed_rare = present_rare & ~masked
    min_carriers = int(carriers[exposed_rare].min()) if exposed_rare.any() else None

    # ---- relatives ----
    rel = relative_exposure(set(ids), relationships, t)
    carrier_donors = set()
    if exposed_rare.any():
        any_carry = (sub[:, exposed_rare] > 0).any(axis=1)
        carrier_donors = {ids[i] for i in np.where(any_carry)[0]}
    exposed_ids = set(rel["exposed_ids"])
    kin_links = 0
    for r in relationships:
        if r["shared"] < t.close_shared or r["meioses"] > t.max_meioses:
            continue
        a, b = r["donor_a"], r["donor_b"]
        if (a in carrier_donors and b in exposed_ids) or (b in carrier_donors and a in exposed_ids):
            kin_links += 1

    # ---- band ----
    size_band = "high" if n < t.k_min else "low"
    if not record:
        uniq_band = "low"
    elif uniq > t.uniqueness_high:
        uniq_band = "high"
    elif uniq >= t.uniqueness_medium:
        uniq_band = "medium"
    else:
        uniq_band = "low"
    rare_band = "high" if min_carriers is not None and min_carriers < t.min_carriers_high \
        else "low"
    kin_band = "medium" if kin_links > 0 or (record and rel["close_total"] > 0) else "low"
    band = _worst(size_band, uniq_band, rare_band, kin_band)

    return {
        "n": n,
        "below_k_min": n < t.k_min,
        "k_min": t.k_min,
        "data_level": data_level,
        "n_variants": m,
        "uniqueness_rate": round(uniq, 4),
        "info_bits": None if bits is None else round(bits, 2),
        "log2_n": round(math.log2(n), 2) if n > 0 else 0.0,
        "rare_variants": int(present_rare.sum()),
        "rare_variants_masked": int((present_rare & masked).sum()),
        "min_carriers": min_carriers,
        "relatives_exposed": {k: v for k, v in rel.items() if k != "exposed_ids"},
        "kin_linked_rare_pairs": kin_links,
        "band_components": {"size": size_band, "uniqueness": uniq_band, "rare": rare_band,
                            "kin": kin_band},
        "band": band,
    }
