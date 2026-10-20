import numpy as np

from app.core.transform import EpsilonLedger, TransformPlan, materialize, run_ladder


def cohort(n=60, m=6, rare_carriers=3, seed=1):
    rng = np.random.default_rng(seed)
    g = rng.binomial(2, 0.3, size=(n, m)).astype(np.int8)
    maf = np.full(m, 0.3)
    if rare_carriers is not None:  # last column rare with exact carrier count
        g[:, -1] = 0
        g[:rare_carriers, -1] = 1
        maf[-1] = 0.004
    return g, maf, list(range(1, n + 1))


def test_ledger_charges_and_refuses_overspend():
    L = EpsilonLedger(1.0)
    assert L.remaining(1, "d") == 1.0
    L.charge(1, "d", 0.4)
    assert abs(L.remaining(1, "d") - 0.6) < 1e-12 and L.remaining(2, "d") == 1.0
    try:
        L.charge(1, "d", 0.7)
        raise AssertionError("should have refused")
    except ValueError:
        pass
    L.charge(1, "d", 0.6)
    assert L.remaining(1, "d") < 1e-9


def test_safe_request_is_permitted_untouched():
    g, maf, ids = cohort(rare_carriers=None)
    r = run_ladder(g, maf, ids, [0, 1, 2], "frequency", [])
    assert r.outcome == "permit" and r.steps == [] and r.epsilon_spent == 0.0
    assert r.release["level"] == "frequency" and r.release["variant_ids"] == [1, 2, 3]


def test_too_small_cohort_denied():
    g, maf, ids = cohort(n=12, rare_carriers=None)
    r = run_ladder(g, maf, ids, [0, 1], "frequency", [])
    assert r.outcome == "deny" and r.reasons == ["below_k_min"] and r.release is None


def test_dropping_rare_variant_is_enough():
    g, maf, ids = cohort()
    r = run_ladder(g, maf, ids, [0, 1, 2, 5], "count", [])
    assert r.outcome == "permit_with_transform"
    assert [s["step"] for s in r.steps] == ["drop_rare_variants"]
    assert 6 not in r.release["variant_ids"]  # variant index 5 -> id 6 was dropped
    assert r.risk_before["band"] == "high" and r.risk_after["band"] == "low"


def test_all_rare_denied():
    g, maf, ids = cohort()
    r = run_ladder(g, maf, ids, [5], "count", [])
    assert r.outcome == "deny" and r.reasons == ["all_variants_below_maf_floor"]


def test_record_request_never_auto_released_as_rows():
    g, maf, ids = cohort(m=40, rare_carriers=None)
    r = run_ladder(g, maf, ids, list(range(40)), "record", [])
    assert r.steps[0]["step"] == "downgrade_to_count"
    assert r.plan.level != "record"


def test_kin_linked_medium_triggers_bins_and_noise():
    # rare variant has 8 carriers (not 'high'), but a carrier has a close relative outside the
    # release -> band medium -> ladder goes on to generalise + noise, then accepts medium
    g, maf, ids = cohort(n=50, rare_carriers=8)
    rels = [{"donor_a": 1, "donor_b": 99, "relation": "sibling", "meioses": 2, "shared": 0.5}]
    r = run_ladder(g, maf, ids, [0, 1, 5], "frequency", rels, maf_floor=0.0)
    names = [s["step"] for s in r.steps]
    assert names[:2] == ["generalise_bins", "laplace_noise"]
    assert r.outcome in ("permit_with_transform", "escalate")


def test_budget_exhausted_denies_when_noise_needed():
    g, maf, ids = cohort(n=50, rare_carriers=3)
    r = run_ladder(g, maf, ids, [0, 1, 5], "frequency", [], maf_floor=0.0,
                   epsilon_available=0.01)
    assert r.outcome == "deny" and r.reasons == ["epsilon_budget_exhausted"]


def test_noise_scale_grows_with_number_of_variants():
    a = TransformPlan("count", (0, 1), epsilon=0.5).noise_scale
    b = TransformPlan("count", tuple(range(20)), epsilon=0.5).noise_scale
    assert abs(a - 8.0) < 1e-9 and abs(b - 80.0) < 1e-9 and b == 10 * a


def test_materialize_frequency_bins_and_noise_statistics():
    g, maf, ids = cohort(n=200, m=3, rare_carriers=None)
    raw = g.sum(axis=0) / 400.0
    rng = np.random.default_rng(0)
    out = materialize(g, ids, TransformPlan("frequency", (0, 1, 2)), rng)["values"]
    assert np.allclose(out, np.round(raw, 4))
    binned = materialize(g, ids, TransformPlan("frequency", (0, 1, 2), bin_width=0.05), rng)
    assert all(abs(v / 0.05 - round(v / 0.05)) < 1e-6 for v in binned["values"])
    # noisy release is random but centred: average over many draws approaches the truth
    plan = TransformPlan("frequency", (0,), epsilon=2.0)  # scale = 2*1/2 = 1 count
    draws = [materialize(g, ids, plan, np.random.default_rng(s))["values"][0] for s in range(400)]
    assert abs(np.mean(draws) - raw[0]) < 0.01
    assert np.std(draws) > 0


def test_materialize_boolean_and_clipping():
    g, maf, ids = cohort(n=30, m=2, rare_carriers=None)
    assert materialize(g, ids, TransformPlan("boolean", (0, 1)), np.random.default_rng(0))[
        "values"] == [True, True]
    plan = TransformPlan("count", (0,), epsilon=0.05)  # huge noise
    vals = materialize(g, ids, plan, np.random.default_rng(1))["values"]
    assert 0 <= vals[0] <= 60  # clipped to [0, 2n]


def test_ladder_is_deterministic_for_a_seed():
    g, maf, ids = cohort(n=50, rare_carriers=8)
    rels = [{"donor_a": 1, "donor_b": 99, "relation": "sibling", "meioses": 2, "shared": 0.5}]
    kw = dict(maf_floor=0.0)
    a = run_ladder(g, maf, ids, [0, 1, 5], "frequency", rels,
                   rng=np.random.default_rng(5), **kw)
    b = run_ladder(g, maf, ids, [0, 1, 5], "frequency", rels,
                   rng=np.random.default_rng(5), **kw)
    assert a.release == b.release and a.to_json() == b.to_json()


def test_transform_json_shape():
    g, maf, ids = cohort()
    j = run_ladder(g, maf, ids, [0, 1, 5], "count", []).to_json()
    assert set(j) == {"outcome", "steps", "final", "risk_before", "risk_after", "reasons"}
    assert j["risk_before"]["band"] == "high" and j["risk_after"]["band"] == "low"


def test_demo_scenario_on_synthetic_cohort():
    """Registered researcher asks for frequencies incl. the planted rare variants."""
    from app.data.synth import generate

    c = generate()
    ids = [d["id"] for d in c.donors][:300]  # an eligible subset: relatives are left outside
    maf = c.variants["maf"]
    common = [j for j in range(3000) if maf[j] >= 0.1][:20]
    # the demo preset picks planted variants that are actually carried inside the eligible set
    carried = [j for j in c.planted if 1 <= (c.genotypes[:300, j] > 0).sum() < 5]
    assert carried
    req = common + carried
    r = run_ladder(c.genotypes, maf, ids, req, "frequency", c.relationships)
    assert r.outcome in ("permit_with_transform", "escalate")
    assert r.steps[0]["step"] == "drop_rare_variants"
    assert r.risk_before["band"] == "high"
    assert r.risk_after["band"] != "high" or r.outcome == "escalate"
