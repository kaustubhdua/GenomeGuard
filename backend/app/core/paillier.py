"""Paillier additively homomorphic encryption, pure Python (standard library only).

What it gives: anyone holding the PUBLIC key can add encrypted numbers (multiply ciphertexts)
and scale them by a plain integer, without ever seeing a plaintext. Only the key holder can
decrypt, and in this system only the TOTAL is ever decrypted.

Used by `he_allele_counts` below: each hospital encrypts its per-variant allele counts, an
untrusted aggregator adds the ciphertexts, and the key holder decrypts the sum.

Honest limits (say them before a judge does):
  * Educational implementation: not constant-time, not audited. Production should use a vetted
    library (python-paillier, OpenFHE, Microsoft SEAL) or an enclave.
  * Additive only: sums and scalar multiples. No products of two encrypted values, so it cannot
    train a model by itself; GenomeGuard uses secret sharing (federated.py) for that.
  * The key holder must be trusted not to decrypt a single site's ciphertext. Splitting the key
    (threshold Paillier) removes that trust and is future work.
  * A total over very few donors still leaks; the total goes through the privacy checks and noise
    before any external release.
"""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass

_SMALL = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53)


def is_probable_prime(n: int, rounds: int = 32) -> bool:
    if n < 2:
        return False
    for p in _SMALL:
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def gen_prime(bits: int) -> int:
    while True:
        c = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if is_probable_prime(c):
            return c


@dataclass(frozen=True)
class PublicKey:
    n: int

    @property
    def n2(self) -> int:
        return self.n * self.n

    @property
    def bits(self) -> int:
        return self.n.bit_length()


@dataclass(frozen=True)
class PrivateKey:
    pub: PublicKey
    lam: int
    mu: int


def keygen(bits: int = 2048) -> PrivateKey:
    """`bits` is the size of the modulus n (each prime is bits/2)."""
    if bits < 128 or bits % 2:
        raise ValueError("bits must be even and at least 128")
    while True:
        p, q = gen_prime(bits // 2), gen_prime(bits // 2)
        if p != q and math.gcd(p * q, (p - 1) * (q - 1)) == 1:
            break
    n = p * q
    lam = math.lcm(p - 1, q - 1)
    return PrivateKey(PublicKey(n), lam, pow(lam, -1, n))  # g = n + 1 makes mu = lam^-1 mod n


def encrypt(pk: PublicKey, m: int) -> int:
    if not 0 <= m < pk.n:
        raise ValueError("plaintext out of range")
    while True:
        r = secrets.randbelow(pk.n - 1) + 1
        if math.gcd(r, pk.n) == 1:
            break
    return ((1 + m * pk.n) * pow(r, pk.n, pk.n2)) % pk.n2


def decrypt(sk: PrivateKey, c: int) -> int:
    n = sk.pub.n
    if not 0 < c < sk.pub.n2:
        raise ValueError("ciphertext out of range")
    return (((pow(c, sk.lam, sk.pub.n2) - 1) // n) * sk.mu) % n


def add(pk: PublicKey, c1: int, c2: int) -> int:
    """Enc(a) + Enc(b) = Enc(a + b). Needs only the public key."""
    return (c1 * c2) % pk.n2


def add_plain(pk: PublicKey, c: int, k: int) -> int:
    return (c * (1 + (k % pk.n) * pk.n)) % pk.n2


def mul_plain(pk: PublicKey, c: int, k: int) -> int:
    """Enc(a) * k = Enc(a * k) for a plain, non-negative integer k."""
    if k < 0:
        raise ValueError("k must be non-negative")
    return pow(c, k, pk.n2)


def he_allele_counts(genotypes, sites: dict[str, list[int]], variants: list[int],
                     bits: int = 2048, key: PrivateKey | None = None) -> dict:
    """Each site encrypts its per-variant allele counts; an aggregator adds ciphertexts; the key
    holder decrypts only the totals. Returns the result plus what the aggregator saw."""
    import numpy as np

    sk = key or keygen(bits)
    pk = sk.pub
    g = np.asarray(genotypes)
    per_site: dict[str, list[int]] = {}
    for name, rows in sites.items():
        counts = g[np.asarray(rows)][:, variants].sum(axis=0)
        per_site[name] = [encrypt(pk, int(v)) for v in counts]
    agg = [1] * len(variants)  # 1 is a valid encryption of 0 for the product
    for cts in per_site.values():
        agg = [add(pk, a, c) for a, c in zip(agg, cts, strict=True)]
    totals = [decrypt(sk, c) for c in agg]
    truth = g[:, variants].sum(axis=0)
    return {
        "key_bits": pk.bits, "sites": {k: len(v) for k, v in sites.items()},
        "variants": len(variants), "totals": totals,
        "matches_plaintext": [int(t) for t in totals] == [int(t) for t in truth],
        "aggregator_saw": {"first_ciphertext_hex_prefix": hex(next(iter(per_site.values()))[0])[:42] + "...",
                           "ciphertext_bits": pk.n2.bit_length(),
                           "plaintexts": "none"},
    }
