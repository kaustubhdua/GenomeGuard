# Scalability: what was measured, and what is only reasoning

Everything in the first two sections comes from `make bench` (`scripts/bench.py`). It runs the
full decision pipeline in one process against SQLite on disk, with no network. The machine was a
shared cloud sandbox with **2 vCPUs, Python 3.13**; the raw output is in `bench-results.json`.
Run `make bench` on the target hardware and record the result together with the hardware and runtime details whenever publishing performance figures.

## 1. Decision latency and cohort size (measured)

One `submit()` is the whole pipeline: consent filter, risk estimate, transform ladder, anomaly
monitor, release, a handful of audit-chain writes, and five to six agent notes (deterministic
templates, so no model latency). Requests were varied (4 purposes, 4 populations, varying
variant sets) and spread across 40 accounts with simulated time, so the anomaly monitor saw
ordinary traffic. Every outcome was `permit` or `permit_with_transform`.

| Cohort | Genotype matrix | Requests | Throughput | Latency p50 / p95 / p99 |
|---|---|---|---|---|
| 600 donors x 3,000 variants (default) | 1.8 MB | 300 | 29.9 req/s | 32.8 / 43.3 / 59.5 ms |
| 2,000 x 8,000 | 16 MB | 60 | 28.3 req/s | 33.6 / 54.4 / 64.1 ms |
| 5,000 x 20,000 | 100 MB | 60 | 18.4 req/s | 49.9 / 96.8 / 113.3 ms |

Reading: median latency grew about 1.5x while the cohort grew about 8x in donors and 7x in
variants. Per-request work is a few numpy operations over the eligible rows.

Start-up is the part that grows steeply, because the *synthetic generator* builds family
structure and encrypts the matrix on first run: 2 s, 13 s and 69 s for the three rows. A real
cohort loaded from a file (`GG_REAL_COHORT_FILE`) skips generation.

What these numbers do **not** show: concurrency (this is one process, and SQLite serialises
writes), network and TLS cost, an LLM in the loop (a model call adds its own latency to every
agent note that uses one, which is why only some roles may call a model), or genuinely large
cohorts (a biobank has millions of rows; see section 4).

## 2. Audit chain cost (measured)

| Log length | Full `verify()` |
|---|---|
| about 3,400 entries | 94 ms |
| 5,000 | 97 ms |
| 20,000 | 308 ms |

Appending one entry takes about 1.3 ms (roughly 770 a second). Verification is O(n), because it
recomputes every hash, so a full check on a log of millions of entries would take on the order of
a minute or more. The page verifies on every view today; at scale you would verify incrementally
from a stored checkpoint and run the full check on a schedule. That is a design change, not a
tuning change, and is not built.

## 3. Memory (measured)

The whole genotype matrix is held in RAM as `int8`: 1.8 MB, 16 MB and 100 MB for the three
cohorts above. A free web host with 512 MB of RAM is therefore comfortable at the default size
and still plausible at 5,000 x 20,000, but it has not been tried on such a host.

## 4. What would need to change for a real deployment (reasoning, not measured)

| Limit today | Why it matters | Direction |
|---|---|---|
| SQLite, one writer | Concurrent requests serialise on writes | Postgres for requests, ledger and audit log |
| Audit chain has one writer and an O(n) full check | Cannot append from several processes; verification slows as it grows | A sequencer or per-shard chains, periodic Merkle checkpoints anchored outside the system |
| Genotype matrix in process memory | Millions of donors do not fit | Columnar or chunked store, queries pushed down to it |
| Anomaly windows and epsilon state in process | Two workers would each see part of the traffic | Shared store (Redis or Postgres) for monitor state |
| Escalations wait in a table | No notification, no SLA | A queue and a review inbox |
| Master key in an environment variable | Single point of compromise | A KMS or HSM |
| Epsilon accounting is simple sequential composition | Loose, so budgets are used up faster than a formal accountant would need | A formal privacy accountant |

None of these have been built or measured. They are the honest answer to "how would it scale":
the per-request logic is cheap and does not need to change, and the state around it does.
