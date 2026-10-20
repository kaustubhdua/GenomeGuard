"""Synthetic cohort generator (section 7.1). Pure numpy: no database, no config import, so it is
easy to test and reuse. ALL DATA IS SYNTHETIC; nothing here is derived from a real person.

Simplifications (state these honestly to judges): variants are treated as unlinked (no
recombination model), each family belongs to a single population, and population differences are
a simple Beta perturbation of a shared base frequency, not a coalescent simulation (msprime is an
optional upgrade, not a dependency).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from app.core.consent import ConsentRequest, permitted
from app.data import pedigree as ped

# The scripted demo asks for diabetes-study frequencies; the first two planted variants are
# carried by at least one donor whose consent allows that request, so the demo is deterministic.
DEMO_REQUEST = ConsentRequest(purpose="disease_research", disease="diabetes")

POPULATIONS = ["POP_A", "POP_B", "POP_C", "POP_D", "POP_E"]
COHORTS = ["BIOBANK-A", "BIOBANK-B", "DIABETES-STUDY", "ONCO-STUDY"]
DISEASES = ["diabetes", "cancer", "cardiovascular", "asthma"]
DISEASE_WEIGHTS = [0.4, 0.3, 0.2, 0.1]
BASES = ["A", "C", "G", "T"]


@dataclass
class SyntheticCohort:
    donors: list[dict]  # index i is donor id i+1
    genotypes: np.ndarray  # (n_donors, n_variants) int8 in {0,1,2}: alt-allele counts
    variants: dict[str, np.ndarray]  # chrom, pos, ref, alt, maf, is_rare, planted
    relationships: list[dict]  # donor_a, donor_b (1-based ids), relation, meioses, shared
    planted: list[int] = field(default_factory=list)  # variant indices used in the demo
    seed: int = 0


def _consent(rng: np.random.Generator, population: str) -> dict:
    """DUO-style consent: ~35% GRU, 30% HMB, 25% DS, remainder GRU + NCU/NPU. A few extra
    modifiers are sprinkled on top so every consent rule is exercised by the data."""
    r = rng.random()
    use, disease, mods = "GRU", None, []
    if r < 0.35:
        pass
    elif r < 0.65:
        use = "HMB"
    elif r < 0.90:
        use = "DS"
        disease = str(rng.choice(DISEASES, p=DISEASE_WEIGHTS))
    else:
        mods.append(str(rng.choice(["NCU", "NPU"])))
    for code, prob in (("NMDS", 0.05), ("NAGR", 0.03), ("NCTRL", 0.05)):
        if rng.random() < prob:
            mods.append(code)
    if "NCU" not in mods and "NPU" not in mods and rng.random() < 0.08:
        mods.append("NCU")
    day = date(2015, 1, 1) + timedelta(days=int(rng.integers(0, 365 * 10)))
    return {
        "use": use,
        "disease": disease,
        "modifiers": sorted(set(mods)),
        "population": population if rng.random() < 0.04 else None,
        "consent_date": day.isoformat(),
    }


def _family_sizes(rng: np.random.Generator, n_donors: int, n_families: int) -> list[int]:
    """Sizes in 3..8 that sum exactly to n_donors."""
    if not 3 * n_families <= n_donors <= 8 * n_families:
        raise ValueError("n_donors must lie in [3*n_families, 8*n_families]")
    sizes = rng.integers(3, 9, size=n_families)
    while sizes.sum() != n_donors:
        i = int(rng.integers(n_families))
        if sizes.sum() > n_donors and sizes[i] > 3:
            sizes[i] -= 1
        elif sizes.sum() < n_donors and sizes[i] < 8:
            sizes[i] += 1
    return [int(s) for s in sizes]


def generate(
    n_donors: int = 600,
    n_variants: int = 3000,
    n_populations: int = 3,
    n_families: int = 120,
    seed: int = 1337,
    n_planted: int = 5,
    rare_maf: float = 0.01,
    withdrawn_rate: float = 0.03,
) -> SyntheticCohort:
    rng = np.random.default_rng(seed)
    pops = POPULATIONS[:n_populations]

    # ---- allele frequencies: skewed low so a realistic share is rare ----------------------
    base = np.clip(rng.beta(0.25, 3.0, n_variants), 0.002, 0.5)
    planted = list(range(n_variants - n_planted, n_variants))
    base[planted] = 0.003  # very rare, used in the demo
    kappa = 40.0  # smaller = more population differentiation
    pop_freq = {
        p: np.clip(rng.beta(base * kappa, (1 - base) * kappa), 1e-4, 0.999) for p in pops
    }

    # ---- families: build pedigree, simulate genotypes by Mendelian transmission ----------
    sizes = _family_sizes(rng, n_donors, n_families)
    geno_rows: list[np.ndarray] = []
    donors: list[dict] = []
    relationships: list[dict] = []
    family_donors: dict[int, list[int]] = {}

    for fam, size in enumerate(sizes, start=1):
        pop = pops[int(rng.integers(len(pops)))]
        cohort = COHORTS[int(rng.integers(len(COHORTS)))]
        people = ped.build_pedigree(rng)
        g = np.zeros((len(people), n_variants), dtype=np.int8)
        for p in people:  # parents are always created before children
            if p.father is None:  # founder: Hardy-Weinberg draw from the population frequencies
                g[p.pid] = rng.binomial(2, pop_freq[pop])
            else:  # each parent passes one allele; carrier of 1 copy transmits it with prob 1/2
                from_f = rng.binomial(1, g[p.father] / 2.0)
                from_m = rng.binomial(1, g[p.mother] / 2.0)
                g[p.pid] = from_f + from_m
        kin = ped.kinship_matrix(people)
        registered = ped.sample_registered(rng, people, size, kin)
        pid_to_donor: dict[int, int] = {}
        for pid in registered:
            donors.append(
                {
                    "id": len(donors) + 1,
                    "cohort_id": cohort,
                    "population": pop,
                    "consent": _consent(rng, pop),
                    "family_id": fam,
                    "withdrawn": bool(rng.random() < withdrawn_rate),
                }
            )
            geno_rows.append(g[pid])
            pid_to_donor[pid] = donors[-1]["id"]
        family_donors[fam] = list(pid_to_donor.values())
        for a, b, name, meioses, shared in ped.pedigree_relationships(people, registered):
            relationships.append(
                {
                    "donor_a": pid_to_donor[a],
                    "donor_b": pid_to_donor[b],
                    "relation": name,
                    "meioses": meioses,
                    "shared": shared,
                }
            )

    genotypes = np.vstack(geno_rows).astype(np.int8)

    # ---- plant demo variants: carried by one donor and some close relatives ---------------
    close = {}
    for r in relationships:
        if r["shared"] >= 0.25:
            close.setdefault(r["donor_a"], []).append(r["donor_b"])
            close.setdefault(r["donor_b"], []).append(r["donor_a"])
    anchors = [d for d, rel in close.items() if len(rel) >= 1]
    by_id = {d["id"]: d for d in donors}
    eligible_anchors = [a for a in anchors
                        if permitted(by_id[a]["consent"], DEMO_REQUEST, by_id[a]["withdrawn"])[0]]
    for k, j in enumerate(planted):
        genotypes[:, j] = 0
        pool = eligible_anchors if (k < 2 and eligible_anchors) else anchors
        anchor = int(pool[int(rng.integers(len(pool)))])
        genotypes[anchor - 1, j] = 1
        for rel in close[anchor]:
            if rng.random() < 0.5:
                genotypes[rel - 1, j] = 1

    # ---- observed MAF in the cohort (this is what `is_rare` refers to) ---------------------
    freq = genotypes.sum(axis=0) / (2.0 * n_donors)
    maf = np.minimum(freq, 1 - freq)
    chrom = np.sort(rng.integers(1, 23, n_variants))
    pos = np.zeros(n_variants, dtype=np.int64)
    for c in np.unique(chrom):
        idx = np.where(chrom == c)[0]
        pos[idx] = np.sort(rng.choice(250_000_000, size=len(idx), replace=False))
    ref = rng.integers(0, 4, n_variants)
    alt = (ref + rng.integers(1, 4, n_variants)) % 4
    is_planted = np.zeros(n_variants, dtype=bool)
    is_planted[planted] = True
    variants = {
        "chrom": chrom.astype(str),
        "pos": pos,
        "ref": np.array(BASES)[ref],
        "alt": np.array(BASES)[alt],
        "maf": maf,
        "is_rare": maf < rare_maf,
        "planted": is_planted,
    }
    return SyntheticCohort(donors, genotypes, variants, relationships, planted, seed)


def summarize(c: SyntheticCohort) -> dict:
    """Plain-number summary printed by `make seed`."""
    from collections import Counter

    n, v = c.genotypes.shape
    rel = Counter(r["relation"] for r in c.relationships)
    carriers = {int(j): int((c.genotypes[:, j] > 0).sum()) for j in c.planted}
    use = Counter(d["consent"]["use"] for d in c.donors)
    return {
        "donors": n,
        "variants": v,
        "families": len({d["family_id"] for d in c.donors}),
        "populations": dict(Counter(d["population"] for d in c.donors)),
        "rare_variants_(MAF<1%)": int(c.variants["is_rare"].sum()),
        "consent_use": dict(use),
        "withdrawn": sum(d["withdrawn"] for d in c.donors),
        "related_pairs": len(c.relationships),
        "relations": dict(rel.most_common()),
        "planted_variant_carriers": carriers,
    }
