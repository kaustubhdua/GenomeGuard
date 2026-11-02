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
