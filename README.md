# GenomeGuard

[![CI](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/ci.yml/badge.svg)](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/ci.yml)
[![Security verification](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/security.yml/badge.svg)](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/security.yml)
[![Live acceptance](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/live-acceptance.yml/badge.svg)](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/live-acceptance.yml)
[![License: All rights reserved](https://img.shields.io/badge/License-All%20rights%20reserved-red.svg)](LICENSE)

**Repository status snapshot (14 November 2026):** GitHub `main` is `fa75e1a64ef4d6affe726ca2e0e97735fdf46a93` (PR #173 merged). Draft PR [#174](https://github.com/kaustubhdua/GenomeGuard/pull/174) adds regression coverage and hardens browser security headers on unhandled 500 responses; it is not merged. The exact-main backend, security, Beacon-schema, deployment-config, FHIR and live-acceptance workflows were observed queued with no completed result. A queued check is not a pass.

**Deployment evidence (read-only audit, 14 November 2026):** the production Vercel deployment metadata records the current `main` SHA, but `frontend/vercel.json` rewrites application requests to Render. The public Vercel URL therefore serves the primary Render service's older live commit `3280ebc1924039bcfa19f4c58bb75e83a8c370eb`, not the Vercel deployment's recorded source SHA. The recovery demo is live on Free at `f200b643f05a5f959887ac51accd7e202c424557`. Three staging services also exist; see [the deployment audit](docs/production-deployment.md) for service IDs, branches and deployed SHAs. The Render workspace's managed PostgreSQL inventory is empty; this does not rule out an external PostgreSQL provider. No secret values were inspected.

**Release verification at audit time:** exact-main CI/security/Beacon/deployment checks for `1774f5a` and PR #167 checks were queued; no green result was claimed. Consult GitHub Actions for the current exact-SHA results. The public service's `/health/ready` returns HTTP 503 while institutional production gates are unverified. Keep readiness fail-closed; configure host liveness against `/health/live`, never `/health/ready`. Investigate the stale Render deployment and auto-deploy mismatch before promoting any unvalidated commit.

**Database and research boundary:** the prior Neon audit recorded demo/staging branches and a 600-donor synthetic staging fixture, but the exact Render-to-Neon connection mapping remains unverified. Do not infer it from project names. The public app remains synthetic-only. Private/controlled participant data, clinical use and production readiness remain blocked pending verified institutional identity, consent authority, tenant isolation, durable storage/backup/restore, monitoring, external audit anchoring and independent review.

GenomeGuard is a research prototype for governing access to genomic datasets. It evaluates research requests against consent-inspired policy rules, estimates disclosure risk, applies output transformations, monitors suspicious query patterns, and records decisions in a tamper-evident audit chain. Offline advisory agents use deterministic templates and a bounded rules planner to explain evidence for reviewers; no hosted AI provider or API key is used, and deterministic application code remains responsible for access decisions.

> **Research prototype — not for clinical or production use.** The currently hosted public service is a synthetic-only demonstration. The separate real-public-genotype research image is defined in the repository but is not yet deployed as a separately accepted research service. Any public-release policy mapping is not participant-specific consent, and requester API keys are not verified institutional identities. The service has not undergone independent security, privacy, clinical, or legal review. It must not be used for private participant data or clinical decisions.

## What it does

- **Request governance:** evaluates a request against purpose and consent-like policy rules and returns a reasoned decision.
- **Disclosure-risk assessment:** estimates risks from rare variants, uniqueness, membership signals, and potential exposure of relatives.
- **Output protection:** applies configured transformations to reduce disclosure risk and records the associated privacy-budget estimate.
- **Query-abuse monitoring:** detects selected probing and differencing patterns and can flag or freeze demo accounts.
- **Human review support:** provides a read-only steward copilot that gathers approved summaries and recommends next steps. It cannot grant access or change a decision.
- **Auditability:** records decisions and events in a hash-chained audit log with verification tooling.
- **Interoperability experiments:** includes a Beacon v2-style endpoint and export of synthetic FHIR R4 Consent resources for validation.
- **Research evaluation:** includes repeatable synthetic-data evaluations and optional workflows for public 1000 Genomes genotype data.
- **Research discovery:** searches live Europe PMC and NCBI PubMed publications, exposes Open Targets gene–disease evidence, retrieves ClinVar variant-level classifications, explores GWAS Catalog v2 associations, and searches MONDO, HPO, and Disease Ontology terms through EMBL-EBI OLS4 with user-controlled label/synonym query expansion. Source provenance and research exports are retained; these are research-discovery tools, not clinical decision support.

## Current scope

| Area | Current implementation | Important boundary |
| --- | --- | --- |
| Consent and requester identity | Public-release dataset policy mapping in hosted research mode; synthetic personas only in local demo mode | No participant-specific consent records in the public dataset, and no institutional identity provider |
| Genotype data | Public hosted deployment is configured as a synthetic-only demo; a separate public-cohort research image is defined but is not an accepted institutional service | Public dataset terms are not participant-specific consent or legal authorization |
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
