# GenomeGuard release-readiness and validation record

Updated: 10 November 2026

## Executive status

GenomeGuard is a first-party Python/Starlette research application with a browser workbench, synthetic/public-data workflow, PostgreSQL persistence, institutional-control foundations, and evaluation/interoperability tooling.

The repository is **not yet verified as a final submission build**. PR #120 is open as a draft from `feat/institutional-production-controls` to `main`. The current feature head is `0258fe3169028fa823da582f959c0c8a37ab7312`. The isolated Render staging service is live on that exact commit, and the exact-head hosted acceptance, security verification, and deployment-configuration checks have passed. Backend CI is still running its unit/API suite; PostgreSQL integration, backup/restore, evaluation, demo, compilation, and local browser/accessibility stages have not yet completed. See the current workflow links below.

This is **not production-ready for controlled participant genomic data or clinical use**. The hosted demo uses synthetic data and simulated consent. Private institutional cohort ingestion, real institutional OIDC, authoritative consent, external audit anchoring, provider-grade recovery, monitoring, and governance approvals remain incomplete or external dependencies.

## Source and pull-request topology

- PR #111 (Supabase-free runtime) and PR #113 (institutional controls) are merged into `main`. PR #113 merge commit: `088eaa9adde25cf95b748c31bad365880fe95343`.
- PR #112 was merged into the intermediate `feat/remove-supabase-runtime` branch; its follow-up work was carried into the PR #113 integration branch.
- PRs #116, #117 and #118 were merged into the feature branch before PR #113 merged and are included in main.
- PR #119 was merged into `feat/institutional-production-controls` after PR #113 merged. PR #120 is the current draft and includes the positive steward approval/separate-release safety test, a PostgreSQL-backed tenant workflow integration test, CI separation/deduplication, and smaller unit-test synthetic fixtures.
- Current feature head: `0258fe3169028fa823da582f959c0c8a37ab7312`. PR #120 remains draft pending exact-head CI completion and review.
- GitHub reports `main` as unprotected (`protected: false`). Branch protection and required status checks remain unconfigured/unverified.
- Do not merge another change or declare a release until exact-head CI and staging acceptance are green. Production is to remain untouched.

## PostgreSQL migrations and direct validation

Two disposable Neon child branches were used:

| Purpose | Branch | Branch ID |
|---|---|---|
| Render synthetic staging | `gg-render-staging-2026-11-10` | `br-flat-wildflower-a1pgfnhn` |
| Independent controls validation | `gg-controls-validation-2026-11-10` | `br-royal-morning-a1kkj0ho` |

Migrations **001–012** are applied on both branches. The migration ledger reports every version from 1 through 12.

### Defects discovered and fixed

1. Migration 007 transferred ownership but omitted the required grants to the actual `genomeguard_runtime` application role. It now grants only documented service DML and required sequence access, then revokes consent-ledger mutation.
2. Migration 009 contained mismatched dollar-quote delimiters and could not create the audit immutability trigger. The delimiters are corrected.
3. Migration 010 removes broad cohort DML from the web role. It leaves cohort reads available, limits donor consent changes to an admin-scoped update, and prevents runtime modification of variants, genotypes, relationships, and cohort metadata.
4. Migration 011 adds organization ownership to cohort rows, forces RLS on donors, genotypes, variants, relationships, cohort metadata, and donor-access events, and adds composite donor/organization constraints for genotype and relationship rows.
5. Migration 012 corrects donor-access event binding: a tenant can record access to a shared public/synthetic donor, but cannot log access to another organization's private donor. A row trigger enforces that distinction while preserving the ordinary donor foreign key.
6. The migration runner now avoids `CREATE SCHEMA IF NOT EXISTS` when the schema is already provisioned, because even that statement requires database CREATE privilege. It fails with an actionable error if initial schema provisioning is genuinely missing.
7. Synthetic demo cohort seeding uses the separate migration-owner connection for the one-time cohort write. Runtime web credentials do not receive broad cohort write/delete privileges. PostgreSQL INSERTs use explicit column lists so added tenant columns do not break seeding.
8. Demo requester bootstrap now sets an explicit unscoped-demo context inside one transaction rather than weakening tenant RLS globally.

### Direct database checks

On both disposable branches:

- Runtime role is not superuser, does not have BYPASSRLS, CREATEDB, or CREATEROLE, cannot create in either application schema, is not a member of the owner role, and owns no application tables.
- Runtime can read the migration ledger but cannot write it.
- Runtime can append audit and consent events but cannot update, delete, or truncate those ledgers.
- Runtime can read the public/synthetic cohort and tenant-scoped rows, but cannot insert/update/delete variants, genotypes, relationships, or cohort metadata.
- Donor consent updates are available only through the admin-scoped policy; donor inserts/deletes are not granted to runtime.
- Donor-access rows are append-only to runtime and bound to the requesting organization.
- RLS is enabled and forced for requesters, requests, decisions, epsilon ledger, alerts, identity bindings, consent events, donors, genotypes, variants, relationships, cohort metadata, and donor-access records.

Synthetic rows for two organizations were inserted and queried as separate runtime principals. Tenant A and tenant B saw their own rows plus the shared public/synthetic rows, but not the other tenant's rows. An unscoped session saw only shared rows. A relationship attempting to link donors across organizations was rejected by the composite foreign key. A tenant could log access to a shared public donor; access to another tenant's private donor was rejected by the donor-access trigger.

The staging branch currently contains a freshly generated synthetic cohort (600 donors, 600 encrypted genotype records, 3,000 variants, 959 relationships), four unscoped demo requesters, and audit events. No real participant data was used.

## Hosted synthetic staging

- Service: `genomeguard-staging-pr113`
- URL: https://genomeguard-staging-pr113.onrender.com
- Service ID: `srv-dbpjsie1egvs73cajdlg`
- Neon database branch: `br-flat-wildflower-a1pgfnhn`
- Current live Render deployment: `0258fe3169028fa823da582f959c0c8a37ab7312`, deployment `dep-dbpn762jnfac73bq0a1g`, status `live`.
- The exact-head staging acceptance workflow is running for the same SHA. API/database/authorization/provenance/audit checks passed; hosted browser/mobile checks are in progress: https://github.com/kaustubhdua/GenomeGuard/actions/runs/42887847389
- Exact-head security verification passed secret scanning, CodeQL Python/JavaScript, and dependency vulnerability audit: https://github.com/kaustubhdua/GenomeGuard/actions/runs/42887847324
- Exact-head deployment configuration checks passed: https://github.com/kaustubhdua/GenomeGuard/actions/runs/42887847574
- The service is configured for commit-based auto-deploy, but the integration has not consistently deployed automatically. The latest deployment was explicitly triggered and then verified live on the exact SHA.
- Staging contains synthetic data only and simulated consent. It is not approved for controlled participant genomic data or clinical use.
- Render environment-variable values are not exposed by the available service interface; the exact mapping of runtime and migration URLs to the Neon branch/roles cannot be independently confirmed from Render metadata alone.

The previous staging service on `feat/remove-supabase-runtime` remains separate and unchanged.

## CI and delivery status

Current exact feature head: `0258fe3169028fa823da582f959c0c8a37ab7312`.

- Backend CI run [42887847565](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42887847565): setup, lint, and seed passed; unit/API suite is in progress. Real PostgreSQL integration/tenant-isolation, encrypted backup/restore, evaluation, demo, frontend syntax, Python compilation, and local browser/accessibility steps are pending.
- Hosted staging acceptance [42887847389](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42887847389): API/database/authorization/provenance/audit passed; browser/mobile stage is in progress.
- Security verification [42887847324](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42887847324): secret scanning, CodeQL Python/JavaScript, and dependency audit passed.
- Deployment configuration checks [42887847574](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42887847574): passed.
- Main branch remains at `088eaa9adde25cf95b748c31bad365880fe95343` and is unprotected (`protected: false`). Main-branch CI on the merge commit is not a substitute for the current feature-head validation.
- Vercel preview deployments have hit the account's daily deployment quota. A successful prior preview is not a substitute for current exact-head CI or Render staging validation.
- Do not merge PR #120 until all exact-head CI stages pass and review gates are satisfied.

## Cohort and institutional boundary

The database now supports organization-owned cohort rows with RLS and composite donor/organization integrity. The current service loads the shared public/synthetic cohort into one in-memory dataset at startup; it does not yet provide a complete per-institution private-cohort ingestion and per-tenant in-memory dataset lifecycle. Keep the hosted app on public/synthetic data. Do not claim controlled institution-supplied cohort processing is production-complete.

