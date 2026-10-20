from functools import cache

import numpy as np

from app.data import pedigree as ped
from app.data.synth import generate, summarize


@cache
def cohort():
    return generate(n_donors=300, n_variants=800, n_families=60, seed=7)


def test_shapes_and_values():
    c = cohort()
    assert c.genotypes.shape == (300, 800)
    assert set(np.unique(c.genotypes)) <= {0, 1, 2}
    assert len(c.donors) == 300
    assert [d["id"] for d in c.donors] == list(range(1, 301))


def test_family_sizes_between_3_and_8():
    from collections import Counter

    sizes = Counter(d["family_id"] for d in cohort().donors).values()
    assert min(sizes) >= 3 and max(sizes) <= 8


def test_deterministic_with_seed():
    a = generate(n_donors=60, n_variants=100, n_families=12, seed=3)
    b = generate(n_donors=60, n_variants=100, n_families=12, seed=3)
    assert np.array_equal(a.genotypes, b.genotypes)
    assert a.relationships == b.relationships


def test_realistic_rare_share():
    maf = cohort().variants["maf"]
    share = (maf < 0.01).mean()
    assert 0.05 < share < 0.9  # skewed low, but not everything


def test_planted_variants_have_few_but_nonzero_carriers():
    c = cohort()
    for j in c.planted:
        k = int((c.genotypes[:, j] > 0).sum())
        assert 1 <= k <= 12


def test_relatives_share_more_alleles_than_strangers():
    """Mendelian transmission must create real relatedness: close pairs agree on rare-ish
    variants far more often than unrelated donors do."""
    c = cohort()
    g = c.genotypes.astype(float)
    informative = c.variants["maf"] > 0.05
    close = [r for r in c.relationships if r["shared"] >= 0.5]
    assert close
    def sim(a, b):
        return np.mean(np.abs(g[a - 1, informative] - g[b - 1, informative]))
    rel = np.mean([sim(r["donor_a"], r["donor_b"]) for r in close])
    rng = np.random.default_rng(0)
    fam = {d["id"]: d["family_id"] for d in c.donors}
    strangers = []
    while len(strangers) < 200:
        a, b = rng.integers(1, 301, 2)
        if fam[int(a)] != fam[int(b)]:
            strangers.append(sim(int(a), int(b)))
    assert rel < np.mean(strangers) * 0.8


def test_relationship_table_values():
    """Derived kinship must match the textbook expected fractions."""
    people = [
        ped.Person(0, 0, "M"), ped.Person(1, 0, "F"),
        ped.Person(2, 1, "M", 0, 1), ped.Person(3, 1, "F", 0, 1),  # full siblings
        ped.Person(4, 1, "F", 0, None),  # paternal half-sibling
        ped.Person(5, 1, "F"), ped.Person(6, 2, "M", 2, 5), ped.Person(7, 2, "F", 2, 5),
        ped.Person(8, 2, "M", 3, None), ped.Person(9, 1, "M"),
    ]
    rel = {(a, b): (n, m, round(s, 4)) for a, b, n, m, s in
           ped.pedigree_relationships(people, list(range(9)))}
    assert rel[(2, 3)] == ("sibling", 2, 0.5)
    assert rel[(2, 4)] == ("half-sibling", 2, 0.25)
    assert rel[(0, 2)] == ("parent", 1, 0.5)
    assert rel[(0, 6)][0] == "grandparent" and rel[(0, 6)][2] == 0.25
    assert rel[(3, 6)][0] == "aunt/uncle" and rel[(3, 6)][2] == 0.25
    assert rel[(6, 8)][0] == "first cousin" and rel[(6, 8)][2] == 0.125


def test_deep_cousin_fractions():
    assert abs(0.5**6 * 2 - 0.03125) < 1e-12  # second cousin
    assert round(0.5**8 * 2, 4) == 0.0078  # third cousin (~0.8%)


def test_consent_mix_and_withdrawals():
    s = summarize(generate(n_donors=600, n_variants=300, n_families=120, seed=1337))
    use = s["consent_use"]
    # 35% plain GRU + the ~10% "rest" (GRU with an NCU/NPU restriction) = ~45% use=GRU
    assert abs(use["GRU"] / 600 - 0.45) < 0.08
    assert abs(use["HMB"] / 600 - 0.30) < 0.08
    assert abs(use["DS"] / 600 - 0.25) < 0.08
    assert 5 <= s["withdrawn"] <= 35
