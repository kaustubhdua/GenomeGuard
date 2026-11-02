# Public genomic source discovery

GenomeGuard exposes a small, curated source index at `GET /catalogue/sources` and in
the **Source discovery** page. It links to official source and policy pages for:

- IGSR / 1000 Genomes Project Phase 3 sample-level variation data.
- gnomAD v4.1 aggregate population-frequency data.
- NCBI ClinVar variant-submission summary metadata.

The index is discovery metadata only. It does not download data, verify a particular
artifact checksum, approve its reuse, import it, or add it to the verified dataset
catalogue. Each entry reports exact-artifact terms review as pending and import as
not completed. Public access must not be interpreted as participant-specific consent,
legal authorization, or permission for every intended use.

The API also exposes a `lifecycle_status` object for discovery, metadata registration,
download, checksum verification, QC validation, steward approval, import, and permitted
research availability. For the current curated entries, only discovery and metadata
registration are complete. No source artifact is recorded as downloaded, checksum
verified, QC validated, approved, imported, or available for research use.

## Source review notes

- **IGSR:** IGSR describes 1000 Genomes data as unembargoed, but warns that rights and
  restrictions can vary between and within collections. Review the exact collection's
  reuse statement and publication; do not infer one license for every artifact.
- **gnomAD:** the AWS Open Data Registry lists the v4.1 GRCh38 summary release, an MIT
  license, and gnomAD terms. GenomeGuard handles this as aggregate reference data, not
  individual genotype calls. Verify terms for the exact artifact before import.
- **ClinVar:** NCBI's usage policy says NCBI itself places no restriction on molecular
  database data, while submitter or third-party rights may apply; NCBI does not grant
  those rights. The listed summary is variant-submission metadata, not a participant
  genotype cohort.

The source and policy links are part of each API record and open in a new browser tab.
Local workflows exist for VCF QC/import, gnomAD aggregate-reference ingestion, and
research-only ClinVar baseline training, but this index does not claim that any of
those workflows has approved, loaded, or validated a source release.

Before any import, a steward must review the exact artifact's provenance and reuse
statement, record and independently verify its checksum, confirm the assembly and
intended use, and follow the existing import/count-reconciliation gates. QC success
does not establish reuse approval or participant-specific consent.

Official references:

- [IGSR: Using data from IGSR](https://www.internationalgenome.org/data/)
- [IGSR: data disclaimer](https://www.internationalgenome.org/IGSR_disclaimer/)
- [IGSR: Phase 3 collection](https://www.internationalgenome.org/data-portal/data-collection/phase3/)
- [AWS Open Data Registry: gnomAD](https://registry.opendata.aws/broad-gnomad/)
- [gnomAD terms](https://gnomad.broadinstitute.org/terms)
- [NCBI: ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/)
- [NCBI: data usage policies](https://www.ncbi.nlm.nih.gov/home/about/policies/)

## Candidate-source screen

The following official guidance was reviewed on 2026-11-02. It supports discovery
research, not automatic import approval:

- **HPRC:** its data page describes public access to sequencing data, assemblies,
  and pangenomes, and directs users to data-use best practices. These include file
  types and workflows outside GenomeGuard's current VCF/aggregate-reference import
  contracts, so no HPRC artifact is listed as importable.
- **UCSC Genome Browser:** its data policy permits broad use of many browser data
  files but explicitly identifies track- and source-specific restrictions. A source
  name alone is not enough to approve an assembly track or annotation artifact.
- **EMBL-EBI and Ensembl:** EMBL-EBI's general terms defer to data-owner terms and
  resource-specific conditions. The Ensembl legal page retrieved during this review
  was an archived snapshot and did not establish blanket reuse terms for a selected
  genomic data artifact. The exact dataset and its attribution/reuse conditions must
  be pinned before adding it.
- **GEO, SRA, and Human Cell Atlas:** this review did not establish current,
  artifact-specific access and reuse conditions for a candidate that fits the
  existing importer. No source was added on the basis of an unverified policy page.
- **GTEx:** the portal provides a distinct protected-data-access path. No data from
  that path is included or treated as available to GenomeGuard.

These resources are not represented in the current catalogue as imported or
integration-ready. Adding a source requires a compatible parser/import contract,
an exact artifact and assembly, verified checksum, source-specific reuse review,
and the existing steward approval and reconciliation steps.

Additional official references:

- [HPRC data availability](https://humanpangenome.org/data/)
- [UCSC data and software use policy](https://genome.ucsc.edu/license/)
- [EMBL-EBI terms of use](https://www.ebi.ac.uk/about/terms-of-use)
- [Ensembl legal information](https://www.ensembl.org/info/about/legal/index.html)
- [GTEx protected data access](https://gtexportal.org/home/protectedDataAccess)
