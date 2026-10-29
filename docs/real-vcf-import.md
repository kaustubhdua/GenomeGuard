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
- The VCF must include recognizable assembly metadata, unique sample IDs, GT fields, supported chromosome labels, valid coordinates and DNA alleles.
- Only haploid and diploid genotype calls are supported. Symbolic/breakend alleles and unsupported ploidy fail closed.
- Multi-allelic records are split into one normalized row per ALT allele; genotype calls store ALT dosage, called-allele count and phase flag.
- Duplicate records and allele indices absent from a record are rejected.
- The importer streams variants and commits bounded batches. The manifest remains `loading` until database counts reconcile.
- The catalogue only lists manifests marked `loaded` with non-zero measured counts. An interrupted import remains unpublished and can be restarted from scratch with the same key/checksum; a completed dataset cannot be overwritten by this CLI.

## Dry run

First calculate the file checksum independently, then run:

```bash
python -m app.data.vcf_import \
  --vcf /secure/path/cohort.vcf.gz \
  --dataset-key study-release-chr22-v1 \
  --source-name "Exact source collection name" \
  --source-url "https://official-source.example/path/to/file.vcf.gz" \
  --source-release "exact release identifier" \
  --assembly GRCh37 \
  --expected-sha256 "<64 lowercase hex characters>" \
  --reuse-statement-url "https://official-source.example/reuse-terms" \
  --citation "Exact collection publication citation" \
  --dry-run
```

Replace all example values with the actual source metadata. The example domain is deliberately non-operational and must not be used as source provenance.

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

## Test coverage

The VCF parser tests use tiny synthetic fixtures only to exercise parser correctness; they are test data, not production genomic data and are never loaded into the live database.
