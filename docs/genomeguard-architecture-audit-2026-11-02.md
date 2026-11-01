# GenomeGuard architecture and implementation audit — 2 November 2026

## Scope and baseline

This is the Phase 1 audit requested for the GenomeGuard genomic-intelligence roadmap. The review inspected the default-branch README, package configuration, Starlette API, service/decision-engine structure, PostgreSQL adapter, VCF importer, gnomAD aggregate importer, Supabase migrations, relevant frontend pages, tests, and the repository's 29 October readiness/provenance audits.

- Repository: https://github.com/kaustubhdua/GenomeGuard
- Audited baseline: `main` at `5c121e4a872bf84de95c4115b5b05cdc23b6955b` (1 November 2026)
- Existing project license: all rights reserved. External contributions and derivative work remain subject to the repository license.
- This document records repository evidence; it does not claim that live data imports, production migrations, training, or deployments have been performed.

## Architecture found

| Layer | Existing implementation | Assessment |
| --- | --- | --- |
| Frontend | Vanilla JavaScript, lazy-loaded pages, API client; dataset catalogue and locus/variant inspector | Existing UI is functional, but the variant inspector explicitly says clinical annotation is not linked and frequency evidence is not available from its metadata lookup. |
| HTTP/API | Python 3.11+, Starlette routes in `backend/app/api.py` | Existing governance/request endpoints, metadata-only `/variants/search`, Beacon-style lookup and dataset/QC endpoints. No evidence found of clinical-annotation or aggregate-population-frequency query endpoints. |
| Decision engine | `GenomeGuardService`, deterministic policy, consent-inspired checks, risk scoring, transformations, anomaly monitoring and audit chain | A mature governance engine, not a supervised variant-pathogenicity model. Advisory agents do not make release decisions. |
| Persistence | SQLite Store contract plus opt-in PostgreSQL adapter; separate Supabase `genomeguard` and `genomeguard_runtime` schema contracts | Persistence foundations exist, but the repository's readiness audits say the hosted research API still uses Render/SQLite and the normalized Supabase dataset is not connected to the Python decision engine. |
| Individual-level ingestion | Provenance-gated VCF importer with assembly checks, strict parsing, bounded/idempotent batches and manifest controls | Useful existing importer. It is a bounded VCF subset, not a general-purpose VCF parser. It must remain distinct from aggregate reference ingestion. |
| Aggregate reference ingestion | gnomAD aggregate frequency schema, normalized TSV importer and Excel export | gnomAD v4/GRCh38 aggregate AC/AN/AF rows are supported. The importer rejects sample/individual columns and does not create genotype records. It expects a pre-normalized TSV and a steward-approved manifest. |
| Dataset catalogue | Supabase Edge Function-backed public catalogue and explicit empty/error states | Good provenance-oriented behavior; catalogue visibility is not proof of a local import or a working query path. |
| ML and validation | Existing synthetic and real-cohort research evaluations for the governance engine | No supervised ClinVar/ClinGen pathogenicity training pipeline, independent variant-level holdout, model registry, calibration report, or ancestry-stratified model validation was identified in the inspected code/configuration. The current evaluation artifacts must not be described as clinical ML validation. |
| Quality/security | Pytest, Ruff, CI workflows, PostgreSQL checks, security workflows and browser/accessibility smoke tests | Strong foundations. This audit did not execute the workflows; status must be verified against the commit that runs them. |

## Confirmed strengths to preserve

1. The deterministic governance pipeline remains authoritative; language-model agents are advisory and sanitized.
2. Public research data, synthetic demo data, aggregate population frequencies and individual-level genotype calls have explicit provenance/scope boundaries.
3. The VCF importer requires explicit source/assembly/checksum metadata and does not invent consent records.
4. The gnomAD importer uses a separate aggregate table and rejects individual-level fields.
5. The dataset catalogue does not manufacture populated records when the verified catalogue is empty.
6. Readiness checks fail closed rather than equating a reachable website with production readiness.

## Material gaps against the requested objective

### Data and ingestion
- gnomAD import currently begins with a normalized TSV; automated acquisition and source-release-specific normalization are not implemented by the inspected importer.
- The importer is an operator-run process and does not approve its own manifest. No actual import success is established by the code or documentation.
- ALFA, 1000 Genomes High Coverage, ClinVar, ClinGen, VEP, dbSNP, CIViC, COSMIC, PharmGKB, BRCA Exchange, WebSTR, TOPMed, All of Us, UK Biobank and GenomeIndia ingestion were not identified as integrated working pipelines in this audit. Some resources may have catalog or planning references; that is not equivalent to ingestion.
- Controlled-access datasets must remain out of the public research instance unless approvals, permitted-use terms and the secure deployment boundary are established.

