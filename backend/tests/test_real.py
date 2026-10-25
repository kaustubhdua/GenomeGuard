import base64
import gzip
import tempfile
from pathlib import Path

import numpy as np
import pytest

from app.config import Settings
from app.data import real
from app.service import bootstrap

PED = "\n".join([
    "Family ID\tIndividual ID\tPaternal ID\tMaternal ID\tGender\tPhenotype\tPopulation",
    "F1\tdad\t0\t0\t1\t0\tGBR",
    "F1\tmum\t0\t0\t2\t0\tGBR",
    "F1\tkid1\tdad\tmum\t1\t0\tGBR",
    "F1\tkid2\tdad\tmum\t2\t0\tGBR",
] + [f"U{i}\ts{i}\t0\t0\t{1 + i % 2}\t0\t{'GBR' if i % 2 else 'YRI'}" for i in range(40)]) + "\n"

SAMPLES = ["dad", "mum", "kid1", "kid2"] + [f"s{i}" for i in range(40)]

def test_high_coverage_population_pedigree_panel_format():
    text = "\n".join([
        "FamilyID SampleID FatherID MotherID Sex Population Superpopulation",
        "F1 father 0 0 1 YRI AFR",
        "F1 mother 0 0 2 YRI AFR",
        "F1 child father mother 1 YRI AFR",
        "U2 unrelated 0 0 2 GBR EUR",
    ]) + "\n"
    info = real.parse_ped(text)
    assert info["child"]["father"] == "father"
    assert info["child"]["mother"] == "mother"
    assert info["child"]["family"] == "F1"
    assert info["child"]["pop"] == "YRI"
    assert info["unrelated"]["pop"] == "GBR"


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
        assert meta["source_vcf_file"] == "t.vcf.gz"
        assert len(meta["source_vcf_sha256"]) == 64
        assert len(meta["source_sample_metadata_sha256"]) == 64
        assert meta["source_sample_metadata_file"] == "provided-sample-metadata"
        assert meta["pedigree_relationships_present"] is True
        assert meta["build_parameters"] == {
            "requested_samples": 44, "max_variants": 50, "keep_prob": 1.0,
            "rare_maf": 0.01, "withdrawn_rate": 0.03,
        }
        assert c.genotypes.shape == (44, 50)
        assert all("consent" in x for x in c.donors)
        assert meta["relative_pairs"] == 5  # 2 parents x 2 kids + the sibling pair
        real.save_cohort(c, meta, out)
        c2 = real.load_cohort(out)
        assert np.array_equal(c.genotypes, c2.genotypes)
        assert c.relationships == c2.relationships
        assert np.allclose(c.variants["maf"], c2.variants["maf"])


def test_non_demo_bootstrap_refuses_real_genotypes_with_simulated_consent():
    with tempfile.TemporaryDirectory() as d:
        v, out = Path(d) / "t.vcf.gz", Path(d) / "cohort.npz"
        make_vcf(v)
        cohort, meta = real.build_cohort(v, PED, n_samples=44, max_variants=50,
                                         keep_prob=1.0, seed=7)
        real.save_cohort(cohort, meta, out)
        settings = Settings(
            db_path=":memory:",
            demo_mode=False,
            allow_tamper_demo=False,
            admin_api_key="a-unique-production-admin-secret-long-enough",
            master_key=base64.b64encode(b"x" * 32).decode(),
            real_cohort_file=str(out),
            dataset_id="test-approved-cohort",
        )
        with pytest.raises(ValueError, match="simulated or missing consent"):
            bootstrap(settings)


def test_build_cohort_uses_explicit_source_matched_consent_records():
    with tempfile.TemporaryDirectory() as d:
        v = Path(d) / "t.vcf.gz"
        make_vcf(v)
        records = {
            sample: {"use": "GRU", "disease": None, "modifiers": [],
                     "population": None, "consent_date": "2024-01-15", "withdrawn": False}
            for sample in SAMPLES
        }
        c, meta = real.build_cohort(v, PED, n_samples=44, max_variants=50, keep_prob=1.0,
                                    seed=3, consent_records=records)
        assert meta["genotypes_real"] is True
        assert meta["consent_simulated"] is False
        assert meta["consent_records_matched"] == 44
        assert all(d["consent"]["use"] == "GRU" and not d["withdrawn"] for d in c.donors)
        assert all(d["consent"]["consent_date"] == "2024-01-15" for d in c.donors)


