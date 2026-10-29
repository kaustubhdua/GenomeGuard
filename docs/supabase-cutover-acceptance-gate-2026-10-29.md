# Supabase cutover and production acceptance gate

Updated: 2026-10-29. Scope: GenomeGuard schema only in the shared Supabase project. Never alter the `bharatsim` schema as part of this procedure.

## Verified live state

- Supabase project is healthy and the `genomeguard` schema contains the legacy request/decision/audit store, normalized genotype tables, dataset manifest, organization memberships, and participant consent records.
- The live `public.genomeguard_deployment_status` row still reports `api_migration_complete=false`, `genomic_dataset_loaded=false`, `render_dependency_present=true`, and `release_gate_passed=false`.
- The Vercel/Render-backed `/health` endpoint reports `storage_backend=sqlite`.
- `/health/ready` returns HTTP 503 and `ready=false`, as it should while storage, backup/restore, institutional identity and external audit anchoring remain unverified.
- The live `/health` reports a real VCF-derived runtime cohort of 600 donors and 3,000 variants with the pinned source SHA-256, but labels the consent basis as dataset-level public-release terms (not participant-specific consent) and reports `storage_backend=sqlite`. This image-bundled cohort is not the same as a normalized Supabase import; the Supabase manifest and genotype tables remain empty.
- CI now performs a disposable logical dump/restore round-trip of the migrated clean PostgreSQL schema and fixture rows. This checks schema/fixture restoration only; it does not substitute for restoring a real Supabase backup into an isolated project and measuring production recovery time/data loss.
- The latest observed Render build (commit `d0fdf8cda13fff24cf2d7e3f1f1195f46bd6ecdc`) failed while reading the downloaded chromosome 22 VCF with a gzip CRC mismatch. The branch now pins the known size/SHA-256 for the exact Phase 3 v5b artifact, retries failed downloads, removes invalid partial files, and adds a regression test for checksum-mismatch retries. GitHub Actions' real-data Docker image build passed on commit `a6d03750ac11939470bc2361282e0549968bde17`; a successful Render production deployment of that code is still unconfirmed.
- `genomeguard.variant_dataset_manifest` is empty. The Supabase Edge Function catalogue must therefore return no verified datasets; never insert a fake manifest to make the UI look complete.
- The repository migration `20261029220000_genomeguard_audit_append_only_and_consent_indexes.sql` defines the append-only trigger and both consent lookup indexes. Supabase's live migration history records the applied migration under version `20261029090645` and name `genomeguard_audit_append_only_and_consent_indexes`; the trigger definition and both indexes were verified by read-only SQL queries. The CI workflow now explicitly tests the trigger's UPDATE/DELETE rejection and index presence on a clean PostgreSQL database.

## Why the API cutover is not complete

The Python service currently bootstraps a NumPy cohort through `app.service.bootstrap`. Setting `GG_DATABASE_URL` alone selects PostgreSQL for the legacy Store, but production startup also requires a matching, locally mounted real cohort file with source-matched consent records. The normalized VCF importer is a separate pipeline that writes `dataset_samples`, `dataset_variants`, `dataset_genotype_calls`, and the manifest; it does not currently feed the Python decision engine. These are different storage contracts and must not be confused.

The Supabase Edge Function implements identity-aware request listing/submission, review and consent-withdrawal RPC calls, and public dataset/chromosome catalogues. Its own readiness response intentionally says the full policy engine, loaded dataset, backup/restore, identity review, external audit anchor, and complete frontend parity are not ready. Do not route the entire production UI to this Edge Function until its API contract matches the existing product and parity tests pass.

## Cutover sequence

1. **Establish a server-side connection.** Configure a least-privilege PostgreSQL connection string in the Render service as secret `GG_DATABASE_URL` only after an operator obtains the connection details from Supabase. Never put it in Vercel public environment variables, Git, CI logs or browser bundles. The current tools cannot retrieve the database password, so this secret must not be guessed or fabricated. Important: the live `genomeguard` schema currently grants no `USAGE` to `service_role`, `authenticated`, or `anon`; do not assume the Supabase service-role API key can be reused as a PostgreSQL login. Provision and test a dedicated server-side database role with only the privileges required by the selected serving model, including the private schema, the legacy request/audit store, and any normalized importer tables. Verify its actual grants and RLS behavior in an isolated environment before adding its connection string to Render.
2. **Resolve the data model bridge.** Choose and implement one canonical serving model: either a fully verified source-matched cohort loaded into the Python engine's compatible store, or a refactor that reads normalized calls from PostgreSQL. Do not silently load a different dataset or relabel GRCh37 as GRCh38. Include deterministic mapping from manifest UUID to the dataset identifier used by requests.
3. **Use only an authorized real artifact.** Obtain the exact source artifact from its official distribution, record its release and source terms, compute SHA-256 locally, check assembly, sample IDs, duplicate records, allele validity and call counts, and run the importer first with `--dry-run`. The importer requires a server-side `DATABASE_URL`; it does not download data or infer consent. A public dataset policy is not a participant-specific consent record.
4. **Wire policy enforcement into every release path.** Before any genotype-derived result, require authenticated identity, active organization membership, permitted purpose/data level, an approved manifest, applicable consent/withdrawal status and a successful risk/transform decision. Withdrawals must invalidate future releases; audit both allowed and refused attempts. The current Edge Function's RPCs are not a substitute for parity with the complete Python decision pipeline.
5. **Validate transactional behavior.** Run tests against PostgreSQL for concurrent submissions, epsilon budget charging, unique decision per request, atomic request/decision/audit writes, restart persistence, permission denial, revoked membership, expired/withdrawn consent, malformed payloads, database timeouts, and idempotent/restarted imports.
6. **Prove backup and restore.** Configure provider backups/PITR as supported by the chosen plan, restore to an isolated database, compare manifest checksums and counts, verify audit-chain continuity, and record a dated result. A configured PostgreSQL URL is not evidence of recoverability.
7. **Verify audit anchoring.** The live audit table now rejects ordinary UPDATE/DELETE. This is append-only behavior inside the database, not immutable external anchoring. Add independently controlled signed checkpoints, verify them after restore, and keep signing keys outside the database.
8. **Run exact-production acceptance.** Exercise all frontend routes at the exact deployed commit; check 401/403/404/413/422/503 paths, authenticated request ownership, keyboard-only operation, screen reader labels, mobile widths, reduced motion, failed lazy imports, and no-JS/API failure states. Store output with commit SHA and deployment URL.
9. **Release only when every gate has evidence.** Update `public.genomeguard_deployment_status` only after the matching tests, real data load, identity/consent review and restore drill actually pass. Do not update readiness flags manually to bypass checks.

## Minimum acceptance evidence

| Gate | Required evidence |
| --- | --- |
| API parity | Contract tests for each production route against PostgreSQL |
| Dataset | Official source citation/reuse review, checksum, assembly and reconciled non-zero sample/variant/call counts |
| Consent | Authoritative records for the actual dataset or a clearly scoped public-release policy; withdrawal tested on the real release path |
| Authorization | Cross-organization, revoked-member and unauthenticated tests all deny |
| Persistence | Request/decision/audit survive service restart and concurrent load |
| Recovery | Restore drill passes and data checksums/counts reconcile |
| Audit | Chain verifies after restart/restore and external checkpoint is independently verified |
| Frontend | All route/API/keyboard/mobile/accessibility smoke checks pass on the exact production commit |

Until this evidence exists, the supported status is **research prototype / release blocked**, not production-ready for private, controlled-access or clinical genomic data.