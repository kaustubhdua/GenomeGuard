# GenomeGuard

[![CI](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/ci.yml/badge.svg)](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/ci.yml)
[![Security verification](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/security.yml/badge.svg)](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/security.yml)
[![Live acceptance](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/live-acceptance.yml/badge.svg)](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/live-acceptance.yml)
[![License: All rights reserved](https://img.shields.io/badge/License-All%20rights%20reserved-red.svg)](LICENSE)

**Legacy live research API:** https://genomeguard.onrender.com — its public health response reports a 1000 Genomes source, 600 donors, and 3,000 variants, but this provenance is operator-declared and has not been independently authenticated. The same response has an unresolved `consent_records_matched=600` discrepancy despite describing dataset-level policy, not participant-specific consent. The current production frontend is behind GitHub mainline. Do not treat these values as verified participant-consent or dataset evidence.

GenomeGuard is a research prototype for governing access to genomic datasets. It evaluates research requests against consent-inspired policy rules, estimates disclosure risk, applies output transformations, monitors suspicious query patterns, and records decisions in a tamper-evident audit chain. Advisory AI components explain evidence for reviewers; deterministic application code remains responsible for access decisions.

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

## Current scope

| Area | Current implementation | Important boundary |
| --- | --- | --- |
| Consent and requester identity | Public-release dataset policy mapping in hosted research mode; synthetic personas only in local demo mode | No participant-specific consent records in the public dataset, and no institutional identity provider |
| Genotype data | Hosted cohort built from public 1000 Genomes chromosome 22 VCF; synthetic default for local demo mode | Public genotypes are not private clinical data; source-level terms are not individual consent or legal authorization |
| Privacy protections | Risk heuristics, transformations, and a simplified privacy-budget ledger | Not a formally audited differential-privacy implementation |
| Cryptography | Encryption helpers and an educational Paillier aggregation path | Not independently audited and not a production cryptographic service |
| Federated analysis | Demonstration workflow | Not a hardened multi-organization deployment |
| Interoperability | Core Beacon-style response checks and synthetic FHIR R4 validation | Not full Beacon conformance or proof of legally valid consent |
| Hosting and persistence | The first-party Python/Starlette API serves the frontend and all application routes; SQLite supports local development and PostgreSQL supports durable deployments | No managed backend or hosted authentication service is required. Production still requires operator-managed PostgreSQL, persistent storage, backups, and identity governance. |

These boundaries are intentional and should remain visible in the interface and any exported results.

## Backend and identity

GenomeGuard does not require Supabase, a hosted authentication provider, a browser publishable key, or a third-party Edge Function. The browser calls the same-origin Python API. Local development runs entirely on the machine; hosted deployments use the configured GenomeGuard API and a PostgreSQL database.

The current application authentication contract is first-party API-key authentication:
- researchers use individually provisioned `X-API-Key` credentials;
- stewards use the `X-Admin-Key` credential;
- donor-facing demo workflows use a separate `X-Donor-Key`;
- demo personas and demo credentials are available only when explicit demo mode is enabled.

API keys are not institutional identity verification. Do not treat a named requester record as proof of affiliation, participant consent, or legal authorization. For institutional deployments, place the API behind an independently operated OIDC identity provider and enforce organization membership server-side before enabling controlled-data workflows.

The old Supabase migrations and Edge Function implementation are retained as historical migration artifacts only; they are not part of the runtime, build, or deployment path. Do not apply them as part of a new installation.

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

For the latest read-only check of the hosted API and deployment drift, see the [live-readiness audit (2 November 2026)](docs/live-readiness-audit-2026-11-02.md). For evidence-based hosting, persistence, and release blockers, see the [production-readiness audit (29 October 2026)](docs/production-readiness-audit-2026-10-29.md).

For the dataset source review, provenance ledger, and safe import acceptance criteria, see [Genomic dataset provenance and import gate](docs/genomic-dataset-provenance-import-gate.md).

For the normalized VCF importer, provenance checks, local QC CLI, steward-only temporary VCF upload, and report privacy boundaries, see [Real VCF import pipeline](docs/real-vcf-import.md). Local JSON preview does not upload the report; the VCF upload sends genomic bytes to the configured GenomeGuard server and must only be used with a trusted deployment. Neither QC path approves imports. For server-verified organization membership, human review, and consent-ledger limitations, see [Organization authorization and review](docs/organization-authorization-and-review.md).

For the curated public-source discovery index and its release-specific reuse-review boundaries, see [Public genomic source discovery](docs/public-genomic-source-discovery.md). Listing a source does not approve reuse, import data, or establish participant-specific consent.

## Architecture

The service applies a deterministic request pipeline: request validation, policy checks, risk assessment, output transformation, anomaly monitoring, decision handling, and audit recording. Advisory agents receive sanitized summaries rather than raw genotypes and do not have authority to approve, deny, freeze, or release data.

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
