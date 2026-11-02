import pytest

pytest.importorskip("sklearn")
pytest.importorskip("pandas")

from app.ml.clinvar_vep_train import label, numeric_af


def test_clinvar_binary_label_policy():
    assert label("Pathogenic") == 1
    assert label("Likely pathogenic") == 1
    assert label("Pathogenic/Likely pathogenic") == 1
    assert label("Benign") == 0
    assert label("Likely benign") == 0
    assert label("Benign/Likely benign") == 0
    assert label("Uncertain significance") is None
    assert label("Pathogenic/Benign") is None
    assert label("Conflicting classifications of pathogenicity") is None


def test_population_frequency_extraction_is_bounded():
    assert numeric_af([{"frequencies": {"A": {"gnomad": 0.02, "1000G": 0.01}}}]) == 0.02
    assert numeric_af([{"frequencies": {"A": {"unknown": 1.4}}}]) != 1.4
    assert numeric_af([]) != numeric_af([])
