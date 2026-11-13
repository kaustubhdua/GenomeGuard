# GenomeGuard product specification

**Status:** Product baseline for review  
**Scope:** Genomic research governance and scientific literature discovery  
**Audience:** Researchers, institutional stewards, data custodians, security/privacy reviewers and platform operators

## 1. Product definition

GenomeGuard is a research-governance platform that helps institutions discover biomedical evidence, describe genomic datasets, evaluate research-access requests against documented data-use rules, and preserve an inspectable record of governance decisions.

It has two related but independently useful capabilities:

1. **Evidence discovery:** search public scientific literature and explore source-linked gene, disease, phenotype, variant and dataset references.
2. **Research governance:** register datasets and their provenance, capture authoritative consent or dataset-policy evidence, evaluate purpose-bound requests, route decisions to authorized stewards, and release only outputs permitted by the applicable policy.

GenomeGuard is not a clinical decision-support system, diagnostic tool, variant interpretation authority, substitute for an institutional review board, or legal determination of consent.

## 2. Product principles

- Source-backed: every publication, dataset, identifier and scientific assertion must link to its original source and retrieval/version context.
- Evidence before inference: derived relationships and summaries must distinguish source facts, computed results and model-generated explanations.
- Governance before release: discovery and approval never imply that underlying records are available to a researcher.
- Consent is specific: public dataset terms are not participant-specific consent; simulated consent is never presented as real.
- Fail closed: missing, ambiguous, expired or unverifiable authorization prevents controlled-data release.
- Privacy by design: minimize collected information, avoid participant identifiers in literature search, and protect family/relative exposure.
- Reproducible: record software versions, data hashes, query parameters, policy versions and decision evidence needed to reproduce permitted operations.
- Honest status: distinguish implemented, tested, deployed, independently reviewed and institutionally approved capabilities.

## 3. Users and responsibilities

### Researcher
Discovers literature, explores public dataset metadata, saves research work, submits a purpose-specific access request and reproduces approved aggregate outputs. A researcher cannot approve their own request or bypass policy controls.

### Institutional steward / data-access committee member
Reviews research purpose, scope, conflicts of interest, applicable consent/data-use terms and risk evidence. Records an attributable decision and rationale. Steward permissions are institution-scoped.

### Data custodian
Registers datasets, source terms, artifact provenance, reference assemblies, consent evidence and release constraints. Controls ingestion and the operational release process.

### Security/privacy administrator
Manages identity integration, organization membership, role assignment, retention controls, key custody, monitoring and incident response. Administrative access does not silently grant research access.

### Public visitor
Can explore public literature and public source catalogues. Cannot see private cohort membership, donor identifiers, restricted records, governance deliberations or steward-only risk information.

## 4. Core user journeys

### 4.1 Public literature discovery
1. Visitor or authenticated researcher selects a department or enters a biomedical research question.
2. GenomeGuard validates and bounds the query, then searches configured public literature providers.
3. Results show provider-supplied titles, authors, journal/date metadata, identifiers, abstracts when available and original-source links.
4. Users can refine, paginate and save searches subject to retention policy.
5. The interface clearly states that search relevance is not evidence quality, clinical applicability or treatment advice.

### 4.2 Research project workflow
1. Researcher creates a project and records a research question, department and intended purpose.
2. Researcher saves publications, notes and reproducible query parameters.
3. The workspace links evidence records to source identifiers and retrieval dates.
4. Exports include references and provenance; they do not imply authorization to access underlying genomic records.

### 4.3 Dataset discovery
1. Researcher opens the dataset catalogue.
2. Each dataset profile shows source, release, artifact checksum, assembly, measured sample/variant/call counts, reuse statement, license/data-use review, consent basis, import status and limitations.
3. Only reconciled and explicitly approved public catalogue entries are discoverable.
4. A catalogue listing is not an access grant and is not participant-specific consent.

### 4.4 Controlled research request
1. Authenticated researcher selects a dataset, states a purpose and submits a scoped request.
2. Server validates identity, organization membership, purpose and request schema.
3. Policy engine evaluates applicable consent/data-use terms, purpose, requested data level, risk and abuse signals.
4. Request is held, denied or routed to the institutional steward; a policy pass alone does not release data.
5. Steward reviews the evidence, declares conflicts and records an attributable decision.
6. A separate release operation rechecks identity, decision validity, consent/withdrawal state, scope and release safeguards.
7. Only the permitted transformed output is returned and the operation is written to the audit history.

### 4.5 Consent withdrawal
1. Authorized consent authority records a verifiable superseding withdrawal event.
2. GenomeGuard preserves the prior event and appends the new event.
3. Future authorization and release checks observe the effective withdrawal state.
4. Relevant queued requests, cached permissions and derived artifacts are invalidated or quarantined according to documented policy.
5. The system records propagation status and exceptions for steward review.

## 5. Research discovery experience

### Initial departments
- Genetics & Genomics
- Oncology
- Neurology
- Cardiology
- Immunology
- Rare Diseases
- Bioinformatics
- Pharmacogenomics

Department pages are curated entry points, not claims that GenomeGuard has complete coverage of each specialty.

### Search capabilities
- Natural-language research question or symptom/topic description (for literature retrieval only).
- Department scoping and Boolean grouping.
- Provider-specific pagination and error handling.
- Source filters, publication dates, article type, journal and open-access metadata as provider support is implemented.
- Identifier resolution for DOI, PMID, PMCID, gene, protein, disease, phenotype and variant.
- Saved searches and research workspaces only after retention, access and deletion behavior are implemented and tested.

