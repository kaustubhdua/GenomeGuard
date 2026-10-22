# Threat model

All data is synthetic unless you build the optional real cohort (`make fetch-real`). Nothing here
claims legal compliance: GenomeGuard is **designed around the ideas of** DPDP, GDPR and HIPAA.

## What we protect

1. Donors' genotypes (and through them, their relatives who never consented).
2. Donors' consent choices, including withdrawal.
3. The integrity of the record of who got what (audit log).

## Attackers considered

| Attack | Idea | Defence | Measured by `make eval` |
|---|---|---|---|
| Differencing / tracker | Ask for a cohort with the target, then without; subtract | Differencing guard blocks the second query; noise | 100% recovery with no defence; 54.3% with the guard, equal to the 54.3% guessing baseline |
| Membership inference | Likelihood-ratio test against released frequencies | Bin, cap variants, Laplace noise, epsilon budget | AUC 0.72 on 100 raw frequencies; about 0.50 once noised at epsilon 0.5, at a large utility cost (correlation 0.04) |
| Triangulation | Many narrow queries shrinking a cohort to one person | Near-duplicate, narrowing and rate detectors, freeze | Frozen in 100% of trials at gaps up to 120 s, median 8 to 10 queries |
| Slow probing | Same as above but waiting out the 15-minute window | k_min, differencing guard, epsilon budget (the window detectors do not help) | Not frozen at 600 s gaps: reported as a limitation |
| Beacon variant scan | Ask a Beacon-style endpoint about one variant at a time, very fast | `/beacon/g_variants` runs every query through consent, risk, budget and the anomaly monitor; 15+ queries a minute throttles and 30+ freezes | `tests/test_beacon.py`, `tests/test_anomaly.py` (35 queries at 1 a second: frozen) |
| Beacon update-flip | Snapshot a beacon before and after an update, read the flips (arXiv 2001.08852) | Hide variants below the MAF floor; batch updates | Boolean flips leak less as update size grows; count level leaks far more; GenomeGuard setup shows no flips |
| Relative exposure | A released rare variant implicates carriers' relatives | Rare variants dropped; exposure shown to stewards | Simulated model, not an attack success rate |
| Stolen database file | Read genotypes from disk or a backup | AES-256-GCM per dataset, ciphertext bound to dataset and donor | `tests/test_crypto.py` |
| Tampering with history | Edit or delete a log entry | Hash chain: change breaks the chain at that entry | `tests/test_audit_chain.py`, demo step 4 |
| Prompt injection | Craft input so an LLM leaks or approves | Agents see whitelisted numbers only and decide nothing | `tests/test_agents.py` canary test |

## Thresholds (`app/core/params.py`, override with `GG_<NAME>`)

| Parameter | Default | Meaning |
|---|---|---|
| `k_min` | 20 | Never release for a cohort smaller than this |
| `rare_maf` / `maf_floor` | 0.01 | Variants below this are "rare" and dropped first |
| `min_carriers_high` | 5 | A rare variant with 1 to 4 carriers is high risk unless hidden |
| `uniqueness_medium` / `uniqueness_high` | 1% / 10% | Record-level bands |
| `signal_medium` / `signal_high` | 1.0 / 3.0 | Aggregate-level membership signal z |
| `freq_bin_width` | 0.05 | Frequency bins |
| `epsilon_budget` | 1.0 | Per requester per dataset, simple sequential composition |
| `epsilon_per_release` | 0.5 | Spent by one noised release, split across its variants |
| `max_variants_noised` | 25 | Noise grows with variant count, so release few |
| `anomaly_warn` / `throttle` / `freeze` | 0.35 / 0.55 / 0.75 | Combined anomaly score actions |
| `anomaly_window_minutes` | 15 | Sliding window |

## Limits you must state

- **Synthetic data.** Real genomes have linkage, population structure and relatives that the
  generator only approximates. Real attack success could differ in either direction.
- **Simplified attacks written by the defenders.** Treat results as evidence the mechanisms work
  as designed, not as a security proof.
- **Differential privacy is simplified.** Sequential composition, not a formal accountant. Noise
  is added to raw counts and binning is post-processing, which keeps the guarantee valid, but the
  per-release epsilon split is a design choice.
- **The hash chain makes tampering detectable, not impossible.** Someone with full database
  write access can recompute every hash. Publish the head hash outside the system (README, slide,
  the Audit page's "Save as my anchor") so a rewritten history no longer matches.
- **Encryption at rest protects a stolen file, not a compromised process.** The master key is an
  environment variable here; production needs a KMS or HSM. Transport security (TLS) comes from
  the hosting platform.
- **Secure aggregation** (`core/federated.py`) assumes honest-but-curious sites. It fails if all
  other sites collude, handles no dropouts, and does not stop a malicious site sending bad values.
  It is not homomorphic encryption and not an enclave.
- **Demo mode is deliberately insecure.** `GG_DEMO_MODE=true` publishes the demo API keys and the
  steward key at `/demo/requesters` so judges can switch roles. That is only acceptable because
  the data is synthetic. Turn it off for anything else.
- **Not modelled:** the DUO consent-form-date limit; per-jurisdiction legal tests; insider abuse
  by a steward; side channels such as timing.
- **DUO fidelity:** NAGR and NCTRL follow the project spec's wording. Run `make fetch-duo` and
  compare with the official labels before describing them as DUO terms.
