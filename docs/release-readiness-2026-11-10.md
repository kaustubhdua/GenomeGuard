# GenomeGuard release-readiness and validation record

Updated: 10 November 2026

## Executive status

GenomeGuard has a substantial first-party Python/Starlette research application, browser UI, synthetic/public-data workflows, evaluation tooling, and institutional-control foundations. The repository is **not yet verified as a finished hackathon release**, because the latest exact-head CI and a deployment of the new code to synthetic staging are still pending.

It is **not production-ready for controlled participant genomic data or clinical use**. Institutional identity, consent authority, cohort data partitioning, independent audit anchoring, provider-level recovery, and external governance remain separate requirements.

## Source and pull-request topology

- PR #111, the Supabase-free runtime, was merged to `main`. Main is at merge commit `0ff7b8c4c5223787606781057224326bab8e2cc1`.
- PR #112 was merged into the intermediate `feat/remove-supabase-runtime` branch, not directly into main.
- PR #113 is the current draft proposal from `feat/institutional-production-controls` to `main`. It contains the institutional-control implementation and follow-up database fixes discovered during validation.
- Keep PR #113 in draft until exact-head CI, staging acceptance, and the restricted-role staging deployment pass. Do not bypass review by moving the main ref directly.

## Verified PostgreSQL migration exercise

A disposable child branch in the linked Neon staging project was created specifically for this exercise:

- Branch: `gg-controls-validation-2026-11-10`
- Branch ID: `br-royal-morning-a1kkj0ho`
- Parent: `br-morning-field-a19ap5kw`
- Database: `genomeguard`

Migrations 003–009 were applied in order on this disposable branch after the existing 001–002 baseline. The migration ledger reports versions 1 through 9.

### Defects discovered and corrected in source

1. Migration 007 transferred ownership to `genomeguard_owner` but did not grant the actual `genomeguard_runtime` application role the DML/sequence privileges required by the service. It now grants the required DML and sequence privileges and sets matching default privileges for future owner-created objects. It revokes UPDATE/DELETE/TRUNCATE on the consent ledger after the broad grants.
2. Migration 009 had mismatched PostgreSQL dollar-quote delimiters. The audit-trigger function and privilege block now have matching delimiters.
3. Existing staging databases can have `genomeguard_runtime` as the owner of the pre-existing runtime schema. The migration runner now detects that legacy state and, only when the migration owner can safely SET ROLE to the schema owner, grants migration-only CREATE to `genomeguard_owner`. Migration 007 then transfers ownership and removes runtime CREATE. Other ownership mismatches fail closed with an actionable error.
4. PostgreSQL integration tests now assert that the runtime role can read/append consent events but cannot update, delete, or truncate them. A regression test covers migration bootstrap for the legacy runtime-owned schema.

### Direct database checks

On the disposable validation branch, the runtime principal was verified as:

- not superuser, not BYPASSRLS, not CREATEDB, not CREATEROLE;
- unable to CREATE in either GenomeGuard schema;
- not a member of `genomeguard_owner`;
- not owner of application tables;
- unable to TRUNCATE protected tables;
- able to append audit entries, but unable to update/delete/truncate audit entries;
- able to read and append consent events, but unable to update/delete/truncate them;
- able to read the migration ledger, but unable to insert/update/delete it.

RLS was enabled and forced for requesters, requests, decisions, epsilon ledger, alerts, identity bindings, and consent events. Identity-binding policy was present after migration 008.

Synthetic test identities for two organizations were used to verify that tenant A and tenant B saw only their own identity bindings. An insert attempting to write an organization-B request while scoped to organization A was rejected by PostgreSQL with an RLS violation. Missing tenant context returned no requester, request, or identity-binding rows.

The validation branch contains disposable test rows and is not the Render staging database or a production database.

### Important cohort-data boundary

The current schema does not apply tenant RLS to the shared cohort/reference tables `donors`, `genotypes`, `variants`, `relationships`, `donor_access`, or `cohort_metadata`. The current design treats the public/synthetic cohort as shared service data and relies on server-side application policy; it does not provide participant-level tenant partitioning for arbitrary institution-supplied cohorts. Do not expose database credentials to browsers or untrusted clients. Before controlled multi-institution cohorts are accepted, define and test an explicit cohort ownership/access model or isolate each institution's cohort in a separate database/schema with independently verified policy.

## Current staging and production state

### Render synthetic staging

