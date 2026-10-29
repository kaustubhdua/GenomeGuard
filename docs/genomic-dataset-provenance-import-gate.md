# Genomic dataset provenance and import gate

This document defines the minimum provenance contract for any real variant/genotype import into GenomeGuard. It is deliberately not a claim that a dataset has been loaded.

## Source review

For public 1000 Genomes / IGSR data, use the official [IGSR data portal](https://internationalgenome.org/data/), inspect the exact collection's README and data-reuse statement, and cite the collection's associated publication. IGSR warns that rights and restrictions can vary by collection and over time. Public availability is not blanket authorization for every downstream purpose.

Do not import controlled-access or private participant data into the public research instance. Do not synthesize participants, genotype calls, consent records, or variants to make coverage look populated.

## Manifest schema

Migration `20261029120000_genomeguard_variant_dataset_manifest.sql` adds the private `genomeguard.variant_dataset_manifest` ledger. A row records:
- stable dataset key, exact source URL and source release;
- reference assembly;
- SHA-256 of the exact source artifact;
- a human-reviewed data-use status and accurately described consent basis;
- import status and measured sample, variant, and genotype-call counts.

The ledger is not a substitute for verifying a source or consent. It intentionally has no browser grants and RLS is enabled. Server-side access must be provided through a narrowly scoped, reviewed function; do not grant broad direct access to the table.

A dataset cannot be marked `loaded` unless non-zero variant, sample, and genotype-call counts and an import timestamp are recorded, and the data-use status is approved. The schema does not itself validate biological correctness.

## Required importer behavior before any live import

1. Download the exact approved source artifact to controlled temporary storage; record the final URL, release, retrieval time, file size and SHA-256.
2. Confirm source assembly and contig naming. Reject assembly mismatches rather than silently relabeling coordinates.
3. Parse VCF with a maintained standards-compliant parser, validate header/sample identities, and reject malformed records, unsupported ploidy, invalid alleles, duplicate keys and out-of-range coordinates.
4. Calculate allele frequency from actual genotype calls with a documented missing-call denominator. Do not infer genotype data from variant catalogue records.
5. Use bounded batches and idempotent keys. Keep source files and participant-level identifiers out of Git and application logs.
6. Load variants and genotypes atomically or use a staged import that cannot be mistaken for released data until validation passes.
7. Reconcile imported counts against source counts; verify sample/variant relationships, chromosome ranges, duplicate counts, and checksums.
8. Record the manifest only from measured import results; preserve the source's data-use statement and citations.
9. Run negative tests for malformed input, checksum mismatch, build mismatch, duplicate import, interrupted import and unauthorized access.
10. Verify live query results and the user interface against the exact imported dataset before setting any release gate.

## Current known state

At the last live check on 2026-10-29, GenomeGuard's GRCh38 reference catalogue contained 25 rows, while `genomeguard.variants`, `genomeguard.genotypes`, donors, requests, decisions and audit log had zero rows. The application API migration and release gate were still false, and the legacy Render dependency flag remained true. The provenance migration is proposed on a feature branch and has not been applied to the shared live database.

## Acceptance rule

A green frontend deployment is not evidence of a loaded cohort or a complete application. Do not call GenomeGuard production-ready until the dataset import, endpoint parity, identity/authorization, durable persistence, audit integrity, backup/restore and deployed end-to-end acceptance checks all pass. Continue to label this as research software and do not use it for clinical decisions.
