# GenomeGuard privacy impact assessment (draft)

**Status:** Engineering assessment for institutional review; not a legal opinion or approval  
**Assessment scope:** Current repository architecture and public/synthetic research prototype  
**Last reviewed:** 13 November 2026

## 1. Purpose and decision

GenomeGuard is intended to support biomedical literature discovery, genomic dataset provenance, research-access governance and controlled release of permitted aggregate outputs.

This assessment identifies privacy risks and proposed controls. It does **not** establish a lawful basis, institutional approval, ethics approval, consent validity, HIPAA/GDPR/DPDP compliance, or permission to process a particular cohort. The institution acting as data controller/custodian must complete and sign off the assessment for its own datasets, jurisdictions, purposes and identity provider.

**Current deployment boundary:** Public literature discovery and explicitly labelled synthetic demonstration data may be used for evaluation. Publicly released reference-genotype datasets require source-specific terms and provenance review. Private/controlled-access participant data must remain disabled until all institutional governance, identity, privacy, security, infrastructure and release gates pass.

## 2. Data subjects and stakeholders

- Participants/donors represented in a genomic dataset.
- Biological relatives who may be indirectly implicated by shared genetic information.
- Researchers and institutional staff using the platform.
- Data custodians, stewards, security administrators and service operators.
- Public literature authors and publishers whose metadata is indexed by external providers.

The institution must determine controller/processor roles, joint-controller relationships, data-subject rights responsibilities and processor/subprocessor contracts before production use.

## 3. Data inventory and sensitivity

| Data category | Examples | Classification | Purpose | Current boundary |
|---|---|---|---|---|
| Public scientific metadata | PMID, DOI, title, authors, journal, abstracts where provider permits | Public | Literature discovery | Retrieved from public providers with source links |
| Research queries | Disease/topic/symptom/gene query text | Confidential by default | Literature retrieval | Do not enter names, MRNs or private genotype details; avoid persistence |
| Researcher identity | OIDC subject, organization, role, requester ID | Confidential | Authentication and authorization | Institutional provider and organization binding must be configured and verified |
| Consent evidence | Consent event, scope, source, version, effective date, withdrawal | Restricted | Purpose-bound governance | Demo consent is simulated and must never be represented as real |
| Genomic records | VCF, variants, genotype calls, sample mappings | Restricted | Approved research only | No private/controlled-access cohort use until release gates pass |
| Derived outputs | Aggregate counts, risk scores, transformed values | Restricted or confidential based on disclosure risk | Permitted research result | Aggregation does not automatically make data anonymous |
| Family/relative links | Pedigree edges, inferred exposure, relatedness | Restricted | Relative-aware risk assessment | Must minimize, justify and review each use |
| Audit/security metadata | Actor, organization, action, timestamp, policy version, decision evidence | Confidential/restricted | Accountability and incident investigation | Do not log raw genotype or unnecessary identifiers |
| Secrets and keys | Database URLs, API keys, master keys, signing keys | Restricted | Service operation | Secret manager only; never repository, browser or logs |

## 4. Data-flow summary

1. A user enters a literature query in the browser. Public provider requests may be sent to Europe PMC or NCBI PubMed. Query text is not a GenomeGuard research record; the PubMed endpoint uses POST, no-store responses and avoids putting query text in the HTTP request line. Users must not submit patient-identifying information.
2. A researcher authenticates through an institution-controlled OIDC provider. GenomeGuard validates token claims and separately checks an operator-provisioned organization/role binding. A valid token alone is not sufficient authorization.
3. A researcher submits a purpose-specific access request. The server checks identity, organization, dataset policy, applicable consent evidence, request scope and risk signals.
4. A steward reviews the request and records an attributable decision. Approval and data release are separate operations.
5. A release operation rechecks the effective consent/withdrawal state, decision validity, purpose, policy, cohort eligibility and output controls.
6. The permitted output and governance evidence are written to the database and audit history. Backups and operational logs may contain sensitive governance metadata and must receive equivalent protection.

The institution must validate this data-flow map against its actual deployment, network, identity provider, logs, backups, external services and operational support arrangements.

## 5. Necessity and proportionality questions

Before enabling a dataset, the institution must document:

- The specific research purpose and why genomic data is necessary.
- Whether a less identifying or aggregate dataset would satisfy the purpose.
- Which fields, variants, cohorts and output granularity are strictly necessary.
- Whether family/relative-level analysis is necessary and authorized.
- The applicable consent, data-use agreement, ethics approval, legal basis and jurisdiction.
- Whether external literature APIs, hosting, observability and backup providers receive any user or dataset information.
- Retention periods for raw data, derived outputs, identity bindings, consent evidence and audit records.
- How data-subject requests, consent withdrawal and downstream copies are handled.

