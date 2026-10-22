import numpy as np
import pytest

from app.core import federated as fed


def test_shares_reconstruct_exactly():
    v = np.array([3.0, -7.5, 0.0, 1234.25])
    shares = fed.share(v, 4)
    assert len(shares) == 4
    total = [sum(col) % fed.P for col in zip(*shares, strict=True)]
    assert np.allclose(fed.decode(total), v, atol=2 / fed.SCALE)


def test_single_share_looks_uniform_not_secret():
    """One share of an all-zero secret is still spread across the whole modulus."""
    s = fed.share(np.zeros(2000), 3)[0]
    frac = np.array(s, dtype=float) / fed.P
    assert 0.45 < frac.mean() < 0.55
    assert frac.min() < 0.05 and frac.max() > 0.95


def test_shares_differ_between_runs():
    v = np.array([5.0, 5.0])
    assert fed.share(v, 3)[0] != fed.share(v, 3)[0]


@pytest.mark.parametrize("n_sites", [2, 3, 7])
def test_secure_sum_equals_plain_sum(n_sites):
    rng = np.random.default_rng(n_sites)
    vecs = [rng.normal(0, 50, 20) for _ in range(n_sites)]
    total, tr = fed.secure_sum(vecs)
    assert np.allclose(total, np.sum(vecs, axis=0), atol=n_sites / fed.SCALE)
    assert tr.n_parties == n_sites


def test_needs_two_parties():
    with pytest.raises(ValueError):
        fed.share(np.ones(3), 1)


def test_federated_frequencies_match_pooled_exactly():
    rng = np.random.default_rng(0)
    g = rng.integers(0, 3, size=(90, 12)).astype(np.int8)
    sites = {"A": list(range(0, 30)), "B": list(range(30, 70)), "C": list(range(70, 90))}
    idx = [0, 3, 5, 11]
    freq, info = fed.federated_allele_frequencies(g, sites, idx)
    assert np.allclose(freq, g[:, idx].sum(axis=0) / (2.0 * 90), atol=1e-6)
    assert info["sites"] == 3 and info["chromosomes"] == 180


def test_federated_logreg_matches_centralised():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(240, 4))
    y = (rng.random(240) < fed._sigmoid(X @ np.array([1.5, -1.0, 0.5, 0.0]))).astype(float)
    parts = [(X[i::3], y[i::3]) for i in range(3)]
    w_f = fed.federated_logreg(parts, rounds=60)
    w_c = fed.centralised_logreg(X, y, rounds=60)
    assert np.abs(w_f - w_c).max() < 1e-4
    assert fed.auc(X @ w_f, y) > 0.7


def test_noisy_total_scale():
    rng = np.random.default_rng(2)
    noise = fed.noisy_total(np.zeros(20000), sensitivity=2.0, epsilon=1.0, rng=rng)
    assert abs(np.mean(np.abs(noise)) - 2.0) < 0.1  # E|Laplace(b)| = b
    with pytest.raises(ValueError):
        fed.noisy_total(np.zeros(3), 2.0, 0.0, rng)


def test_auc_perfect_and_random():
    y = np.array([0, 0, 1, 1.0])
    assert fed.auc(np.array([0.1, 0.2, 0.8, 0.9]), y) == 1.0
    assert fed.auc(np.array([0.1, 0.9, 0.2, 0.8]), y) == 0.5


def test_demo_runs_and_reports_equivalence():
    out = fed.demo(seed=3)
    assert out["allele_frequency"]["max_abs_error_vs_pooled"] < 1e-5
    assert out["logistic_regression"]["max_weight_difference_vs_centralised"] < 1e-3
    assert len(out["sites"]) >= 2


def test_he_demo_matches_plaintext_and_is_cached():
    from app.core.federated import he_demo

    a = he_demo(seed=5, variants=3, bits=512)
    assert a["matches_plaintext"] is True and a["key_bits"] == 512
    assert he_demo(seed=5, variants=3, bits=512) is a
