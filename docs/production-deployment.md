# Hosted deployment record

Last audited: 14 November 2026.

> **Re-verification note — 14 November 2026:** the user confirmed the `kaustubh dua` Render workspace, and its service and PostgreSQL inventories were queried read-only during this audit. The inventory below now reflects the connected provider snapshot. No service settings, environment variables, deploys, databases, or billing/plan settings were changed. The exact external Neon branch and service-to-database mapping remain unverified; do not infer them from project names.
>
> **Fresh Render evidence:** the workspace contains five GenomeGuard web services, all reported live and on the Free plan: `genomeguard` (main, current live commit `3280ebc1924039bcfa19f4c58bb75e83a8c370eb`), `genomeguard-demo-recovery` (main, `f200b643f05a5f959887ac51accd7e202c424557`), `genomeguard-staging-pr122` (branch `fix/main-release-acceptance-blockers`, `c129d496c9008c4740b9af50ea4062c8ff499fc8`), `genomeguard-staging-pr113` (branch `feat/institutional-production-controls`, `caa754ba96dc6c3574b12b754b7ed63e251d76d5`), and `genomeguard-staging` (branch `feat/remove-supabase-runtime`, `60fc7f33c1a971cbca37195f9c41b2eef23ed005`). All are in Singapore. The primary `genomeguard` service and the recovery service have no provider-side health-check path configured; the PR113 staging service uses `/health/live`; the other staging service health-check paths are empty. The connected workspace's Render PostgreSQL inventory is empty.
>
> **Fresh log evidence:** the primary service returns HTTP 200 for `/health` and repeatedly returns HTTP 503 for `/health/ready`. The recovery service returns HTTP 200 for `/health/live` and HTTP 503 for `/health/ready`. The PR122 staging service returns HTTP 200 for `/health` and HTTP 503 for `/health/ready`. These readiness failures are consistent with the documented fail-closed production gates and are not evidence that the process is down. No secrets or environment-variable values were read.

## Neon database evidence (read-only)

- Project `genomeguard-free-demo` default branch has schema migrations 1–12.
- Project `genomeguard-staging` default branch has only migrations 1–2.
- Its existing child branch `gg-render-staging-2026-11-10` has migrations 1–12 and 600 synthetic donors, 600 genotype rows and 3,000 variants. Its cohort metadata reports `genotypes_real=false` and `consent_simulated=true`.
- On that child branch, public dataset sample/variant tables and gnomAD reference manifest/frequency tables each have zero rows. This is a synthetic staging candidate, not evidence of a 1000 Genomes or gnomAD production import.
- The actual Render service-to-Neon branch mapping remains unverified. The default staging branch and the child staging candidate must not be treated as interchangeable.
- Attempts to protect both Neon default branches were rejected because the current plan has reached its protected-branch limit. No plan upgrade, branch deletion or live/default-branch migration was performed.
- No paid infrastructure or controlled-data import was performed.


## Current live status (14 November 2026)

### Public synthetic demo

