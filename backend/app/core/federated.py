"""Federated analysis with secure aggregation (simulated hospitals).

The idea: hospitals keep their raw genomes. Each site computes statistics locally and the sites
combine them with ADDITIVE SECRET SHARING, so no party (including the coordinator) ever sees any
single site's counts or gradients: only the sum.

Protocol (per aggregation round, n sites, vectors fixed-point encoded modulo P = 2^61 - 1):
  1. Site i splits its vector x_i into n random shares that add up to x_i (mod P).
  2. Site i sends share j to site j (keeps one for itself). Any n-1 shares look uniformly random.
  3. Each site adds the shares it received and publishes that partial sum.
  4. The coordinator adds the n partial sums: that equals sum_i x_i, and nothing else is revealed.

What this does and does NOT give you (say this plainly to judges):
  + Honest-but-curious sites: a single site, or the coordinator, learns only the total.
  - Not secure if all other n-1 sites collude (they can reconstruct the missing site's vector).
  - No dropout handling and no protection against a site sending malicious values.
  - The TOTAL itself still leaks (e.g. membership signal in frequencies), so for releases outside
    the consortium add differential-privacy noise to the total (`noisy_total`), exactly as in
    app/core/transform.py. Secure aggregation protects inputs; DP protects outputs.
  - This is NOT homomorphic encryption and not a secure enclave. Those are future work.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import numpy as np

P = (1 << 61) - 1  # Mersenne prime modulus
SCALE = 1 << 20  # fixed-point scale: 2^-20 resolution


def encode(vec: np.ndarray) -> list[int]:
    """Real vector -> residues mod P (negative numbers wrap around)."""
    return [int(round(float(x) * SCALE)) % P for x in np.asarray(vec, dtype=float).ravel()]


def decode(residues: list[int]) -> np.ndarray:
    half = P // 2
    return np.array([(r if r <= half else r - P) / SCALE for r in residues], dtype=float)


def share(vec: np.ndarray, n_parties: int) -> list[list[int]]:
    """Split `vec` into n additive shares mod P using a cryptographic RNG."""
    if n_parties < 2:
        raise ValueError("secret sharing needs at least 2 parties")
    secret = encode(vec)
    shares = [[secrets.randbelow(P) for _ in secret] for _ in range(n_parties - 1)]
    last = [(s - sum(col)) % P for s, col in zip(secret, zip(*shares, strict=True), strict=True)]
    return [*shares, last]


@dataclass
class AggregationTranscript:
    """What each party saw, kept so the demo/tests can show nothing but random-looking numbers."""

    n_parties: int
    messages_per_party: int
    sample_message: list[int]  # one share a curious site received (look: uniformly random)


def secure_sum(vectors: list[np.ndarray]) -> tuple[np.ndarray, AggregationTranscript]:
    """Simulate the full protocol and return (the exact sum, transcript)."""
    n = len(vectors)
    outbox = [share(v, n) for v in vectors]  # outbox[i][j] = share of site i for site j
    partial = []
    for j in range(n):
        received = [outbox[i][j] for i in range(n)]
        partial.append([sum(col) % P for col in zip(*received, strict=True)])
    total = [sum(col) % P for col in zip(*partial, strict=True)]
    # the sample message is what site 0 got from site 1: a single share, not a secret
    return decode(total), AggregationTranscript(n, n - 1, outbox[1][0][:5])


def laplace_noise(scale: float, size: int, rng: np.random.Generator) -> np.ndarray:
    return rng.laplace(0.0, scale, size)


def noisy_total(total: np.ndarray, sensitivity: float, epsilon: float,
                rng: np.random.Generator) -> np.ndarray:
    """Add Laplace(sensitivity / epsilon) noise to an aggregate before it leaves the consortium."""
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    return total + laplace_noise(sensitivity / epsilon, total.shape[0], rng)


# ---------------------------------------------------------------- federated allele frequencies

def split_into_sites(cohort_ids: list[str]) -> dict[str, list[int]]:
    """Group donor row indices by cohort id: each cohort plays one hospital."""
    sites: dict[str, list[int]] = {}
    for i, c in enumerate(cohort_ids):
        sites.setdefault(c, []).append(i)
    return sites


def federated_allele_frequencies(genotypes: np.ndarray, sites: dict[str, list[int]],
                                 variant_idx: list[int]) -> tuple[np.ndarray, dict]:
    """Pooled alt-allele frequency for `variant_idx`, computed without any site sharing its rows.
    Each site contributes (alt allele counts per variant, number of chromosomes)."""
    vecs = []
    for rows in sites.values():
        g = genotypes[np.ix_(rows, variant_idx)].astype(float)
        vecs.append(np.concatenate([g.sum(axis=0), [2.0 * len(rows)]]))
    total, tr = secure_sum(vecs)
    freq = total[:-1] / total[-1]
    return freq, {"sites": len(sites), "chromosomes": int(total[-1]),
                  "sample_share_seen_by_a_site": tr.sample_message}


# ---------------------------------------------------------------- federated logistic regression

def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def federated_logreg(site_data: list[tuple[np.ndarray, np.ndarray]], rounds: int = 200,
                     lr: float = 0.5, l2: float = 1e-3) -> np.ndarray:
    """Train logistic regression where each site keeps (X, y) private. Every round the sites
    compute local gradient sums and securely sum them; only the total gradient is revealed.
    Mathematically identical to centralised full-batch gradient descent (up to 2^-20 rounding)."""
    d = site_data[0][0].shape[1]
    w = np.zeros(d)
    for _ in range(rounds):
        vecs = []
        for X, y in site_data:
            g = X.T @ (_sigmoid(X @ w) - y)
            vecs.append(np.concatenate([g, [float(len(y))]]))
        total, _ = secure_sum(vecs)
        n = total[-1]
        w -= lr * (total[:-1] / n + l2 * w)
    return w


def centralised_logreg(X: np.ndarray, y: np.ndarray, rounds: int = 200, lr: float = 0.5,
                       l2: float = 1e-3) -> np.ndarray:
    """Reference implementation on pooled data, used only to check the federated one."""
    w = np.zeros(X.shape[1])
    for _ in range(rounds):
        w -= lr * (X.T @ (_sigmoid(X @ w) - y) / len(y) + l2 * w)
    return w


def auc(scores: np.ndarray, y: np.ndarray) -> float:
    """Rank-based AUC (probability a random positive outscores a random negative)."""
    order = scores.argsort()
    ranks = np.empty(len(scores))
    ranks[order] = np.arange(1, len(scores) + 1)
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def demo(seed: int = 1337) -> dict:
    """Self-contained demonstration on the synthetic cohort; also served at /federated/demo.
    The phenotype is simulated from a few variants, so there is a real signal to recover."""
    from app.data.synth import generate

    c = generate(n_donors=600, n_variants=300, n_families=120, seed=seed)
    cohorts = [d["cohort_id"] for d in c.donors]
    sites = split_into_sites(cohorts)
    g = c.genotypes.astype(float)
    var = list(range(25))
    fed_freq, info = federated_allele_frequencies(c.genotypes, sites, var)
    pooled = c.genotypes[:, var].sum(axis=0) / (2.0 * len(c.donors))

    rng = np.random.default_rng(seed)
    informative = [j for j in range(g.shape[1]) if c.variants["maf"][j] > 0.15][:8]
    beta = rng.normal(0.0, 0.9, len(informative))
    X = g[:, informative]
    X = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-9)
    prob = _sigmoid(X @ beta - 0.2)
    y = (rng.random(len(prob)) < prob).astype(float)
    site_data = [(X[rows], y[rows]) for rows in sites.values()]
    w_fed = federated_logreg(site_data)
    w_cen = centralised_logreg(X, y)
    return {
        "note": "Simulated hospitals on SYNTHETIC data. Secure aggregation hides each site's "
                "inputs from the others; it is not homomorphic encryption or an enclave.",
        "sites": {name: len(rows) for name, rows in sites.items()},
        "allele_frequency": {"variants": len(var),
                             "max_abs_error_vs_pooled": float(np.abs(fed_freq - pooled).max()),
                             "a_share_one_site_saw": info["sample_share_seen_by_a_site"]},
        "logistic_regression": {
            "features": len(informative),
            "max_weight_difference_vs_centralised": float(np.abs(w_fed - w_cen).max()),
            "auc_federated": round(auc(X @ w_fed, y), 4),
            "auc_centralised": round(auc(X @ w_cen, y), 4),
        },
        "limits": ["all-but-one collusion breaks it", "no dropout handling",
                   "the total still needs differential privacy before external release"],
    }


if __name__ == "__main__":
    import json

    print(json.dumps(demo(), indent=2, default=float))
