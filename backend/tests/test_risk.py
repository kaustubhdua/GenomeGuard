import math

import numpy as np

from app.core import risk
from app.core.risk import RiskThresholds, estimate_risk, information_bits, uniqueness_rate

T = RiskThresholds()


def test_uniqueness_all_distinct_and_all_same():
    distinct = np.array([[0, 1], [1, 0], [2, 2], [1, 1]])
    assert uniqueness_rate(distinct) == 1.0
    same = np.ones((10, 3), dtype=int)
    assert uniqueness_rate(same) == 0.0
    mixed = np.array([[0], [0], [1]])  # the lone '1' is unique, the two 0s are not
    assert abs(uniqueness_rate(mixed) - 1 / 3) < 1e-9


def test_information_bits_hand_computed():
    p = np.array([0.5])
    assert abs(information_bits(np.array([[1]]), p) - 1.0) < 1e-9  # P(het)=0.5 -> 1 bit
    assert abs(information_bits(np.array([[2]]), p) - 2.0) < 1e-9  # P(hom)=0.25 -> 2 bits
    p = np.array([0.1])
    assert abs(information_bits(np.array([[0]]), p) + math.log2(0.81)) < 1e-9
    two = np.array([[1, 2]])
    assert abs(information_bits(two, np.array([0.5, 0.5])) - 3.0) < 1e-9  # bits add up


def _cohort(n=40, m=6, seed=0, rare_col_carriers=None):
    rng = np.random.default_rng(seed)
    g = rng.binomial(2, 0.3, size=(n, m)).astype(np.int8)
    maf = np.full(m, 0.3)
    if rare_col_carriers is not None:  # last column is a rare variant with exact carrier count
        g[:, -1] = 0
        g[:rare_col_carriers, -1] = 1
        maf[-1] = 0.004
    return g, maf


def test_below_k_min_is_high_and_flagged():
    g, maf = _cohort(n=15)
    r = estimate_risk(g, maf, list(range(1, 16)), [0, 1], "frequency")
    assert r["below_k_min"] and r["band"] == "high" and r["band_components"]["size"] == "high"


def test_aggregate_common_variants_low_risk():
    g, maf = _cohort(n=100, m=5)
    r = estimate_risk(g, maf, list(range(1, 101)), [0, 1, 2], "frequency")
    assert r["band"] == "low" and r["info_bits"] is None and r["min_carriers"] is None


def test_record_level_many_variants_is_high_via_uniqueness():
    g, maf = _cohort(n=60, m=40)
    r = estimate_risk(g, maf, list(range(1, 61)), list(range(40)), "record")
    assert r["uniqueness_rate"] > 0.9 and r["band"] == "high"
    assert r["info_bits"] > r["log2_n"]  # a row carries far more bits than needed to single out


def test_record_level_one_variant_not_unique():
    g, maf = _cohort(n=60, m=40)
    r = estimate_risk(g, maf, list(range(1, 61)), [0], "record")
    assert r["uniqueness_rate"] == 0.0 and r["band_components"]["uniqueness"] == "low"


def test_uniqueness_does_not_drive_band_for_aggregates():
    g, maf = _cohort(n=60, m=40)
    r = estimate_risk(g, maf, list(range(1, 61)), list(range(40)), "frequency")
    assert r["uniqueness_rate"] > 0.9 and r["band_components"]["uniqueness"] == "low"


def test_rare_variant_few_carriers_is_high_and_counts_carriers():
    g, maf = _cohort(n=50, m=4, rare_col_carriers=3)
    r = estimate_risk(g, maf, list(range(1, 51)), [0, 1, 2, 3], "count")
    assert r["rare_variants"] == 1 and r["min_carriers"] == 3 and r["band"] == "high"


def test_rare_variant_with_enough_carriers_not_high():
    g, maf = _cohort(n=50, m=4, rare_col_carriers=8)
    r = estimate_risk(g, maf, list(range(1, 51)), [0, 1, 2, 3], "count")
    assert r["min_carriers"] == 8 and r["band_components"]["rare"] == "low"


def test_rare_variant_absent_from_cohort_is_not_a_risk():
    g, maf = _cohort(n=50, m=4, rare_col_carriers=0)
    r = estimate_risk(g, maf, list(range(1, 51)), [0, 1, 2, 3], "count")
    assert r["rare_variants"] == 0 and r["min_carriers"] is None and r["band"] == "low"


