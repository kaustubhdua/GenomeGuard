> **Live status refresh — 14 November 2026 (supersedes the 10 November snapshot below).**
>
> Current `main`: `50658f1ae0ec1df9f4b8c1e512d720bd4e7f5f94`. PR #150 (OLS4-backed ontology discovery) and PR #151 (filterable dataset catalogue) are merged.
>
> Open implementation/review PRs:
> - [#152](https://github.com/kaustubhdua/GenomeGuard/pull/152): CSV formula-injection whitespace correction.
> - [#153](https://github.com/kaustubhdua/GenomeGuard/pull/153): this live-status, README, threat-model and deployment-documentation reconciliation.
> - [#154](https://github.com/kaustubhdua/GenomeGuard/pull/154): require gnomAD TSV checksum to match the reviewed manifest before database writes.
> - [#155](https://github.com/kaustubhdua/GenomeGuard/pull/155): signed-consent policy-basis, timestamp and event-ordering corrections.
> - [#156](https://github.com/kaustubhdua/GenomeGuard/pull/156): official DUO mappings for POA/NPOA and NCU/NPU/NPUNCU semantics, explicit consent-basis enforcement, and fail-closed verification of commercial-use/organisation attributes across policy, import, FHIR and UI.
>
> Exact-head backend CI, CodeQL, secret scanning, dependency audit and deployment-configuration checks for current `main` and PRs #152–#156 are queued. A queued check is not a passing check; do not merge or deploy until required checks complete successfully. The GitHub branch inventory reports `main` as unprotected, and a maintainer must configure a required-check ruleset.
>
> Render currently reports the primary public synthetic demo live at `3280ebc1924039bcfa19f4c58bb75e83a8c370eb` and a separate recovery demo live at `f200b643f05a5f959887ac51accd7e202c424557`; both are behind current `main`. The connected workspace has no Render-managed PostgreSQL instance, and no accepted institutional research-mode deployment. Do not treat a Render `live` status as production acceptance.
>
> The public demo remains **synthetic-only**. Do not upload private or controlled-access participant data. The separate public-cohort research image and CI fixtures are not participant-specific consent or institutional authorization.
>
> Institutional OIDC/SSO and MFA, a verified organisation/legal-entity registry, DAC-verified commercial-purpose classification, durable production PostgreSQL, independently verified backups/restores, external audit anchoring, production observability/incident response, participant-specific consent authority, and independent scientific/privacy/security/legal/institutional sign-off remain release blockers. No paid infrastructure or production configuration was changed during this audit.
>
> The authoritative, actively maintained acceptance ledger is [GitHub issue #124](https://github.com/kaustubhdua/GenomeGuard/issues/124). Deployment-specific operational evidence is in [docs/production-deployment.md](docs/production-deployment.md); older dated sections in this file are historical and must not be treated as current live status.

---

Updated: 2 November 2026

## Overall status

**NOT IMPLEMENTED as a complete production genomic-governance product.** The repository
contains a functioning research prototype and substantial workflow foundations. It is
not verified for private or controlled-access participant data, clinical use, or
production governance. Do not infer completion from local tests or a reachable hosted
frontend. The [latest live-readiness audit](docs/live-readiness-audit-2026-11-03.md)
records the current hosted evidence. An additive steward-queue migration and Edge Function
deployment were applied; no production genomic or participant data was inserted.

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
| Supabase API/persistence cutover | PARTIAL / BLOCKED BY EXTERNAL DEPENDENCY | The isolated GenomeGuard schema is live and additive migrations are applied. The Python backend still uses SQLite; a server-side PostgreSQL runtime connection, durable end-to-end persistence, backup/restore, and production cutover are not verified. |
| Production identity, deployment, and acceptance | BLOCKED BY EXTERNAL DEPENDENCY | Requires an authoritative identity provider, organization provisioning, configured production services, and acceptance against the exact deployed commit. |
| Clinical annotation and validated pathogenicity ML | NOT IMPLEMENTED | Existing locus lookup is not a clinical annotation service or a validated pathogenicity model. |

## Completed in this implementation

- Added public, read-only `/population-frequencies` serving only exact-coordinate
  aggregate records from approved and loaded manifests, with source, release, URL,
  checksum, assembly, population, AC, AN, AF, and homozygote-count evidence.
- Added and applied the exact-locus aggregate population-frequency lookup index as live migration `20261102213956`; readiness gates were not changed. The new population-reference tables remain empty.
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
- `supabase/migrations/20261102213956_genomeguard_population_reference_lookup_index.sql`
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

## 3 November 2026 execution update

### Supabase steward queue implementation

- Added `supabase/migrations/20261102212149_genomeguard_steward_review_queue.sql` and applied the migration to Supabase project `common 1` as `genomeguard_steward_review_queue`.
- Added `GET /steward/requests?limit=50&offset=0` to `supabase/functions/genomeguard-api/index.ts`; deployed Edge Function version 11.
- Added the service-role-only `public.gg_list_review_queue(uuid,integer,integer)` RPC. It resolves reviewer membership from server-side records, rejects missing or ambiguous memberships, bounds pagination, filters to the reviewer's organization, and exposes only request metadata.
- Added a clean-PostgreSQL migration regression test for queue pagination, organization isolation, researcher denial, ambiguous multi-organization denial, and function grants. GitHub Actions is running the new checks on the current mainline; do not mark the suite complete until that run finishes.
- Live SQL inspection confirmed `SECURITY DEFINER`, an empty search path, execute permission for `service_role` only, and denial for `anon` and `authenticated`. A request using an unprovisioned identity failed closed with SQLSTATE `42501`.
- A successful queue response and review lifecycle are **not verified**: the live GenomeGuard organization, membership, request, decision, and review-history tables are empty. No test identity has been provisioned.
- Added authenticated `GET /me` backed by `gg_get_my_access_status(uuid)`; it exposes only the signed-in user's memberships and fails closed for ambiguous, pending, inactive, or absent memberships. The RPC's live grants were verified.
- Added a Supabase Auth email/password sign-in, sign-up, and sign-out panel to the frontend. Tokens are held in tab memory and are not persisted to browser storage. The UI clearly reports that account creation does not grant organization access.
- Routed authenticated request submission, request detail, steward queue, and review actions through the Supabase Edge Function. The request/review interface explicitly states that this API path stores governance requests and human review only; it does not run the genomic risk engine or release data.
- Routed public source discovery, verified dataset catalogue, and chromosome-reference pages through the Supabase Edge Function. Live SQL confirms 25 GRCh38 chromosome-reference records and zero verified public datasets; the empty dataset state is truthful.
- Deployed `genomeguard-api` Edge Function version 11. The current frontend changes are in GitHub mainline; Vercel must finish deploying the matching frontend commit before browser acceptance can be claimed.
- Applied the missing importer-privilege, append-only importer, population-reference schema, and exact-locus lookup-index migrations as live versions `20261102213657` through `20261102213956`. The importer roles are NOLOGIN, have scoped INSERT/SELECT grants, and do not have DELETE; the two population-reference tables are empty.
- Reconciled repository migration filename prefixes to the live Supabase versions and added a migration-history report. The missing identity-foundation file was reconstructed from the duplicated DDL and verified live schema; it is explicitly marked for human review. No migration-history repair or `supabase db push` was run. The future reader migration `20261104000000` remains unapplied.

- Supabase Auth account creation, email confirmation delivery, successful sign-in in a real browser, positive request submission, and positive steward review are **not verified**. The live project has two Auth users but zero GenomeGuard organizations and memberships; no account was selected or promoted without the owner's instruction.

### Current hosted deployment evidence

- The latest Vercel production deployment observed is `dpl_6D31fP2Fjb4xBf5TgZUArhY5q6i7`, serving commit `cdf906c83f8fff97dd5aecd96d26770436628482`. It is behind the current GitHub mainline.
- The public frontend returned HTTP 200. The proxied `/health` returned HTTP 200 but still reports `storage_backend=sqlite` and `consent_records_matched=600` even though the source policy is dataset-level and not participant-specific. Treat the count as a deployment/data-provenance discrepancy, not participant consent.
- `/catalogue/datasets` and `/catalogue/sources` returned HTTP 404. `/health/ready` returned HTTP 503, which is the correct fail-closed state while production gates remain incomplete.
- Supabase project `common 1` is healthy. The GenomeGuard schema has 25 tables, but normalized dataset manifests/samples/variants/genotype calls, organizations, memberships, participant consent, requests, decisions and API events are all empty. The Python Render backend is not yet connected to this PostgreSQL database.
- The Supabase security advisor reports informational RLS-enabled/no-policy findings for private GenomeGuard tables and unrelated shared-project tables; direct schema usage and table grants for browser roles remain denied. The Auth advisor also reports leaked-password protection disabled. These findings require deliberate review; do not add broad policies or change shared-project tables to silence the advisor.
- See [the 3 November live-readiness audit](docs/live-readiness-audit-2026-11-03.md) for the exact checks and boundaries.

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
