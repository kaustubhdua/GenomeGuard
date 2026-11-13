# Hosted deployment record

Last audited: 13 November 2026 (after merges of PRs #143 and #144).


## Environment separation and current live status (13 November 2026)

### Public synthetic demo

- Public URL: https://genomeguard.onrender.com
- Render service: srv-dbev1ka9lscs738813t0 — https://dashboard.render.com/web/srv-dbev1ka9lscs738813t0
- Hosting: Render Free plan, Singapore region, Dockerfile ./Dockerfile; repository branch main; auto-deploy reports enabled.
- Latest provider-reported live deployment: dep-dbr3gpou01pc738prrh0, source commit 10fb08dcc11ca09282cc1085fd86e3c73708281a, deployment trigger api, status live.
- Security fix: PR #142 merged as 10c429d393afd474e806939e80212e8182635e08, but that commit is not the live deployment. Render's event history showed no deployment event for the merge. The public service therefore still runs the older implementation.
- Live acceptance: run 43401555435 verified the synthetic cohort and audit chain but failed the requester-credential exposure check. The deployed /demo/requesters response still exposes requester API-key fields. Do not treat the public demo as security-accepted until the merged fix is actually deployed and the exact-commit live smoke passes.
- The live monitor previously reported demo_mode=true, synthetic_data_only=true, 600 samples, 3,000 variants, and storage_backend=postgresql. This is evidence that the application reported a PostgreSQL backend at that time; it does not identify the external database provider, prove which Neon project (if any) is connected, or prove provider-level backup, PITR, key custody, durability, or recovery. A fresh inspection of the connected Render workspace found no Render Postgres instances.
- The public service is a synthetic demonstration environment. Do not upload private or controlled-access participant data or use it for clinical decisions.

### Separate research-mode service

- render.yaml now describes a separate genomeguard-research service with demo mode disabled, real public-cohort provenance, OIDC, tenant isolation and consent-authority requirements.
- That service is a blueprint only; it has not been provisioned or accepted. Do not apply it to the existing public synthetic demo service.
- .github/workflows/live-research-mode-smoke.yml is manual-only and requires an explicit research-mode URL. It refuses the public synthetic-demo URL. Use it only after a separate research-mode service has been provisioned and its secrets and identity provider configured.
- .github/workflows/live-acceptance.yml remains the automated acceptance workflow for the public synthetic demo. These two modes must never share one deployment URL.

### Staging and real-data validation

- PR-branch synthetic staging is the separate Render service genomeguard-staging-pr122; staging-acceptance.yml targets that service and branch. It is not the non-demo research-mode deployment.
- High-coverage family cohort validation run 43401555287 passed. It downloaded the official 1000 Genomes high-coverage chr22 VCF and pedigree/population metadata, built a 600-sample/3,000-variant family-enriched cohort with 355 relative pairs, verified source hashes and produced aggregate evaluation evidence. Its consent records are simulated and dataset_policy_samples_scoped=0, so this family cohort is evaluation-only and must not be loaded into non-demo research mode.
- The Phase 3 1000 Genomes CI validation run 43401555222 uses simulated consent by design and is an evaluation pipeline, not a hosted research-mode import. The Dockerfile builds the separate research-mode cohort with docs/policies/igsr-1000-genomes-public-release.json, which records a dataset-level public-release policy (not participant-specific consent and not independently legal-reviewed). The live research-mode smoke requires that policy provenance to cover every loaded sample.

### Deployment actions still required

1. Restore or repair the Render GitHub auto-deploy integration. Although auto-deploy is enabled in service settings, no deployment event followed the merge, and the live service remains on commit 10fb08d.
2. Verify the public demo service is running 10c429d or a later reviewed commit, then rerun live synthetic-demo acceptance and verify that requester/donor endpoints return session metadata only, never API keys.
3. Provision the separate research-mode service from render.yaml only after its external PostgreSQL target, OIDC issuer/client/JWKS, organization membership, consent authority, master key and operational controls are available.
4. Run the manual research-mode smoke against that separate service and exact deployed commit. Keep the public synthetic demo and non-demo research instance separate.

## Historical deployment snapshot (10 November 2026; superseded by the live status above)

- Public URL: https://genomeguard.onrender.com
- Render service: `srv-dbev1ka9lscs738813t0` — [dashboard](https://dashboard.render.com/web/srv-dbev1ka9lscs738813t0)
- Hosting: Render web service, Free plan, Singapore region, Dockerfile `./Dockerfile`
- Connected repository and branch: `kaustubhdua/GenomeGuard`, `main`; auto-deploy is enabled.
- Latest provider-reported live deployment: `dep-dbhkcnijnfac73a7uk7g`
- Latest live source commit: `42c1bb0f1fb1dfa34357bdc864fc276fb99509d4`
- Provider service health-check path: empty (not configured).
- Current code changes are in [PR #111](https://github.com/kaustubhdua/GenomeGuard/pull/111), branch `feat/remove-supabase-runtime`; they are not deployed to this service.

The latest observed `/health` response reported 600 samples and 3,000 variants, `storage_backend: sqlite`, and readiness `not_ready`. The public-cohort provenance is operator-declared; dataset-level public-release terms are not participant-specific consent. The latest observed `/health/ready` response was not ready. The live `/catalogue/sources` and `/catalogue/datasets` routes returned 404 because the deployed `main` revision predates the first-party catalogue routes on PR #111.

These observations describe a public research prototype only. Do not upload private participant genomic data, identify individuals, or use the output for clinical decisions.

## Health and readiness configuration

The connected Render service currently reports an empty provider-side health-check path. The repository's current `render.yaml` uses `/health/live`, the cheap process liveness endpoint that does not initialize the cohort or database. Align the provider configuration with `/health/live`; do not use the readiness endpoint as the host liveness probe.

Required verification:
- Set and verify Render's health-check path as `/health/live`.
- Confirm `GET /health/live` returns process liveness only.
- Confirm `GET /health/ready` remains not-ready (HTTP 503) while production controls are absent.
- Deploy the reviewed PR commit to an isolated staging service and run read-only API, route/UI, authorization, and accessibility smoke tests against that exact SHA.

Do not treat a liveness response, deployment status, or green CI as production readiness.

## Historical PostgreSQL and legacy Supabase snapshot (10 November 2026; superseded)

The first-party PostgreSQL adapter and native migrations are maintained in `backend/app/postgres_store.py` and `backend/migrations/`. The connected Render service has no verified GenomeGuard PostgreSQL connection: `GG_DATABASE_URL` is not configured. It currently uses SQLite at `/data/genomeguard.sqlite3` on an ephemeral filesystem, so request/audit persistence across restart, redeploy, or free-instance spin-down is not guaranteed.

The active runtime architecture on PR #111 removes Supabase browser authentication, Edge Function routing, and database runtime dependencies. The historical `supabase/` migrations and old Supabase project notes are archival records of an earlier architecture; they are not used by the current application and must not be applied as part of this deployment. Do not connect GenomeGuard to the old shared Supabase project or reuse another application's schema.

The PostgreSQL adapter, migration tests, and recovery scripts do not provision production infrastructure. The backup/restore drill checks the actual `genomeguard_runtime` schema, refuses a non-empty restore target, encrypts its temporary dump with age, and verifies the restored audit hash chain. CI is configured to exercise this against disposable PostgreSQL databases; this does not prove provider-level backups, offsite retention, key custody, PITR, or a production restore drill.

Required before production:
1. Provision a dedicated PostgreSQL database with supported backups/recovery and least-privilege runtime credentials.
2. Configure `GG_DATABASE_URL` as a server-side secret; never put it in browser or `NEXT_PUBLIC_*` variables.
3. Verify migrations, request ownership, concurrent writes, audit ordering, and failure behavior against staging.
4. Prove records survive restart/redeploy and complete a separately controlled encrypted backup and restore drill.
5. Configure monitoring, retention, key custody, and incident response.

## Vercel frontend status

- Project: `genome-guard` — [Vercel project](https://vercel.com/jyc-website/genome-guard)
- Project ID: `prj_Q2uhnuLdzXTo4JoZUXqzhW6YuICT`
- Settings: root directory `frontend`, static/Other framework, output directory `.`, preview SSO protection.
- Latest combined Vercel status checked for PR #111 head `8584ebbe657109213df3d4889f902ea68869de5e`: **failure**, target reports `build-rate-limit`.
- An earlier preview status on an older commit succeeded, but it is not evidence that the latest head has a usable preview.
- Production deployment and public route-by-route acceptance are **not verified**.

The frontend rewrites API requests to the Render service. Vercel is not a replacement for durable backend storage. Do not promote a production deployment until preview build limits are resolved, the UI/API acceptance tests pass, and private-data security controls are in place.

## Explicit production blockers

1. **Database identity and durability:** the live application reports a PostgreSQL backend, but the exact external database target/provider, connection ownership, backup/PITR configuration, key custody, and production restore evidence are not independently verified. Render has no managed PostgreSQL resource attached to the public service. The disposable PostgreSQL CI drills are not a production provider backup or restore drill.
2. **Database security and isolation:** a dedicated production PostgreSQL instance, least-privilege runtime role, database network boundary, and live authorization path are not verified.
3. **Institutional identity:** no institutional OIDC/SSO, verified organization membership, or institution-controlled MFA lifecycle. Provisioned API keys are not verified human identity.
4. **Participant consent and withdrawal:** hosted public-data policy is dataset-level only. There is no authoritative participant-specific consent/withdrawal source.
5. **External audit anchoring:** the local hash chain is tamper-evident but not immutable against an actor able to rewrite the database and recompute hashes. Exported checkpoints are unsigned integrity envelopes; no independently controlled external anchor, trusted timestamp, or signing service is configured.
6. **Independent assurance:** no independent penetration test, privacy impact assessment, institutional ethics/legal review, clinical validation, or cryptographic review has been completed.
7. **Manual accessibility:** automated axe/browser checks do not replace manual screen-reader and assistive-technology review.
8. **Operational controls:** monitoring/alerting, incident response, retention/deletion, recurring recovery drills, and multi-instance consistency are not verified.
9. **Live acceptance and deployment:** the public service still runs commit `10fb08dcc11ca09282cc1085fd86e3c73708281a`, not the merged security fix `10c429d393afd474e806939e80212e8182635e08`. Render auto-deploy is enabled but no deploy event followed the merge. Live synthetic acceptance run 43401555435 failed because the old requester endpoint still exposes API-key fields. The Vercel preview status is separately blocked by `build-rate-limit`.

## Data and policy boundary

The currently deployed public service reports a synthetic-only demonstration cohort. The 1000 Genomes Phase 3 and high-coverage family workflows build and evaluate public real-genotype cohorts in CI; those workflow artifacts are not evidence that the data has been imported into the hosted research-mode database. Dataset-level public-release terms are not participant-specific consent, legal advice, or independent approval for any specific use.

Local demo and test workflows intentionally use synthetic fixtures. Keep those paths explicitly labelled and never describe synthetic fixtures as real people or consent. Do not use the public research instance for private participant data.

The privacy-risk output is heuristic, not an independently validated guarantee. The privacy-budget ledger is not a formally audited differential-privacy implementation. The Beacon-style endpoint is not full Beacon certification. FHIR Consent fixtures are synthetic validation artifacts, not real consent records. Agent explanations run offline using deterministic templates and a bounded rules planner; no hosted LLM provider is used. The local audit chain has no external immutable anchor, and its checkpoint digest is unkeyed and unsigned.

## Reproduce checks

From a local clone with Python 3.11+, dependencies, and Playwright Chromium installed:

```bash
python scripts/live_research_mode_smoke.py --base https://genomeguard.onrender.com
python scripts/live_ui_smoke.py --base https://genomeguard.onrender.com
npm install --prefix /tmp/gg-axe --no-save --package-lock=false axe-core@4.14.0
AXE_CORE_PATH=/tmp/gg-axe/node_modules/axe-core/axe.min.js python scripts/live_accessibility_smoke.py --base https://genomeguard.onrender.com
```

Research-mode smoke checks should be read-only. Run write-enabled acceptance only against an isolated staging service with synthetic fixtures. Never run destructive persistence probes against production data.

## Release decision

The service is a working **public-genotype research prototype**, not a production genomic-data-governance service. Do not submit private participant data, identifiable genomic data, controlled-access cohorts, or clinical records. Keep readiness fail-closed until the relevant controls exist and their live behavior is verified.