def test_build_cohort_refuses_missing_or_malformed_consent_records():
    with tempfile.TemporaryDirectory() as d:
        v = Path(d) / "t.vcf.gz"
        make_vcf(v)
        with pytest.raises(ValueError, match="no explicit record"):
            real.build_cohort(v, PED, n_samples=44, max_variants=50, keep_prob=1.0,
                              consent_records={"dad": {"use": "GRU"}})
        bad = {sample: {"use": "GRU", "disease": None, "modifiers": [],
                        "population": None, "consent_date": "not-a-date", "withdrawn": False}
               for sample in SAMPLES}
        with pytest.raises(ValueError, match="invalid consent_date"):
            real.build_cohort(v, PED, n_samples=44, max_variants=50, keep_prob=1.0,
                              consent_records=bad)


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


def test_dataset_public_release_policy_is_real_source_provenance_not_fake_personal_consent():
    with tempfile.TemporaryDirectory() as d:
        v, out, policy_path = Path(d) / "t.vcf.gz", Path(d) / "cohort.npz", Path(d) / "policy.json"
        make_vcf(v)
        policy = {
            "policy_id": "test-public-release-v1",
            "source_url": "https://example.org/source-terms",
            "scope": "dataset",
            "duo_use": "GRU",
            "duo_modifiers": [],
            "withdrawal_supported": False,
            "review_status": "source_documented_not_legal_review",
        }
        policy_path.write_text(__import__("json").dumps(policy), encoding="utf-8")
        cohort, meta = real.build_cohort(
            v, PED, n_samples=44, max_variants=50, keep_prob=1.0, seed=8,
            consent_policy=policy, consent_source_file=str(policy_path),
        )
        assert meta["genotypes_real"] is True
        assert meta["consent_simulated"] is False
        assert meta["consent_basis"] == "dataset_policy"
        assert meta["consent_records_matched"] == 44
        assert meta["consent_policy"]["not_individual_consent"] is True
        assert len(meta["consent_records_sha256"]) == 64
        assert all(d["consent"]["consent_basis"] == "dataset_policy" for d in cohort.donors)
        assert all(d["consent"]["consent_date"] is None for d in cohort.donors)
        assert all(d["consent"]["source_policy_id"] == "test-public-release-v1"
                   for d in cohort.donors)
        real.save_cohort(cohort, meta, out)
        assert real.read_meta(out)["consent_basis"] == "dataset_policy"


def test_production_bootstrap_preserves_dataset_policy_provenance():
    with tempfile.TemporaryDirectory() as d:
        v, out, policy_path = Path(d) / "t.vcf.gz", Path(d) / "cohort.npz", Path(d) / "policy.json"
        make_vcf(v)
        policy = {
            "policy_id": "test-public-release-v1",
            "source_url": "https://example.org/source-terms",
            "scope": "dataset",
            "duo_use": "GRU",
            "duo_modifiers": [],
            "withdrawal_supported": False,
            "review_status": "source_documented_not_legal_review",
        }
        policy_path.write_text(__import__("json").dumps(policy), encoding="utf-8")
        cohort, meta = real.build_cohort(
            v, PED, n_samples=44, max_variants=50, keep_prob=1.0, seed=9,
            consent_policy=policy, consent_source_file=str(policy_path),
        )
        real.save_cohort(cohort, meta, out)
        settings = Settings(
            db_path=":memory:", demo_mode=False, allow_tamper_demo=False,
            admin_api_key="a-unique-production-admin-secret-long-enough",
            master_key=base64.b64encode(b"x" * 32).decode(),
            real_cohort_file=str(out), dataset_id="test-public-source-policy",
        )
        svc = bootstrap(settings)
        assert svc.provenance["genotypes"] == "real_vcf"
        assert svc.provenance["consent"] == "source_policy"
        assert svc.provenance["consent_records_matched"] == 44
        assert svc.provenance["consent_policy"]["not_individual_consent"] is True
        assert "not participant-specific" in svc.provenance["consent_label"]
        assert len(svc.provenance["source_vcf_sha256"]) == 64
        assert len(svc.provenance["source_sample_metadata_sha256"]) == 64
        assert len(svc.provenance["consent_records_sha256"]) == 64
        assert svc.provenance["dataset_id"] == "test-public-source-policy"


# ---- the high-coverage release's pedigree: whitespace separated, different header names ----
PED_HC = "\n".join([
    "FamilyID SampleID FatherID MotherID Sex Population Superpopulation",
    "T1 dad 0 0 1 GBR EUR",
    "T1 mum 0 0 2 GBR EUR",
    "T1 kid1 dad mum 1 GBR EUR",
    "T2 d2 0 0 1 YRI AFR",
    "T2 m2 0 0 2 YRI AFR",
    "T2 k2 d2 m2 2 YRI AFR",
    "T3 d3 0 0 1 CHB EAS",
    "T3 m3 0 0 2 CHB EAS",
    "T3 k3 d3 m3 2 CHB EAS",
] + [f"U{i} s{i} 0 0 {1 + i % 2} {'GBR' if i % 2 else 'YRI'} EUR" for i in range(40)]) + "\n"
SAMPLES_HC = ["dad", "mum", "kid1", "d2", "m2", "k2", "d3", "m3", "k3"] + [f"s{i}" for i in range(40)]


