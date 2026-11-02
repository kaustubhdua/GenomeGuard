# ClinVar variant-level evidence

GenomeGuard can serve aggregate variant-level assertions from a steward-reviewed ClinVar snapshot. It does not make a pathogenicity prediction, diagnosis, or treatment recommendation.

## Scope and matching

The importer reads the public ClinVar variant_summary tab-delimited release and stores only GRCh38, equal-length substitutions (SNVs and MNVs) with exact chromosome, position, REF, and ALT. It skips indels and complex representations until an HGVS/VCF canonical normalizer is available; ClinVar documents different coordinate conventions for these formats.

For each exact match the Variant Inspector can show the reported clinical significance, textual review status, last evaluated date, submitter count, gene symbols, associated phenotype labels, NCBI Variation ID link, source release, and source file checksum. Conflicting and uncertain classifications are visibly flagged. The summary is variant-level: its phenotype list is associated metadata and must not be read as a separate classification for every condition. GenomeGuard does not calculate review stars or merge disagreeing assertions into a new verdict.

The lookup endpoint is GET /variants/clinical-annotations and requires chromosome, position, reference_allele, alternate_allele, and assembly. It returns only rows from a manifest whose data-use review is approved_public_research and import status is loaded. A missing database or unconfigured reader role returns unavailable; no matching assertion returns empty. No synthetic assertions are created.

## Validate a downloaded release

Review NCBI ClinVar's data-use and release information. Download the official summary in a controlled workspace and record the source release/date:

    curl -fL https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz \
      -o /secure/variant_summary.txt.gz
    PYTHONPATH=backend python -m app.data.clinvar_reference validate \
      --input /secure/variant_summary.txt.gz \
      --dataset-key clinvar-variant-summary-grch38-YYYYMMDD \
      --expected-sha256 <64-character-sha256> \
      --report /secure/reports/clinvar-validation.json

Validation streams the file and reports its checksum, file size, and eligible/excluded row counts. It does not connect to the database, approve a manifest, or import rows. It retains no individual genotypes or raw variants in the report.

## Import and steward reconciliation

1. Apply migration 20261105000000_genomeguard_clinvar_annotation.sql through the reviewed database deployment process.
2. A steward registers the source manifest with assembly GRCh38, source release, URL, SHA-256, data_use_review approved_public_research, and import_status validated.
3. Configure DATABASE_URL only in the trusted runtime. The import login must be authorized to SET ROLE genomeguard_clinvar_importer.
4. Run:

    DATABASE_URL='...' PYTHONPATH=backend python -m app.data.clinvar_reference import \
      --input /secure/variant_summary.txt.gz \
      --dataset-key clinvar-variant-summary-grch38-YYYYMMDD \
      --source-release YYYY-MM-DD \
      --expected-sha256 <64-character-sha256> \
      --report /secure/reports/clinvar-import.json

The importer is streaming and idempotent. It inserts only eligible aggregate ClinVar summary rows. It does not download data, modify the manifest, or mark a dataset loaded. A steward must reconcile the report's inserted/database row counts and then update manifest status using an administrative session. The API/UI will not serve the snapshot until that independent review marks it loaded.

## Interpretation limits

- The UI displays the source's wording and review status; it does not turn assertions into a GenomeGuard score.
- Conflicting records remain conflicts. Uncertain significance remains uncertain.
- The listed conditions are associated phenotype metadata, not a condition-specific interpretation.
- Last evaluated is displayed as provided by the source summary, or as not recorded.
- The initial connector intentionally excludes indels and complex variants where coordinate normalization is ambiguous.
- The code does not claim that any ClinVar snapshot has been downloaded, approved, or imported.

Official references:
- ClinVar downloads: https://www.ncbi.nlm.nih.gov/clinvar/docs/downloads/
- ClinVar file and coordinate guide: https://www.ncbi.nlm.nih.gov/clinvar/docs/ftp_primer/
- ClinVar review status definitions: https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/

