# GenomeGuard project completion status

Updated: 2 November 2026

## Overall status

**NOT IMPLEMENTED as a complete production genomic-governance product.** The repository
contains a functioning research prototype and substantial workflow foundations. It is
not verified for private or controlled-access participant data, clinical use, or
production governance. Do not infer completion from local tests or a reachable hosted
frontend. The [live readiness audit](docs/live-readiness-audit-2026-11-02.md) records
the latest read-only checks; no live infrastructure was changed.

## Current evidence

| Area | Status | Evidence and remaining boundary |
|---|---|---|
| Approved aggregate-frequency lookup | COMPLETE AND VERIFIED | API and PostgreSQL query adapter enforce exact allele and assembly matching, `approved_public_research` review, and `loaded` status. Local API/storage tests pass; the browser renders provenance and truthful empty/unavailable states. No live reference import or database connection was verified. |
| Local VCF QC report | IMPLEMENTED AND LOCALLY VERIFIED | A database-free CLI streams supported VCF/VCF.GZ files and reports parser/checksum checks, metadata counts, genotype missingness, allele-frequency, QUAL, and optional GQ metrics without sample identifiers. The parser validates declared INFO/FORMAT/FILTER fields and supported cardinalities. The report cannot establish source terms or import eligibility, and it does not compare REF alleles to a reference genome. |
| Steward VCF QC upload/report UI | IMPLEMENTED AND BROWSER-VERIFIED WITH SYNTHETIC DATA | The steward-only endpoint streams a capped raw VCF to the configured backend for temporary QC processing; it does not persist or import the source file. Browser tests exercised a valid checksum-verified upload, a rejected undeclared INFO field, sample-ID omission, and JSON/text export payloads. This is not a browser-only VCF workflow; only use a trusted backend deployment. The browser harness did not confirm the operating-system download event. |
| Public-source discovery catalogue | IMPLEMENTED, NOT APPROVAL- OR IMPORT-VERIFIED | `/catalogue/sources` and the Source discovery page list IGSR/1000 Genomes, gnomAD aggregate data, and ClinVar summary metadata with official source/policy links. Exact-artifact review and import remain pending; no source is claimed as licensed for a particular project use, approved, downloaded, or loaded by this index. |
| Expanded per-dataset exploration/comparison | NOT IMPLEMENTED | The imported-dataset catalogue remains a verified-source listing and is not a persistent dataset explorer/comparison system. |
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
- Added a database-free VCF QC CLI and local JSON report preview. It reuses the supported
  VCF parser, reports checks and aggregate metrics without sample identifiers, and keeps
  import eligibility explicitly unestablished.
- Strengthened the shared VCF parser to reject records before `#CHROM`, metadata after
  the column header, undeclared INFO/FORMAT/FILTER identifiers, invalid declared scalar
  types, and supported fixed/A/R/G cardinality mismatches.
- Added steward-only `POST /admin/vcf-qc` with bounded temporary server processing,
  explicit assembly selection, optional expected checksum, cancellation support, and
  aggregate QC reports. Added file-free allowlisted JSON/text exports; QC success remains
  separate from source review and import eligibility.
- Added a read-only public source-discovery endpoint and lazy-loaded UI page for three
  official public references. The page records source-specific caveats and leaves
  exact-artifact reuse review and import status pending.
- Restricted the verified imported-dataset catalogue to source-backed real VCF cohorts;
  synthetic demo fixtures are no longer reported as imported research datasets.
- Updated the API and aggregate-reference documentation.
- Made the embedded-cohort Docker build cache key explicit and passed the commit SHA
  from the CI image build. Expanded deployed UI smoke coverage for chromosome, dataset,
  and source-discovery routes with page-specific heading and mobile overflow assertions.
- Added a secret-free Render deployment revision field to liveness/health responses and
  made live acceptance wait for the exact GitHub-tested commit when run in CI.

## Relevant files and commits

