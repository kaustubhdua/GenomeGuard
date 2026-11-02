# gnomAD aggregate population reference: import and Excel export

## Important distinction

This pipeline stores **aggregate allele frequencies**, not individual genomes or genotype calls. gnomAD v4 represents 807,162 upstream individuals (730,947 exomes and 76,215 genomes) on GRCh38. That number is provenance metadata; it is not the number of people or records stored locally.

The existing `backend.app.data.vcf_import` importer is for sample-level VCFs with GT fields and must not be used for gnomAD aggregate sites files.

## Input format

Download the appropriate public gnomAD v4 GRCh38 sites artifact and prepare a normalized UTF-8 TSV with one row per variant and population. Required columns:

`chromosome, position, reference_allele, alternate_allele, population, allele_count, allele_number, allele_frequency`

Optional: `homozygote_count`. No additional columns are accepted; sample identifiers, individual genotype fields, and participant IDs are rejected. Preserve source release, artifact URL, checksum, and documented population labels. The normalizer must map the release's INFO/frequency annotations to AC, AN, AF and homozygote count without deriving sample-level calls.

## Preflight validation and import reports

Validate the normalized file before connecting to the database:

The validate command needs no database connection:

    python -m app.data.gnomad_reference validate \
      --input /secure/gnomad-frequency.tsv \
      --dataset-key gnomad-v4-grch38 \
      --expected-sha256 <64-character-sha256> \
      --report /secure/reports/gnomad-v4-validation.json

The preflight streams and validates the complete TSV, then reports its checksum, byte size, row counts by chromosome and population, and AF range. It contains aggregate metadata only; it does not list variant rows, connect to a database, approve a manifest, or import data.

The import command can also write a JSON report with the same source checksum and dimensions, inserted row count, rows skipped by the unique-key conflict rule, and total database rows after import:

    python -m app.data.gnomad_reference import \
      --input /secure/gnomad-frequency.tsv \
      --dataset-key gnomad-v4-grch38 \
      --expected-sha256 <64-character-sha256> \
      --report /secure/reports/gnomad-v4-import.json

Treat this report as reconciliation evidence for a steward. The importer still does not update the manifest or mark the dataset loaded; a steward must compare the database row count and report with the source manifest before changing status. Keep report files in the approved data-handling location.

## Import

1. Apply migration `20261103000000_genomeguard_population_reference.sql` through the normal reviewed deployment process.
2. A trusted data steward must register the source manifest, verify the exact artifact checksum and terms, and set `data_use_review='approved_public_research'` and `import_status='validated'`. This is intentionally not done by the importer.
3. Configure `DATABASE_URL` only in the trusted runtime. The database login must be authorized to `SET ROLE genomeguard_reference_importer`.
4. Install the project and optional Excel dependency:

```bash
pip install -e '.[reference]'
DATABASE_URL='...' python -m app.data.gnomad_reference import \
  --input /secure/gnomad-frequency.tsv \
  --dataset-key gnomad-v4-grch38 \
  --expected-sha256 <64-character-sha256>
```

The import streams in batches and is idempotent. It inserts only into `genomeguard.population_variant_frequency`; it does not approve or mark a manifest loaded. A steward must reconcile the database row count and update the manifest using an administrative session after a successful import.

## Excel export

Only a manifest already approved and marked `loaded` can be exported:

```bash
DATABASE_URL='...' python -m app.data.gnomad_reference export-xlsx \
  --dataset-key gnomad-v4-grch38 \
  --output ./gnomad-v4-population-frequencies.xlsx
```

The exporter streams database rows and splits at Excel's 1,048,576-row worksheet limit (including the header). It fails rather than generating an empty or misleading workbook. For very large datasets, use the database or source TSV for analysis; Excel is a convenience export, not the canonical store.


## Read-only API lookup

After applying both reference migrations and configuring the runtime database login to assume genomeguard_reference_reader, the public metadata endpoint can serve an exact allele lookup:

GET /variants/population-frequency?chromosome=22&position=105123&reference_allele=A&alternate_allele=G&assembly=GRCh38

The API reads only aggregate frequency rows whose manifest is both approved_public_research and loaded. It returns source name, release, URL, artifact checksum, assembly, population, AC, AN, AF, and homozygote count. It never queries participant calls. Applying the migration creates the narrow reader role and grants its membership to Supabase service_role when that role exists; for another runtime login, a database administrator must grant membership before serving lookups.

The response status is available, empty, or unavailable. Missing serving-role grants, database access, migrations, or a matching approved loaded manifest produce an honest empty or unavailable response; the endpoint does not synthesize values. The Variant Inspector requires a selected or provenance-declared assembly and labels these results as aggregate reference evidence, separate from GenomeGuard participant data and governed releases. No public reference is claimed to be imported or loaded by this code alone.

## Current implementation status

This code provides normalized TSV preflight validation, import reconciliation reports, Excel export, and a read-only exact-locus API lookup. It does not download the source artifact, perform source-term approval, run the import, or connect to a production database. Do not claim data is loaded until a steward has completed those steps and reconciled row counts. gnomAD's represented cohort size must never be described as 807,162 individual profiles available for download.

Sources:
- https://gnomad.broadinstitute.org/news/2023-11-gnomad-v4/
- https://registry.opendata.aws/broad-gnomad/
