# Application walkthrough

This guide describes the main workflows in the local GenomeGuard interface. Use a fresh local database so the seeded records, anomaly demonstrations, and audit-integrity examples start in a known state.

## Start the application

From the repository root:

```bash
make setup
make seed
make run
```

Open http://127.0.0.1:8000. For a disposable database with the audit-tampering demonstration enabled, use a separate local environment and set `GG_DB_PATH` and `GG_ALLOW_TAMPER_DEMO=true` before starting the server. Never enable demonstration tampering on a non-demo environment.

## Explore the workflows

1. **Overview:** review the service status, cohort provenance, and summary metrics. Check whether the current cohort is synthetic or uses public genotype data.
2. **Requests:** submit a research request using a demo requester. Review the policy outcome, reason codes, risk estimate, and any output transformation.
3. **Decision details:** inspect the evidence and transformations behind a decision. Relative-exposure figures are model estimates, not predictions about any specific person's relatives.
4. **Family exposure:** review the relationship model and its provenance. The default model is simulated; it must not be interpreted as an assessment of a real family.
5. **Anomalies:** inspect flagged query patterns and the state of demo accounts. The included traffic is scripted and does not represent measured production traffic.
6. **Steward review:** open a held request and run the read-only copilot. It can gather sanitized summaries and recommend next steps, but a human makes the final decision.
7. **Audit log:** verify the hash chain and inspect the event history. The chain makes edits detectable when checked against a trusted anchor; it does not prevent a privileged operator from rewriting the database and recomputing hashes.
8. **Donor view:** inspect the simulated consent record and available export. These records are not real participant consents.
9. **Red-team results:** review the evaluation scenarios, assumptions, and limitations alongside the reported metrics.
10. **Federated analysis:** explore the demonstration of multi-party analysis. The local implementation is not a hardened multi-organization service.

## Guided tour and automated checks

The Overview page includes a guided tour that demonstrates selected request and anomaly workflows. To replay the automated scenario and its assertions, run:

```bash
make demo
make ui-smoke
```

These checks run against local test/demo data. They do not verify a public deployment or substitute for manual accessibility and usability testing.

## Resetting demo state

Some workflows intentionally change state: the probing account can be frozen, and the audit-integrity example can mark a demo entry as tampered. Use the corresponding demo-only recovery action or restart with a fresh `GG_DB_PATH`. Do not use these controls against real records.
