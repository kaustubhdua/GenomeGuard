# Research discovery

GenomeGuard's Research Discovery page provides department-specific entry points and a live search of Europe PMC publication records.

## Data source and behavior

- Requests use the public Europe PMC Articles REST search endpoint:
  `https://www.ebi.ac.uk/europepmc/webservices/rest/search`.
- Search terms are sent to Europe PMC. Results are returned from its publication index; GenomeGuard does not fabricate papers, authors, abstracts, identifiers, or publication dates.
- The page requests JSON `core` records and displays the source-provided title, author string, journal (including the nested journalInfo field used by core records), publication date, abstract, PMID, PMCID, DOI, and open-access flag when present.
- Each department hyperlink immediately runs a curated Europe PMC literature query; users can refine it with a symptom description, biomedical concept, gene, condition, or research question. Department terms and user terms are combined with explicit Boolean grouping.
- The search requests Europe PMC's documented MeSH/UniProt synonym expansion and defaults to the provider's relevance ranking.
- Results use the documented cursorMark / nextCursorMark pagination contract. The UI appends source records and stops when the provider no longer returns a continuation cursor.
- Publication links open the original DOI, PubMed, or Europe PMC record. External links use HTTPS and `noopener noreferrer`.

## Important limitations

This first implementation is a live literature retrieval and department-filtering feature, **not an AI diagnostic model or semantic clinical decision-support system**. The source index performs its own retrieval and ranking; GenomeGuard does not claim to infer a diagnosis, determine pathogenicity, recommend treatment, or assess clinical applicability. A future AI summarization or semantic-reranking layer must be separately evaluated, remain advisory, cite the underlying papers, and never affect GenomeGuard's deterministic access-governance decisions.

Symptoms and research questions may be sensitive. The page warns users not to enter names, contact details, or identifying patient information. Search text is transmitted to Europe PMC; do not use this page with private patient records.

A publication's appearance in search results is not evidence of study quality. Researchers must review the original paper, study design, population, limitations, publication status, and applicable reuse terms.

## Verification

The route is included in local and deployed UI smoke inventories, including phone-width checks. Opening the route alone does not send a query; selecting a department or submitting the search form does. Local browser acceptance intercepts Europe PMC with provider-shaped fixtures to test department links, result rendering, cursor pagination and symptom/question queries. A separate CI integration smoke test calls the real Europe PMC API and validates its response and cursor pagination contract.
