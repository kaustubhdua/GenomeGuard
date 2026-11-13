# GenomeGuard

[![CI](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/ci.yml/badge.svg)](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/ci.yml)
[![Security verification](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/security.yml/badge.svg)](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/security.yml)
[![Live acceptance](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/live-acceptance.yml/badge.svg)](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/live-acceptance.yml)
[![License: All rights reserved](https://img.shields.io/badge/License-All%20rights%20reserved-red.svg)](LICENSE)

**Legacy live research API:** https://genomeguard.onrender.com — its public health response reports a 1000 Genomes source, 600 donors, and 3,000 variants, but this provenance is operator-declared and has not been independently authenticated. The same response has an unresolved `consent_records_matched=600` discrepancy despite describing dataset-level policy, not participant-specific consent. The current production frontend is behind GitHub mainline. Do not treat these values as verified participant-consent or dataset evidence.

GenomeGuard is a research prototype for governing access to genomic datasets. It evaluates research requests against consent-inspired policy rules, estimates disclosure risk, applies output transformations, monitors suspicious query patterns, and records decisions in a tamper-evident audit chain. Offline advisory agents use deterministic templates and a bounded rules planner to explain evidence for reviewers; no hosted AI provider or API key is used, and deterministic application code remains responsible for access decisions.

> **Research software — not for clinical or production use.** The hosted research instance uses public 1000 Genomes genotype data and a dataset-level public-release policy mapping; local demo mode still uses synthetic data. The policy mapping is not participant-specific consent, and requester API keys are not verified institutional identities. The service has not undergone independent security, privacy, clinical, or legal review. It must not be used for private participant data or clinical decisions.

## What it does

- **Request governance:** evaluates a request against purpose and consent-like policy rules and returns a reasoned decision.
- **Disclosure-risk assessment:** estimates risks from rare variants, uniqueness, membership signals, and potential exposure of relatives.
- **Output protection:** applies configured transformations to reduce disclosure risk and records the associated privacy-budget estimate.
- **Query-abuse monitoring:** detects selected probing and differencing patterns and can flag or freeze demo accounts.
- **Human review support:** provides a read-only steward copilot that gathers approved summaries and recommends next steps. It cannot grant access or change a decision.
- **Auditability:** records decisions and events in a hash-chained audit log with verification tooling.
- **Interoperability experiments:** includes a Beacon v2-style endpoint and export of synthetic FHIR R4 Consent resources for validation.
- **Research evaluation:** includes repeatable synthetic-data evaluations and optional workflows for public 1000 Genomes genotype data.
- **Research discovery:** searches live Europe PMC and NCBI PubMed publication records by department or research question, deduplicates source records, and exposes Open Targets direct gene–disease associations with source-level evidence, release provenance, and reproducible exports. These are research-discovery tools, not clinical decision support.

## Current scope

| Area | Current implementation | Important boundary |
| --- | --- | --- |
| Consent and requester identity | Public-release dataset policy mapping in hosted research mode; synthetic personas only in local demo mode | No participant-specific consent records in the public dataset, and no institutional identity provider |
| Genotype data | Hosted cohort built from public 1000 Genomes chromosome 22 VCF; synthetic default for local demo mode | Public genotypes are not private clinical data; source-level terms are not individual consent or legal authorization |
| Privacy protections | Risk heuristics, transformations, and a simplified privacy-budget ledger | Not a formally audited differential-privacy implementation |
| Cryptography | Encryption helpers and an educational Paillier aggregation path | Not independently audited and not a production cryptographic service |
| Federated analysis | Demonstration workflow | Not a hardened multi-organization deployment |
| Interoperability | Core Beacon-style response checks and synthetic FHIR R4 validation | Not full Beacon conformance or proof of legally valid consent |
| Research discovery | Europe PMC + PubMed publication retrieval and Open Targets target–disease evidence with provenance-aware exports | Provider retrieval order and Open Targets scores are not evidence-quality rankings, clinical validity, diagnosis, causality, or treatment advice. |
| Hosting and persistence | The first-party Python/Starlette API serves the frontend and all application routes; SQLite supports local development and PostgreSQL supports durable deployments | The current Render workspace has no managed PostgreSQL instance. Production still requires a dedicated durable database, backups, key custody, identity governance, and live acceptance. |

These boundaries are intentional and should remain visible in the interface and any exported results. See the [current hosted deployment and release blockers](docs/production-deployment.md), [literature discovery behavior](docs/research-discovery.md), and [Open Targets integration and evidence limitations](docs/open-targets-integration.md). The dated November 10 status and release-readiness records are historical snapshots, not the current deployment state.

## Backend and identity

GenomeGuard does not require Supabase, a hosted authentication provider, a browser publishable key, or a third-party Edge Function. The browser calls the same-origin Python API. Local development runs entirely on the machine; hosted deployments use the configured GenomeGuard API and a PostgreSQL database.

GenomeGuard supports two deliberately separate authentication modes:

- **Local/demo or compatibility mode:** researchers use individually provisioned `X-API-Key` credentials; the steward compatibility path uses `X-Admin-Key`; donor-facing demo workflows use a separate `X-Donor-Key`. Demo personas and credentials are available only when explicit demo mode is enabled.
- **Institutional mode:** set `GG_OIDC_REQUIRED=true` and `GG_TENANT_ISOLATION_REQUIRED=true`. The browser uses Authorization Code + PKCE S256; the API independently verifies the signed access-token JWT, issuer, audience, time claims, and allow-listed organization claim, then resolves an explicitly provisioned active issuer/subject/organization binding. Researcher, reviewer, steward, and global-administrator operations remain separated.

API keys are not institutional identity verification. A named requester record is not proof of affiliation, participant consent, or legal authorization. Institutional OIDC configuration and organization membership must be supplied and operated by the institution before controlled-data workflows are enabled.

The old Supabase migrations and Edge Function implementation are retained as historical migration artifacts only; they are not part of the runtime, build, or deployment path. Do not apply them as part of a new installation.

The public demo-account endpoints return synthetic requester and donor persona metadata only. They never return static requester, donor or administrator credentials. The browser obtains short-lived, process-local demo sessions that expire after 30 minutes; these are for the single-process synthetic demo only and are not an institutional identity system.

## Get started

Requirements: Python 3.11 or newer and the make utility.

```bash
git clone https://github.com/kaustubhdua/GenomeGuard.git
cd GenomeGuard
make setup
make seed
make run
```

Open http://127.0.0.1:8000 in your browser.

The default seed is for local demonstration only. Keep synthetic data enabled and do not import real participant records.

## Development checks

Run the main checks from the repository root:

```bash
make test
make lint
make eval-smoke
make demo
```

The CI workflows also exercise API behavior, evaluation scenarios, browser routes, responsive layouts, accessibility checks, and selected interoperability/security validations. Results belong to the exact commit and workflow that produced them; a passing CI run does not establish that a hosted deployment is working.

For optional public-genotype research evaluation, see [Real-data evaluation](docs/real-data.md). Review the data source, cohort build settings, and provenance before running it.

For the current hosted API, Render deployment, persistence, and release blockers, see the [hosted deployment record](docs/production-deployment.md). Older live-readiness and production-readiness audits are historical evidence and may describe superseded commits.

For the dataset source review, provenance ledger, and safe import acceptance criteria, see [Genomic dataset provenance and import gate](docs/genomic-dataset-provenance-import-gate.md).

For the normalized VCF importer, provenance checks, local QC CLI, steward-only temporary VCF upload, and report privacy boundaries, see [Real VCF import pipeline](docs/real-vcf-import.md). Local JSON preview does not upload the report; the VCF upload sends genomic bytes to the configured GenomeGuard server and must only be used with a trusted deployment. Neither QC path approves imports. For server-verified organization membership, human review, and consent-ledger limitations, see [Organization authorization and review](docs/organization-authorization-and-review.md).

For the curated public-source discovery index and its release-specific reuse-review boundaries, see [Public genomic source discovery](docs/public-genomic-source-discovery.md). Listing a source does not approve reuse, import data, or establish participant-specific consent.

## Architecture

The service applies a deterministic request pipeline: request validation, policy checks, risk assessment, output transformation, anomaly monitoring, decision handling, and audit recording. Advisory agents receive sanitized summaries rather than raw genotypes and do not have authority to approve, deny, freeze, or release data.

- [Research discovery and literature-search boundaries](docs/research-discovery.md)
- [Open Targets gene–disease evidence integration](docs/open-targets-integration.md)
- [Architecture](docs/architecture.md)
- [API reference](docs/api.md)
- [Configuration](docs/configuration.md)
- [Consent policy](docs/consent-policy.md)
- [Threat model](docs/threat-model.md)
- [Verification and test coverage](docs/verification.md)
- [Evaluation results](docs/eval-results.md)
- [Scalability notes](docs/scalability.md)
- [Application walkthrough](docs/walkthrough.md)
- [Three-minute demo script](docs/demo-script.md)
- [Real-data evaluation and provenance](docs/real-data.md)
- [Real cohort ingestion and consent requirements](docs/real-cohort-consent.md)
- [Hosted deployment and operational limitations](docs/production-deployment.md)
- [PostgreSQL operations, backups, and recovery](docs/postgresql-operations.md)
- [Release readiness and database validation evidence](docs/release-readiness-2026-11-10.md)
- [Five-minute hackathon demo and submission guide](docs/hackathon-demo-guide.md)
- [Evidence-based completion audit (26 October 2026)](docs/completion-audit-2026-10-26.md)
- [Production assurance implementation status](docs/production-assurance-implementation-2026-10-26.md)
- [OWASP ASVS verification register](docs/asvs-verification.md)
- [Incident response and recovery runbooks](docs/incident-response.md)
- [Supabase-free deployment](docs/supabase-free-deployment.md)

## Security and privacy

Please read [SECURITY.md](SECURITY.md) and the [threat model](docs/threat-model.md) before experimenting. Do not submit secrets, personal information, participant identifiers, or private genomic data through public issues. Report suspected vulnerabilities privately using the process described in SECURITY.md.

## Contributing

Bug reports, focused improvements, tests, and documentation corrections are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Changes should preserve provenance labels, avoid overstating privacy or interoperability guarantees, and include tests for changed behavior.

## License

Copyright (c) 2026 Kaustubh Dua. All rights reserved. The source is visible for evaluation only; copying, redistribution, derivative works and commercial use need written permission. See [LICENSE](LICENSE).
