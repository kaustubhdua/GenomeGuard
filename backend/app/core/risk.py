"""Re-identification risk estimator (section 7.3).

`estimate()` scores a *candidate release*: a set of donors (the eligible cohort), a set of variants
and a data level ("boolean" < "count" < "frequency" < "record"), optionally with protections
already applied by the transform ladder. It never returns genotypes, only numbers and a band.

What the recipient can learn depends on the level, so the band is computed differently:

RECORD level (individual genotype rows are released)
    uniqueness_rate  share of donors whose genotype vector over the released variants is unique in
                     the cohort (found by hashing/grouping rows). Band: <1% low, 1-10% medium,
                     >10% high. Simple, honest and verifiable.
    info_bits        sum of -log2 P(genotype) under Hardy-Weinberg per donor, shown against
                     log2(n): once a donor's bits exceed log2(n) the genotype alone singles them out.

AGGREGATE levels (count / frequency / boolean: no individual rows leave the system)
    Individual vectors are not released, so uniqueness is not the leak. Two leaks remain:
    (a) rare variants with very few carriers: a count of 1-4 effectively names the carrier(s)
        (and rare alleles cluster in families); hidden only if binning/noise blurs the count;
    (b) membership inference (Homer/Sankararaman-style likelihood-ratio attacks), whose power grows
        with (number of released statistics) / (cohort size). We use a transparent proxy,
        `membership_signal` z = sqrt(sum_v effect_v^2 / (sampling_var_v + distortion^2)), where the
        effect of one donor on a frequency is ~1/n. Binning and Laplace noise add `distortion`.
        This proxy is CALIBRATED against the measured attack in `make eval`.
    n < K_MIN is always high: never release below the minimum cohort size.

RELATIVE exposure (the differentiator, a SIMULATED model, not a forecast about any real database)
    Subjects = all donors (record level) or the carriers of released rare variants (aggregate).
    Exposed relatives = registry members related to a subject, expected to share >= ~0.8% of DNA
    (third cousins), who are not themselves subjects. Grouped by degree = round(-log2(shared)):
    1 = parent/child/sibling (50%), 2 = grandparent/aunt/half-sibling (25%), 3 = first cousin
    (12.5%), 5 = second cousin (3.1%), 7 = third cousin (0.8%). Shares are expected averages.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

import numpy as np

from app.core.dataset import Dataset
from app.core.params import BANDS, DEFAULT, Params


@dataclass(frozen=True)
class Protections:
    """What the transform ladder has already done to the candidate release."""

    bin_width: float | None = None  # frequencies rounded into bins this wide
    epsilon: float | None = None  # total epsilon spent on Laplace noise for this release


def _bump(band: str, to: str) -> str:
    return to if BANDS.index(to) > BANDS.index(band) else band


def distortion_variance(n: int, prot: Protections, n_variants: int, p: Params) -> float:
    """Variance added to each released FREQUENCY by binning and Laplace noise."""
    var = 0.0
    if prot.bin_width:
        var += prot.bin_width**2 / 12.0  # uniform quantisation error
    if prot.epsilon and n_variants:
        scale = p.allele_count_sensitivity * n_variants / prot.epsilon  # b = 2V/eps (composition)
        var += 2.0 * scale**2 / (2.0 * n) ** 2  # Laplace variance 2b^2, count -> frequency
    return var


def membership_signal(n: int, p_vec: np.ndarray, prot: Protections, p: Params) -> float:
    if n <= 0 or len(p_vec) == 0:
        return 0.0
    pq = p_vec * (1 - p_vec)
    effect2 = pq / (2.0 * n**2)  # variance contributed by one donor's genotype
    samp2 = pq / (2.0 * n)  # attacker's baseline uncertainty about the frequency
    d2 = distortion_variance(n, prot, len(p_vec), p)
    return float(math.sqrt(np.sum(effect2 / (samp2 + d2))))


def relative_exposure(ds: Dataset, subjects: set[int], p: Params) -> dict:
    by_degree: Counter[int] = Counter()
    by_relation: Counter[str] = Counter()
    exposed: dict[int, float] = {}
    for s in subjects:
        for other, relation, shared in ds.relatives.get(s, []):
            if other in subjects or shared < p.exposure_min_shared:
                continue
            if shared > exposed.get(other, 0.0):
                exposed[other] = shared
                # attribute each exposed relative to their closest subject once (below)
    closest: dict[int, tuple[str, float]] = {}
    for s in subjects:
        for other, relation, shared in ds.relatives.get(s, []):
            if other in exposed and shared == exposed[other] and other not in closest:
                closest[other] = (relation, shared)
    for _, (relation, shared) in closest.items():
        by_degree[round(-math.log2(shared))] += 1
        by_relation[relation] += 1
    return {
        "total": len(closest),
        "subjects": len(subjects),
        "by_degree": {int(k): int(v) for k, v in sorted(by_degree.items())},
        "by_relation": dict(by_relation.most_common()),
        "expected_shared_dna": round(sum(sh for _, sh in closest.values()), 3),
        "model": "simulated: expected-average kinship, not a forecast about any real database",
    }


def estimate(
    ds: Dataset,
    donor_ids: list[int],
    variant_idx: np.ndarray,
    level: str,
    prot: Protections | None = None,
    p: Params = DEFAULT,
) -> dict:
    prot = prot or Protections()
    variant_idx = np.asarray(variant_idx, dtype=int)
    n, v = len(donor_ids), len(variant_idx)
    reasons: list[str] = []
    out: dict = {
        "n": n, "level": level, "n_variants": v, "below_k_min": n < p.k_min,
        "uniqueness_rate": None, "info_bits_mean": None, "log2_n": round(math.log2(max(n, 1)), 2),
        "rare_variants": 0, "min_carriers": None, "rare_few_carriers": 0, "rare_hidden": False,
        "carrier_families": 0, "membership_signal": 0.0,
        "protections": {"bin_width": prot.bin_width, "epsilon": prot.epsilon},
    }
    if n == 0 or v == 0:
        out.update(band="high" if n < p.k_min else "low", band_reasons=["empty_release"],
                   relatives_exposed=relative_exposure(ds, set(), p))
        return out

    rows = ds.rows(donor_ids)
    g = ds.genotypes[np.ix_(rows, variant_idx)]  # (n, v), local copy; never leaves this function
    maf = ds.maf[variant_idx]

    # ---- rare variants and carrier counts ---------------------------------------------------
    rare = maf < p.rare_maf
    carriers = (g > 0).sum(axis=0)
    rare_present = rare & (carriers > 0)
    out["rare_variants"] = int(rare.sum())
    if rare_present.any():
        out["min_carriers"] = int(carriers[rare_present].min())
    few = rare_present & (carriers < p.min_carriers_high)
    out["rare_few_carriers"] = int(few.sum())

    carrier_donors: set[int] = set()
    if rare_present.any():
        mask = (g[:, rare_present] > 0).any(axis=1)
        carrier_donors = {int(donor_ids[i]) for i in np.where(mask)[0]}
    fam = {d.id: d.family_id for d in ds.donors}
    out["carrier_families"] = len({fam[d] for d in carrier_donors})

    # ---- how much blurring protects small counts (alleles) -----------------------------------
    d_var = distortion_variance(n, prot, v, p)
    hidden_by_bins = bool(prot.bin_width and prot.bin_width >= 2 * p.rare_maf)
    noise_alleles = math.sqrt(d_var) * 2.0 * n  # distortion expressed in allele counts
    hidden = level in ("count", "frequency") and (hidden_by_bins or noise_alleles >= p.min_carriers_high)
    out["rare_hidden"] = bool(hidden)

    # ---- release-level quantities ------------------------------------------------------------
    pv = ds.alt_freq[variant_idx]
    if level == "record":
        uniq = np.unique(g, axis=0, return_counts=True)[1]
        out["uniqueness_rate"] = round(float((uniq == 1).sum()) / n, 4)
        lp = np.stack([2 * np.log2(1 - pv), np.log2(2 * pv * (1 - pv)), 2 * np.log2(pv)])
        bits = -lp[g, np.arange(v)].sum(axis=1)
        out["info_bits_mean"] = round(float(bits.mean()), 2)
    if level in ("count", "frequency"):
        out["membership_signal"] = round(membership_signal(n, pv, prot, p), 3)

    # ---- band --------------------------------------------------------------------------------
    band = "low"
    if n < p.k_min:
        band = "high"
        reasons.append("cohort_below_k_min")
    if level == "record":
        u = out["uniqueness_rate"]
        if u > p.uniqueness_high:
            band = _bump(band, "high")
            reasons.append("record_uniqueness_high")
        elif u >= p.uniqueness_medium:
            band = _bump(band, "medium")
            reasons.append("record_uniqueness_medium")
    else:
        z = out["membership_signal"]
        if z >= p.signal_high:
            band = _bump(band, "high")
            reasons.append("membership_signal_high")
        elif z >= p.signal_medium:
            band = _bump(band, "medium")
            reasons.append("membership_signal_medium")
    if few.any() and not hidden:
        band = _bump(band, "high")
        reasons.append("rare_variant_few_carriers")
    elif rare_present.any() and level == "boolean":
        band = _bump(band, "medium")
        reasons.append("rare_variant_existence_revealed")

    subjects = set(int(d) for d in donor_ids) if level == "record" else carrier_donors
    if level != "record" and hidden:
        subjects = set()  # carriers are not singled out when counts are blurred
    out["relatives_exposed"] = relative_exposure(ds, subjects, p)
    out["band"] = band
    out["band_reasons"] = reasons
    return out