- Image contract: the root `Dockerfile` is synthetic-only. It must not download, embed, or mount a real participant cohort. The public demo must remain synthetic-only.
- Primary public URL: https://genomeguard.onrender.com
- Primary Render service: `srv-dbev1ka9lscs738813t0` — [dashboard](https://dashboard.render.com/web/srv-dbev1ka9lscs738813t0).
- Provider configuration: branch `main`, auto-deploy `yes`, Render Free plan, Singapore region, Dockerfile `./Dockerfile`. The provider health-check path is currently empty; it should be configured as `/health/live`, not `/health/ready`.
- Latest provider-reported live deployment: `dep-dbrgucce7ovs73femptg`, commit `3280ebc1924039bcfa19f4c58bb75e83a8c370eb`, status `live`. This is the PR #146 synthetic/research image separation commit, not current GitHub `main` (`50658f1ae0ec1df9f4b8c1e512d720bd4e7f5f94`).
- A separate recovery demo service exists at https://genomeguard-demo-recovery.onrender.com, Render service `srv-dbri7fp5efls73amo2q0`, Free plan, root `./Dockerfile`, latest observed live commit `f200b643f05a5f959887ac51accd7e202c424557`. It is also behind current `main`; it is a recovery/demo service, not a research-mode deployment.
- The primary service's `/health/ready` is expected to fail closed (HTTP 503) while institutional controls are absent. Render application logs contain successful liveness/application requests and readiness 503 responses. Do not configure readiness as the host liveness check or interpret readiness 503 as proof that the process is down.
- The current `main` commit has not yet been deployed to the primary service. Although auto-deploy is enabled in provider settings, the latest provider deployment is still `3280ebc`. Investigate the missing automatic deployment after subsequent mainline merges; do not manually promote an unvalidated SHA.
- The current mainline `/demo/requesters` and `/demo/donors` handlers return synthetic persona metadata only. The requester and donor session endpoints issue short-lived, process-local demo tokens. This is code-level evidence; live exact-SHA acceptance of the current mainline is still pending.
- The connected Render workspace contains **no Render-managed PostgreSQL instances**. The exact external database provider, account/plan, retention, backup/PITR, encryption/key custody and restore guarantees are not established by Render service metadata. A configured PostgreSQL backend alone is not proof of durable production storage.
- No private or controlled-access participant data may be uploaded to either public demo service. Do not treat a public demo as an institutional research deployment or use it for clinical decisions.

### Staging services and environment sprawl

The connected workspace currently lists three separate GenomeGuard staging services:
- `genomeguard-staging-pr122` on branch `fix/main-release-acceptance-blockers`, using `Dockerfile.staging`.
- `genomeguard-staging-pr113` on branch `feat/institutional-production-controls`, using `Dockerfile.staging`.
- `genomeguard-staging` on branch `feat/remove-supabase-runtime`, using `Dockerfile.staging`.

All three are on the Free plan. They are not interchangeable and must not be treated as a single canonical staging environment. Consolidation requires an explicit owner and retention decision; do not delete or suspend any service as part of this audit.

### GitHub repository protection and CI queue

- The GitHub branch inventory reports `main` as `protected=false`. The connected GitHub integration cannot read or change branch-protection settings (the protection endpoint returns HTTP 403, `Resource not accessible by integration`). Until a repository maintainer configures a ruleset, required checks are not guaranteed to be enforced before a direct push or merge.
- Required `main` checks should include the backend CI job, Python and JavaScript CodeQL, secret scanning, Python dependency audit, and deployment-configuration checks. Require pull requests, at least one independent approval, dismissal of stale approvals after new commits, no force pushes/deletion, and no administrator bypass for normal releases.
- As of this audit, the current `main` SHA and open PR heads #152–#156 all have backend/security/deployment check runs reported as `queued`. The integration does not expose the underlying hosted-runner queue reason. A queued check is not a passing check; do not merge or deploy while required checks are pending.
- The Vercel GitHub integration has returned `api-deployments-free-per-day` (more than 100 deployments/day) on PR preview attempts. This is an external preview quota, not a backend CI result. Do not upgrade a paid plan or change the production deployment target without explicit approval.

### Separate research-mode service

- `Dockerfile.research` is the dedicated image for building the public 1000 Genomes research evaluation cohort. It is not the public demo image.
- `render.yaml` describes a separate research-mode service requiring demo mode off, institutional OIDC, tenant isolation and a consent-authority configuration.
- No separately accepted institutional research-mode Render service is currently present in the workspace service inventory. The research image and blueprint are not proof of a live research deployment.
- Public-cohort release terms remain dataset-level terms, not participant-specific consent. The high-coverage family cohort and simulated-consent CI artifacts are evaluation-only and must not be promoted into an institutionally governed deployment without separate authority.

### Database and production status

- Render-managed PostgreSQL inventory is empty.
- No production-grade database target, backup schedule, PITR window, independently held backup key, KMS/HSM key custody, or production restore evidence has been verified.
- The repository includes native PostgreSQL migrations, restricted runtime/migration roles, RLS, consent event ledger and signed checkpoint code. These are implementation foundations; they do not provision infrastructure or prove live production controls.
- Institutional OIDC/SSO, organization membership lifecycle, MFA policy, participant-specific consent authority, independent audit anchoring, monitoring/alerting, incident response and independent legal/privacy/scientific/security sign-off remain unaccepted.
- DUO restrictions NCU/NPU/NPUNCU require verified commercial-use and not-for-profit organisation attributes. The current service has no independently verified organisation/legal-entity registry or DAC-verified commercial-purpose workflow; it passes these attributes as unknown and fails closed. Do not override this by trusting a requester-supplied `is_commercial=false`.
- Consent records without an explicit `consent_basis` are rejected. Signed consent events require timezone-aware, non-future, strictly increasing effective timestamps; this is an event-integrity control, not proof that the issuing authority's statement is truthful.

### Immediate deployment actions

1. Diagnose why the primary Render service has not advanced from `3280ebc` to the current `main` SHA despite auto-deploy being enabled.
2. Configure the primary service health-check path to `/health/live` through an approved Render service update.
3. Run public synthetic-demo live acceptance against the exact deployed SHA and verify requester/donor endpoints expose metadata and short-lived sessions only.
4. Select one canonical staging service and document the intended branch/database pairing before consolidating the other staging services. Do not delete or suspend services without explicit approval.
5. Provision a dedicated durable production database only after the institution approves provider, plan, retention, backup, key custody and budget.
6. Provision a separate research-mode service only after institutional identity, consent authority, database, security, privacy and legal release gates are approved.

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
9. **Live acceptance and deployment:** the primary public Render service reports live commit `3280ebc1924039bcfa19f4c58bb75e83a8c370eb`, behind GitHub `main` at `50658f1ae0ec1df9f4b8c1e512d720bd4e7f5f94`. A separate recovery service reports `f200b643f05a5f959887ac51accd7e202c424557`, also behind current `main`. The current mainline demo endpoints return persona metadata and short-lived process-local session tokens in source code, but exact-SHA live acceptance is pending. Render auto-deploy is enabled on the primary service, yet the observed deployment has not advanced to current `main`.

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


## Fresh operational audit — 13 November 2026, 14:22 UTC

This addendum supersedes earlier deployment snapshots above where their timestamps conflict with the observations below.

### Render public service

- Service: `srv-dbev1ka9lscs738813t0`, branch `main`, Free plan, Singapore, Dockerfile `./Dockerfile`, auto-deploy enabled.
- Last confirmed live backend revision remains `10fb08dcc11ca09282cc1085fd86e3c73708281a`. A live `GET /health` returns HTTP 200 and explicitly reports a synthetic-only dataset (600 synthetic donors, 3,000 synthetic variants), simulated consent, and no verified participant-consent records.
- `GET /health/ready` returns HTTP 503. Durable storage, backup/restore, monitoring/alerting, external audit anchoring, institutional identity, private-cohort ingestion, tenant processing isolation and participant-consent authority are not verified.
- Deployment `dep-dbrgl2c9v7es73chrnd0` has remained `build_in_progress` since 13:03:05 UTC on commit `267c040cecd695f52ebdecb88c34341348c368b6`. The newer synthetic-only image deployment `dep-dbrgucce7ovs73femptg` for commit `3280ebc1924039bcfa19f4c58bb75e83a8c370eb` is queued behind it.
- The connected Render tools support inspection and triggering but do not expose the Render cancel-deploy operation. An operator must cancel the stalled deployment in the Render dashboard (or use the documented Render cancel-deploy API) before the queued synthetic-only deployment can proceed. Do not trigger additional deployments behind the stalled build.

### Vercel frontend

- Latest production deployment remains READY at commit `c12868d951cf966cb4a44852115b230c07b870e9`; it does not include the merged GWAS Catalog PR #149.
- The GWAS merge commit `f200b643f05a5f959887ac51accd7e202c424557` has no production deployment. Vercel reports `api-deployments-free-per-day` (more than 100 deployments; retry after the 24-hour quota window). PR previews are affected by the same quota.
- The deployed frontend's same-origin API reaches the stale Render backend. The live `/openapi.json` contract does not expose the newer PubMed, Open Targets, ClinVar, or GWAS endpoints. Do not mark the frontend/backend integration accepted until the matching backend is live and its API contracts pass.

### Database and research-mode separation

- The connected Neon projects `genomeguard-staging` (`nameless-smoke-96099231`) and `genomeguard-free-demo` (`lingering-wind-59343068`) are both on the `free_v3` subscription with 6-hour history retention. The staging project contains migration/restore validation branches; the free-demo project has a synthetic-demo `main` and PR/research-preview branches. Neither is a durable production database, and neither is configured as an accepted production database.
- The Render workspace has no Render Postgres instances.
- The separate `Dockerfile.research`/research-mode blueprint remains unprovisioned and unaccepted. Do not apply it to the public synthetic demo service or load private participant data.
- PR #150 adds OLS4-backed MONDO/HPO/DOID discovery on a feature branch; it is not merged or deployed. Its exact-head CI is a separate acceptance gate.

### Operator actions and release gates

1. Cancel the stalled Render deployment above; allow the queued synthetic-only deployment to complete.
2. Verify the exact deployed Render SHA, live health, readiness and `/openapi.json` contract.
3. Resolve the Vercel daily deployment quota; deploy the exact main SHA and verify frontend/backend compatibility.
4. Provision and approve durable production storage, backups/PITR, monitoring, key management and recovery evidence before any production data claim.
5. Provision a separate research-mode service only after institutional OIDC, authoritative consent, tenant isolation and independent governance/security reviews are available.

A successful image build, a synthetic demo, a PostgreSQL driver setting, or a CI test does not satisfy production acceptance by itself.


## Fresh public synthetic-demo acceptance — 14 November 2026

Direct HTTP checks against `https://genomeguard.onrender.com` returned:

| Check | Result | Interpretation |
|---|---|---|
| `GET /health/live` | HTTP 200 | ASGI process responds; deployed SHA `3280ebc1924039bcfa19f4c58bb75e83a8c370eb` |
| `GET /health` | HTTP 200 | `demo_mode=true`, synthetic-only, 600 donors, 3,000 variants, PostgreSQL backend |
| `GET /audit/verify` | HTTP 200, `ok=true`, length 4 | Current audit chain verifies; this is only the current chain, not an external immutable anchor |
| `GET /demo/requesters`, `/demo/donors` | HTTP 200 | Demo personas are listed without exposing API keys |
| Demo requester session → `GET /me` | HTTP 200 | Short-lived scoped demo session works |
| Demo donor session → donor profile | HTTP 200 | Short-lived donor session is scoped to the selected demo donor |
| `GET /health/ready` | HTTP 503, `ready=false` | Expected fail-closed production gate; institutional identity, private cohort provenance, durable storage/restore, monitoring, audit anchoring and participant consent authority remain unverified |
| `GET /` | HTTP 200 | HTML document served |

The session-flow check created only short-lived public synthetic-demo sessions; tokens were not logged or retained.

**Browser-origin discrepancy remains open:** a separate hosted-browser run loaded the root HTML but displayed the frontend's API-connection error. Browser `fetch()` to `/health` and `/health/live` rejected with `TypeError: Failed to fetch`, while `/demo/requesters` and `/demo/donors` succeeded. Direct HTTP GETs to the health endpoints returned 200. This may be specific to the hosted-browser environment, but it is not explained. Verify the complete first-load and retry flow in a normal user browser and in GitHub-hosted Playwright before declaring the public UI accepted.

The previous mainline live-demo workflow failed at its first health assertion without reporting the actual status/body. PR #158 adds bounded retries and actionable diagnostics; it does not claim to fix the browser-origin discrepancy. A Render deployment status of `live` and a successful direct health response are not substitutes for full browser acceptance or institutional production readiness.
