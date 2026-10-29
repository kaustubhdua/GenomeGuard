# Genomic dataset provenance and import gate

This document defines the minimum provenance contract for any real variant/genotype import into GenomeGuard. It is deliberately not a claim that a dataset has been loaded.

## Source review

For public 1000 Genomes / IGSR data, use the official [IGSR data portal](https://internationalgenome.org/data/), inspect the exact collection's README and data-reuse statement, and cite the collection's associated publication. IGSR warns that rights and restrictions can vary by collection and over time. Public availability is not blanket authorization for every downstream purpose.

Do not import controlled-access or private participant data into the public research instance. Do not synthesize participants, genotype calls, consent records, or variants to make coverage look populated.

## Pinned public research artifact selected for the prototype

- Collection/release: 1000 Genomes Project Phase 3, release 20130502, integrated call set v5b, chromosome 22 only.
- Official artifact: `https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/ALL.chr22.phase3_shapeit2_mvncall_integrated_v5b.20130502.genotypes.vcf.gz`
- Expected artifact size: 205,612,353 bytes.
- Pinned SHA-256: `a90c16c4ff2b3196476d506ae13cb3047fae8670163c7c932c4b0239aef3daf5` (verified by the repository's pinned-download check; re-verify the exact local artifact before database import).
- Reference assembly: GRCh37; Phase 3 represents 2,504 samples, but the actual imported sample count must be measured from this exact artifact.
- Citation: The 1000 Genomes Project Consortium, *A global reference for human genetic variation*, Nature 526, 68–74 (2015), DOI: 10.1038/nature15393.
- Reuse review: read the IGSR collection page, its specific reuse statement and [IGSR's data-use disclaimer](https://www.internationalgenome.org/IGSR_disclaimer/) before import. The CLI's review flag is an operator attestation, not independent ethics/legal approval.
- Scope: this is chromosome 22 only, not whole-genome coverage. No normalized Supabase import is currently verified.

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
3. Validate the source with a maintained VCF tool such as BCFtools, then run GenomeGuard's deliberately strict importer parser. The current importer supports a bounded VCF subset (simple DNA alleles, autosomes/X/Y/MT, haploid/diploid GT); symbolic/breakend alleles and unsupported records are rejected rather than silently coerced. It is not a general-purpose VCF implementation.
4. Calculate allele frequency from actual genotype calls with a documented missing-call denominator. Do not infer genotype data from variant catalogue records.
5. Use bounded batches and idempotent keys. The current importer requires a timezone-aware operator-supplied retrieval timestamp and stores it separately from the database import timestamp. Keep source files and participant-level identifiers out of Git and application logs.
6. Load variants and genotypes atomically or use a staged import that cannot be mistaken for released data until validation passes.
7. Reconcile imported counts against source counts; verify sample/variant relationships, chromosome ranges, duplicate counts, and checksums.
8. Record the manifest only from measured import results; preserve the source's data-use statement and citations.
9. Run negative tests for malformed input, checksum mismatch, build mismatch, duplicate import, interrupted import and unauthorized access.
10. Verify live query results and the user interface against the exact imported dataset before setting any release gate.

## Current known state

At the live check on 2026-10-29, the normalized manifest, sample, variant and genotype-call tables all had zero rows. The application API migration and release gate remained false, and the legacy Render dependency flag remained true. The schema exists in the live project, but no normalized dataset has been imported or verified.

## Acceptance rule

A green frontend deployment is not evidence of a loaded cohort or a complete application. Do not call GenomeGuard production-ready until the dataset import, endpoint parity, identity/authorization, durable persistence, audit integrity, backup/restore and deployed end-to-end acceptance checks all pass. Continue to label this as research software and do not use it for clinical decisions.
