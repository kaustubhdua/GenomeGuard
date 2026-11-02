# Real VCF import pipeline

## What this importer does

`python -m app.data.vcf_import` validates an operator-supplied VCF and, when explicitly requested, writes normalized variant and genotype-call rows into private GenomeGuard tables. It records the exact artifact SHA-256 and import metadata in a pre-existing `genomeguard.variant_dataset_manifest` entry. The importer cannot approve its own source: a trusted steward must separately register and approve the exact source metadata before import. It does not download data, infer consent, or create participant-consent records.

The normalized model is deliberately separate from the legacy `genomeguard.variants` / `genomeguard.genotypes` tables because the latter store a packed genotype blob with implicit variant ordering. Importing into those tables without an explicit encoding contract could silently mis-map calls.

## Required source review

Before import, a responsible data steward must inspect the exact collection's data-use statement and publication, verify that public research reuse is allowed for the intended purpose, and keep the source file in controlled temporary storage. Public availability alone is not sufficient. Do not use controlled-access data or private participant cohorts in the shared research project.

The VCF header must identify an assembly that exactly matches the command-line assembly. In particular, 1000 Genomes Phase 3 data commonly uses GRCh37; it must not be labelled GRCh38 without a separately validated liftover and allele reconciliation.

## Validation performed

- SHA-256 must exactly match the operator-provided expected checksum.
- Source and reuse-statement URLs must be HTTPS.
- The operator must supply the actual source retrieval timestamp as timezone-aware ISO-8601; the importer never infers retrieval time from import start time.
- The VCF must include recognizable assembly metadata, unique sample IDs without surrounding whitespace/control characters, exactly one GT field in each FORMAT declaration, supported chromosome labels, strictly decimal valid coordinates and DNA alleles.
- Only haploid and diploid genotype calls are supported. Symbolic/breakend alleles and unsupported ploidy fail closed.
- Multi-allelic records are split into one normalized row per ALT allele; genotype calls store ALT dosage, called-allele count and phase flag.
- Duplicate records and allele indices absent from a record are rejected. Input must be coordinate-sorted; duplicate detection retains only records at the current coordinate so memory use does not grow with total variant count.
- The importer streams variants and commits bounded batches. The manifest remains `loading` until database counts reconcile; a retry resumes only after verifying a contiguous committed-variant checkpoint and matching source sample set.
- The catalogue only lists manifests marked `loaded` with non-zero measured counts. An interrupted import remains unpublished and can resume from the last committed batch with the same key/checksum. A repeat import of a loaded dataset is a no-op only after the manifest counts are reconciled against the normalized tables and source sample count; a completed dataset cannot be overwritten by this CLI.

## Dry run

First calculate the file checksum independently, then run:

```bash
python -m app.data.vcf_import \
  --vcf /secure/path/cohort.vcf.gz \
  --dataset-key study-release-chr22-v1 \
  --source-name "Exact source collection name" \
  --source-url "https://official-source.example/path/to/file.vcf.gz" \
  --source-release "exact release identifier" \
  --retrieved-at "2026-10-29T08:30:00Z" \
  --assembly GRCh37 \
  --expected-sha256 "<64 lowercase hex characters>" \
  --reuse-statement-url "https://official-source.example/reuse-terms" \
  --citation "Exact collection publication citation" \
  --reviewed-public-research \
  --dry-run
```

Replace all example values with the actual source metadata. The example domain is deliberately non-operational and must not be used as source provenance.

## Quality-control reports

For structural validation and measured QC without importing data, use the database-free
`genomeguard-vcf-qc` command locally (available after installing the project) or run the
module from an environment where `backend` is on `PYTHONPATH`:

```bash
genomeguard-vcf-qc \
  --vcf /secure/path/cohort.vcf.gz \
  --assembly GRCh37 \
  --expected-sha256 "<64 lowercase hex characters>" \
  --output /secure/path/cohort-qc.json
```

The checksum option is optional; when omitted, the report marks the calculated checksum
as not independently verified. The CLI accepts plain `.vcf` and gzip-compressed
`.vcf.gz`, streams through the existing importer parser, and does not connect to a
database or import records.

The Dataset QC page has two separate report workflows:

1. **Local JSON preview.** Selecting an existing report reads it in the browser; it
   does not upload the JSON or a VCF. The preview treats the file as unsigned and
   omits its free-text details and filename. JSON and text exports redact the filename
   and include only allowlisted aggregate fields.
2. **Steward-only VCF upload.** Selecting a VCF sends its raw bytes to the configured
   GenomeGuard backend at `POST /admin/vcf-qc` for temporary processing. The upload is
   not processed solely in the browser. The service does not call a commercial or other
   third-party analysis API, but the file is transmitted to and processed by that
   configured server; use only a deployment you trust for genomic information. The
   backend stages the file in a temporary directory and removes it when request
   processing exits normally. A host/process failure may require operator cleanup of
   temporary files.

   The upload response uses a generic `[uploaded VCF]` label rather than echoing the
   source filename. The filename is used only to validate the extension and compression
   type.

