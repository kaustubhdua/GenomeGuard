# Architecture

GenomeGuard sits in front of a genomic data store. A request never touches genotypes directly: it
passes a fixed pipeline, and only an aggregate or transformed release comes out.

```mermaid
flowchart LR
  R[Researcher request] --> A[API: key check]
  A --> T{Credential tier}
  T --> C[Consent engine<br/>DUO-inspired rules]
  C --> K[Risk estimator<br/>uniqueness, rare carriers,<br/>membership signal, relatives]
  K --> L[Transform ladder<br/>drop rare, bin, noise,<br/>epsilon ledger]
  L --> M[Anomaly monitor<br/>incl. differencing guard]
  M --> D{Decision<br/>permit / transform /<br/>deny / escalate}
  D --> O[Aggregate release]
  D --> H[Human reviewer]
  subgraph Agents[Advisory agents, never see genotypes]
    E[Explainer] ; P[Privacy] ; N[Anomaly] ; S[Access] ; Q[Consent]
  end
  C -.reason codes.-> Agents
  K -.bands, counts.-> Agents
  Agents -.explanation text.-> O
  A & C & K & L & M & D & Agents --> G[(Hash-chained audit log)]
  DB[(SQLite: genotypes encrypted<br/>AES-256-GCM, per-dataset key)] --> C
  DB --> K
```

## The decision is deterministic; agents advise

`app/service.py` (`GenomeGuardService`) runs the pipeline and **makes every decision**. The agents
(`app/agents/`) turn the numbers into plain language and give advisory opinions (the privacy agent
can note whether it agrees with the ladder; the access agent summarises requester history). They:

- receive only what `agents/sanitizer.py` lets through: counts, bands, reason codes, epsilon
  values, outcomes. Not genotypes, donor ids, family ids, cohort membership or free text. A test
  plants a canary string in all of those and asserts it never appears in a prompt.
- never hold authority. An LLM-only gate could be talked into releasing data by a crafted request;
  a deterministic gate cannot.
- fall back to templates (`agents/templates.py`) when there is no API key, so the demo never fails.
- have their outputs written to the audit chain with the model name and a hash of the prompt.

## Modules

| Module | Job |
|---|---|
| `core/consent.py` | Rules: withdrawal, GRU/HMB/DS, NCU/NPU/NMDS/NAGR/NCTRL, population. First failing rule wins, so reasons are deterministic. Returns counts, never donor ids. |
| `core/risk.py` | Scores a candidate release. Record level: uniqueness and information bits. Aggregate level: rare-variant carriers and a membership-inference signal. Always: relative exposure (simulated model). |
| `core/transform.py` | Ladder: drop rare variants, record to count, bin, cap variants, Laplace noise, last-resort boolean. Re-scores after each step, stops when risk is low. Epsilon ledger per requester per dataset. |
| `core/anomaly.py` | Rate, near-duplicate probing, cohort narrowing, differencing guard, cumulative exposure. Weighted score to ok, warn, throttle, freeze. |
| `core/audit_chain.py` | `hash = SHA256(canonical_json({idx, ts, actor, action, payload, prev_hash}))`. `verify()` returns `{ok, length, head_hash, first_broken_index}`. |
| `core/crypto.py` | AES-256-GCM at rest, key per dataset derived from a master key with HKDF, ciphertext bound to dataset and donor id. |
| `core/federated.py` | Secure aggregation by additive secret sharing; federated allele frequencies and logistic regression across simulated hospitals. |
| `data/synth.py`, `data/pedigree.py` | Synthetic cohort with real Mendelian transmission and a derived relationship graph. |
| `data/real.py`, `data/duo.py` | Optional: build a cohort from real 1000 Genomes files; compare our rules with the official DUO. |
| `service.py`, `api.py`, `store.py` | Orchestration, Starlette HTTP layer, SQLite store. |
| `redteam/` | Attacks, benign traffic and the evaluation behind `make eval`. |

## Tiers and levels

Credential tiers mirror GA4GH Beacon v2: `anonymous` (boolean or count only, and only for cohorts of at least 5 x `k_min` = 100),
`registered` (frequencies), `controlled` (may ask for record level, which always needs a human).
Data levels run coarse to fine: boolean, count, frequency, record.

## What a researcher can and cannot see

Responses contain aggregates, transformed releases, counts and reason codes. Steward-only detail
(`min_carriers`, family exposure, detector scores, advisory notes) is removed from researcher
responses, because it describes withheld variants and would let an attacker tune queries to stay
under thresholds. See `requester_view` in `app/api.py`.

## Scaling, honestly

- **Fine as built:** one dataset of thousands of donors; per-request cost is a few numpy
  operations over the eligible cohort.
- **Would change first:** SQLite to Postgres (the store is one small class); the in-memory
  `Dataset` to a column store or memory-mapped array when the genotype matrix exceeds RAM; the
  anomaly monitor's in-process windows to Redis so several API replicas share state; a job queue
  for large requests; a KMS/HSM for the master key.
- **Not solved here:** the audit chain is single-writer. Multi-writer needs consensus or a
  transparency-log service.