The public/synthetic rows are intentionally visible across organizations. Private rows must have an explicit `organization_id`; application roles cannot import or rewrite cohort data through broad web DML. Any future institutional cohort-ingestion workflow must preserve tenant-scoped context and prove the same isolation end to end.

## Recovery and operations

- The encrypted PostgreSQL backup/restore and audit-verification test is part of CI and must pass on the final head.
- The linked Neon project is on a free plan with a short history-retention window and no scheduled snapshot policy. This is suitable only for disposable demo staging, not production recovery.
- No institution-approved PITR/offsite retention, RPO/RTO, independent key custody, monitoring/alert routing, or recurring restore drill has been verified.
- The live Render staging service is on a free plan. Its current provider health-check path is `/health/live`, matching the checked-in staging Blueprint. Commit-triggered deployment is not currently observed despite the configured auto-deploy setting.

## Historical hosted acceptance and CI follow-up

The following 16:23 UTC checkpoint is historical and is superseded by the current 18:06 UTC snapshot above. At 16:23 UTC on 10 November 2026:

- The isolated Render service deployed commit `b6a13be11341622dc7854de54efdc4a2d8443a60` successfully and served the synthetic cohort over PostgreSQL.
- GitHub Actions staging-acceptance run [42853659255](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42853659255) passed. Its read-only API checks verified the expected commit, PostgreSQL backend, 600 synthetic donors, 3,000 variants, simulated-consent disclosure, anonymous authorization denials, public audit-chain verification, and source/dataset/chromosome catalogues. Browser acceptance passed in light and dark themes, all ten checked routes had no JavaScript errors, and responsive checks at 320, 375, and 414 px reported no horizontal overflow.
- CI run [42853659273](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42853659273) on that same commit failed at lint only: `backend/app/service.py` retained an unused `os` import after startup no longer removed the migration URL from process state. The import was removed in commit `d215ae0ce2625e5b5016f6990b5288314783b71b`.
- The exact latest commit `d215ae0ce2625e5b5016f6990b5288314783b71b` is being deployed to the isolated staging service. A fresh full CI run on that exact commit, including PostgreSQL integration, backup/restore, evaluations, and browser/accessibility checks, is still required. The successful staging acceptance above is for the immediately preceding commit, not a substitute for that exact-head run.

## Final hackathon submission gates

1. Finish exact-head CI on the merged main commit and the follow-up feature test commit: PostgreSQL integration, encrypted backup/restore, audit verification, evaluation, demo, Python/JS checks, Playwright browser routes, responsive layouts, and axe accessibility.
2. Resolve the Render Git-provider/commit-trigger issue, deploy the exact tested commit to `genomeguard-staging-pr113`, and verify the deployed SHA before hosted acceptance.
3. Verify `/health`, `/health/ready`, database readiness, demo personas, request submission, steward approval/rejection, output transformation, privacy-budget accounting, audit verification, consent examples, FHIR/Beacon outputs, and browser journeys.
4. Reconcile the live Render health-check path with `render.staging.yaml` through a reviewed Blueprint plan.
5. Capture current screenshots and a five-minute demo recording using `docs/hackathon-demo-guide.md`.
6. Keep the README, current-status page, and demo guide aligned with the deployed SHA.

## External gates before controlled-data or production use

1. Institution-supplied OIDC issuer/client, trusted JWKS, verified organization lifecycle, MFA/revocation policy, and real provisioned identities.
2. Authoritative consent-source integration, correct sample mapping, withdrawal timing, and institution-approved legal/ethics governance.
3. Per-institution cohort ingestion and dataset lifecycle, including tenant-bound in-memory processing and full end-to-end tests.
4. Approved durable database/PITR, offsite backup retention, monitoring, RPO/RTO, restore drills, and independent key custody.
5. External immutable audit anchoring, trusted timestamps, signing-key rotation/custody, and independent review.
6. Threat-model, penetration, cryptographic, privacy, legal, ethics, and (if applicable) clinical/regulatory review.

## Safety boundary

GenomeGuard remains research software. The live environment is synthetic-only. Do not upload private or controlled-access participant genomic data, claim clinical validity, or enable a real institution until identity, consent, data-use, privacy, operational, and governance approvals are in place.
