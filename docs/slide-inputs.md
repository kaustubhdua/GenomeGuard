# Slide inputs (for the 6-slide deck)

**Slide 1 needs:** team name, project name **GenomeGuard**, GitHub repo link, working prototype
link, demo video link. (Fill the three links after deploying; keep them live through 14 Nov.)

**Hook:** "Genomic data can expose your relatives, so we built a guard that decides who can see
what, explains why, and proves it never looked the other way."

> **Track:** Track 2, Agentic AI for Healthcare. Pitch it as: a steward copilot (decision support),
> consent and audit records (information management), a patient consent concierge (patient
> interaction) and automatic triage with human sign-off (workflow automation).

## Problem
- DNA cannot be changed like a password, and it is shared with relatives who never consented.
- Erlich et al., *Science* 2018: with data from 1.28 million people who took consumer genomics
  tests, about 60% of searches for people of European descent would find a third-cousin-or-closer
  match, enough to help identify someone with demographic information.
- Beacons (yes/no allele queries) leak: before/after snapshots reveal newly added people
  (arXiv 2001.08852); membership inference against beacons was shown earlier (Shringarpure and
  Bustamante, 2015).

## Solution
A governance layer in front of a genomic data store. Every request is checked against donor
consent, scored for re-identification risk including **relatives**, protected (drop rare
variants, bin, add noise within an epsilon budget), monitored for attack patterns, and written to
a tamper-evident log. Agents explain in plain language; a deterministic core decides.

## Key features
Consent engine (DUO-inspired) | risk estimator with relative exposure | transform ladder with
epsilon ledger | anomaly monitor with differencing guard | hash-chained audit log | AES-256-GCM
at rest with per-dataset keys | advisory agents that never see genotypes | federated secure
aggregation | red-team harness (`make eval`) | optional real 1000 Genomes cohort.

## Workflow diagram
Use the Mermaid diagram in `docs/architecture.md`.

## Tech stack
Python 3.11, Starlette + uvicorn, numpy, SQLite, `cryptography` (AES-GCM, HKDF), vanilla JS
frontend (no build step), optional Anthropic API for agent text, Docker.

## USP / innovation
Consent-aware, **relative-aware**, explainable, tamper-evident, and red-teamed with measured
results including what the evaluation does not show.

## Real numbers (all from `make eval`, fixed seeds, synthetic data)
- Tracker attack: 100% recovery with no defence; 54.3% with the guard, equal to guessing.
- Membership inference (100 variants): AUC 0.72 raw, about 0.50 at epsilon 0.5, with correlation
  to true frequencies dropping to 0.04. Privacy costs utility.
- Triangulation: frozen in 100% of trials at gaps up to 120 s, median 8 to 10 queries. Not frozen
  at 600 s gaps.
- 500 simulated researcher sessions: 0.0% flagged (95% CI up to 0.8%); 0.4% of queries refused.

## Impact
Genomic sharing is growing (consortia, hospitals, biobanks). A reusable guard lets stewards say
yes more safely, lets donors see their consent honoured, and gives auditors evidence.

## Limitations and future scope (say these yourself before a judge does)
Synthetic data; simplified attacks; simple epsilon accounting (formal DP accountant is future
work); consent records simulated for real genomes; no homomorphic encryption or secure enclave
(future); no real consent-management integration; no independent security review; single-writer
audit log.

## Likely judge questions
- **Why agents if rules decide?** Agents turn numbers into explanations stewards and researchers
  can read, and give advisory second opinions. A deterministic core holds authority because an
  LLM gate can be prompt-injected. Agents see only whitelisted numbers.
- **What is simulated?** All genomes (unless you ran the real-data build), all traffic, the
  family exposure model (expected averages), and consent for real genomes.
- **Does it scale?** Per-request work is small numpy operations. First changes: Postgres, a
  column store for the genotype matrix, Redis for shared monitor state, a queue, a KMS.
- **Is it compliant?** No claim. It is designed around the ideas of DPDP, GDPR and HIPAA
  (purpose-limited consent, withdrawal, safeguards, audit). Double-check any DPDP dates against
  the official gazette before putting them on a slide.
- **Can the log be forged?** Someone with full database write access can recompute it. Publishing
  the head hash externally makes that detectable.
- **Why not full homomorphic encryption?** It cannot run these statistics at useful speed on a
  free tier; secure aggregation covers multi-site analysis, and HE is future work.
- **Is the real-data mode real?** Genotypes are real 1000 Genomes data; consent is simulated; the
  Phase 3 samples are unrelated so family exposure is sparse. Only claim it after you ran it.
