"""A dataset may only be called real if the cohort file's OWN metadata says so, and the
evaluation / provenance labels follow that. Plumbing is exercised with a small synthetic cohort
saved in the same file format; the labels under test come from the metadata we write."""

import hashlib
import tempfile
import warnings
from pathlib import Path

import pytest

from app.config import Settings
from app.data import real
from app.data.synth import generate
from app.service import bootstrap
from redteam import run_eval

warnings.filterwarnings("ignore", message="GG_MASTER_KEY")
REAL_META = {"source": "1000 Genomes (IGSR)", "genotypes_real": True, "consent_simulated": True,
             "family_enriched": True, "reference_assembly": "GRCh37"}


def _cohort_file(d: str, meta: dict) -> str:
    c = generate(n_donors=600, n_variants=3000, n_families=100, seed=5)
    out = Path(d) / "c.npz"
    real.save_cohort(c, meta, out)
    return str(out)


def test_read_meta_round_trips_and_defaults_to_empty():
    with tempfile.TemporaryDirectory() as d:
        assert real.read_meta(_cohort_file(d, REAL_META)) == REAL_META
        import numpy as np
        np.savez_compressed(Path(d) / "bare.npz", genotypes=np.zeros((2, 2), dtype=np.int8))
        assert real.read_meta(Path(d) / "bare.npz") == {}


def test_eval_on_a_cohort_marked_real_is_labelled_real_and_hashed():
    with tempfile.TemporaryDirectory() as d:
        f = _cohort_file(d, REAL_META)
        res = run_eval.run_all(quick=True, cohort=f)
        m = res["meta"]
        assert m["dataset"] == "real_1000g" and m["genotypes_real"] and m["consent_simulated"]
        assert m["cohort_sha256"] == hashlib.sha256(Path(f).read_bytes()).hexdigest()
        assert res["robustness"] == []  # the seed-robustness section is synthetic-only
        md = run_eval.to_markdown(res)
        assert "real genotypes" in md and "family-enriched" in md
        assert "Not run for a real cohort" in md
        assert "All data is synthetic" not in md
        assert "make eval-real" in md


def test_eval_on_a_cohort_not_marked_real_is_never_called_real():
    with tempfile.TemporaryDirectory() as d:
        f = _cohort_file(d, {"source": "someone's file"})
        res = run_eval.run_all(quick=True, cohort=f)
        assert res["meta"]["dataset"] == "custom_cohort" and not res["meta"]["genotypes_real"]
        md = run_eval.to_markdown(res)
        assert "not marked as real genotypes" in md and "**real genotypes" not in md
        assert "do not describe these as real-data results" in md


def test_default_eval_is_unchanged_and_synthetic():
    res = run_eval.run_all(quick=True)
    assert res["meta"]["dataset"] == "synthetic" and res["robustness"]
    assert "Dataset: **synthetic**" in run_eval.to_markdown(res)


def _boot(cohort_file):
    s = Settings()
    s.db_path = ":memory:"
    s.real_cohort_file = cohort_file
    return bootstrap(s)


def test_app_provenance_follows_the_files_metadata_not_its_existence():
    with tempfile.TemporaryDirectory() as d:
        real_svc = _boot(_cohort_file(d, REAL_META))
        assert real_svc.provenance["genotypes"] == "real_vcf"
        assert "Real VCF genotypes" in real_svc.provenance["genotypes_label"]
        assert "source not independently authenticated" in real_svc.provenance["genotypes_label"]
        assert real_svc.provenance["consent"] == "simulated"  # consent is never real
        assert real_svc.provenance["reference_assembly"] == "GRCh37"
        fake_svc = _boot(_cohort_file(d, {"source": "unknown"}))
        assert fake_svc.provenance["genotypes"] == "custom"
        assert "Real" not in fake_svc.provenance["genotypes_label"]
    assert _boot("").provenance["genotypes"] == "synthetic"


def test_health_reports_synthetic_only_correctly_for_each_kind():
    from starlette.testclient import TestClient

    from app.api import create_app
    with tempfile.TemporaryDirectory() as d:
        for meta, expect in ((REAL_META, False), ({"source": "x"}, False), (None, True)):
            svc = _boot(_cohort_file(d, meta) if meta else "")
            h = TestClient(create_app(svc)).get("/health").json()
            assert h["synthetic_data_only"] is expect, (meta, h["provenance"])


def test_exposure_note_names_the_pedigree_file_only_for_real_data():
    from tests.helpers import DEMO_REQ, RESEARCHER, make_service
    svc = make_service()
    d = svc.submit(svc.authenticate(RESEARCHER), DEMO_REQ)
    assert "synthetic pedigree" in svc.exposure(d["id"])["model"]
    with tempfile.TemporaryDirectory() as dd:
        rs = _boot(_cohort_file(dd, REAL_META))
        u = rs.create_requester("R", "researcher", "registered", "Lab", "k-real")
        assert u
        d2 = rs.submit(rs.authenticate("k-real"), DEMO_REQ)
        model = rs.exposure(d2["id"])["model"]
        assert "pedigree file" in model and model.startswith("SIMULATED")



def _dataset_policy_meta(*, bad_digest=False):
    import json

    policy_path = Path(__file__).resolve().parents[2] / "docs" / "policies" / "igsr-1000-genomes-public-release.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    return {
        "source": "1000 Genomes (IGSR)",
        "genotypes_real": True,
        "consent_simulated": False,
        "consent_basis": "dataset_policy",
        "consent_policy": {
            "policy_id": policy["policy_id"],
            "source_url": policy["source_url"],
            "scope": policy["scope"],
            "review_status": policy["review_status"],
            "terms_summary": policy["terms_summary"],
            "withdrawal_supported": policy["withdrawal_supported"],
            "not_individual_consent": True,
        },
        "consent_policy_source_file": policy_path.name,
        "consent_policy_source_sha256": ("0" * 64 if bad_digest else digest),
        "consent_records_matched": 0,
        "dataset_policy_samples_scoped": 600,
        "source_vcf_sha256": "a" * 64,
        "source_sample_metadata_sha256": "b" * 64,
        "source_vcf_file": "public-test.vcf.gz",
    }


def test_dataset_policy_provenance_requires_matching_source_document_hash():
    with tempfile.TemporaryDirectory() as d:
        svc = _boot(_cohort_file(d, _dataset_policy_meta()))
        from app.api import create_app
        from starlette.testclient import TestClient

        health = TestClient(create_app(svc)).get("/health").json()
        assert health["consent_provenance_consistent"] is True
        assert health["participant_consent_records_matched"] == 0
        assert health["dataset_policy_samples_scoped"] == 600
        assert health["provenance"]["consent_source"] is None
        assert health["provenance"]["consent_policy_source_sha256"] == _dataset_policy_meta()["consent_policy_source_sha256"]


def test_dataset_policy_provenance_rejects_wrong_source_document_hash():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(ValueError, match="SHA-256 does not match"):
            _boot(_cohort_file(d, _dataset_policy_meta(bad_digest=True)))
