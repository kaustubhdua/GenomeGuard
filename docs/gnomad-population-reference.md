# gnomAD aggregate population reference: import and Excel export

## Important distinction

This pipeline stores **aggregate allele frequencies**, not individual genomes or genotype calls. gnomAD v4 represents 807,162 upstream individuals (730,947 exomes and 76,215 genomes) on GRCh38. That number is provenance metadata; it is not the number of people or records stored locally.

The existing `backend.app.data.vcf_import` importer is for sample-level VCFs with GT fields and must not be used for gnomAD aggregate sites files.

## Input format

Download the appropriate public gnomAD v4 GRCh38 sites artifact and prepare a normalized UTF-8 TSV with one row per variant and population. Required columns:

`chromosome, position, reference_allele, alternate_allele, population, allele_count, allele_number, allele_frequency`

Optional: `homozygote_count`. No additional columns are accepted; sample identifiers, individual genotype fields, and participant IDs are rejected. Preserve source release, artifact URL, checksum, and documented population labels. The normalizer must map the release's INFO/frequency annotations to AC, AN, AF and homozygote count without deriving sample-level calls.

## Import

1. Apply the native migration `backend/migrations/002_normalized_public_references.sql` through the normal reviewed deployment process. It creates the normalized dataset and aggregate-reference tables without Supabase or PostgREST.
2. A trusted data steward must register the source manifest, verify the exact artifact checksum and terms, and set `data_use_review='approved_public_research'` and `import_status='validated'`. This is intentionally not done by the importer.
3. Configure `GG_IMPORT_DATABASE_URL` only in the trusted operator environment. The importer falls back to `GG_DATABASE_URL`, then `DATABASE_URL`; it does not issue provider-specific `SET ROLE` commands. Use a dedicated PostgreSQL login with SELECT on the population manifest and INSERT/SELECT on the aggregate frequency table, plus the frequency ID sequence.
4. Install the project and optional Excel dependency:

```bash
pip install -e '.[reference]'
GG_IMPORT_DATABASE_URL='...' python -m app.data.gnomad_reference import \
  --input /secure/gnomad-frequency.tsv \
  --dataset-key gnomad-v4-grch38 \
  --expected-sha256 <64-character-sha256>
```

The import streams in batches and is idempotent. It inserts only into `genomeguard.population_variant_frequency`; it does not approve or mark a manifest loaded. A steward must reconcile the database row count and update the manifest using an administrative session after a successful import.

## Excel export

Only a manifest already approved and marked `loaded` can be exported:

```bash
GG_IMPORT_DATABASE_URL='...' python -m app.data.gnomad_reference export-xlsx \
  --dataset-key gnomad-v4-grch38 \
  --output ./gnomad-v4-population-frequencies.xlsx
```

The exporter streams database rows and splits at Excel's 1,048,576-row worksheet limit (including the header). It fails rather than generating an empty or misleading workbook. For very large datasets, use the database or source TSV for analysis; Excel is a convenience export, not the canonical store.


## Read-only API lookup

After applying the native PostgreSQL migration and granting the application database login SELECT access to the aggregate reference tables, the public metadata endpoint can serve an exact allele lookup:

GET /variants/population-frequency?chromosome=22&position=105123&reference_allele=A&alternate_allele=G&assembly=GRCh38

The API reads only aggregate frequency rows whose manifest is both approved_public_research and loaded. It returns source name, release, URL, artifact checksum, assembly, population, AC, AN, AF, and homozygote count. It never queries participant calls. The query executes in a read-only transaction and filters to approved, loaded manifests. No Supabase role or Edge Function is involved.

The response status is available, empty, or unavailable. Missing database access, migrations, or a matching approved loaded manifest produce an honest empty or unavailable response; the endpoint does not synthesize values. The Variant Inspector requires a selected or provenance-declared assembly and labels these results as aggregate reference evidence, separate from GenomeGuard participant data and governed releases. No public reference is claimed to be imported or loaded by this code alone.

## Current implementation status

This code provides normalized TSV import, Excel export, and a read-only exact-locus API lookup. It does not download the source artifact, perform source-term approval, run the import, or connect to a production database. Do not claim data is loaded until a steward has completed those steps and reconciled row counts. gnomAD's represented cohort size must never be described as 807,162 individual profiles available for download.

Sources:
- https://gnomad.broadinstitute.org/news/2023-11-gnomad-v4/
- https://registry.opendata.aws/broad-gnomad/
