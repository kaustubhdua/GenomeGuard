# Supabase-only backend migration

Status checked: 2026-11-03. This is an implementation plan and status ledger, not a claim that the migration is complete.

## Target

- **Vercel** serves the static frontend.
- **Supabase Auth** provides human identity and sessions once the UI and policy model are migrated.
- **Supabase PostgreSQL** is the durable application store, isolated in the private `genomeguard` schema.
- **Supabase Edge Functions** host the TypeScript API only after endpoint-by-endpoint parity and security tests pass.
- **No Render dependency in the final target.** Do not remove the current Render API proxy before all required routes have working replacements and end-to-end checks pass.

## Work completed

- Created the private `genomeguard` schema in project `common 1` (`hkyieaovolkethovyenb`, region `ap-south-1`).
- Applied the existing PostgreSQL table contract: `cohort_metadata`, `donors`, `genotypes`, `variants`, `relationships`, `requesters`, `requests`, `decisions`, `epsilon_ledger`, `audit_log`, `donor_access`, `alerts`, and `schema_migrations`.
- Seeded migration version 1 in `genomeguard.schema_migrations` to match the existing Python PostgreSQL adapter's migration guard.
- Added an index for `donor_access.request_id` after the Supabase performance advisor identified that foreign key as unindexed.
- Verified the schema and tables exist. Application tables are empty; the genomic cohort has not been imported and the application API has not been migrated to Edge Functions.
- Deployed the first Edge Function, `genomeguard-health` (version 1). It reads a non-sensitive deployment-status row and intentionally returns HTTP 503 / `migration_incomplete` until the API, cohort, and release gates are explicitly marked complete. This is a migration-status endpoint, not the GenomeGuard API.
- Added `.github/workflows/supabase-smoke.yml` to validate the live function response and ensure the readiness gate remains fail-closed. The smoke workflow must pass before this part of the migration is considered verified.
- Added `public.genomeguard_deployment_status` with RLS enabled, no browser-role grants, and an explicit server-role read policy. The service-role key is used only inside the function; it is not returned to clients.
- On 28 October, migration `20261028180028_genomeguard_private_schema_rls.sql` was applied to `common 1` and recorded as `20261028180028` (`genomeguard_private_schema_rls`). Direct SQL verification confirms RLS enabled on all 13 GenomeGuard tables and no schema `USAGE` for `anon`, `authenticated`, or `service_role`. No browser-facing policies are defined because this schema is intended for a trusted server-side connection only. This is defense in depth, not a complete authorization model. The latest Supabase security advisor reports informational `rls_enabled_no_policy` findings for both GenomeGuard and BharatSim tables; preserve the isolation and document these findings rather than adding broad client policies. Performance findings include unused-index informational notices and must be reviewed rather than blindly deleting indexes.

## Current project decision and safety boundary\n\nThe user has explicitly selected the existing Supabase project `common 1` (`hkyieaovolkethovyenb`) for this iteration. It is shared with BharatSim, so this is logical schema isolation, not a dedicated project-level security boundary. Keep all GenomeGuard DDL and data strictly inside the private `genomeguard` schema; do not modify `bharatsim` objects. No synthetic participant/cohort records have been inserted. The live GenomeGuard application tables are empty and the current Render API has not been connected to this database. Until a separately reviewed least-privilege server connection, durable persistence tests, backup/restore proof, and independent security/governance review are complete, keep the service in research-prototype status and do not accept private or controlled-access genomic data.\n\n## Critical migration rule

The existing API is not a thin CRUD API. It contains the decision pipeline, disclosure-risk calculations, consent/policy filtering, epsilon accounting, anomaly monitoring, audit hash-chain, steward review, donor withdrawal, Beacon-style responses, and cohort-backed genotype queries. A generic database CRUD function would bypass these controls and is not an acceptable replacement.

The current Edge Function runtime is TypeScript/Deno, whereas the current implementation is Python/Starlette with NumPy and a loaded cohort artifact. Porting every route is a real rewrite. Keep the old API available until the replacement passes the contract tests below; do not route all traffic to an incomplete Edge Function or claim Render is removed early.

