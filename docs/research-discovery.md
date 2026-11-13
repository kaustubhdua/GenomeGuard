# Research discovery

GenomeGuard's Research Discovery page provides department-specific entry points and a live search of Europe PMC publication records.

## Data source and behavior

- Requests use the public Europe PMC Articles REST search endpoint:
  `https://www.ebi.ac.uk/europepmc/webservices/rest/search`.
- Search terms are sent to Europe PMC. Results are returned from its publication index; GenomeGuard does not fabricate papers, authors, abstracts, identifiers, or publication dates.
- The page requests JSON `core` records and displays the source-provided title, author string, journal, publication date, abstract, PMID, PMCID, DOI, and open-access flag when present.
- Department links preselect a field query. The search form accepts a symptom description, biomedical concept, gene, condition, or research question and combines it with the selected department.
- Publication links open the original DOI, PubMed, or Europe PMC record. External links use HTTPS and `noopener noreferrer`.

## Important limitations

This first implementation is a live literature retrieval and department-filtering feature, **not an AI diagnostic model or semantic clinical decision-support system**. The source index performs its own retrieval and ranking; GenomeGuard does not claim to infer a diagnosis, determine pathogenicity, recommend treatment, or assess clinical applicability. A future AI summarization or semantic-reranking layer must be separately evaluated, remain advisory, cite the underlying papers, and never affect GenomeGuard's deterministic access-governance decisions.

Symptoms and research questions may be sensitive. The page warns users not to enter names, contact details, or identifying patient information. Search text is transmitted to Europe PMC; do not use this page with private patient records.

A publication's appearance in search results is not evidence of study quality. Researchers must review the original paper, study design, population, limitations, publication status, and applicable reuse terms.

## Verification

The route is included in local and deployed UI smoke inventories, including phone-width checks. The route can be opened without a search; the live external literature query is only sent after the user submits the form. A live search requires network access to Europe PMC.
