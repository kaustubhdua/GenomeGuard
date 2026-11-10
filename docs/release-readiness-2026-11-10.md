# GenomeGuard release-readiness and validation record

Updated: 10 November 2026

## Executive status

GenomeGuard is a first-party Python/Starlette research application with a browser workbench, synthetic/public-data workflow, PostgreSQL persistence, institutional-control foundations, and evaluation/interoperability tooling.

The repository is **not yet verified as a final submission build**: the latest exact-head CI and hosted staging acceptance must finish on the same commit. A live synthetic-only Render staging service now starts successfully, connects to Neon through distinct runtime and migration credentials, loads a freshly encrypted 600-donor synthetic cohort, and provisions four demo personas. The exact PR head still needs to be deployed and accepted.

This is **not production-ready for controlled participant genomic data or clinical use**. The live demo uses synthetic data and simulated consent. Institutional OIDC, authoritative consent, external audit anchoring, provider recovery policy, and governance approvals remain external dependencies.

## Source and pull-request topology

- PR #111 (Supabase-free runtime) is merged into `main`.
- PR #112 (institutional controls) was merged into the intermediate `feat/remove-supabase-runtime` branch, not directly into `main`.
- PR #113 is the current draft proposal from `feat/institutional-production-controls` to `main`.
- Keep PR #113 draft until exact-head CI and staging acceptance are green. Do not bypass review or merge an unverified commit.
- Main remains on the previously merged Supabase-free baseline. Production has not been changed.

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
- Live deployment observed: `52126ade746fae914bd90f67c800328aa1da8be7`
- Logs show application startup complete, `GET /health` returning 200, and the four demo requesters present in PostgreSQL.
- The live service uses distinct runtime and migration URLs and a unique staging encryption key. Database URLs and secrets are not exposed to the browser or this report.
- The checked-in Blueprint specifies `/health/live`, but the live Render service currently reports an empty provider health-check path. A Blueprint adoption plan is still required to reconcile this without changing production.
- The latest PR head is newer than the currently observed live deployment. Deploy and verify the final exact head before submission.

The previous staging service on `feat/remove-supabase-runtime` remains separate and unchanged.

## CI and delivery status

- Earlier CI run `42850704480` failed at lint due to import formatting; that issue was fixed.
- CI run `42851307521` on commit `c451dd6279fa809318fbafbfc8e68a10dc4cbe3b` passed lint and seed and is running PostgreSQL integration tests. It is not the latest PR head.
- On that run, deployment configuration, CodeQL (Python and JavaScript), dependency audit, FHIR R4 Consent validation, GA4GH Beacon v2 validation, and the real-data image build passed.
- The staging acceptance workflow is still running and must finish against the exact deployed PR head.
- A Vercel preview or successful Docker image build is not proof of database, OIDC, consent, or staging workflow readiness.

## Cohort and institutional boundary

The database now supports organization-owned cohort rows with RLS and composite donor/organization integrity. The current service loads the shared public/synthetic cohort into one in-memory dataset at startup; it does not yet provide a complete per-institution private-cohort ingestion and per-tenant in-memory dataset lifecycle. Keep the hosted app on public/synthetic data. Do not claim controlled institution-supplied cohort processing is production-complete.

The public/synthetic rows are intentionally visible across organizations. Private rows must have an explicit `organization_id`; application roles cannot import or rewrite cohort data through broad web DML. Any future institutional cohort-ingestion workflow must preserve tenant-scoped context and prove the same isolation end to end.

## Recovery and operations

- The encrypted PostgreSQL backup/restore and audit-verification test is part of CI and must pass on the final head.
- The linked Neon project is on a free plan with a short history-retention window and no scheduled snapshot policy. This is suitable only for disposable demo staging, not production recovery.
- No institution-approved PITR/offsite retention, RPO/RTO, independent key custody, monitoring/alert routing, or recurring restore drill has been verified.
- The live Render service is on a free plan. The provider health-check path still needs to be reconciled with the checked-in Blueprint.

## Latest hosted acceptance and CI follow-up

At 16:23 UTC on 10 November 2026:

- The isolated Render service deployed commit `b6a13be11341622dc7854de54efdc4a2d8443a60` successfully and served the synthetic cohort over PostgreSQL.
- GitHub Actions staging-acceptance run [42853659255](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42853659255) passed. Its read-only API checks verified the expected commit, PostgreSQL backend, 600 synthetic donors, 3,000 variants, simulated-consent disclosure, anonymous authorization denials, public audit-chain verification, and source/dataset/chromosome catalogues. Browser acceptance passed in light and dark themes, all ten checked routes had no JavaScript errors, and responsive checks at 320, 375, and 414 px reported no horizontal overflow.
- CI run [42853659273](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42853659273) on that same commit failed at lint only: `backend/app/service.py` retained an unused `os` import after startup no longer removed the migration URL from process state. The import was removed in commit `d215ae0ce2625e5b5016f6990b5288314783b71b`.
- The exact latest commit `d215ae0ce2625e5b5016f6990b5288314783b71b` is being deployed to the isolated staging service. A fresh full CI run on that exact commit, including PostgreSQL integration, backup/restore, evaluations, and browser/accessibility checks, is still required. The successful staging acceptance above is for the immediately preceding commit, not a substitute for that exact-head run.

## Final hackathon submission gates

1. Complete exact-head CI: PostgreSQL integration, encrypted backup/restore, audit verification, evaluation, demo, Python/JS checks, Playwright browser routes, responsive layouts, and axe accessibility.
2. Deploy the exact tested commit to `genomeguard-staging-pr113`.
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