## Endpoint migration inventory

Port in small, testable slices; the route list below is from `backend/app/api.py`.

1. **Runtime and release gates:** `GET /health`, `GET /health/ready`, `GET /eval/results`, `GET /openapi.json`, `GET /docs`.
2. **Requester identity and credentials:** `GET /demo/requesters`, `POST /admin/requesters`, `GET /me`.
3. **Research request pipeline:** `POST /requests`, `GET /requests`, `GET /requests/{id}`, `POST /requests/{id}/review`, `GET /requests/{id}/exposure`, `GET /consent/summary`.
4. **Steward tools and audit:** `POST /requests/{id}/copilot`, `GET /audit`, `GET /audit/verify`, `GET /audit/head`, `GET /anomalies`, `POST /requesters/{id}/freeze`, `POST /requesters/{id}/unfreeze`, `GET /reports/compliance`.
5. **Donor consent workflow:** `GET /demo/donors`, `GET /donor/{id}`, `GET /donor/{id}/consent.fhir.json`, `POST /donor/{id}/withdraw`, `PUT /donor/{id}/consent`, `POST /donor/{id}/restore`, `POST /donor/{id}/ask`.
6. **Interoperability / research demos:** `GET /beacon/g_variants`, `GET /federated/he`, `GET /federated/demo`.
7. **Demo-only destructive controls:** `POST /admin/tamper/{idx}`, `POST /admin/untamper`. These must remain disabled outside explicitly isolated demo mode.

## Verified endpoint parity snapshot (2026-10-29)

This is an explicit cutover blocker list. It describes the checked-in Edge Function implementation, not a promise that an endpoint is production-ready. The public catalogue pages and the authenticated request/review workflow are intentionally switched to Supabase in the current integration branch; this is still a partial migration.

| API contract group | Edge Function state | Release consequence |
|---|---|---|
| `GET /health` | Implemented as a liveness/status-store check | Does not prove readiness |
| `GET /health/ready` | Implemented and deliberately returns HTTP 503 / not-ready | Keep release blocked |
| `GET /datasets`, `GET /chromosomes`, `GET /sources` | Implemented as public, read-only Supabase Edge catalogues | Can display empty/unavailable truthfully; no approved dataset is currently loaded and source discovery is informational only |
| `POST /requests`, `GET /requests`, `GET /requests/{id}` | Implemented with verified Supabase Auth identity and organization-scoped RPCs | Request creation is queued for review; it is not a completed policy-evaluation or data-release workflow |
| `POST /requests/{id}/review` | Implemented for an active reviewer/organization-admin membership and request organization | Records a human review outcome; approval explicitly does not release genomic data |
| `POST /consents/{id}/withdraw` | Implemented for an active consent-steward role | Updates the consent ledger; downstream release paths still need to enforce the withdrawal |
| `GET /me` | Implemented with verified Supabase Auth identity and a service-role-only membership-status RPC | Returns only the caller's own memberships; it does not provision identity or roles |
| `POST /admin/requesters`, `GET /eval/results`, `GET /openapi.json`, `GET /docs` | Not ported to the Edge Function contract | Do not route these paths to Supabase as if parity existed |
| `GET /beacon/g_variants`, `GET /consent/summary` | Not ported | No Beacon or consent summary parity |
| `GET /requests/{id}/exposure`, `POST /requests/{id}/copilot` | Not ported | Exposure graph and advisory copilot remain legacy-only |
| `GET /audit`, `GET /audit/verify`, `GET /audit/head` | Not ported as a complete Edge API | Append-only SQL trigger is not a complete audit API or external anchor |
| `GET /anomalies`, freeze/unfreeze, compliance report | Not ported | Monitoring and steward operations are not migrated |
| Donor consent, withdrawal, restoration, FHIR export and concierge routes | Not ported | Demo donor flows are not equivalent to authoritative participant consent |
| Federated analysis and homomorphic-encryption routes | Not ported as a governed production contract | Treat as demos/experiments only |
| Demo keys and destructive tamper controls | Must remain unavailable outside isolated demo mode | Never expose demo credentials or tamper operations in production |

