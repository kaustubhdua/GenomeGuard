# Hosted deployment record

## Current public research instance

- Public URL: https://genomeguard.onrender.com
- Hosting: Render web service, free plan, Singapore region
- Service: `srv-dbev1ka9lscs738813t0`
- Deployed source commit: `154ee80916e1a45080bc4160902516768afaee15`
- Render deployment: `dep-dbf0ijrrjlhs73951960` (reported `live`)
- Runtime: Docker, Python 3.12 image, Uvicorn
- Data: public 1000 Genomes/IGSR chromosome 22 genotype calls, 600 samples × 3,000 variants
- Policy provenance: a versioned mapping of published dataset-level public-release terms; not participant-specific consent and not independent legal review
- Demo mode and destructive audit-tampering mode: disabled
- Explanations: built-in templates; no live LLM configured
- Secrets: master and admin keys are environment configuration and must never be committed to the repository or copied into public issues/screenshots.

The Docker image builds the cohort from the official public source and records source-file and policy-file hashes. See the [Render service dashboard](https://dashboard.render.com/web/srv-dbev1ka9lscs738813t0) for live service state.

## Health and readiness

- `GET /health` is a liveness/provenance endpoint. HTTP 200 means the app can answer requests; it does not mean production use is safe.
- `GET /health/ready` intentionally returns HTTP 503 with `ready: false` while required production controls are unverified.
- The latest [live research-mode workflow #40199498444](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40199498444) verified real public-source genotype provenance, the dataset-level policy boundary, disabled demo endpoints, unauthorized-call rejection, all nine UI routes, responsive layouts, keyboard behavior, reduced motion, reflow, and automated accessibility checks.
- [Main CI run #40199498577](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40199498577) passed on deployed source commit `154ee80916e1a45080bc4160902516768afaee15`.


## PostgreSQL implementation status (feature branch)

An opt-in PostgreSQL adapter and migration/recovery tooling are proposed in
[PR #33](https://github.com/kaustubhdua/GenomeGuard/pull/33). This is **not yet deployed** and does
not change the active Render service. It includes a schema migration, a one-time offline SQLite
migration tool, PostgreSQL audit-sequence locking, and backup/restore instructions. It does not
prove a provider backup policy, perform a real restore drill, or provide atomic transactions spanning
the complete request/decision/privacy-budget/audit lifecycle. Do not describe the hosted service as
durably persisted until a dedicated database is configured and persistence plus recovery are tested
against the deployed commit.

## Why the service is not production-ready

The following are explicit, unmet requirements, not implied future promises:

1. **Durable persistence and recovery:** The service is on Render's free plan with no persistent disk. SQLite lives at `/data/genomeguard.sqlite3`, on an ephemeral filesystem. Request history and audit events can be lost on restart/redeploy. No production backup/restore drill has passed.
2. **Institutional identity and authorization:** The app accepts provisioned API keys. It has no verified institutional OIDC/SSO integration, membership lifecycle, MFA policy, or institutional identity proof. API keys alone are not proof of researcher identity.
3. **External audit anchoring:** The hash chain is tamper-evident, not immutable if an actor can rewrite the database and recompute hashes. No independently controlled external anchor or trusted timestamp is configured.
4. **Consent/legal authority:** The current public dataset's policy is dataset-level public-release provenance. It is not a per-participant consent record, does not support withdrawal, and has not been independently reviewed for a specific intended use or jurisdiction. Do not apply it to private/controlled-access data.
5. **Clinical/security/privacy assurance:** No independent security penetration test, privacy impact assessment, institutional ethics review, or clinical validation has been completed. The privacy ledger is not a formal differential-privacy guarantee; the cryptographic/federated components are not independently audited.
6. **Human accessibility review:** Automated checks pass, but manual testing with a screen reader and assistive technology remains outstanding.
7. **Operational controls:** Backup/restore, incident response, retention/deletion, monitoring/alerting, disaster recovery, and multi-instance consistency have not been verified.

The readiness endpoint must remain fail-closed until the relevant capabilities exist and their behavior is tested. Do not store private participant information, identifiable genomic data, or clinical records in this public instance.

## Reproduce checks

From a local clone with Python 3.11+, dependencies, and Playwright Chromium installed:

```bash
python scripts/live_research_mode_smoke.py --base https://genomeguard.onrender.com
python scripts/live_ui_smoke.py --base https://genomeguard.onrender.com
npm install --prefix /tmp/gg-axe --no-save --package-lock=false axe-core@4.14.0
AXE_CORE_PATH=/tmp/gg-axe/node_modules/axe-core/axe.min.js python scripts/live_accessibility_smoke.py --base https://genomeguard.onrender.com
```

The research-mode smoke checks are read-only. UI and accessibility scripts navigate routes and exercise browser controls but do not create real participant data. Run any write-enabled API acceptance test only against an isolated test instance with synthetic fixtures.

## Release status

The hosted site is a working **public-genotype research instance**, not a production genomic-data-governance service. It uses real public genotype calls and source-documented policy provenance, while deliberately disabling synthetic demo endpoints in the hosted mode. Durable storage, institutional identity, external audit anchoring, consent governance for any non-public cohort, independent review, and human screen-reader testing remain release blockers.