### Result display requirements
- Preserve source title and identifiers.
- Link directly to the publisher, PubMed or Europe PMC record using HTTPS.
- Distinguish unavailable metadata from zero values.
- Do not invent abstracts, sample sizes, study types, conclusions, citations or relevance explanations.
- Display provider and retrieval context.
- Label summaries as generated interpretations and attach evidence references to every material claim.

## 6. Dataset and evidence model

Every scientific object should have a stable identifier and provenance record.

- Publication: DOI, PMID, PMCID, provider ID, title, source, publication date and retrieval timestamp.
- Gene/protein: authoritative namespace and accession, organism, reference release and mapping evidence.
- Disease/phenotype: ontology identifier, ontology release and synonym mapping.
- Variant: genome assembly, normalized representation, reference/alternate alleles and source evidence.
- Dataset: persistent ID, source/release, license/data-use statement, consent basis, assembly, artifact checksum, measured counts, import software/version and review status.
- Derived evidence: input source identifiers, transformation method/version, parameters and limitations.

Evidence graph edges must be typed and traceable (for example: publication-reports-association, dataset-contains-variant, gene-associated-with-disease). A graph edge is not proof of causality or clinical validity.

## 7. Governance and authorization model

- Identity must be authenticated through an institution-controlled identity provider for controlled access.
- Organization membership and role must be verified server-side on every protected operation.
- Research purpose is part of the authorization decision and cannot be broadened after approval without a new review.
- Dataset terms and participant consent are separate evidence types and must never be conflated.
- Approval and release are separate operations.
- Consent events are append-only and verifiable; withdrawal takes effect according to source authority and policy.
- Family/relative risks are considered where relevant; a person's authorization does not automatically authorize disclosure about relatives.
- Private/controlled-access data remains disabled until institutional governance, privacy, identity, infrastructure and security release gates pass.

## 8. Security and privacy boundaries

- Use TLS for all external traffic and managed encryption at rest.
- Keep secrets, database URLs and identity credentials server-side.
- Separate runtime and migration database principals; runtime must not own tables, bypass RLS, mutate audit history or alter migration state.
- Enforce tenant scoping in the database and application layer.
- Log security-relevant decisions without logging raw genotypes or unnecessary personal information.
- Rate-limit expensive searches and governance operations; monitor query abuse and suspicious access.
- Document retention, deletion, backup, restore, incident response and key rotation.
- A heuristic disclosure-risk score is not a formal privacy guarantee.
- Differential privacy may be claimed only after its formal model, implementation, accountant, composition, tests and independent review are documented.

## 9. Scientific integrity and AI boundaries

- Public APIs and datasets are authoritative only for their stated scope, release and license.
- Clinical variant interpretations must preserve submitter-level classifications, review status and conflicts.
- Literature ranking is a retrieval aid, not a measure of evidence certainty.
- AI summaries must be grounded in retrieved source text and expose supporting citations and uncertainty.
- Models must not receive raw genotypes or direct identifiers unless a separately reviewed architecture and authorization explicitly permit it.
- Deterministic advisory agents must not be described as validated biomedical AI.
- GenomeGuard does not diagnose, recommend treatment or replace qualified scientific/clinical judgment.

## 10. Architecture baseline

The existing Python/Starlette backend remains the governance authority. The browser frontend is a presentation and discovery client, not an authorization boundary. PostgreSQL is the target durable operational store, with separate migration and runtime roles, row-level tenant controls and append-only audit structures. Literature and knowledge integrations are external, source-attributed adapters. Genomic ingestion is a versioned pipeline with explicit provenance and validation.

SQLite remains suitable only for local tests and disposable demonstrations where persistence is not claimed. A production-like service must not silently fall back to SQLite on ephemeral storage.

## 11. Release gates

A release cannot be described as production-ready until all five gates are evidenced:

1. **Scientific:** real source-backed publications, identifiers, dataset provenance and reproducible results.
2. **Governance:** institutionally verified identity, purpose, applicable consent/data-use terms, steward decision and separate release authorization.
3. **Privacy:** threat model, privacy-impact assessment, adversarial testing and independently reviewed privacy claims.
4. **Engineering:** exact-commit CI, PostgreSQL integration, tenant isolation, security checks, browser/accessibility tests and recovery evidence.
5. **Production:** durable infrastructure, secret/key custody, backup/restore, monitoring, incident response, exact deployed SHA and independent acceptance.

## 12. Explicit non-goals

- Clinical diagnosis, treatment recommendation or clinical-grade variant interpretation.
- Replacing IRB/ethics committees, data access committees, legal counsel or institutional consent authorities.
- Treating public data availability as unrestricted reuse permission.
- Claiming formal differential privacy from a heuristic risk score or epsilon-like counter.
- Claiming Beacon/FHIR certification from schema validation alone.
- Exposing private or controlled-access genotypes in a public demonstration.
- Presenting synthetic data, fabricated records or simulated approvals as real.

## 13. Product acceptance checklist

- [ ] Each role has a documented, tested journey and least-privilege permissions.
- [ ] Every public scientific result has source metadata and a working original-source link.
- [ ] Search supports department entry points, symptom/question queries, pagination and graceful provider failures.
- [ ] Dataset profiles expose provenance, license/data-use scope, assembly, checksums and measured counts.
- [ ] Consent evidence is authoritative, versioned, purpose-bound and withdrawal-aware.
- [ ] Steward approval and data release are separate and independently audited.
- [ ] Tenant isolation, privacy controls and audit verification pass adversarial tests.
- [ ] Database and deployment recovery are reproducible.
- [ ] Accessibility and researcher/steward usability are independently reviewed.
- [ ] Production claims match the evidence actually obtained.
