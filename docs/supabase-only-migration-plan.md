# Supabase-only backend migration

Status checked: 2026-10-27. This is an implementation plan and status ledger, not a claim that the migration is complete.

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
- Supabase security advisor returned no lints at the last check. The performance advisor initially flagged the donor-access request foreign key; an index migration was applied. Re-run advisors after the next schema changes.

## Critical migration rule

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
