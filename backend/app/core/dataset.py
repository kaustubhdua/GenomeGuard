"""In-memory view of the genomic data store used by the risk/transform/anomaly modules.

The Dataset is the ONLY object that holds genotypes. API code never serialises it; agents never
receive it. Donor ids are 1..N and map to genotype row id-1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.core.consent import DonorView


@dataclass
class Dataset:
    genotypes: np.ndarray  # (N, V) int8 alt-allele counts
    maf: np.ndarray  # (V,) observed minor-allele frequency in this cohort
    donors: list[DonorView]
    relationships: list[dict]  # donor_a, donor_b, relation, meioses, shared
    planted: list[int] = field(default_factory=list)  # variant indices used in the demo
    dataset_id: str = "synthetic-v1"
    coords: list = field(default_factory=list)  # (chrom, pos, ref, alt) per variant, for Beacon lookups
    alt_freq: np.ndarray = field(init=False)
    relatives: dict[int, list[tuple[int, str, float]]] = field(init=False)

    def __post_init__(self) -> None:
        n = self.genotypes.shape[0]
        f = self.genotypes.sum(axis=0) / (2.0 * n)
        self.alt_freq = np.clip(f, 1e-4, 1 - 1e-4)  # clipped so HWE log-probs stay finite
        self.relatives = {d.id: [] for d in self.donors}
        for r in self.relationships:
            self.relatives[r["donor_a"]].append((r["donor_b"], r["relation"], r["shared"]))
            self.relatives[r["donor_b"]].append((r["donor_a"], r["relation"], r["shared"]))

    @property
    def n_donors(self) -> int:
        return self.genotypes.shape[0]

    @property
    def n_variants(self) -> int:
        return self.genotypes.shape[1]

    def rows(self, donor_ids) -> np.ndarray:
        return np.asarray(list(donor_ids), dtype=int) - 1

    @classmethod
    def from_cohort(cls, c, dataset_id: str = "synthetic-v1") -> Dataset:
        donors = [DonorView(d["id"], d["population"], d["cohort_id"], d["family_id"],
                            d["consent"], d["withdrawn"]) for d in c.donors]
        v = c.variants
        coords = [(str(v["chrom"][i]), int(v["pos"][i]), str(v["ref"][i]), str(v["alt"][i]))
                  for i in range(len(v["maf"]))] if "pos" in v else []
        return cls(c.genotypes, np.asarray(v["maf"]), donors, c.relationships,
                   list(c.planted), dataset_id, coords)

    @classmethod
    def synthetic(cls, **kwargs) -> Dataset:
        from app.data.synth import generate

        return cls.from_cohort(generate(**kwargs))