The upload requires a steward credential, an explicit `GRCh37` or `GRCh38` selection,
and a `.vcf` or `.vcf.gz` filename whose compression matches the file. The optional
expected SHA-256 must come from an independent source. Server limits are 100 MiB
compressed upload, 1 GiB decompressed input, 16 MiB per VCF line, 10,000 sample
columns, and 10 million sample-by-split-ALT genotype cells. The browser request has a
30-minute timeout and can be cancelled; cancelling the browser request does not
guarantee that validation already running on the server stops immediately.

The CLI and server upload use the shared constrained VCF parser. It requires a VCF
fileformat and column header in the correct order, checks assembly labels, parses
INFO/FORMAT/FILTER definitions, and validates used field identifiers, scalar types,
fixed counts, and Number=A/R/G cardinalities where ploidy is known. It also checks
sample-column count, record coordinates/order, DNA alleles, QUAL, FORMAT value counts,
supported GT ploidy, and optional GQ values. These checks cover VCF structure and
declared field shapes, not the scientific meaning of every INFO field. The local JSON
preview validates report shape but does not parse a VCF. Neither path compares REF
alleles with a reference genome, normalizes variants, or proves that a header's
assembly claim is true. An explicitly selected assembly plus a matching header label
is not reference-sequence verification.

Reports include file size/hash, header metadata counts, raw source-record and
split-ALT counts, chromosome/type counts, genotype-cell counts, fully and partially
missing calls, missing-allele rate, ALT-frequency summaries, QUAL, and GQ when
available. A genotype cell with unknown ploidy is counted separately and excluded from
the missing-allele denominator. Frequency, QUAL, and GQ summaries are unweighted over
their measured split-ALT rows/cells; multi-ALT records therefore contribute more than
one observation. Missing quality values and insufficient metadata evidence are
reported rather than silently treated as passing. No universal clinical or scientific
acceptance thresholds are applied.

The backend report omits sample identifiers and raw genotype rows, but aggregate
genomic metadata can still be sensitive. Store reports under the same controls as the
source file. Neither report path establishes licensing, consent, source authenticity,
or steward approval; `import_eligibility` always remains `NOT_ESTABLISHED`. QC success
does not authorize an import.

## Register the reviewed manifest first

The importer refuses to create or approve a manifest. A trusted data steward must review the exact source artifact and create a manifest entry using an administrative database session. Example only—replace every placeholder with independently verified values:

```sql
insert into genomeguard.variant_dataset_manifest
  (dataset_key, source_name, source_url, source_release, reference_assembly,
   file_sha256, data_use_review, consent_basis, import_status, metadata)
values
  ('<stable-release-key>', '<exact source collection>', '<exact HTTPS file URL>',
   '<exact release>', 'GRCh37', '<verified lowercase SHA-256>',
   'approved_public_research', 'dataset_policy', 'registered',
   jsonb_build_object(
     'reuse_statement_url', '<exact HTTPS reuse terms>',
     'citation', '<publication citation>',
     'reviewed_by', '<steward identity>',
     'reviewed_at', '<timestamp>',
     'review_notes', '<documented scope and restrictions>'
   ));
```

Do not run the example as written. The review decision and exact checksum must be established independently before inserting the manifest row. The importer compares every source field and checksum with that row and fails closed on any mismatch.

## Actual import

Only after the dry run succeeds and the manifest is approved, configure `DATABASE_URL` in the trusted operator environment. The importer explicitly executes `SET ROLE genomeguard_importer`; that `NOLOGIN` role is provisioned by the importer-privileges migration and has only the required manifest-update, normalized-table, and sequence grants. The connection user must be authorized to assume that role. The database login used by `DATABASE_URL` must be explicitly granted membership in `genomeguard_importer` so `SET ROLE genomeguard_importer` can succeed; do not grant that membership to browser-facing or general application roles. Never place the connection string in frontend variables, Git, shell history, screenshots or logs.

The import writes no synthetic rows. It does not enable data release, create consent, or prove that a particular use is ethically or legally authorized. The participant-specific consent path and a governed release function must be completed and tested before private-cohort workflows are enabled.


## Decision-engine integration boundary

The normalized VCF tables are not currently an input adapter for `GenomeGuardService`. The legacy decision engine uses its own `Dataset` contract and consent-filtered participant records; the normalized public-release tables contain source sample identifiers and genotype calls under dataset-level reuse review. Treating those source identifiers as participants with verified individual consent, or copying calls into the legacy store without a documented identity/consent mapping, would be unsafe. The current API therefore does not release these calls into the decision engine. A future integration must be an explicitly reviewed aggregate-only adapter with dataset-policy authorization, minimum-cohort thresholds, no raw sample/genotype output, and independent tests for consent, withdrawal, and privacy controls. Do not mark the release gate complete merely because the importer reports `loaded`.

## Test coverage

The VCF parser tests use tiny synthetic fixtures only to exercise parser correctness; they are test data, not production genomic data and are never loaded into the live database.
