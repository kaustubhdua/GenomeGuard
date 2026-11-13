# PubMed E-utilities integration

## Scope

GenomeGuard's PubMed adapter retrieves public PubMed search results and article summary metadata using NCBI E-utilities ESearch and ESummary. It is a separate provider from Europe PMC. It does not fetch or reproduce full article text or abstracts.

## Endpoint

`GET /literature/pubmed/search?q={query}&retstart=0&retmax=20`

- `q`: required research query, 1–500 characters.
- `retstart`: zero-based offset, 0–10,000.
- `retmax`: page size, 1–50.
- Results are sorted by PubMed relevance.
- Response includes provider, query, total count, offset, page size, returned count, has-more flag, normalized papers, retrieval timestamp and provider provenance.
- Each paper preserves PMID, DOI and PMCID when supplied by PubMed, source title, authors, journal, publication date, article types and the canonical PubMed URL.
- Abstracts are not included by this adapter; `abstract_available` is explicitly false.

Search responses use `Cache-Control: no-store` because a research query can be sensitive even when callers are instructed not to send patient-identifying or private genomic information. Queries are not written to GenomeGuard's database or audit log.

## NCBI configuration

Optional server-side environment variables:

- `GG_NCBI_TOOL`: client/tool name; defaults to `GenomeGuard`.
- `GG_NCBI_EMAIL`: registered maintainer contact email. Configure this before a public institutional deployment.
- `GG_NCBI_API_KEY`: optional NCBI API key. Keep it server-side; never expose it to the browser.

Without an API key, the adapter spaces requests to no more than three requests per second per application process. With an API key, it deliberately retains the conservative rate. ESearch plus ESummary normally requires two requests per search page. The in-process limiter is appropriate for the current single-worker staging deployment; horizontally scaled production must use a shared/distributed limiter to enforce an account-wide rate.

Transient HTTP 429 and 5xx responses and transport timeouts are retried with bounded backoff. Other 4xx responses, malformed JSON and missing provider fields fail closed with a safe provider error. The browser receives no upstream stack trace or credentials.

## Data and scientific boundaries

- PubMed metadata is attributed to NCBI PubMed and each record links to its original PubMed page.
- Missing metadata remains missing; GenomeGuard does not synthesize authors, journals, dates, abstracts or conclusions.
- PubMed indexing and article type do not establish study quality, clinical validity or causal evidence.
- Abstract and full-text retrieval is intentionally excluded pending a separate copyright/access review.
- Never submit patient names, medical record numbers, raw genotypes or other identifying private information to this public literature endpoint.

## Verification

Unit tests mock the official ESearch and ESummary response shapes and cover normalization, pagination metadata, empty result sets, invalid input, HTTP 429 retry behavior, malformed responses, API error envelopes and cache policy. A separate low-rate live smoke test should use a public research query and must not contain participant information.

## Official references

- [NCBI E-utilities Reference Guide](https://eutilities.github.io/site/Reference_Guide/a_reference/)
- [NCBI E-utilities Usage Guidelines and API Key](https://eutilities.github.io/site/API_Key/usageandkey/)
- [NCBI E-utilities Quick Start](https://eutilities.github.io/site/Quick_Start/eu_quick/)
