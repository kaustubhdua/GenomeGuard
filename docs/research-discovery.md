# Multi-source literature and genomic evidence discovery

GenomeGuard's Research Discovery workspace contains two related but distinct evidence surfaces:

1. **Publication search** retrieves publication metadata from two independent public sources: Europe PMC and NCBI PubMed.
2. **Gene–disease evidence** retrieves direct target–disease associations and optional source-level evidence from the Open Targets Platform. These records are not publication-search results and their platform scores are not GenomeGuard confidence or clinical validity.

The surfaces share a research workspace but preserve each provider's own response contract, provenance, identifiers, and scientific limitations.

## Search behavior

- Department entry points: Genetics & Genomics, Oncology, Neurology, Cardiology, Immunology, Rare Diseases, Bioinformatics and Pharmacogenomics.
- Research questions may describe a disease, symptom, gene, biological process or topic. Search is for literature discovery, not diagnosis.
- The source selector supports both providers together or either provider individually.
- Europe PMC uses its documented JSON core response and cursorMark pagination.
- PubMed uses GenomeGuard's server-side POST /literature/pubmed/search endpoint, backed by NCBI ESearch and ESummary. The browser never receives the NCBI API key.
- The UI normalizes provider fields for display and deduplicates across the current and previously loaded pages by PMID, then DOI, then PMCID, then normalized title.
- When one source is unavailable, results from the other source remain available and the UI reports the partial failure. If both fail, no placeholder or fabricated publication is shown.
- Pagination maintains an independent cursor for each provider. A provider that stops advancing is not allowed to cause an infinite load-more loop.

## Source attribution and scientific limits

Every publication card labels its source and links to an HTTPS DOI, PubMed or Europe PMC record. Metadata is displayed as supplied by the provider; missing authors, journal, dates, abstracts or identifiers remain missing.

PubMed ESummary metadata in this initial integration does not include abstracts. An absent PubMed abstract is not inferred or generated. Europe PMC may return abstract text for records where its API provides it.

Search ranking is the provider's retrieval order, not a GenomeGuard evidence-quality score. A publication record is not proof of clinical validity, causality, pathogenicity or treatment effectiveness. Researchers must review the original work, study design, population, methods, limitations and publication status.

## Privacy and provider behavior

- Query text is sent to the selected public providers. Users must not submit names, medical record numbers, private genotypes, private cohort membership or other identifying patient information.
- PubMed query text is submitted in a POST body, not the URL request line. The API sets Cache-Control: no-store, avoids persistence, and applies a per-process concurrency guard.
- The NCBI request limiter is per process. A distributed/shared limiter is required before horizontal scaling or multiple application workers.
- Europe PMC is called directly by the browser. Review its terms and institutional data-handling requirements before using sensitive or institution-confidential queries.

## Verification

- scripts/research_provider_smoke.py exercises the real Europe PMC API and checks metadata types and cursor advancement.
- scripts/pubmed_provider_smoke.py exercises real NCBI ESearch and ESummary using a public query.
- scripts/research_ui_smoke.py intercepts both provider APIs with deterministic fixtures, tests department searches, pagination, cross-source duplicate removal, source links and mobile layout.
- The full browser test runs as part of make ui-smoke and CI.


## Research workspace, source filters and exports

The research workspace includes an Open Targets evidence panel that accepts an explicit Ensembl gene identifier and optional EFO disease identifier. It does not guess gene symbols or resolve identifiers silently. Association and evidence source filters preserve the provider's datasource/datatype attribution. Original HTTPS evidence URLs and numeric PMID links are rendered as source links.

The panel displays the Open Targets API version, data release, retrieval timestamp, endpoint and exact query identifiers. JSON and Markdown exports include those provenance fields, the loaded result pages, original evidence identifiers/URLs, and explicit citation requirements. The export warns that association scores are Open Targets prioritisation scores, not probabilities, clinical validity, causality or GenomeGuard confidence. Pagination refuses to combine records if the API or data release changes during a search.


## ClinVar variant evidence

The workspace includes a ClinVar panel for searching variant-level records by an explicit gene symbol. The server uses NCBI E-utilities ESearch and ESummary v2.0, and the browser never receives an NCBI API key. Supported filters use ClinVar's documented Properties terms (for example, `clinsig pathogenic` and `clinsig has conflicts`). These are source search properties that find variants with at least one matching report; they are not a GenomeGuard classification or a guarantee that the aggregate VCV classification has that exact value.

Each result preserves the VCV accession/version, source title, gene identifiers, variation type, assembly-specific genomic locations, SPDI where supplied, molecular consequences, and the three distinct ClinVar classification groups: germline, somatic clinical impact, and somatic oncogenicity. Review status, last-evaluated date, traits, and counts of supporting SCV/RCV submissions are displayed as source-provided. Conflicting classifications are not flattened or resolved by GenomeGuard.

The UI exports the exact query, loaded source records, retrieval time, API version, and interpretation limits as JSON. ClinVar records are variant-level assertions, not patient-specific interpretations, diagnosis, treatment recommendations, or independent proof of clinical validity. Researchers should review the original VCV/RCV/SCV submissions and evidence.

Verification:
- `scripts/clinvar_provider_smoke.py` performs a live BRCA1 + ClinVar Properties search and checks the ESearch/ESummary contract.
- `backend/tests/test_clinvar.py` validates query construction, classification filters, pagination, source metadata, review status, and conflict preservation.
- `backend/tests/test_clinvar_api.py` validates request bounds, safe errors, no-store headers, and concurrency limits.
- `scripts/research_ui_smoke.py` intercepts the API with deterministic source-shaped fixtures and checks conflict display, pagination, export, and mobile layout.


## GWAS Catalog association discovery

GenomeGuard uses **GWAS Catalog REST API v2 only**. The former v1 API was retired in August 2026. The v2 integration searches literature-curated top associations by mapped gene, rsID, and/or EFO trait; optional child-trait expansion is explicit. The standard Ensembl gene set is used (`extended_geneset=false`) to match the Catalog's default mapping behavior.

Each response preserves the association ID, study accession, PubMed ID, first author, reported and EFO traits, p-value and mantissa/exponent, beta or odds ratio, confidence interval, risk frequency, mapped genes, genomic locations, effect alleles, source links, and retrieval time. The API metadata endpoint contributes the data release date, API release date, dbSNP build, gene build, EFO version, Ensembl version, commit hash, and license. Pagination follows the provider's validated v2 next link and is bounded to a maximum page size of 50. The adapter spaces requests at 1.5 seconds per process (below the documented 100-requests-per-minute limit); deployments with multiple application processes should add a shared rate limiter before increasing worker count.

**Scope boundary:** the v2 API provides literature-curated top associations and metadata. It does not provide full genome-wide summary statistics; the previous summary-statistics API was retired in 2026. A GWAS association or p-value is not proof of causation, clinical validity, or an individual's risk. Effect estimates and allele frequencies remain source-reported and must be interpreted in the context of study design, ancestry, phenotype, and replication.

The research panel supports gene, rsID, and trait searches and exports the query, source records, release metadata, and interpretation limits as JSON.

Verification:
- `scripts/gwas_catalog_provider_smoke.py` checks the live v2 metadata and BRCA1 association contract.
- `backend/tests/test_gwas_catalog.py` validates query parameters, release provenance, p-values, alleles, links, pagination, and malformed responses.
- `backend/tests/test_gwas_api.py` validates input bounds, safe provider errors, no-store responses, and concurrency limits.
- `scripts/research_ui_smoke.py` checks search, pagination, provenance, exports, and mobile layout with deterministic source-shaped fixtures.