No generic product setting can answer these institution-specific questions.

## 6. Principal privacy threats

| Threat | Potential impact | Current/proposed controls | Residual risk / required evidence |
|---|---|---|---|
| Re-identification from rare variants or aggregate outputs | Participant and relative identification | k-minimum thresholds, rare-variant suppression, risk checks, query monitoring | Heuristic controls are not an anonymity guarantee; independent attack evaluation required |
| Membership inference and differencing | Inferring cohort membership or attributes | Noise, query controls, budgets and anomaly monitoring | Formal DP is not established; adversarial evaluation and independent privacy review required |
| Cross-tenant access | Unauthorized disclosure between institutions | Server-side organization checks, PostgreSQL RLS and adversarial tests | Must prove against exact production schema, roles, endpoints and identity mappings |
| Consent mismatch or withdrawal race | Processing beyond permitted scope | Versioned consent events, purpose-bound checks, separate release | Need authoritative consent evidence and end-to-end propagation acceptance |
| Insider or compromised steward | Unauthorized approval or data release | Least privilege, conflict declarations, separate release, audit | Independent access review, dual control and institutional governance needed |
| Database/backup compromise | Exposure of genotypes and identity mappings | Encryption at rest, TLS, managed keys, separate roles | Production KMS/HSM, key rotation, restore drills and independent security assessment needed |
| Log/query leakage | Sensitive query or identity exposure | POST for PubMed, no-store, minimize logs, avoid raw genotypes | Review all proxy, application, provider, analytics and observability logs |
| Family inference | Impacts relatives who did not consent | Relative-aware risk model and steward visibility | Model is not a validated family privacy guarantee; expert review required |
| AI/provider misuse | Misleading scientific summary or unauthorized data transfer | Source provenance, no raw genotypes to LLM, deterministic authorization | Validate every integration, prompt boundary and model data-handling contract |

## 7. Existing safeguards and limitations

- OIDC token validation and organization bindings exist in code, but live institutional identity, membership lifecycle, MFA and account recovery require institution-specific acceptance.
- PostgreSQL row-level controls and integration tests exist, but the production service is not yet connected to durable production PostgreSQL.
- AES-GCM encryption and key separation exist in code; production key custody must move to an institution-approved KMS/HSM with rotation and recovery.
- The local hash chain detects modification relative to its current chain but is not independently immutable. A separately controlled signed anchor is required.
- The current epsilon-like ledger and noise configuration are prototype controls, not a formal differential-privacy guarantee.
- Synthetic FHIR Consent validation does not prove participant consent or interoperability with an institution's real consent system.
- Beacon schema validation does not prove full Beacon conformance or privacy safety.
- A successful CI run is not an independent security, scientific, legal or institutional review.

## 8. Required mitigations before controlled-data release

1. Institution-approved lawful basis, ethics review, data-use agreements and consent authority.
2. Dataset-specific provenance, license/data-use terms, reference assembly and checksum reconciliation.
3. Verified OIDC/SSO, MFA, organization membership, steward lifecycle and revocation.
4. Durable PostgreSQL with separated least-privilege runtime/migration/backup roles and tested RLS.
5. Managed encryption keys, rotation, recovery and access audit.
6. Independently controlled signed audit checkpoints.
7. Adversarial re-identification, membership, differencing, linkage and family exposure testing.
8. Formal privacy model and qualified independent review before any DP claim.
9. Encrypted backups, point-in-time recovery where supported and isolated restore acceptance.
10. Security assessment, incident response exercise, monitoring, alerting and vulnerability disclosure process.
11. Accessibility, researcher/steward usability and operational acceptance.
12. Signed release approval by the institution's authorized representatives.

## 9. Open decisions and sign-off

The following are deliberately **not** filled in by the software team:

- Controller/custodian and processor roles.
- Lawful basis and jurisdiction-specific obligations.
- Dataset-specific consent and permitted purposes.
- Ethics/IRB approval and participant communication.
- Retention and deletion periods.
- Cross-border transfers and subprocessors.
- Contact for privacy requests and incidents.
- Independent privacy/security reviewers.
- Residual-risk acceptance authority.

| Reviewer | Name/role | Decision | Date | Evidence/reference |
|---|---|---|---|---|
| Data controller / institution | Pending | Pending | Pending | Pending |
| Data custodian | Pending | Pending | Pending | Pending |
| Ethics / IRB representative | Pending | Pending | Pending | Pending |
| Privacy officer / DPO | Pending | Pending | Pending | Pending |
| Security reviewer | Pending | Pending | Pending | Pending |
| Genomics/scientific reviewer | Pending | Pending | Pending | Pending |

**Do not enable private or controlled-access genomic data based solely on this draft.**
