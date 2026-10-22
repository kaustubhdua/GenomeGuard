import numpy as np

from app.core import paillier as ph

KEY = ph.keygen(512)
PK = KEY.pub


def test_roundtrip_and_homomorphic_add():
    for m in (0, 1, 7, 12345, PK.n - 1):
        assert ph.decrypt(KEY, ph.encrypt(PK, m)) == m
    a, b = ph.encrypt(PK, 41), ph.encrypt(PK, 1001)
    assert ph.decrypt(KEY, ph.add(PK, a, b)) == 1042


def test_plain_ops():
    c = ph.encrypt(PK, 25)
    assert ph.decrypt(KEY, ph.add_plain(PK, c, 10)) == 35
    assert ph.decrypt(KEY, ph.mul_plain(PK, c, 4)) == 100


def test_encryption_is_randomised_and_ciphertext_hides_value():
    c1, c2 = ph.encrypt(PK, 5), ph.encrypt(PK, 5)
    assert c1 != c2 and ph.decrypt(KEY, c1) == ph.decrypt(KEY, c2) == 5
    assert c1.bit_length() > PK.n.bit_length()  # a ciphertext lives mod n^2, not as the number


def test_rejects_bad_input():
    for bad in (-1, PK.n):
        try:
            ph.encrypt(PK, bad)
        except ValueError:
            continue
        raise AssertionError("should reject")
    try:
        ph.keygen(64)
    except ValueError:
        pass
    else:
        raise AssertionError("tiny keys must be refused")


def test_primality():
    assert ph.is_probable_prime(2**61 - 1) and not ph.is_probable_prime(2**61 + 1)
    assert not ph.is_probable_prime(561)  # Carmichael number


def test_he_allele_counts_matches_plaintext_sum():
    rng = np.random.default_rng(3)
    g = rng.integers(0, 3, size=(60, 8)).astype(np.int8)
    sites = {"A": list(range(0, 20)), "B": list(range(20, 45)), "C": list(range(45, 60))}
    out = ph.he_allele_counts(g, sites, [0, 2, 5], key=KEY)
    assert out["matches_plaintext"] is True
    assert out["totals"] == [int(x) for x in g[:, [0, 2, 5]].sum(axis=0)]
    assert out["aggregator_saw"]["plaintexts"] == "none"