- Service: `genomeguard-staging` (`srv-dbp41m5bedkc73fk4aug`)
- URL: https://genomeguard-staging.onrender.com
- Render branch: `feat/remove-supabase-runtime`
- Last inspected live deploy: `dep-dbp64otbedkc73fq1ec0`, commit `60fc7f33c1a971cbca37195f9c41b2eef23ed005`
- The service is still on the earlier branch; it has not yet been deployed from PR #113.
- Render service details report auto-deploy enabled but no provider health-check path configured. The checked-in Blueprint and live service configuration therefore need reconciliation.
- Logs show normal page/API requests returning 200 and `/health/ready` returning 503. In synthetic demo mode, fail-closed readiness is expected and must not be described as production readiness.
- The Render connector does not expose the service's secret environment values. Its exact Neon branch URL binding is therefore not asserted here.

### Linked Neon project

The default branch `br-patient-recipe-a1agz4kb` in the linked staging project has 600 synthetic donors, 3,000 variants, 600 genotype rows, and 16 audit rows. Its migration ledger still reports only versions 1 and 2. It has the `genomeguard_owner` and `genomeguard_runtime` roles. The migration exercise was deliberately completed on the separate disposable child branch, not on this default branch.

The Neon project is on Free v3 with a six-hour history-retention window and no scheduled snapshot policy. This is not an approved production recovery plan. The CI encrypted backup/restore test and the documented synthetic snapshot restore are not substitutes for provider-level PITR, offsite retention, key custody, and recurring restore drills.

### Production

The Render production service `genomeguard` (`srv-dbev1ka9lscs738813t0`) still deploys the `main` branch. No production environment variables, database, deployment, or data were changed in this work. The previously documented production persistence model uses SQLite on an ephemeral hosting filesystem and must be replaced before any production claim.

## CI and delivery status

- The earlier exact-head CI run `42736856617` was cancelled during the PostgreSQL integration step; its later steps were skipped.
- The cancelled run is not evidence of a passing test suite.
- New workflows were queued for the updated PR head. Record their final conclusions in PR #113 before marking the project release-ready.
- Vercel preview status is reported separately from Render staging; a successful preview build does not establish database, OIDC, consent, or production readiness.
- Repository branch protection is not enabled on the current plan. Preserve review and required-check discipline manually.

## Product capabilities and demo scope

The intended hackathon demonstration is synthetic/public-data research governance:

- research request submission and policy/risk decisions;
- output transformation and privacy-budget tracking;
- steward review and audit verification;
- public-source provenance and genotype QC;
- synthetic consent examples and FHIR/Beacon interoperability demonstrations;
- OIDC identity/organization-control foundations;
- repeatable evaluations, API tests, browser journeys, responsive checks, and accessibility automation.

Do not present dataset-level public-release terms as participant-specific consent, a synthetic FHIR resource as an actual consent record, QC success as import approval, or a risk heuristic as a formally audited differential-privacy guarantee.

## Remaining release gates

### Before calling the hackathon demo finished

1. Complete exact-head CI on PR #113: PostgreSQL integration, encrypted backup/restore, evaluation, demo, syntax/compile, browser routes, responsive behavior, axe checks, and guided tour.
2. Deploy the exact tested commit to the synthetic Render staging service using a restricted runtime URL and a separate migration-owner URL. Keep synthetic demo mode explicit.
3. Verify startup migrations, role assertions, database persistence, route behavior, audit verification, and browser journeys against the deployed SHA.
4. Reconcile the live Render service with the checked-in Blueprint, including the health-check path and auto-deploy policy.
5. Refresh the demo script, architecture/data-flow diagrams, screenshots, and evaluation results so they describe the deployed commit rather than an earlier build.
6. Perform a manual keyboard/screen-reader review in addition to automated accessibility checks.

### Before controlled-data or production use

1. Supply an institutional OIDC issuer/client, trusted JWKS, verified organization lifecycle, MFA/revocation policy, and real provisioned identities.
2. Establish authoritative consent-source integration, correct sample mapping, withdrawal timing, and institution-approved legal/ethics governance.
3. Define tenant ownership and row-level isolation for institution-supplied cohort data, not only operational requests.
4. Use an approved durable database plan with scheduled backups/PITR, retention, independent key custody, monitoring, and tested RPO/RTO.
5. Configure external immutable audit anchoring/signing, trusted timestamps, and key rotation/custody.
6. Complete independent threat-model, penetration, cryptographic, privacy, legal, ethics, and (if applicable) clinical/regulatory review.

## Safety boundary

GenomeGuard remains research software. Keep synthetic/public-data demo behavior separate from participant/controlled data. Do not load private or controlled genomic records, claim clinical validity, or enable a real institution until the institution's identity, consent, data-use, privacy, and operational approvals are in place.