def test_parse_ped_whitespace_separated_with_alternate_headers():
    info = real.parse_ped(PED_HC)
    assert info["kid1"] == {"family": "T1", "father": "dad", "mother": "mum", "pop": "GBR"}
    assert info["dad"]["father"] is None and info["s2"]["pop"] == "YRI"
    assert len(info) == 9 + 40


def test_parse_ped_names_the_missing_column():
    with pytest.raises(ValueError, match="mother"):
        real.parse_ped("FamilyID SampleID FatherID Population\nF1 a 0 GBR\n")
    with pytest.raises(ValueError):
        real.parse_ped("")


def test_family_first_takes_whole_families_so_real_relatives_exist():
    info = real.parse_ped(PED_HC)
    rng = np.random.default_rng(3)
    chosen = real.choose_samples(info, SAMPLES_HC, 12, rng, family_first=True)
    assert len(chosen) == 12 and len(set(chosen)) == 12
    fams = {}
    for s in chosen:
        fams.setdefault(info[s]["family"], []).append(s)
    trios = [f for f, m in fams.items() if f.startswith("T")]
    assert len(trios) == 3 and all(len(fams[f]) == 3 for f in trios)  # whole trios, never a half
    assert len(real.relationships_from_pedigree(info, chosen)) == 6  # 2 parent-child pairs per trio; the parents are unrelated


def test_family_first_with_a_small_budget_never_splits_a_family():
    info = real.parse_ped(PED_HC)
    for seed in range(8):
        chosen = real.choose_samples(info, SAMPLES_HC, 7, np.random.default_rng(seed), True)
        per_fam = {}
        for s in chosen:
            per_fam.setdefault(info[s]["family"], []).append(s)
        assert all(len(m) == 3 for f, m in per_fam.items() if f.startswith("T"))


def test_random_sampling_is_still_available_and_deterministic():
    info = real.parse_ped(PED_HC)
    a = real.choose_samples(info, SAMPLES_HC, 10, np.random.default_rng(5), False)
    b = real.choose_samples(info, SAMPLES_HC, 10, np.random.default_rng(5), False)
    assert a == b and len(a) == 10


def test_build_cohort_family_first_records_enrichment_and_finds_real_relatives():
    with tempfile.TemporaryDirectory() as d:
        v = Path(d) / "t.vcf.gz"
        lines = ["##fileformat=VCFv4.1",
                 "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t" + "\t".join(SAMPLES_HC)]
        rng = np.random.default_rng(0)
        for i in range(200):
            gts = [f"{int(rng.random() < 0.2)}|{int(rng.random() < 0.2)}" for _ in SAMPLES_HC]
            lines.append("\t".join(["22", str(1000 + i), ".", "A", "G", ".", "PASS", ".", "GT", *gts]))
        with gzip.open(v, "wt") as f:
            f.write("\n".join(lines) + "\n")
        c, meta = real.build_cohort(v, PED_HC, n_samples=15, max_variants=100, keep_prob=1.0,
                                    seed=4, family_first=True)
        assert meta["family_enriched"] is True and meta["relative_pairs"] == 6
        assert meta["genotypes_real"] and meta["consent_simulated"]
        c2, meta2 = real.build_cohort(v, PED_HC, n_samples=15, max_variants=100, keep_prob=1.0,
                                      seed=4)
        assert meta2["family_enriched"] is False


# ---- the public Phase 3 panel has sample/population labels, not pedigree columns ----
PHASE3_PANEL = """sample pop super_pop gender
HG00096 GBR EUR male
HG00097 GBR EUR female
NA12340 YRI AFR male
"""


def test_parse_official_phase3_panel_without_private_working_pedigree():
    info = real.parse_ped(PHASE3_PANEL)
    assert info["HG00096"] == {
        "family": "HG00096", "father": None, "mother": None, "pop": "GBR"
    }
    assert info["NA12340"]["pop"] == "YRI"
    assert real.relationships_from_pedigree(info, ["HG00096", "HG00097", "NA12340"]) == []


def test_unrelated_phase3_style_panel_does_not_claim_family_enrichment():
    """Family-first sampling must not imply enrichment when the source has no pedigrees."""
    with tempfile.TemporaryDirectory() as d:
        v = Path(d) / "unrelated.vcf.gz"
        make_vcf(v)
        panel = "sample pop super_pop gender\n" + "\n".join(
            f"{sample} GBR EUR male" for sample in SAMPLES
        ) + "\n"
        _, meta = real.build_cohort(v, panel, n_samples=44, max_variants=50, keep_prob=1.0,
                                    seed=7, family_first=True)
        assert meta["relative_pairs"] == 0
        assert meta["family_enriched"] is False
