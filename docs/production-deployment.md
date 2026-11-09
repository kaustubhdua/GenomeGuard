# Hosted deployment record

Last audited: 28 October 2026.

## Current public research instance

- Public URL: https://genomeguard.onrender.com
- Hosting: Render web service, free plan, Singapore region
- Service ID: `srv-dbev1ka9lscs738813t0`
- Current Render deployment: `dep-dbg42osipgvc73eesutg`, status `live`
- Deployed source commit: `a100921c98dbb194e365f76d32f9340700b2c196` (merge of PR #43)
- Runtime: Docker, Python 3.12 image, Uvicorn
- Dataset: public 1000 Genomes / IGSR chromosome 22 genotype calls, 600 samples × 3,000 variants
- Policy provenance: versioned mapping of published dataset-level public-release terms; not participant-specific consent and not independent legal review
- Hosted demo mode and destructive audit-tampering mode: disabled
- Explanations: built-in templates; no live LLM configured

Render reports the current main commit as live. This confirms deployment status, not end-to-end runtime health. The available web verifier could not fetch the public URL or health endpoints, and the connected Vercel account could not independently inspect the current deployment content. Do not claim a live UI/API acceptance pass until the documented checks pass from a network-enabled runner.

# Hosted deployment record

Last audited: 10 November 2026.

## Current public research instance

- Public URL: https://genomeguard.onrender.com
- Render service: `srv-dbev1ka9lscs738813t0` — [dashboard](https://dashboard.render.com/web/srv-dbev1ka9lscs738813t0)
- Hosting: Render web service, Free plan, Singapore region, Dockerfile `./Dockerfile`
- Connected repository and branch: `kaustubhdua/GenomeGuard`, `main`; auto-deploy is enabled.
- Latest provider-reported live deployment: `dep-dbhkcnijnfac73a7uk7g`
- Latest live source commit: `42c1bb0f1fb1dfa34357bdc864fc276fb99509d4`
- Provider service health-check path: empty (not configured).
- The current code changes are in [PR #111](https://github.com/kaustubhdua/GenomeGuard/pull/111), branch `feat/remove-supabase-runtime`; they are not deployed to this service.

The latest observed `/health` response reported 600 samples and 3,000 variants, `storage_backend: sqlite`, and readiness `not_ready`. The public-cohort provenance is operator-declared; dataset-level public-release terms are not participant-specific consent. The latest observed `/health/ready` response was not ready. The live `/catalogue/sources` and `/catalogue/datasets` routes returned 404 because the deployed `main` revision predates the first-party catalogue routes on PR #111.

These observations describe a public research prototype only. Do not upload private participant genomic data, identify individuals, or use the output for clinical decisions.

## Health and readiness configuration

The connected Render service currently reports an empty provider-side health-check path. The repository's current `render.yaml` uses `/health/live`, the cheap process liveness endpoint that does not initialize the cohort or database. Align the provider configuration with `/health/live` after reviewing the Render service change; do not use the readiness endpoint as the host liveness probe.

Required verification:
- Set and verify Render's health-check path as `/health/live`.
- Confirm `GET /health/live` returns process liveness only.
- Confirm `GET /health/ready` remains not-ready (HTTP 503) while production controls are absent.
- Deploy the reviewed PR commit to an isolated staging service and run read-only API, route/UI, authorization, and accessibility smoke tests against that exact SHA.

Do not treat a liveness response, deployment status, or green CI as production readiness.

## PostgreSQL and legacy Supabase artifacts

The first-party PostgreSQL adapter and native migrations are maintained in `backend/app/postgres_store.py` and `backend/migrations/`. The connected Render service has no verified GenomeGuard PostgreSQL connection: `GG_DATABASE_URL` is not configured. It currently uses SQLite at `/data/genomeguard.sqlite3` on an ephemeral filesystem, so request/audit persistence across restart, redeploy, or free-instance spin-down is not guaranteed.

The active runtime architecture on PR #111 removes Supabase browser authentication, Edge Function routing, and database runtime dependencies. The historical `supabase/` migrations and old Supabase project notes are archival records of an earlier architecture; they are not used by the current application and must not be applied as part of this deployment. Do not connect GenomeGuard to the old shared Supabase project or reuse another application's schema.

The PostgreSQL adapter, migration tests, and recovery scripts do not provision production infrastructure. The backup/restore drill now checks the actual `genomeguard_runtime` schema, refuses a non-empty restore target, encrypts its temporary dump with age, and verifies the restored audit hash chain. CI exercises this against disposable PostgreSQL databases; this does not prove provider-level backups, offsite retention, key custody, PITR, or a production restore drill.

Required before production:
1. Provision a dedicated PostgreSQL database with supported backups/recovery and least-privilege runtime credentials.
2. Configure `GG_DATABASE_URL` as a server-side secret; never put it in browser or `NEXT_PUBLIC_*` variables.
3. Verify migrations, request ownership, concurrent writes, audit ordering, and failure behavior against staging.
4. Prove records survive restart/redeploy and complete a separately controlled encrypted backup and restore drill.
5. Configure monitoring, retention, key custody, and incident response.

## Vercel frontend status

- Project: `genome-guard` — [Vercel project](https://vercel.com/jyc-website/genome-guard)
- Project ID: `prj_Q2uhnuLdzXTo4JoZUXqzhW6YuICT`
- Settings updated: root directory `frontend`, static/Other framework, output directory `.`, preview SSO protection.
- GitHub-triggered preview for PR #43 was reported `READY`.
- A production deployment and public route-by-route acceptance test are **not independently verified**. Direct production deployment creation was denied by the connected Vercel API, and current deployment-list access is denied.

The frontend rewrites API requests to the Render service. Vercel is not a replacement for durable backend storage. Promote a production deployment only after the UI and API acceptance tests pass and the private-data security controls are in place.

## Explicit production blockers

1. **Durable persistence and recovery:** Render has no verified `GG_DATABASE_URL`; the backend is not connected to Supabase and no production backup/restore drill has passed.
2. **Database security and isolation:** RLS is now enabled on all 13 GenomeGuard tables and browser roles lack schema `USAGE`, but the trusted server connection, least-privilege runtime role, and production access path are not yet verified. Supabase project `common 1` is shared with BharatSim, so this is schema isolation rather than a dedicated production security boundary.
3. **Institutional identity:** no institutional OIDC/SSO, verified organization membership, or institution-controlled MFA lifecycle. Provisioned API keys are not verified human identity.
4. **Participant consent and withdrawal:** hosted public-data policy is dataset-level only. There is no authoritative participant-specific consent/withdrawal source.
5. **External audit anchoring:** the local hash chain is tamper-evident but not immutable against an actor able to rewrite the database and recompute hashes. No independently controlled external anchor or trusted timestamp is configured.
6. **Independent assurance:** no independent penetration test, privacy impact assessment, institutional ethics/legal review, clinical validation, or cryptographic review has been completed.
7. **Manual accessibility:** automated axe/browser checks do not replace manual screen-reader and assistive-technology review.
8. **Operational controls:** monitoring/alerting, incident response, retention/deletion, recurring recovery drills, and multi-instance consistency are not verified.
9. **Live acceptance:** run read-only research-mode, route/UI, authorization, and accessibility smoke tests on the exact current deployment; the available verifier could not fetch the live endpoints.

## Data and policy boundary

The deployed genotype calls come from the public 1000 Genomes / IGSR release. Source and policy file hashes are recorded during cohort build. The versioned policy maps published dataset-level terms to a DUO-inspired rule set; it is not participant-specific consent, legal advice, or independent approval for any specific use.

Local demo and test workflows intentionally use synthetic fixtures. Hosted research mode disables demo/synthetic participant workflows. Keep those paths explicitly labelled and never describe synthetic fixtures as real people or consent.

The privacy-risk output is heuristic, not an independently validated guarantee. The privacy-budget ledger is not a formally audited differential-privacy implementation. The Beacon-style endpoint is not full Beacon certification. FHIR Consent fixtures are synthetic validation artifacts, not real consent records. No live LLM is configured. The local audit chain has no external immutable anchor.

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
