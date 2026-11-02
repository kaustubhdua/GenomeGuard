"""Curated public genomic data sources; discovery is separate from import approval."""

PUBLIC_GENOMIC_SOURCES = (
    {
        "source_id": "igsr-1000-genomes-phase-3",
        "name": "1000 Genomes Project Phase 3",
        "provider": "International Genome Sample Resource (IGSR)",
        "release": "Phase 3 collection; exact artifact not pinned",
        "data_type": "Sample-level variant calls (VCF)",
        "assembly": "GRCh37 is common; verify the exact artifact header",
        "summary": (
            "Publicly discoverable sample-level variation data. IGSR states that the "
            "1000 Genomes data are unembargoed, while rights and restrictions can vary "
            "between and within collections."
        ),
        "reuse_review": (
            "Review the exact collection's reuse statement and publication; this listing "
            "does not grant permission or establish participant-specific consent."
        ),
        "source_url": "https://www.internationalgenome.org/data-portal/data-collection/phase3/",
        "terms_url": "https://www.internationalgenome.org/IGSR_disclaimer/",
        "terms_review_status": "pending_exact_artifact_review",
        "import_status": "not_imported_by_catalogue",
        "workflow": "Steward VCF QC and the normalized VCF importer are available; no source artifact is approved or imported by this listing.",
    },
    {
        "source_id": "gnomad-v4-1-grch38",
        "name": "gnomAD aggregate reference",
        "provider": "gnomAD Production Team at the Broad Institute",
        "release": "v4.1",
        "data_type": "Aggregate allele-frequency summary data",
        "assembly": "GRCh38",
        "summary": (
            "Aggregate population reference data, not a collection of individual genotype "
            "calls. The AWS Open Data Registry describes the v4.1 GRCh38 summary release "
            "as available to the wider scientific community."
        ),
        "reuse_review": (
            "The AWS registry lists the MIT license and links gnomAD terms. Confirm the "
            "exact artifact and applicable terms before import."
        ),
        "source_url": "https://registry.opendata.aws/broad-gnomad/",
        "terms_url": "https://gnomad.broadinstitute.org/terms",
        "terms_review_status": "pending_exact_artifact_review",
        "import_status": "not_imported_by_catalogue",
        "workflow": "An aggregate-frequency importer and exact-locus lookup are available; no source artifact is approved or loaded by this listing.",
    },
    {
        "source_id": "ncbi-clinvar-variant-summary",
        "name": "NCBI ClinVar variant summary",
        "provider": "National Center for Biotechnology Information (NCBI)",
        "release": "Continuously updated; exact artifact snapshot not pinned",
        "data_type": "Variant assertion and submission summary metadata",
        "assembly": "Multiple/record-specific; filter and verify before use",
        "summary": (
            "Public variant-submission summaries; this is not a participant genotype "
            "cohort. The download artifact is updated by NCBI."
        ),
        "reuse_review": (
            "NCBI states that it places no restriction on molecular database data, but "
            "submitter or third-party rights may apply; NCBI does not grant those rights."
        ),
        "source_url": "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz",
        "terms_url": "https://www.ncbi.nlm.nih.gov/home/about/policies/",
        "terms_review_status": "pending_exact_artifact_review",
        "import_status": "not_imported_by_catalogue",
        "workflow": "A research-only baseline workflow is available; it has not been run or approved by this listing.",
    },
)


def public_source_catalogue() -> list[dict[str, str]]:
    """Return fresh source records so API consumers cannot mutate the registry."""
    return [dict(source) for source in PUBLIC_GENOMIC_SOURCES]