- VCF QC: `backend/app/api.py`, `backend/app/data/vcf_import.py`,
  `backend/app/data/vcf_qc.py`, `backend/tests/test_api.py`,
  `backend/tests/test_vcf_import.py`, and `backend/tests/test_vcf_qc.py`.
- Public-source discovery: `backend/app/data/public_sources.py`,
  `frontend/src/pages/sources.js`, and `docs/public-genomic-source-discovery.md`.
- UI/API: `frontend/src/api.js`, `frontend/src/pages/dataset-qc.js`, and
  `frontend/src/gg.css`.
- Documentation: `docs/real-vcf-import.md`, `docs/api.md`, `docs/architecture.md`,
  `README.md`, and `CHANGELOG.md`.
- Earlier aggregate-frequency implementation: commit `2f7a30c`
  (`Connect aggregate reference frequency lookup`).
- `supabase/migrations/20261103010000_genomeguard_population_reference_lookup_index.sql`
- Earlier related validation also changed `scripts/ui_smoke.py` and
  `docs/gnomad-population-reference.md`.

## Validation record

- Full `python -m pytest -q` after source discovery and catalogue-boundary changes:
  **343 passed, 6 skipped** (Python 3.14.6).
- `python -m compileall -q backend`, `node --check` for all 20 frontend JavaScript
  files, and `git diff --check` passed.
- Browser verification on a local synthetic-only instance: all three public source
  cards rendered, external links used `noopener`, and the imported-dataset link showed
  the honest empty verified state rather than counting synthetic demo records. At
  320, 375, and 390 px there was no horizontal overflow or browser page error.
- Browser verification on a local synthetic-only instance: a valid GRCh38 upload with
  an independently calculated SHA-256 returned HTTP 200 and seven passing checks; a
  synthetic undeclared INFO field returned a visible failed report. Both reports
  omitted the sample identifier, showed a generic upload name, and retained
  `NOT_ESTABLISHED` import eligibility. JSON and text export Blob payloads were
  retrieved and checked for redaction; the browser harness did not confirm the
  operating-system download event.
- At 390 px, the chromosome explorer filter and loaded-only empty state worked, the
  variant inspector returned one exact `v1` match, and its unconfigured aggregate
  frequency lookup reported unavailability instead of fabricating a value. No
  horizontal overflow or uncaught application JavaScript errors were observed.
- Earlier browser checks also covered empty and oversized client-side rejection,
  unsigned-report preview redaction, cancellation messaging, route persistence, and
  phone-width layout. No uncaught application JavaScript error occurred during the
  successful or rejected QC uploads.
- No uncaught browser JavaScript errors occurred during successful QC upload. The
  synthetic demo's `/health/ready` correctly returned 503 because production readiness
  is not configured; cancellation produces the expected aborted-request event.
- Live PostgreSQL/Supabase integration, migration application, public artifact import,
  production deployment, and the complete Playwright smoke suite were **not run**.
  The local Python environment does not have Ruff or the Playwright package installed.
- A read-only check of `https://genomeguard.onrender.com` on 2 November 2026 found
  deployment drift: the health response still reports 600 matched consent records for
  a dataset-level policy (the current source reports zero participant records), and
  both current source/dataset catalogue API routes return 404. `/health/ready` remains
  HTTP 503; the hosted overview heading also differs from the current repository UI.
  The response did not expose a revision, so the exact deployed commit could not be
  independently identified. The new health revision field will be visible after a
  Render deployment. See the [live readiness audit](docs/live-readiness-audit-2026-11-02.md).
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
5. Implement the requested external public-source discovery registry and persistent
   dataset-level exploration/comparison and QC history. Current catalogue routes expose
   local cohort information only.
6. Run the complete browser, accessibility, security, and end-to-end suites against the
   exact production deployment, then complete independent legal, ethics, privacy, and
   security reviews before considering controlled-access or clinical use.
