# GenomeGuard production-readiness audit — 29 October 2026

## Decision

**Release status: BLOCKED — research prototype only. Do not use for private/controlled-access participant data or clinical decisions.**

The codebase has meaningful security and test improvements, but the complete product acceptance criteria are not met. A passing CI run, a Vercel preview marked READY, or a reachable API is not proof of end-to-end production readiness.

## Current evidence

- Live Supabase deployment status remains `api_migration_complete=false`, `genomic_dataset_loaded=false`, `render_dependency_present=true`, `release_gate_passed=false`.
- The normalized Supabase tables `genomeguard.variant_dataset_manifest`, `dataset_samples`, `dataset_variants`, and `dataset_genotype_calls` each contain **zero rows**.
- All 23 tables in the private `genomeguard` schema have RLS enabled and no direct SELECT grants to `anon`, `authenticated`, or `service_role`. Browser access is through narrowly granted server-side RPCs, not direct table reads.
- Security-definer RPCs reviewed here use an empty `search_path`; execution is revoked from `anon` and `authenticated` and granted to `service_role`.
- Request history is membership-scoped; review transitions are stored separately and reject UPDATE/DELETE/TRUNCATE; consent withdrawal requires the explicit `consent_steward` role. Target-organization scoping for reviewers and consent stewards was hardened in the latest migration.
- The existing hosted runtime reports a 600-sample / 3,000-variant cohort derived from the public 1000 Genomes chromosome 22 VCF. Its source is still labelled operator-declared rather than independently authenticated, and its dataset-level policy mapping is explicitly **not** participant-specific consent.
- The legacy Render/SQLite-backed Python API still serves the research instance. The Supabase Edge API only covers a subset of routes. The normalized importer is not connected to the decision engine through one authoritative data path.

## CI and deployment evidence

- Last fully green commit: `9841d7687022b05e898f69f344061dd0b2a87e3b`.
- That commit passed backend and real-PostgreSQL tests, lint, evaluation smoke/full evaluation, demo checks, JavaScript syntax, Python compilation, browser route smoke, guided tour, 320/375/414px responsive checks, and axe critical/serious accessibility scans in both themes.
- On that commit, clean-schema migration/privilege/backup-restore checks, Python and JavaScript CodeQL, secret scanning, dependency audit, real-data image provenance/no-raw-source-retention checks, and GA4GH Beacon v2 schema validation passed.
- Vercel preview deployment `dpl_HtMaApF6imKohEfw8sxPxz5QkpBR` is READY for that exact commit. It was **not** promoted to production.
- Changes after that commit correct public-data UI wording and scope review/consent authorization to the target organization. They have been applied to the feature branch and the relevant database migration applied to live Supabase; the newest CI run must pass before those changes count as verified.
- The currently hosted API is on an older backend deployment and does not expose the readiness snapshot added on the feature branch. No claim is made that the latest branch is running in production.

## Remaining release blockers

1. **Backend parity:** the frontend still uses legacy API-key routes for core request, audit, donor, risk, monitoring, and review workflows. Supabase Edge Function parity is incomplete. Do not switch all traffic to the Edge Function or remove Render until each route has contract, authorization, and negative tests.
2. **Authoritative genomic data path:** the VCF importer exists, but no normalized dataset is loaded into Supabase. No validated bridge connects normalized genotype-call rows to the Python decision engine. Do not flip the dataset or release status flags manually.
3. **Real consent and identity:** public 1000 Genomes data has a dataset-level reuse policy, not per-participant consent records. Institutional identity, organization affiliation verification, consent evidence for private cohorts, and withdrawal enforcement on every release path are not implemented/verified.
4. **Release enforcement:** a review approval is not a data release. A single governed release function must re-check organization membership, current policy, participant consent where applicable, dataset state, purpose, data level, disclosure risk, and withdrawal status in the same transaction as output generation.
5. **Audit assurance:** the local hash chain is not an independently controlled external audit anchor. Signed checkpoint storage and verification are not configured.
6. **Operations:** a dedicated least-privilege production PostgreSQL connection, restart/redeploy persistence, provider backup policy, production restore drill, alerting, and rollback verification are not evidenced.
7. **Independent review:** institutional security, privacy, ethics, legal, and data-use review is still required before any private or controlled-access cohort can be accepted.

## Safe completion path

- Finish and pass the current feature-branch CI, including the multi-organization authorization regression tests and dataset-policy copy tests.
- Configure a least-privilege server-side database connection in the hosting provider without sharing credentials in chat or Git.
- Import one specifically reviewed public dataset using the checksum/assembly/policy gate, reconcile samples/variants/calls, then publish the manifest only after validation.
- Implement and test the normalized-data decision/release path; keep the release gate closed until consent, disclosure controls, identity, audit anchoring and recovery tests are complete.
- Complete endpoint-by-endpoint parity and switch frontend routes incrementally with rollback available.
- Run a production smoke/restore drill against the exact deployed commit; only then consider promotion and updating release status.

**Do not represent the project as complete or production-ready until these blockers are resolved and evidenced.**