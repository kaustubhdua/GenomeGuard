# Live acceptance record — 15 November 2026

## Public synthetic demo

The public demo is hosted at https://genomeguard.onrender.com with the frontend at https://genome-guard.vercel.app. The Render service is `srv-dbev1ka9lscs738813t0`, deployed from `main`. The Vercel production project is configured to proxy application requests to the Render API.

The public service is intentionally synthetic-only. The hosted cohort contains 600 generated donors and 3,000 generated variants. Its consent records are simulated examples, not participant consent. No private or controlled-access genotype data may be loaded into this deployment.

## Repair performed

On 15 November 2026, after a pre-change Neon branch was created, the live synthetic donor records were checked against cohort metadata identifying the source as `GenomeGuard synthetic generator`, with `genotypes_real=false` and `consent_simulated=true`.

- Added `consent_basis=synthetic_demo` to 600 donor records that lacked the field.
- Preserved all 15 withdrawals and all existing DUO use codes and restrictions.
- Updated the cohort metadata to explicitly report `consent_basis=synthetic_demo`.
- Did not create participant consent events or claim that simulated consent is legally valid.
- Recorded the operator repair in the database audit chain.

The backup branch is `genomeguard-live-demo-pre-consent-repair-backup-2026-11-15` in Neon project `genomeguard-free-demo`. This is a manual branch backup, not proof of a recurring retention policy or isolated restore drill.

## Live checks

The following live API checks were observed after the Render redeploy:

- `GET /health`: HTTP 200; synthetic-only and simulated-consent flags reported.
- `GET /audit/verify`: valid hash chain; no broken index.
- `POST /demo/session`: HTTP 200.
- `GET /me`: HTTP 200.
- `POST /requests/preview`: HTTP 200; decision `permit`, 453 eligible of 600, with 147 exclusions explained by withdrawal and policy restrictions.
- Preview is non-consuming; it does not reserve or charge privacy budget.

A previous live workflow also submitted a demo request successfully, but preview is not submission acceptance. Re-run the full request, retrieval, privacy-ledger and audit journey after any code deployment.

## Automated verification

The latest recorded exact-main CI run before this follow-up branch was run `43628051514` for SHA `de6cf6e791dc41083032c7fd854eb15d91b91201`, conclusion `success`. It covered Python/API tests, PostgreSQL integration and tenant-isolation tests, backup/restore tests, evaluation/demo smoke checks, JavaScript/Python compilation, browser routes, responsive behavior and accessibility.

The follow-up metadata fix is on a separate pull request and must pass its own exact-head CI before merging or deploying.

## Not institutionally production-ready

The public demo must remain synthetic-only and its readiness endpoint must remain fail-closed. The following controls require real institutional owners, infrastructure, and independent evidence; they cannot be truthfully manufactured by application code or a demo operator:

- institutional OIDC issuer, audience, organization allow-list and role provisioning;
- verified participant consent authority, signing key custody and signed event operations;
- authorized private-cohort ingestion with source provenance and reconciliation;
- tested tenant isolation on the exact production database and deployment;
- durable backup retention, key recovery and isolated restore drill for the actual live database;
- monitoring, alerting, incident response and operational ownership;
- independent audit anchoring under separate credentials and custody;
- independent security, privacy, legal and (where applicable) clinical review.

No real participant data, institutional identity configuration, external signing authority, independent reviewer, or incident-response owner was supplied for this deployment. The product therefore remains a functioning research prototype and synthetic demonstration, not a certified, clinical, or institutional production system.

## Operational constraints

The connected Render service is on the Free plan. Do not upgrade, add paid infrastructure, enable billing, delete services/branches, or import controlled data without explicit authorization. The Render service health-check path was previously unset; the correct liveness path is `/health/live`. Do not use `/health/ready` as the host liveness check because readiness is expected to return HTTP 503 while institutional gates remain unverified.
