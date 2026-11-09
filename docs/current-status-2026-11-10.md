# GenomeGuard — current implementation and release status

Updated: 10 November 2026

## Executive status

GenomeGuard is a research prototype with a substantial, testable Python/Starlette backend and browser application. The Supabase browser/runtime dependency is being removed in favour of one first-party API. The Supabase-free change is in [PR #111](https://github.com/kaustubhdua/GenomeGuard/pull/111), branch `feat/remove-supabase-runtime`.

**The code change has passed CI and is ready for review. The hosted product is not yet production-ready.** A green CI run verifies the tested branch in an isolated CI environment; it does not provision production infrastructure, prove real-world participant permissions, or establish clinical validity.

## Current architecture target

- Browser frontend uses same-origin GenomeGuard routes.
- Python/Starlette is the only application API and policy engine.
- Local development/demo uses synthetic data and SQLite.
- Non-demo deployment requires PostgreSQL configured through server-side `GG_DATABASE_URL`.
- No Supabase URL, publishable key, browser Auth client, or Supabase Edge Function is required by the active frontend runtime.
- Historical `supabase/` migrations and reports are retained as archival records only. They must not be applied to this runtime or new deployments.

See the [Supabase-free deployment guide](supabase-free-deployment.md), [Render staging setup](render-staging.md), and the [current hosted deployment record](production-deployment.md).

## Verified on PR head

- Branch: `feat/remove-supabase-runtime`
- Commit tested: `1bf0872bb64a33449ad10cdfdbf3dd21fd157d06`
- PR: [#111 — Remove Supabase from GenomeGuard runtime](https://github.com/kaustubhdua/GenomeGuard/pull/111)
- CI: [run #42701970895 — success](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42701970895)
- Vercel preview status: blocked by `build-rate-limit` on this head; no current preview deployment is verified.
- Security verification: [run #42701970484 — success](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42701970484). Deployment configuration: [run #42701970402 — success](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42701970402). GA4GH Beacon v2 schema validation: [run #42701970418 — success](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42701970418).

CI verified:
1. Dependency setup, lint, and seed.
2. Full backend suite, including integration tests against a real PostgreSQL 16 service container.
3. Evaluation smoke, evaluation suite, and demo checks.
4. JavaScript syntax validation and Python compilation.
5. Playwright UI smoke across all registered pages, light/dark themes, mobile widths 320/375/414 px, contrast/name/label/target checks, and axe critical/serious checks.
6. Steward VCF QC upload, malformed and gzip input, oversized-file rejection, JSON/text exports, sample-identifier redaction, and no browser JavaScript errors.
7. Guided-tour workflow and non-demo UI smoke.
8. Screenshot artifact upload for review.
9. Encrypted PostgreSQL custom-format backup piped through `age`, restore into a separate empty database, runtime-schema/migration/row-count/audit-index checks, and a read-only audit-chain verification against the restored PostgreSQL database.

The CI run reported **ALL UI CHECKS PASSED**, zero axe critical/serious findings on the tested pages, no horizontal overflow at tested phone widths, and no JavaScript errors in the tested workflows. The recovery drill also passed on the same head. These are automated checks, not a substitute for manual assistive-technology testing, independent accessibility certification, provider-level backup verification, or a live production restore drill. This is automated coverage, not a substitute for manual assistive-technology testing or independent accessibility certification.

## What the application currently provides

- Research request, review, and policy/risk workflow foundations.
- Local synthetic-data demonstration.
- VCF parsing and QC with explicit distinction between QC success and import eligibility.
- Source discovery and catalogue foundations with source/policy provenance.
- Consent-policy logic that can distinguish participant records from dataset-level terms.
- Audit-chain implementation, malformed-anchor/checkpoint regression tests, and a read-only PostgreSQL audit verifier.
- PostgreSQL-backed code paths, integration tests, and a disposable encrypted backup/restore recovery drill.
- A first-party API and a same-origin browser runtime.

These capabilities must not be overstated: an implemented module or passing synthetic/integration test does not prove that a real institution has configured it, that a dataset has been lawfully imported, or that an analysis is clinically validated.

## Isolated PostgreSQL staging database verification

On 10 November 2026, a separate Neon Free project named `genomeguard-staging` was provisioned in Singapore using PostgreSQL 16. It is not the production database and is not connected to the existing Render service.

The two active repository migrations were applied to this empty staging database using the runtime schema/search-path contract implemented by `PostgresStore`:

- `genomeguard_runtime`: 13 tables, including `schema_migrations`.
- `genomeguard`: 6 normalized reference-data tables.
- Migration ledger: versions 1 and 2 recorded.
- Verification found zero rows in cohort metadata, donors, genotypes, audit log, dataset manifests, normalized samples, normalized variants, and normalized genotype calls.

No participant, cohort, or genomic data was imported. This validates the schema DDL and migration ordering, not the live application's database connection or restart-persistence behaviour. The Neon credential has not been copied into Render; a separate Render staging service and a server-side secret binding remain to be configured manually. The existing production Render service remains unchanged.

## Production release blockers

| Area | Current evidence | Required before production/controlled data |
|---|---|---|
| Hosted API deployment | Render service is still configured to deploy `main`, not the PR branch. | Review/merge the code, deploy the exact tested commit, and run live acceptance against that commit. |
| Persistence | Existing Render production deployment still uses SQLite. Separate Neon Free PostgreSQL staging project has the exact two repository migrations applied and verified empty; it is not connected to Render. Disposable PostgreSQL integration and encrypted backup/restore tests pass in CI. | Bind the Neon staging URI as a server-side secret on a separate staging service; verify application migrations, synthetic-data persistence across restart/redeploy, and recovery. Production additionally requires an appropriately governed durable database, provider backups, offsite retention, PITR, restore, and retention. |
| Identity | API keys authenticate application roles. | Integrate independently verified OIDC identity and enforce verified organization membership server-side. |
| Consent and data-use rights | Dataset-level public terms are not participant-specific consent. | Establish source-specific terms and participant-level consent where required; verify withdrawal and authorization at every release boundary. |
| Real data | No production import/reconciliation was verified. | Review exact artifact, license/terms, assembly, checksum, sample/variant/call counts, and provenance before import. |
| Audit | Hash-chained audit code and a read-only PostgreSQL verifier exist; exported checkpoints are unsigned/unkeyed integrity envelopes. CI verifies a restored audit chain. | Configure independent authenticated external anchoring/signing, key custody, monitoring, and a provider-level recovery drill. |
| Security/privacy governance | Automated checks pass on the branch. | Independent threat-model, privacy, legal, ethics, security, and operational reviews. |
| Clinical validity | No validated clinical annotation or pathogenicity model is established. | Separate clinical validation, regulatory assessment, and qualified expert oversight; never use prototype output as a clinical decision. |

Do not weaken readiness gates to make deployment appear healthy. The readiness endpoint should remain fail-closed while required controls are absent.

## Recommended release sequence

1. Complete review of PR #111 and merge only after repository review and branch protection requirements are satisfied.
2. Provision a durable PostgreSQL service and configure its connection only in the server's secret environment; never put a database URL or API secret in frontend variables.
3. Deploy the merged commit to a staging service first. Confirm the exact commit SHA, schema migration state, health/readiness behaviour, and all browser/API workflows.
4. Add and verify OIDC identity, organization membership, and least-privilege role enforcement.
5. Run a backup and restore drill, verify persistent request/audit behaviour across restart, and configure independent audit anchoring.
6. Have a steward review the exact public dataset artifact and applicable terms; import only after checksum/assembly/count reconciliation.
7. Run production acceptance against the exact deployed commit, then complete independent security, privacy, legal, and ethics review.

## Important limitations

- Do not upload private participant genomic data to the current hosted service.
- Do not infer participant consent from dataset-level open-data or public-release terms.
- Do not treat a VCF QC report as import approval or clinical validation.
- Do not claim institutional identity from an API key alone.
- Do not claim production readiness from a green CI run or a reachable frontend.
- No production database, paid service, domain, or external identity account was provisioned by this work.

## Related records

- [PR #111](https://github.com/kaustubhdua/GenomeGuard/pull/111)
- [CI run #874](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42697223073)
- [Supabase-free deployment guide](supabase-free-deployment.md)
- [Historical live-readiness audit, 3 November 2026](live-readiness-audit-2026-11-03.md)
- [README](../README.md)


## Latest hosted deployment observation

The connected Render service still deploys `main` at commit `42c1bb0f1fb1dfa34357bdc864fc276fb99509d4`, uses SQLite on the free plan, and has no verified `GG_DATABASE_URL`. The PR branch is not deployed. The latest Vercel status on the tested PR head is blocked by `build-rate-limit`. See [production deployment record](production-deployment.md).