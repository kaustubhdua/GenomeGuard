import json
import math

import numpy as np

from app.core.consent import DonorView
from app.core.dataset import Dataset
from app.core.params import Params
from app.core.risk import Protections, estimate, membership_signal

P2 = Params(k_min=2)  # tiny cohorts in hand-built tests


def make_ds(geno, maf=None, relationships=(), families=None):
    geno = np.array(geno, dtype=np.int8)
    n = geno.shape[0]
    donors = [DonorView(i + 1, "POP_A", "C1", (families or [1] * n)[i], {"use": "GRU"})
              for i in range(n)]
    maf = np.array(maf if maf is not None else [0.3] * geno.shape[1])
    return Dataset(geno, maf, donors, list(relationships))


def rel(a, b, name, shared):
    return {"donor_a": a, "donor_b": b, "relation": name, "meioses": 0, "shared": shared}


def test_uniqueness_rate_by_row_hashing():
    ds = make_ds([[0, 0], [0, 0], [1, 0], [2, 2]])
    r = estimate(ds, [1, 2, 3, 4], np.array([0, 1]), "record", p=P2)
    assert r["uniqueness_rate"] == 0.5  # rows 3 and 4 are unique, rows 1-2 identical


def test_info_bits_hardy_weinberg():
    ds = make_ds([[0], [1], [1], [2]])  # alt freq exactly 0.5 -> bits 2,1,1,2
    r = estimate(ds, [1, 2, 3, 4], np.array([0]), "record", p=P2)
    assert r["info_bits_mean"] == 1.5
    assert r["log2_n"] == 2.0


def test_below_k_min_is_high():
    ds = make_ds([[0], [1], [2]])
    r = estimate(ds, [1, 2, 3], np.array([0]), "frequency")  # default k_min = 20
    assert r["band"] == "high" and "cohort_below_k_min" in r["band_reasons"]
    assert r["below_k_min"] is True


def test_empty_release():
    ds = make_ds([[0], [1]])
    assert estimate(ds, [], np.array([0]), "count")["band"] == "high"
    assert estimate(ds, [1, 2], np.array([], dtype=int), "count", p=P2)["band"] == "low"