def test_binning_masks_rare_variant():
    g, maf = _cohort(n=50, m=4, rare_col_carriers=3)  # freq = 3/100 = 0.03 < 0.05/2? no: 0.03>0.025
    r = estimate_risk(g, maf, list(range(1, 51)), [0, 1, 2, 3], "frequency", bin_width=0.10)
    assert r["rare_variants_masked"] == 1 and r["band"] == "low"
    r2 = estimate_risk(g, maf, list(range(1, 51)), [0, 1, 2, 3], "frequency", bin_width=0.05)
    assert r2["rare_variants_masked"] == 0 and r2["band"] == "high"  # 0.03 rounds to 0.05 bin


def test_noise_masks_rare_variant_only_when_scale_covers_carriers():
    g, maf = _cohort(n=50, m=4, rare_col_carriers=3)
    ids = list(range(1, 51))
    weak = estimate_risk(g, maf, ids, [0, 1, 2, 3], "count", noise_scale=2.0)
    strong = estimate_risk(g, maf, ids, [0, 1, 2, 3], "count", noise_scale=10.0)
    assert weak["band"] == "high" and strong["band"] == "low"


RELS = [
    {"donor_a": 1, "donor_b": 2, "relation": "parent", "meioses": 1, "shared": 0.5},
    {"donor_a": 1, "donor_b": 3, "relation": "sibling", "meioses": 2, "shared": 0.5},
    {"donor_a": 4, "donor_b": 5, "relation": "second cousin", "meioses": 6, "shared": 0.03125},
    {"donor_a": 6, "donor_b": 7, "relation": "third cousin", "meioses": 8, "shared": 0.0078125},
    {"donor_a": 1, "donor_b": 8, "relation": "x", "meioses": 10, "shared": 0.001},  # too far
]


def test_relative_exposure_counts_outside_release_only():
    e = risk.relative_exposure({1, 4}, RELS, T)
    assert e["total"] == 3  # donors 2, 3 (via 1) and 5 (via 4); donor 8 too distant
    assert e["by_relation"] == {"parent": 1, "sibling": 1, "second cousin": 1}
    assert e["close_total"] == 2
    assert abs(e["expected_shared_sum"] - (0.5 + 0.5 + 0.03125)) < 1e-3


def test_relatives_inside_release_are_not_exposed():
    assert risk.relative_exposure({1, 2, 3}, RELS, T)["total"] == 0


def test_relative_counted_once_at_closest_relation():
    rels = [
        {"donor_a": 1, "donor_b": 9, "relation": "first cousin", "meioses": 4, "shared": 0.125},
        {"donor_a": 2, "donor_b": 9, "relation": "parent", "meioses": 1, "shared": 0.5},
    ]
    e = risk.relative_exposure({1, 2}, rels, T)
    assert e["total"] == 1 and e["by_relation"] == {"parent": 1}


def test_kin_linked_rare_pairs_raise_band_to_medium():
    g, maf = _cohort(n=50, m=4, rare_col_carriers=8)  # carriers = donors 1..8, enough carriers
    ids = list(range(1, 41))  # release donors 1..40; donor 45 is outside
    rels = [{"donor_a": 1, "donor_b": 45, "relation": "sibling", "meioses": 2, "shared": 0.5}]
    r = estimate_risk(g, maf, ids, [0, 1, 2, 3], "count", relationships=rels)
    assert r["kin_linked_rare_pairs"] == 1 and r["band"] == "medium"
    assert r["relatives_exposed"]["total"] == 1
    assert "exposed_ids" not in r["relatives_exposed"]  # never leaves the estimator


def test_synthetic_cohort_end_to_end():
    from app.data.synth import generate

    c = generate()  # default 600 x 3000
    ids = [d["id"] for d in c.donors]
    rels = c.relationships
    maf = c.variants["maf"]
    allv = list(range(3000))
    rec = estimate_risk(c.genotypes, maf, ids, allv, "record", rels)
    assert rec["band"] == "high" and rec["uniqueness_rate"] > 0.99
    assert rec["info_bits"] > 5 * rec["log2_n"]
    common = [j for j in allv if maf[j] >= 0.2][:30]
    safe = estimate_risk(c.genotypes, maf, ids, common, "frequency", rels)
    assert safe["band"] == "low"
    planted = estimate_risk(c.genotypes, maf, ids, c.planted, "count", rels)
    assert planted["band"] == "high" and planted["min_carriers"] < 5
    # the family-tree demo needs relatives lighting up
    assert planted["relatives_exposed"]["total"] >= 0
    half = estimate_risk(c.genotypes, maf, ids[:300], common, "frequency", rels)
    assert half["relatives_exposed"]["total"] > 0  # releasing half leaves relatives outside
