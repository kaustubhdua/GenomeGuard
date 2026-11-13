# GenomeGuard data classification and handling standard

**Status:** Engineering baseline; institution must approve and adapt before production use.  
**Scope:** Application data, genomic artifacts, identity, audit records, logs, backups and secrets.

## 1. Classification levels

| Level | Definition | Examples |
|---|---|---|
| Public | Approved for unrestricted public access and redistribution under source terms | Public literature metadata, public documentation, approved source links |
| Internal | Operational information not intended for public release but not inherently participant-sensitive | Internal runbooks, non-sensitive deployment metadata, test reports without secrets |
| Confidential | Information whose disclosure may harm users, institutions or research confidentiality | Research queries, researcher identity, organization membership, non-public project notes, security events |
| Restricted | Highly sensitive information requiring explicit purpose, authorization, encryption and audited access | Raw genotypes/VCFs, participant identifiers, consent evidence, family links, private cohort membership, secrets, encryption keys, database credentials |

When in doubt, classify upward. A public source does not make a locally combined or enriched record public.

## 2. Handling rules

### Public
- Preserve source license, attribution, version and retrieval date.
- Do not imply that public availability grants every downstream use.
- Do not remove source identifiers or provenance.

### Internal
- Store only in approved organization-controlled repositories and services.
- Limit access to staff with an operational need.
- Review before external publication.

### Confidential
- Restrict to authorized users and services.
- Avoid putting values in URLs, analytics, browser storage or ordinary access logs.
- Apply no-store where appropriate and define retention/deletion.
- Do not send confidential research queries to external providers if they contain patient identifiers or private cohort details.

### Restricted
- Require explicit authorization, purpose limitation and audited access.
- Encrypt in transit and at rest with institution-managed keys.
- Keep raw genotypes and consent evidence out of browser local storage, client telemetry and public logs.
- Use least-privilege database roles and row-level organization isolation.
- Do not place secrets in source control, issues, pull requests, screenshots, CI artifacts or support tickets.
- Backups inherit the source classification and require encryption, access logging, retention and restore controls.
- No private/controlled-access data in demo mode, shared test environments or public staging.

## 3. Special handling for genomic and family data

- Genomic data can remain identifying even after names and direct identifiers are removed.
- Variant-level and rare-variant outputs may reveal participant membership and information about biological relatives.
- Treat pseudonymous IDs, genotype calls, family/pedigree relationships, consent events and re-identification-risk outputs as Restricted.
- Treat derived aggregates as Restricted until a documented disclosure review justifies a lower classification.
- Never use synthetic demo consent as evidence of real consent.
- Dataset-level public-release terms do not substitute for participant-specific consent.

## 4. Search and external-provider boundary

- Literature search queries are Confidential by default.
- User interfaces must warn users not to enter patient names, record numbers, contact details, raw genotypes or private cohort information.
- PubMed search uses POST, no-store responses and bounded provider concurrency to avoid request-line logging and uncontrolled upstream use.
- Europe PMC search currently sends the query to the public provider; users must submit topic-level research questions only.
- Provider terms, data-use policies and availability must be reviewed before institutional use.

## 5. Access and lifecycle

- Access must be granted by role and organization, not by UI visibility.
- Review privileged access periodically and revoke it on role change or departure.
- Rotate and revoke secrets after exposure or staff changes.
- Define institution-specific retention periods for each classification and data category.
- Deletion must include replicas, exports, caches and backup expiry where technically and legally applicable; retain only records required for an authorized audit/legal purpose.
- Log access and release decisions without copying raw genotype values into audit metadata.

## 6. Prohibited handling

- Committing genomic artifacts, consent records, credentials or private identifiers to Git.
- Using real participant data in public demos or unapproved third-party AI tools.
- Treating an aggregate or pseudonymous dataset as anonymous without an evidence-based assessment.
- Sending identifying patient information to public literature search APIs.
- Publishing unreviewed risk scores, epsilon-like budgets or synthetic validation as privacy certification.

## 7. Required institutional approval

Before production use, the institution must approve data owners, classification decisions, allowed storage/regions, access roles, retention periods, deletion process, external providers, backup policy, key custody and incident contacts. This document is an engineering baseline, not an institution's approved information-classification policy.