### Database and application integration
- Aggregate population-frequency storage and importer exist, but the inspected application API and variant page do not expose that table as a usable, provenance-bound lookup.
- The variant inspector returns locus metadata only and currently renders annotation as “Not linked to an annotation source.”
- The normalized Supabase genotype/reference tables and the Python decision engine are separate data paths. The 29 October repository audit reports zero normalized cohort rows and an incomplete API cutover; current live state must be rechecked before any status is changed.
- Do not combine aggregate population counts with individual-level sample/genotype tables.

### Machine learning and validation
- The package dependencies inspected include Starlette, NumPy, cryptography and psycopg; no scikit-learn, XGBoost, LightGBM or equivalent supervised modeling dependency was present.
- No variant-label training dataset pipeline or independent test-set governance was found.
- The current policy-engine evaluations are not variant pathogenicity model results.
- Any future model must use variant/gene/study-aware leakage controls, protected independent evaluation data, calibrated uncertainty, confidence intervals and ancestry-stratified reporting. A model must not be called clinically validated.

### Operations and safety
- Existing readiness documentation says the hosted service remains a research prototype, not suitable for private/controlled-access participant data or clinical decisions.
- Production PostgreSQL durability, verified backup/restore, external audit anchoring, authoritative institutional identity, and complete API parity remain release gates in the existing readiness audit.
- No credentials are requested or embedded here. Secure environment configuration and source-use approvals must be completed by an authorized operator.

## First implementation task

**Implement a read-only, provenance-bound aggregate population-frequency lookup path in the existing API and variant inspector.**

Why this is first:
- The repository already has a separate aggregate-frequency schema and validated gnomAD TSV importer.
- The existing locus inspector has an explicit integration gap.
- This is a bounded application integration task that can be tested without pretending any dataset has been imported.
- It creates a real serving contract that later approved aggregate references (gnomAD, ALFA, etc.) can implement consistently.

Acceptance criteria:
1. Query only rows whose manifest is explicitly `approved_public_research` and `loaded`; never return staged, failed, pending or retired data.
2. Require exact chromosome, position, REF and ALT matching, plus a validated assembly match (gnomAD v4 is GRCh38).
3. Return source name, release, source URL, checksum, assembly, population label, AC, AN, AF and homozygote count where present; identify the source and release in every result.
4. Keep aggregate-frequency evidence separate from participant-level genotype calls and the governance release pipeline.
5. If the database is not configured, the migration is absent, or no approved loaded dataset matches, return a truthful unavailable/empty response; never synthesize a frequency or claim that a dataset is loaded.
6. Add API and frontend tests for approved vs. unapproved manifests, assembly mismatch, exact allele matching, empty catalogue, missing database configuration and error handling.
7. Preserve the existing readiness gate and do not change production deployment flags.

After this task, proceed to source-specific dataset normalizers and ingestion reports, then clinical annotation connectors, then the separately governed ML training/independent-validation pipeline.

## Verification status

- Repository files and code paths: inspected as listed above.
- Local test suite: not run in this audit session.
- CI: not run by this audit session; CI results must be attached to the exact implementation commit.
- Dataset imports: not run or claimed.
- Model training/validation: not run or claimed.
- Live Supabase/Render/Vercel state: not changed or claimed.
- Production readiness: remains blocked unless and until every existing release gate is independently evidenced.

## Source files reviewed

- `README.md`, `pyproject.toml`, `backend/app/api.py`, `backend/app/service.py`
- `backend/app/config.py`, `backend/app/postgres_store.py`, `backend/app/data/vcf_import.py`
- `backend/app/data/gnomad_reference.py`, `backend/tests/test_gnomad_reference.py`, `backend/tests/test_api.py`
- `frontend/src/pages/variants.js`
- `supabase/migrations/20261027000000_genomeguard_schema.sql`
- `supabase/migrations/20261103000000_genomeguard_population_reference.sql`
- `docs/architecture.md`, `docs/real-vcf-import.md`, `docs/gnomad-population-reference.md`
- `docs/genomic-dataset-provenance-import-gate.md`, `docs/live-readiness-audit-2026-10-29.md`, `docs/production-readiness-audit-2026-10-29.md`
