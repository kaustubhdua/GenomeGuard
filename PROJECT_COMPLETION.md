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
| Local VCF QC report | IMPLEMENTED AND LOCALLY VERIFIED | A database-free CLI streams supported VCF/VCF.GZ files and reports parser/checksum checks, metadata counts, genotype missingness, allele-frequency, QUAL, and optional GQ metrics without sample identifiers. The report cannot establish source terms or import eligibility. |
| Steward VCF QC upload/report UI | IMPLEMENTED AND LOCALLY VERIFIED | The steward-only endpoint streams a capped raw VCF to the configured backend for temporary QC processing; it does not persist or import the source file. The browser also previews unsigned JSON locally and exports allowlisted aggregate fields. This is not a browser-only VCF workflow; only use a trusted backend deployment. |
| Public-source discovery catalogue and expanded per-dataset exploration/comparison | NOT IMPLEMENTED | Existing catalogue endpoints describe local cohort data; they are not the requested discovery catalogue for external genomic resources, nor a persistent imported-dataset explorer/comparison system. |
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
- Added steward-only `POST /admin/vcf-qc` with bounded temporary server processing,
  explicit assembly selection, optional expected checksum, cancellation support, and
  aggregate QC reports. Added file-free allowlisted JSON/text exports; QC success remains
  separate from source review and import eligibility.
- Updated the API and aggregate-reference documentation.

## Relevant files and commits

- VCF QC: `backend/app/api.py`, `backend/app/data/vcf_import.py`,
  `backend/app/data/vcf_qc.py`, `backend/tests/test_api.py`,
  `backend/tests/test_vcf_import.py`, and `backend/tests/test_vcf_qc.py`.
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

- Full `python -m pytest -q` before the final generic filename-redaction tweak: **344
  passed, 6 skipped** (Python 3.14.6). Focused VCF QC, importer, and API selectors after
  that API change: **30 passed, 27 deselected**.
- `python -m compileall -q backend scripts`, `node --check` for all 19 frontend
  JavaScript files, and `git diff --check` passed.
- Browser verification on a local synthetic-only instance: valid upload reported 3
  split ALT rows and 6 genotype cells; the uploaded filename and sample IDs were absent
  and eligibility remained `NOT_ESTABLISHED`. Invalid VCF returned a visible failed
  report. Empty and >100 MiB files were rejected before any upload request. An
  untrusted JSON report's canary text was absent from preview and JSON/text export;
  exports redacted the name and forced `NOT_ESTABLISHED`. Cancellation showed a
  cancelled-request message, the page route survived refresh while demo credentials
  correctly reset, and a 390 px viewport had no horizontal overflow. Export button
  activation and generated Blob payloads were verified; the browser harness did not
  provide a reliable OS-level download-event assertion.
- No uncaught browser JavaScript errors occurred during successful QC upload. The
  synthetic demo's `/health/ready` correctly returned 503 because production readiness
  is not configured; cancellation produces the expected aborted-request event.
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
5. Implement the requested external public-source discovery registry and persistent
   dataset-level exploration/comparison and QC history. Current catalogue routes expose
   local cohort information only.
6. Run the complete browser, accessibility, security, and end-to-end suites against the
   exact production deployment, then complete independent legal, ethics, privacy, and
   security reviews before considering controlled-access or clinical use.
