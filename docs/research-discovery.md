# Multi-source research discovery

GenomeGuard's Research Discovery workspace retrieves publication metadata from two independent public sources: Europe PMC and NCBI PubMed.

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