### Frontend routing facts

- The legacy shared API client still calls relative API paths through the existing deployment rewrite, and sends the legacy `X-API-Key`, `X-Admin-Key`, and `X-Donor-Key` headers for its current product workflows.
- Dataset, chromosome, and source-discovery pages call the public Supabase Edge Function through `frontend/src/catalogue-api.js`.
- Supabase Auth mode routes request submission, request detail, steward queue, and reasoned review to the Edge Function. The interface explicitly states that this path does not run the genomic policy/risk engine or release data.
- No broad Vercel rewrite change has been made. This is intentional: most legacy endpoints do not yet have contract parity, and switching the rewrite now would break core pages or bypass the Python policy engine.
- The publishable Supabase key in the catalogue client is designed for browser use. It is not a service-role key. All governed Edge routes require a verified bearer token and server-side membership checks.
- The current Edge Function uses a server-side service key to call tightly scoped RPCs. Review the grants, SECURITY DEFINER functions, input validation, transaction behavior and negative tests before expanding the API surface.

The checked-in Edge Function therefore is a **partial backend migration**, not a complete Supabase replacement. A route is complete only when its input/output contract, authorization rules, persistence semantics, failure codes and side effects are tested against the legacy reference behavior where that behavior is intended to remain.

## Required implementation order

1. Add TypeScript domain modules and tests for validation, consent policy, risk/transform rules, epsilon budget, audit hash chain, anomaly rules, and requester/admin authorization. Keep the Python implementation as the reference oracle while porting.
2. Implement the persistence layer against the private schema using server-only credentials. Keep genomic genotype tables inaccessible to browser roles. Do not put a Supabase service-role/secret key in any `VITE_*`, `NEXT_PUBLIC_*`, or static frontend variable.
3. Migrate identity and API credentials. Existing `X-API-Key` and `X-Admin-Key` semantics are not equivalent to Supabase Auth; preserve machine-client credentials only through an explicit server-side design, and do not treat editable user metadata as authorization.
4. Port each endpoint group. Compare status codes, response schemas, policy outcomes, privacy-budget deltas, and audit-chain hashes with Python reference tests.
5. Resolve dataset delivery: the database schema is empty. Decide whether the public, provenance-checked 1000 Genomes research artifact is loaded into database tables, Supabase Storage, or a bounded external public source. Measure actual artifact and memory sizes first. Edge Functions have strict runtime/memory limits and are not a safe assumption for CPU-heavy NumPy/cohort processing.
6. Add CI contract tests and run real browser end-to-end tests on a Vercel preview and deployed Supabase functions. Test both allowed and denied requests, held review, donor withdrawal, audit verification, persistence across invocations, and readiness fail-closed behavior.
7. Switch the frontend API base to the Supabase function routes only after the full route matrix passes. Remove the Render rewrite, secrets, and deployment only after a successful canary and rollback window.
8. Verify backup/restore, rate limits, CORS, secret rotation, abuse monitoring, data-retention policy, and privacy/security review before calling the hosted instance production-ready.

## Acceptance gate

The migration is complete only when:
- no browser/API request relies on Render;
- every required route has a real implementation, not a placeholder;
- Python reference and TypeScript contract tests agree on authorization and decisions;
- the deployed cohort is real, provenance-checked, and actually loaded;
- durable writes survive cold starts and concurrent requests;
- audit verification and privacy-budget concurrency tests pass;
- the readiness endpoint reports not-ready until identity, consent governance, external audit anchoring, and other required controls are verified;
- no privileged key is present in frontend bundles or public environment variables;
- deployment, backup, restore, and failure modes are tested.

GenomeGuard remains a research prototype, not a clinical service. Public dataset-level policy mapping is not participant-specific consent, and passing software tests is not independent security, privacy, legal, or clinical approval.


