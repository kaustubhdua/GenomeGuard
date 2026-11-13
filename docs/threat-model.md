# Threat model

The local default and public hosted demo are synthetic. The repository also contains an optional public-cohort research build, which must remain separate and is not evidence of an institutionally accepted real-data deployment. Nothing here claims legal compliance: GenomeGuard is **designed around the ideas of** DPDP, GDPR and HIPAA.

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
| Steward-copilot manipulation | Plant instructions in data the copilot reads, or make a model recommend approval | Tool outputs are whitelist-sanitised; the copilot has read-only tools only; a model answer more permissive than the deterministic rules is discarded | `tests/test_copilot.py` (canary, injected-text, permissiveness and write-access tests) |

## Thresholds (`app/core/params.py`, override with `GG_<NAME>`)

| Parameter | Default | Meaning |
|---|---|---|
| `k_min` | 20 | Never release for a cohort smaller than this |
| `rare_maf` / `maf_floor` | 0.01 | Variants below this are "rare" and dropped first |
| `min_carriers_high` | 5 | A rare variant with 1 to 4 carriers is high risk unless hidden |
| `uniqueness_medium` / `uniqueness_high` | 1% / 10% | Record-level bands |
| `signal_medium` / `signal_high` | 1.0 / 3.0 | Aggregate-level membership signal z |
| `freq_bin_width` | 0.05 | Frequency bins |
| `epsilon_budget` | 1.0 | Configured per-requester/per-dataset ledger value; not a validated DP accountant |
| `epsilon_per_release` | 0.5 | Configured noise parameter; not a formal per-release epsilon guarantee |
| `max_variants_noised` | 25 | Noise grows with variant count, so release few |
| `anomaly_warn` / `throttle` / `freeze` | 0.35 / 0.55 / 0.75 | Combined anomaly score actions |
| `anomaly_window_minutes` | 15 | Sliding window |

## Limits you must state

The risk score, epsilon-like budget and anomaly score are engineering controls. They are not
certifications, clinical validity assessments, legal determinations or formal privacy guarantees.

- **Synthetic data.** Real genomes have linkage, population structure and relatives that the
  generator only approximates. Real attack success could differ in either direction.
- **Simplified attacks written by the defenders.** Treat results as evidence the mechanisms work
  as designed, not as a security proof.
- **No formal differential-privacy guarantee is established.** The epsilon-like ledger and noise
  settings are prototype controls, not a validated DP accountant or a basis for claiming
  epsilon-DP. The repository does not yet establish and independently validate the privacy unit
  and adjacency relation, contribution bounds, sensitivity for every output, mechanism calibration,
  composition across every query/release path, or accountant correctness. Empirical attack
  evaluation can show that tested attacks became less successful on tested fixtures; it does not
  prove differential privacy. Do not describe the configured epsilon values as a formal privacy
  guarantee until a qualified independent review validates the complete mechanism.
- **The hash chain makes tampering detectable, not impossible.** Someone with full database
  write access can recompute every hash. Record the head hash in a trusted location outside the database (for example, a separately stored audit anchor) so a rewritten history can be detected.
- **Encryption at rest protects a stolen file, not a compromised process.** The master key is an
  environment variable here; production needs a KMS or HSM. Transport security (TLS) comes from
  the hosting platform.
- **Secure aggregation** (`core/federated.py`) assumes honest-but-curious sites. It fails if all
  other sites collude, handles no dropouts, and does not stop a malicious site sending bad values.
  It is not homomorphic encryption and not an enclave.
- **The copilot is advisory and its guardrails are partial.** It cannot act, and it cannot be more
  permissive than the rules, but a model could still write a misleading rationale; only the
  numbers in it are checked against the evidence. A human steward makes the call.
- **FHIR validation has a limited scope.** A generated synthetic Consent resource passed the pinned HL7 FHIR Validator CLI against R4 4.0.1 and the project's extension definitions. This does not establish legally valid consent or validate a real consent workflow. DUO terms travel in namespaced extensions, and only the two DUO ids confirmed from the official ontology are emitted as ids.
- **Demo mode is synthetic-only, not an identity system.** `GET /demo/requesters` and
  `GET /demo/donors` expose synthetic persona metadata only; they do not return reusable
  requester, donor or steward credentials. `POST /demo/session` and
  `POST /demo/donor-session` issue short-lived, process-local demo session tokens for
  explicitly synthetic demo mode. These sessions are not institutional authentication,
  do not establish researcher affiliation, and must never be enabled for real or
  controlled-access participant data. The public demo must remain synthetic-only.
- **Not modelled:** the DUO consent-form-date limit; per-jurisdiction legal tests; insider abuse
  by a steward; side channels such as timing.
- **DUO fidelity:** NAGR and NCTRL follow the project spec's wording. Run `make fetch-duo` and
  compare with the official labels before describing them as DUO terms.
