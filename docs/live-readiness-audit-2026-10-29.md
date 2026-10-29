# GenomeGuard live readiness audit — 29 October 2026

## Decision

**Release status: research prototype; not production-ready for private, controlled-access, or clinical genomic data.** The public Vercel workspace is reachable and its lazy-loaded route modules are served, but the API still runs through the Render rewrite and uses SQLite. The Supabase schema is provisioned and private by default, but it is not yet the application's durable API database. The readiness endpoint correctly returns HTTP 503 and `ready: false`.

This document records direct checks against the currently deployed `genome-guard.vercel.app`, the `common 1` Supabase project, and the GitHub repository on 29 October 2026. It does not treat a green deployment badge as proof of end-to-end readiness.

## Live checks performed

| Check | Result | Interpretation |
| --- | --- | --- |
| `https://genome-guard.vercel.app/` | HTTP 200 | The workspace shell loads. |
| `/static/src/main.js` and `/static/src/pages/datasets.js` | HTTP 200 | The JavaScript entrypoint and dataset page are served. |
| `/health` | HTTP 200 | Render-backed research API responds. |
| `/health/ready` | HTTP 503, `ready: false` | Correctly fails closed for production readiness. |
| Production Vercel deployment | READY, main commit `403b9a16934f5fb45f9a199c0347254330c01a68` | Build/deployment succeeded; not a release acceptance test. |
| Supabase `genomeguard.variant_dataset_manifest` | 0 rows | No dataset has passed the Supabase import gate. |
| Supabase application tables | 21 tables, RLS enabled, zero explicit policies | Browser access remains denied by design; server-side role and policy design must be verified before API migration. |
| Supabase deployment-status record | `api_migration_complete=false`, `genomic_dataset_loaded=false`, `render_dependency_present=true`, `release_gate_passed=false` | The database accurately records that the migration/release gates remain closed. |

The live Render health response declares 600 samples and 3,000 variants from a public 1000 Genomes/IGSR chromosome 22 VCF. It explicitly describes the source as operator-declared and not independently authenticated, and describes the policy as dataset-level public-release terms, not participant-specific consent records. Treat these as the existing Render service's reported research dataset facts, not proof that Supabase contains those genotypes.

## Existing product quality that is present

- The frontend route registry uses dynamic `import()` per page; modules are fetched on first route visit, and a failed prefetch is retryable.
- The UI includes loading skeletons, a recoverable route-level error state, responsive styles, a keyboard command/search surface, a guided tour, theme controls, reduced-motion support, and accessibility checks in CI.
- The dataset catalogue calls a read-only Supabase Edge Function and displays explicit empty/error states rather than filling the page with invented dataset records.
- The production API's readiness endpoint fails closed when durable PostgreSQL storage, verified durability, external audit anchoring, and institutional identity are not established.
- The app labels public research provenance and does not claim participant-specific consent for public 1000 Genomes data.

## Release blockers — in execution order

1. **Move the API and persistence layer to Supabase PostgreSQL.** Implement and test endpoint parity for requests, decisions, risk calculations, output transformations, query monitoring, and audit events. Use a narrowly scoped server-side service role; never expose service-role credentials in browser code or `NEXT_PUBLIC_*` variables. The existing Render rewrite is still the production API path.
2. **Prove database contracts and isolation.** Run all application repository tests against PostgreSQL; verify transactionality, concurrent request behavior, audit ordering, ownership, retention, and error semantics. Keep GenomeGuard isolated in the `genomeguard` schema; do not modify BharatSim's schema as a side effect.
3. **Import only a reviewed, real public artifact.** The VCF importer must bind the exact source URL, release, SHA-256, reference assembly, terms/citation, measured sample/variant/call counts, and import status to one reviewed manifest. Test duplicate/interrupted imports, malformed VCF, checksum mismatch, assembly mismatch, and unauthorized reads. Do not seed synthetic or fabricated genotype/consent rows in the live project.
4. **Finish identity and governance.** Provision users and organizations through an authoritative identity workflow; derive role and organization from trusted membership records. Consent withdrawal and release authorization must be enforced in the actual data-release path, not just recorded in a ledger.
5. **Harden audit integrity and recovery.** Configure a supported backup policy, restore to an isolated database, validate data integrity, and establish independently administered signed/append-only audit checkpoints with key custody and trusted timestamps.
6. **Run exact-deployment acceptance.** Test all routes and core workflows against the exact production commit, including unauthenticated/unauthorized paths, persistence after restart, API errors, keyboard navigation, screen-reader behavior, mobile layouts, and reduced-motion settings. Publish the test result and commit SHA.
7. **Complete independent assurance.** Security/privacy threat review, institutional/legal/ethics review, cryptographic review, and scoped penetration testing are required before handling private or controlled-access genomic data.

## Safe operating boundary

Until every release gate above is backed by live evidence, use the deployment only as a public-genotype research prototype. Do not upload private participant data, identifiable genomic data, controlled-access cohorts, or clinical records. A successful Vercel build or HTTP 200 on `/health` is not production readiness.

## Reproducible live-check commands

Run from a trusted terminal; do not put database connection strings in command output or commit secrets:

```sh
curl -fsS https://genome-guard.vercel.app/health
curl -sS -o /tmp/genomeguard-ready.json -w '%{http_code}\n' https://genome-guard.vercel.app/health/ready
```

The readiness request is expected to return 503 until the production readiness gates are genuinely satisfied.