## Latest verified status (3 November 2026)

- Added `GET /steward/requests?limit=&offset=` and the `public.gg_list_review_queue(uuid,integer,integer)` RPC. The queue is organization-scoped, paginated, rejects users without exactly one active reviewer/organization-admin membership, and returns no participant-level genotype data.
- Added `GET /me` and the `public.gg_get_my_access_status(uuid)` RPC. It returns only the caller's own membership status and distinguishes active, ambiguous, pending/inactive, and no-membership states.
- Applied the steward queue and authenticated access-status migrations, the importer privilege and append-only migrations, the aggregate population-reference schema, and the exact-locus lookup index. Live migration versions and local filename prefixes are reconciled in [the migration reconciliation report](supabase-migration-reconciliation-2026-11-03.md). Deployed `genomeguard-api` Edge Function version 11.
- The frontend now includes Supabase email/password sign-in, sign-up, sign-out, in-memory token handling, and explicit no-membership/pending-membership messaging. It routes authenticated request/review calls through the Edge Function and hides legacy-only steward screens in this mode.
- Public source discovery, verified dataset catalogue, and chromosome reference pages now call the Supabase Edge Function rather than the stale Render catalogue endpoints. The source list is discovery-only; no source is marked approved or imported. The verified dataset catalogue is correctly empty until a real import is reviewed and loaded.
- Read-only SQL verification confirms both new RPCs are `SECURITY DEFINER`, use an empty search path, grant execution only to `service_role`, and deny `anon` and `authenticated`. A call using an unprovisioned identity fails closed with SQLSTATE `42501` (`active_reviewer_membership_required`); the access-status RPC returns `no_membership` for an unprovisioned user.
- The project still has zero GenomeGuard organizations, memberships, participant-consent records, normalized dataset samples, variants, genotype calls, requests, and decisions. The two aggregate population-reference tables are also empty. Therefore the positive authenticated request/review lifecycle and any data release cannot yet be exercised end to end.
- The production Vercel frontend is still behind GitHub mainline. The latest deployed commit is `cdf906c83f8fff97dd5aecd96d26770436628482`; the mainline Supabase Auth/catalogue changes are not live yet. The Vercel deployment API returned the free daily deployment quota error (`api-deployments-free-per-day`, retry-after 86,400 seconds). The last live Render health check reported SQLite and the inconsistent `consent_records_matched=600` dataset-policy count; `/health/ready` correctly returned 503. Do not treat the static deployment as proof that the backend is current or durable.
- The latest clean-PostgreSQL migration/privilege workflow passed on an earlier mainline commit, including queue and membership RPC checks. The newest frontend/Auth smoke suite and security workflow must pass on the final mainline commit before those changes count as verified; see GitHub Actions for exact run results.
- The release gate remains closed. The shared Supabase project is not yet connected to the running Render backend, and no real dataset import, authoritative identity provisioning, external audit anchor, or production backup/restore drill has been verified.

## Latest verified status (29 October 2026)

- Full CI, browser/accessibility checks, clean PostgreSQL migration/privilege/backup-restore checks, security verification, real-data image provenance checks and Beacon schema validation passed on commit `9841d7687022b05e898f69f344061dd0b2a87e3b`.
- The Vercel preview for that commit is READY, but it was not promoted to production. The currently hosted Render API is an older backend revision and does not expose the readiness snapshot added on the feature branch.
- Subsequent branch changes clarify that public-dataset policy mapping is not participant-specific consent and scope review/consent authorization to the target organization. The corresponding Supabase migration is applied; the newest CI run must pass before these changes count as verified.
- The release gate remains closed. The normalized manifest, sample, variant and genotype-call tables are empty; the legacy Render/SQLite API still serves traffic; API parity, the normalized-data-to-decision-engine path, institutional identity, independent audit anchoring and production recovery evidence remain incomplete.
- See [production-readiness audit, 29 October 2026](production-readiness-audit-2026-10-29.md) for the current blockers and safe cutover sequence.