def rare_ds(n=40, carriers=3):
    g = np.zeros((n, 2), dtype=np.int8)
    g[:carriers, 0] = 1  # variant 0: rare with `carriers` carriers
    g[:, 1] = np.tile([0, 1], n // 2)  # variant 1: common
    return make_ds(g, maf=[0.004, 0.25], families=[i // 2 + 1 for i in range(n)])


def test_rare_few_carriers_high_and_min_carriers_reported():
    ds = rare_ds(carriers=3)
    r = estimate(ds, list(range(1, 41)), np.array([0]), "frequency")
    assert r["min_carriers"] == 3 and r["rare_few_carriers"] == 1
    assert r["band"] == "high" and "rare_variant_few_carriers" in r["band_reasons"]


def test_enough_carriers_is_not_flagged():
    ds = rare_ds(carriers=6)
    r = estimate(ds, list(range(1, 41)), np.array([0]), "frequency")
    assert r["rare_few_carriers"] == 0 and r["band"] != "high"


def test_binning_hides_rare_counts_but_not_for_boolean_or_record():
    ds = rare_ds(carriers=3)
    ids, v = list(range(1, 41)), np.array([0])
    binned = Protections(bin_width=0.05)
    assert estimate(ds, ids, v, "frequency", binned)["rare_hidden"] is True
    assert estimate(ds, ids, v, "frequency", binned)["band"] != "high"
    assert estimate(ds, ids, v, "boolean", binned)["band"] == "high"  # existence still leaks
    assert estimate(ds, ids, v, "record", binned)["band"] == "high"


def test_zero_carrier_rare_variant_is_not_a_leak():
    ds = rare_ds(carriers=0)
    r = estimate(ds, list(range(1, 41)), np.array([0]), "frequency")
    assert r["min_carriers"] is None and r["rare_few_carriers"] == 0


def test_carrier_families_counted():
    ds = rare_ds(carriers=4)  # donors 1-4 -> families 1,1,2,2
    r = estimate(ds, list(range(1, 41)), np.array([0]), "frequency")
    assert r["carrier_families"] == 2


def test_relative_exposure_by_degree():
    ds = make_ds(np.zeros((8, 1)), relationships=[
        rel(1, 2, "parent", 0.5), rel(1, 3, "first cousin", 0.125),
        rel(1, 4, "third cousin", 0.0078125), rel(1, 5, "distant", 0.001),
        rel(1, 6, "half-sibling", 0.25), rel(2, 6, "x", 0.0625),
    ])
    out = estimate(ds, [1], np.array([0]), "record", p=Params(k_min=1))["relatives_exposed"]
    assert out["subjects"] == 1
    assert out["by_degree"] == {1: 1, 2: 1, 3: 1, 7: 1}  # donor 5 (0.1%) is below the cut
    assert out["total"] == 4
    assert out["expected_shared_dna"] == round(0.5 + 0.125 + 0.0078125 + 0.25, 3)


def test_relatives_inside_the_release_are_not_double_counted():
    ds = make_ds(np.zeros((4, 1)), relationships=[rel(1, 2, "parent", 0.5)])
    out = estimate(ds, [1, 2], np.array([0]), "record", p=Params(k_min=1))["relatives_exposed"]
    assert out["total"] == 0  # donor 2 is already a subject


def test_aggregate_exposure_only_for_rare_carriers_and_vanishes_when_hidden():
    ds = rare_ds(carriers=3)
    ds.relationships.append(rel(1, 41 - 1, "sibling", 0.5))
    ds.relatives = {d.id: [] for d in ds.donors}
    ds.relatives[1].append((40, "sibling", 0.5))
    ds.relatives[40].append((1, "sibling", 0.5))
    ids = list(range(1, 40))  # donor 40 is a relative who is NOT in the release
    raw = estimate(ds, ids, np.array([0]), "frequency")["relatives_exposed"]
    assert raw["total"] == 1 and raw["by_relation"] == {"sibling": 1}
    hidden = estimate(ds, ids, np.array([0]), "frequency", Protections(bin_width=0.05))
    assert hidden["relatives_exposed"]["total"] == 0


def test_membership_signal_grows_with_variants_and_shrinks_with_protection():
    p = Params()
    pv = np.full(100, 0.2)
    base = membership_signal(200, pv, Protections(), p)
    assert math.isclose(base, math.sqrt(100 / 200), rel_tol=1e-9)  # sqrt(V/n) with no blurring
    assert membership_signal(200, np.full(400, 0.2), Protections(), p) > base
    assert membership_signal(200, pv, Protections(bin_width=0.05), p) < base
    assert membership_signal(200, pv, Protections(epsilon=1.0), p) < base
    assert (membership_signal(200, pv, Protections(epsilon=0.1), p)
            < membership_signal(200, pv, Protections(epsilon=1.0), p))


def test_result_is_plain_json_and_has_no_genotype_data():
    ds = rare_ds(carriers=3)
    r = estimate(ds, list(range(1, 41)), np.array([0, 1]), "record")
    text = json.dumps(r)  # raises if numpy arrays/ints leaked in
    assert "genotype" not in text.lower()


def test_planted_variants_on_synthetic_cohort():
    ds = Dataset.synthetic(n_donors=300, n_variants=400, n_families=60, seed=11)
    ids = [d.id for d in ds.donors]
    v = np.array(ds.planted[:2])
    raw = estimate(ds, ids, v, "frequency")
    assert raw["band"] == "high" and raw["rare_few_carriers"] >= 1
    safe = estimate(ds, ids, v, "frequency", Protections(bin_width=0.05))
    assert safe["band"] != "high"
