# Aggregate population-reference import (gnomAD)

## Important distinction

This pipeline is for aggregate population allele counts/frequencies, not individual genomes or genotype calls. gnomAD v4 represents 807,162 individuals (730,947 exomes and 76,215 genomes) on GRCh38, but its public summary variant data does not expose 807,162 individual genotype profiles. GenomeGuard stores only aggregate counts in `genomeguard.population_variant_frequency`; it must never create sample or participant rows from this source.

The existing `backend.app.data.vcf_import` importer is for sample-level VCFs with GT fields and must not be used for gnomAD aggregate sites files.

## Source and scope

- Source: gnomAD v4 public summary data.
- Upstream represented cohort: 807,162 individuals.
- Assembly: GRCh38.
- Official data catalogue: https://registry.opendata.aws/broad-gnomad/
- Release documentation: https://gnomad.broadinstitute.org/news/2023-11-gnomad-v4/
- The upstream cohort size is provenance metadata only; it is not a claim that GenomeGuard has downloaded or stored 807,162 genomes.

Before import, a data steward must verify the exact release, exact artifact URL, SHA-256, applicable terms, and intended-use scope. Register a manifest with `represented_individual_count=807162` only after checking the exact source release documentation. The migration deliberately does not auto-approve or auto-load a dataset.

## Data model

- `population_reference_manifest`: source/release/assembly, represented upstream cohort size, review state, checksum and import state.
- `population_variant_frequency`: one row per variant and population with AC, AN, AF and optional homozygote count.
- No sample IDs, individual GT calls, or participant identities are accepted.
- The manifest's `loaded` state requires explicit public-research approval and non-zero imported row count.

The new importer role is append-only: it can read manifests and insert aggregate rows, but cannot update or delete rows. A trusted steward must separately update manifest review/import status using an administrative session after independently reconciling row counts.

## Current implementation status

The migration establishes the isolated schema and privilege boundary. It does not download gnomAD files, populate rows, approve source terms, or change the decision engine. A parser/import command and integration tests must be completed and run before any source is marked loaded. Do not represent this migration as a 807,162-person dataset import.
