# Three-minute demo script

A spoken walkthrough for judges and reviewers. Every number below is reproduced by `make eval` from fixed seeds (see [evaluation results](eval-results.md)). It is synthetic data, so say so out loud at the start.

**Before you start:** use a fresh database so the probing account has not already been frozen.

```bash
GG_DB_PATH=/tmp/gg-demo.sqlite3 GG_ALLOW_TAMPER_DEMO=true make seed
GG_DB_PATH=/tmp/gg-demo.sqlite3 GG_ALLOW_TAMPER_DEMO=true make run
```

Open http://127.0.0.1:8000. Keep `make demo` ready in a second terminal as a fallback: it replays the same story and checks each step.

## 0:00 to 0:30, the problem

"Genomic data cannot be un-leaked, and it also exposes relatives who never agreed to anything. Most access systems stop at a yes or no. GenomeGuard decides what a researcher may see, shows how risky the answer is, protects the output, and records every step. It is a research prototype running on synthetic data."

Show the **Overview** page: point at the provenance banner that says the cohort is synthetic.

## 0:30 to 1:15, one request end to end

1. Open **Requests** and submit a request as a demo researcher.
2. Show the outcome and its reason codes: consent-style policy rules, not a black box.
3. Open **Decision details**: the disclosure-risk estimate and the output transformation that was applied.
4. Say: "The relative-exposure figure is a model estimate, not a statement about any real family."

## 1:15 to 2:00, the attack it stops

Open **Anomalies** (or run the scripted attack from the guided tour).

- "A differencing attack asks for a cohort that includes one person, then the same cohort without them, and subtracts."
- "With no defence the attacker recovers 100% of the target's genotypes. Per-query protections alone still leave 100%. With the differencing guard it falls to 54.3%, which is the same as guessing from allele frequency."
- "The guard blocked the second query in all 100 trials."
- Show the probing account being flagged and frozen.

## 2:00 to 2:30, privacy has a price

Open **Red-team results**, membership inference.

- "Releasing raw allele frequencies for 100 variants lets an attacker tell who is in the cohort: AUC 0.72, where 0.5 is a coin flip."
- "Adding noise brings it to 0.50, but the released data is then nearly useless (correlation 0.04 at ε = 0.5). We report that trade-off instead of hiding it."

## 2:30 to 3:00, trust and honesty

- Open **Audit log**, run the hash-chain verification, then (demo only) tamper with an entry and show it detected.
- Open **Steward review**: the copilot recommends, a human decides, and it only works from approved summaries and cannot grant access.
- Close with the limits, in your own words: synthetic data, simplified attackers written by the same team as the defences, slow attackers (gap over 15 minutes) evade the rate-based monitor, and a privileged operator could rewrite the database and recompute hashes.

## Likely questions

| Question | Honest answer |
|---|---|
| Is this real genomic data? | The local demo is synthetic. The hosted research instance uses public 1000 Genomes genotypes with a dataset-level policy mapping, which is not participant-specific consent. |
| Is it differentially private? | It adds Laplace noise with a simple budget under sequential composition. It is not a formal accountant. |
| What does the monitor miss? | Patient attackers. At a 10-minute gap it freezes 0% of the scripted attackers; the k-minimum, differencing guard and epsilon budget still limit them. |
| False positives? | 0 of 500 simulated researcher sessions flagged, but that traffic is our assumption, not measured logs. |
| Could it be used clinically? | No. It is research software. |

## If something breaks on stage

Run `make demo`. It prints a pass or fail line per step and needs a fresh database.
