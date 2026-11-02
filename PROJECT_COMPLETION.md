# GenomeGuard project completion status

Updated: 2 November 2026

## Overall status

**NOT IMPLEMENTED as a complete production genomic-governance product.** The repository
contains a functioning research prototype and substantial workflow foundations. It is
not verified for private or controlled-access participant data, clinical use, or
production governance. Do not infer completion from local tests or a reachable hosted
frontend. The [live readiness audit](docs/live-readiness-audit-2026-10-29.md) describes
the known deployment boundary; live infrastructure was not checked or changed for this
implementation.

## Current evidence

| Area | Status | Evidence and remaining boundary |
|---|---|---|
| Approved aggregate-frequency lookup | COMPLETE AND VERIFIED | API and PostgreSQL query adapter enforce exact allele and assembly matching, `approved_public_research` review, and `loaded` status. Local API/storage tests pass; the browser renders provenance and truthful empty/unavailable states. No live reference import or database connection was verified. |
| Request evaluation and human review | IMPLEMENTED, NOT VERIFIED | Local backend tests exercise request and review behavior. Institutional identity, organization isolation, and production persistence remain unverified. |
| VCF ingestion and provenance checks | IMPLEMENTED, NOT VERIFIED | Importer and automated tests exist. No approved public artifact was imported or reconciled in a live database in this work. |
| Participant-specific consent enforcement | NOT IMPLEMENTED | Current documented operation relies on simulated consent or dataset-level policy mapping; it is not evidence of participant-specific consent for hosted public data. |
| Risk analysis | IMPLEMENTED, NOT VERIFIED | Research heuristics exist; independent scientific/privacy validation is not established. Do not use as clinical or validated privacy-risk advice. |
| Audit records | IMPLEMENTED, NOT VERIFIED | A hash-chained local audit implementation is tested. Independent external anchoring, key custody, and production recovery were not verified. |
| Supabase API/persistence cutover | BLOCKED BY EXTERNAL DEPENDENCY | A live database, authorized runtime credentials, applied migrations, and end-to-end persistence evidence are required. No live database was accessed or changed. |
| Production identity, deployment, and acceptance | BLOCKED BY EXTERNAL DEPENDENCY | Requires an authoritative identity provider, organization provisioning, configured production services, and acceptance against the exact deployed commit. |
| Clinical annotation and validated pathogenicity ML | NOT IMPLEMENTED | Existing locus lookup is not a clinical annotation service or a validated pathogenicity model. |

## Completed in this implementation

- Added public, read-only `/population-frequencies` serving only exact-coordinate
  aggregate records from approved and loaded manifests, with source, release, URL,
  checksum, assembly, population, AC, AN, AF, and homozygote-count evidence.
- Added an exact-lookup database index migration without changing readiness gates or
  applying any migration to a live database.
- Integrated the variant inspector with the lookup. It distinguishes database
  unavailability, missing reference evidence, and returned aggregate results; it never
  substitutes active-cohort frequencies.
- Fixed a JavaScript parse error in the dataset QC route and included that route in the
  UI smoke route inventory.
- Updated the API and aggregate-reference documentation.

## Relevant files and commits

- `backend/app/api.py`, `backend/app/postgres_store.py`, and `backend/app/store.py`
- `backend/tests/test_api.py` and `backend/tests/test_postgres_store.py`
- `frontend/src/pages/variants.js` and `frontend/src/pages/dataset-qc.js`
- `supabase/migrations/20261103010000_genomeguard_population_reference_lookup_index.sql`
- `scripts/ui_smoke.py`, `docs/api.md`, and `docs/gnomad-population-reference.md`
- Implementation commit: `2f7a30c` (`Connect aggregate reference frequency lookup`).

## Validation record

- Full `python -m pytest -q`: **333 passed, 6 skipped** (Python 3.14.6); after the
  final endpoint validation refinements, the focused API/storage checks passed (**8
  passed**).
- `python -m compileall -q backend scripts`: passed.
- `node --check` over all `frontend/**/*.js`: passed.
- Browser check against a temporary local server: aggregate provenance/count rendering
  was exercised with a mocked approved-reference API response; the actual local
  synthetic dataset correctly showed “assembly not recorded” and did not query or
  display a frequency. Dataset QC rendered its synthetic-only provenance.
- Live PostgreSQL/Supabase integration, migration application, public artifact import,
  production deployment, and the complete Playwright smoke suite were **not run**.
  The local Python environment does not have Ruff or the Playwright package installed.
- Pytest emitted existing warnings for development-key use in local fixtures and an
  `httpx`/Starlette test-client deprecation; they did not fail the suite.

## Remaining release blockers

1. Establish and verify the production database/API cutover, including runtime
   permissions, migration state, organization isolation, and durable persistence.
2. Provision authoritative identities and organization memberships; enforce the real
   consent and access lifecycle at every data-release boundary.
3. Use only a steward-reviewed, permitted public artifact; complete a real import and
   reconcile its checksum, assembly, source terms, and measured counts.
4. Verify backup/restore and independent audit anchoring.
5. Run the complete browser, accessibility, security, and end-to-end suites against the
   exact production deployment, then complete independent legal, ethics, privacy, and
   security reviews before considering controlled-access or clinical use.
