# Open Targets Platform integration

## Scope

GenomeGuard queries the official Open Targets Platform GraphQL API for one Ensembl target at a time. This is intentionally not a bulk ingestion pipeline. Open Targets recommends its GraphQL API for single-entity/association exploration and data downloads or BigQuery for systematic multi-entity analyses.

Endpoint: https://api.platform.opentargets.org/api/v4/graphql

## GenomeGuard API

POST /research/open-targets/target

JSON body:
- ensembl_id: required Ensembl gene identifier, ENSG followed by 11 digits.
- disease_id: optional stable EFO identifier (EFO_ followed by digits). When supplied, GenomeGuard also requests source evidence for that target/disease pair.
- page_index: zero-based association page, 0–100.
- page_size: 1–50.
- evidence_size: 1–50.
- evidence_cursor: optional opaque cursor returned by the prior evidence response; maximum 2,048 characters.

The server uses a fixed GraphQL document and variables, HTTPS POST, bounded response size, timeout, bounded retry for 429/5xx/transport errors, GraphQL error rejection, conservative per-process request pacing and a per-process concurrency cap. Responses use Cache-Control: no-store. No user-supplied GraphQL document is accepted.

## Returned evidence and provenance

- Target: Ensembl identifier, approved symbol and biotype.
- Associations: disease identifier/name, Open Targets aggregate score, datasource component scores and datatype component scores.
- Optional evidence: evidence identifier, datasource/datatype, source score, release version/date, publication date/first author, literature IDs, external URLs, study identifier/sample size, cohort description and quality-control flags.
- Provenance: API version, Open Targets data release version, retrieval timestamp, official endpoint and direct-only mode.

Missing source fields remain missing. Evidence is not collapsed into a single GenomeGuard confidence score. Publication identifiers are retained as returned by Open Targets.

## Interpretation and limitations

Open Targets association scores are platform-specific heuristic prioritisation scores, not probabilities, clinical validity, pathogenicity, causality or treatment recommendations. Scores and associations can change across data releases and depend on source weighting and evidence aggregation.

This integration explicitly sets enableIndirect=false for the association list. Disease-specific evidence returned by target.evidences may itself represent varied source methods, including predictive, experimental, clinical, text-mined or indirect evidence; review each evidence row, its source and original publication. Do not infer that a source record proves a causal relationship.

The adapter does not resolve free-text gene symbols or disease names. Callers must provide a verified Ensembl ID; disease filters must use a stable ontology identifier. Identifier mapping is a separate workflow and must preserve mapping source and ambiguity rather than guessing.

For large-scale systematic work, use official Open Targets data downloads or BigQuery rather than repeated single-target GraphQL requests.

## Verification

- Deterministic tests mock GraphQL responses and validate association/evidence normalization, release metadata, identifier and pagination bounds, GraphQL partial-error rejection, malformed rows, retry behavior and API errors.
- scripts/open_targets_provider_smoke.py performs a low-volume live query for public TP53 target metadata and one disease-specific evidence page.
- No API key is required by the documented public GraphQL API. Do not add credentials to the client or repository.

## Official references

- GraphQL API: https://platform-docs.opentargets.org/data-access/graphql-api
- Data and code access/licensing: https://platform-docs.opentargets.org/data-access
- Target–disease evidence: https://platform-docs.opentargets.org/evidence
- Target–disease associations: https://platform-docs.opentargets.org/associations
- Official API implementation: https://github.com/opentargets/platform-api
