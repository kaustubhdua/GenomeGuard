# GenomeGuard — current implementation and release status

Updated: 10 November 2026

## Executive status

GenomeGuard is a research prototype with a first-party Python/Starlette API and a browser application. The Supabase-free runtime is implemented in [PR #111](https://github.com/kaustubhdua/GenomeGuard/pull/111), branch `feat/remove-supabase-runtime`.

**A separate synthetic-only staging deployment is live and connected to PostgreSQL. Production is not ready.** Automated CI verifies a commit in an isolated environment; it does not prove legal permission, participant consent, institutional identity, clinical validity, or provider-level disaster recovery.

## Current architecture

- Browser frontend uses same-origin GenomeGuard routes.
- Python/Starlette is the application API and policy engine.
- Local development uses synthetic data and SQLite.
- Hosted non-demo mode requires PostgreSQL via server-side `GG_DATABASE_URL`.
- Supabase Auth, Supabase browser keys, Supabase Edge Functions, and Supabase runtime calls are removed from the active frontend.
- Historical `supabase/` migrations are inert archive records and must not be applied to new deployments.
- Agent explanations are offline deterministic templates and bounded rules; no hosted AI provider or API key is used.

## Latest repository verification

- Branch: `feat/remove-supabase-runtime`
- Latest commit: `51ba51753d34526d22d71a616afcc2e7c7546cf4`
- PR: [#111 — Remove Supabase from GenomeGuard runtime](https://github.com/kaustubhdua/GenomeGuard/pull/111)
- Latest CI: [run #42708010499](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42708010499) — in progress at last check.
- Deployment configuration checks on this head: success.
- Earlier full CI on commit `2254541bc9d8860bcfb22aeaff94b73efaa88404`: success, including backend tests, PostgreSQL integration, browser tests, responsive checks, accessibility checks, VCF QC, and guided tour.
- A subsequent run exposed Ruff import ordering in the newly added staging-image regression test. That was fixed on the current branch and CI was restarted; do not call the latest head green until run #42708010499 finishes.
- Security, Beacon, FHIR, and real-data image validation workflows are running for the current head.

## Live synthetic-only staging

A separate free Render service was created without changing or adopting the production service:

- URL: [https://genomeguard-staging.onrender.com](https://genomeguard-staging.onrender.com)
- Dashboard: [Render staging service](https://dashboard.render.com/web/srv-dbp41m5bedkc73fk4aug)
- Service ID: `srv-dbp41m5bedkc73fk4aug`
- Repository branch: `feat/remove-supabase-runtime`
- Dockerfile: `Dockerfile.staging` (does not download or embed the 1000 Genomes cohort)
- Neon PostgreSQL database: separate free staging project in Singapore.
- Runtime database role: `genomeguard_runtime`, not the database owner. It has CREATE/USAGE on `genomeguard_runtime` and read-only access to the normalized `genomeguard` schema. The role was tested for application-schema DDL and SELECT access.
- Secrets are held in Render environment variables, not in Git or frontend code. The admin key was rotated after the public demo-key disclosure issue was found.

Staging configuration:
- `GG_DEMO_MODE=true`
- `GG_ALLOW_TAMPER_DEMO=false`
- `GG_EXPOSE_DEMO_ADMIN_KEY=false`
- `GG_REAL_COHORT_FILE=`
- `GG_DATASET_ID=synthetic-cohort-1`
- `GG_DATABASE_URL` points to the direct Neon endpoint (not PgBouncer's `-pooler` endpoint).

### Live checks performed

| Check | Observed result |
|---|---|
| `GET /health/live` | HTTP 200 |
| `GET /health` | HTTP 200; `storage_backend=postgresql` |
| Cohort | 600 synthetic donors, 3,000 synthetic variants |
| `GET /health/ready` | HTTP 503, expected for synthetic demo; gates remain fail-closed |
| `GET /catalogue/sources` | HTTP 200, discovery-only metadata |
| `GET /catalogue/datasets` | HTTP 200, empty until approved manifests are imported |
| `GET /audit/verify` | HTTP 200, chain valid |
| Research request | HTTP 201; synthetic request returned `permit_with_transform` |
| Request history | HTTP 200; newly created synthetic request listed |
| Admin endpoint without/wrong key | HTTP 401 |
| Admin endpoint with rotated secret | HTTP 200 |
| Public demo-account endpoint | HTTP 200; no `admin_key` field and no hosted admin secret |

The hosted demo-account endpoint previously returned the configured admin key. This was a genuine security defect. It is fixed: admin-key disclosure now defaults off, is explicitly opt-in for local interactive development only, and the staging key was rotated. Hosted staging hides steward-only controls rather than exposing privileged credentials.

The staging database is currently synthetic-only. Its readiness endpoint must remain not-ready: demo mode is enabled, real participant genotypes and participant consent are absent, and external audit anchoring, independently verified institutional identity, and durable-storage verification are not established.

The request workflow has been exercised against PostgreSQL. A post-redeploy persistence check is still required on the latest staged commit; do not claim that a restore/recovery drill has been completed against this provider instance.

## Product capabilities and boundaries

- Research request, review, and policy/risk workflow foundations.
- Synthetic-data demonstration.
- VCF parsing and QC with a clear distinction between QC success and import eligibility.
- Public source discovery and catalogue provenance.
- Consent logic that distinguishes participant records from dataset-level terms.
- Hash-chained audit trail and PostgreSQL-backed store.
- Encrypted backup/restore tooling and CI recovery tests.
- GA4GH Beacon v2 and FHIR R4 validation workflows.

These are research-software capabilities, not proof of lawful data import, clinical validation, or operational controls.

## Production release blockers

| Area | Current evidence | Required before production or controlled data |
|---|---|---|
| Production deployment | Existing Render production service still deploys `main`, not this PR. | Review and merge only after checks pass; deploy exact reviewed commit and run live acceptance. |
| Persistence | Production Render still uses SQLite. Separate staging Render uses Neon PostgreSQL. | Production-grade managed PostgreSQL, provider backups/PITR, offsite retention, tested restore and retention. |
| Identity | API keys authenticate application roles. | OIDC identity and server-side verified organization membership. |
| Consent | Staging uses simulated consent; dataset terms are not individual consent. | Source-specific rights review and participant-level consent where required, including withdrawal enforcement. |
| Real data | No production import/reconciliation verified. | Steward-approved artifact, license/terms, assembly, checksum, sample/variant/call-count reconciliation and provenance. |
| Audit | Local hash chain and unsigned integrity checkpoint. | Independent authenticated external anchoring/signing, key custody and monitoring. |
| Security/privacy governance | Automated checks only. | Independent threat model, privacy, legal, ethics, security and operational review. |
| Clinical validity | No clinically validated annotation or pathogenicity pipeline. | Qualified validation, regulatory assessment and expert oversight; never use prototype output for clinical decisions. |

Do not weaken readiness gates to make deployment appear healthy.

## Recommended next sequence

1. Complete CI and security verification for the latest PR head.
2. Deploy the exact tested branch commit to the synthetic-only staging service.
3. Verify the same synthetic request and audit history survive a redeploy; then exercise the documented encrypted backup/restore procedure on staging.
4. Complete OIDC and organization-level authorization before any controlled data.
5. Complete legal/ethics/source review and consent provenance before real-data import.
6. Only after independent review, plan production database, backup, monitoring and rollout.
7. Merge and deploy production only after the exact commit and all release gates have passed.

## Important limitations

- Do not upload private participant genomic data to staging or production.
- Do not infer participant consent from dataset-level open-data terms.
- Do not treat VCF QC as import approval or clinical validation.
- Do not treat API keys as institutional identity.
- Do not treat a green CI run or reachable frontend as production readiness.
- No production service was changed, no paid service was provisioned, and no clinical approval is claimed.

## Related records

- [PR #111](https://github.com/kaustubhdua/GenomeGuard/pull/111)
- [Current CI run #42708010499](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42708010499)
- [Supabase-free deployment guide](supabase-free-deployment.md)
- [Render staging setup](render-staging.md)
- [Production deployment record](production-deployment.md)
- [README](../README.md)
