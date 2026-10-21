import gzip
import tempfile
from pathlib import Path

import numpy as np
import pytest

from app.data import real

PED = "\n".join([
    "Family ID\tIndividual ID\tPaternal ID\tMaternal ID\tGender\tPhenotype\tPopulation",
    "F1\tdad\t0\t0\t1\t0\tGBR",
    "F1\tmum\t0\t0\t2\t0\tGBR",
    "F1\tkid1\tdad\tmum\t1\t0\tGBR",
    "F1\tkid2\tdad\tmum\t2\t0\tGBR",
] + [f"U{i}\ts{i}\t0\t0\t{1 + i % 2}\t0\t{'GBR' if i % 2 else 'YRI'}" for i in range(40)]) + "\n"

SAMPLES = ["dad", "mum", "kid1", "kid2"] + [f"s{i}" for i in range(40)]


def make_vcf(path: Path, n_sites=300, seed=0):
    rng = np.random.default_rng(seed)
    lines = ["##fileformat=VCFv4.1",
             "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t" + "\t".join(SAMPLES)]
    for i in range(n_sites):
        ref, alt = "A", "G"
        if i % 10 == 0:
            alt = "G,T"  # multi-allelic: must be skipped
        if i % 13 == 0:
            ref = "AT"  # indel: must be skipped
        gts = []
        for _ in SAMPLES:
            a, b = rng.random(2) < 0.2
            gts.append(f"{int(a)}|{int(b)}")
        lines.append("\t".join(["22", str(1000 + i), ".", ref, alt, ".", "PASS", ".", "GT", *gts]))
    with gzip.open(path, "wt") as f:
        f.write("\n".join(lines) + "\n")


def test_parse_ped_reads_parents_by_header_name():
    info = real.parse_ped(PED)
    assert info["kid1"]["father"] == "dad" and info["kid1"]["mother"] == "mum"
    assert info["dad"]["father"] is None
    assert info["s1"]["pop"] == "GBR" and info["s2"]["pop"] == "YRI"


def test_parse_ped_rejects_unknown_header():
    with pytest.raises(ValueError):
        real.parse_ped("a\tb\tc\n1\t2\t3\n")


def test_vcf_samples_and_filtering():
    with tempfile.TemporaryDirectory() as d:
        v = Path(d) / "t.vcf.gz"
        make_vcf(v)
        assert real.vcf_samples(v) == SAMPLES
        cols, G = real.read_vcf(v, ["dad", "kid1", "s3"], 1.0, 10_000, np.random.default_rng(0))
        assert G.shape[0] == 3 and set(np.unique(G)) <= {0, 1, 2}
        assert set(cols["alt"]) == {"G"} and set(cols["ref"]) == {"A"}  # indels/multiallelic gone
        assert G.shape[1] == len(cols["pos"]) < 300


def test_read_vcf_missing_sample_errors():
    with tempfile.TemporaryDirectory() as d:
        v = Path(d) / "t.vcf.gz"
        make_vcf(v)
        with pytest.raises(ValueError):
            real.read_vcf(v, ["nobody"], 1.0, 10, np.random.default_rng(0))


def test_relationships_from_trio():
    info = real.parse_ped(PED)
    rels = real.relationships_from_pedigree(info, ["dad", "mum", "kid1", "kid2"])
    by = {(r["donor_a"], r["donor_b"]): r for r in rels}
    assert by[(1, 3)]["relation"] == "parent" and by[(1, 3)]["shared"] == 0.5
    assert by[(3, 4)]["relation"] == "sibling" and by[(3, 4)]["shared"] == 0.5
    assert (1, 2) not in by  # the parents are unrelated to each other


def test_unrelated_samples_have_no_relationships():
    info = real.parse_ped(PED)
    assert real.relationships_from_pedigree(info, ["s1", "s2", "s3"]) == []


def test_parents_absent_from_vcf_still_link_children():
    """Children registered, parents only in the pedigree file: siblings are still found."""
    info = real.parse_ped(PED)
    rels = real.relationships_from_pedigree(info, ["kid1", "kid2"])
    assert len(rels) == 1 and rels[0]["relation"] == "sibling"


def test_build_save_load_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        v, out = Path(d) / "t.vcf.gz", Path(d) / "c.npz"
        make_vcf(v)
        c, meta = real.build_cohort(v, PED, n_samples=44, max_variants=50, keep_prob=1.0, seed=1)
        assert meta["genotypes_real"] and meta["consent_simulated"]
        assert c.genotypes.shape == (44, 50)
        assert all("consent" in x for x in c.donors)
        assert meta["relative_pairs"] == 5  # 2 parents x 2 kids + the sibling pair
        real.save_cohort(c, meta, out)
        c2 = real.load_cohort(out)
        assert np.array_equal(c.genotypes, c2.genotypes)
        assert c.relationships == c2.relationships
        assert np.allclose(c.variants["maf"], c2.variants["maf"])


def test_loaded_cohort_works_with_dataset_and_consent_engine():
    from app.core.consent import ConsentRequest, eligible_cohort
    from app.core.dataset import Dataset

    with tempfile.TemporaryDirectory() as d:
        v = Path(d) / "t.vcf.gz"
        make_vcf(v)
        c, _ = real.build_cohort(v, PED, n_samples=44, max_variants=50, keep_prob=1.0, seed=2)
        ds = Dataset.from_cohort(c, "real-test")
        res = eligible_cohort(ConsentRequest(purpose="general_research"), ds.donors)
        assert res.considered == 44
