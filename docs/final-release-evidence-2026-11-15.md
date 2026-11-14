# Final release evidence and remaining acceptance gates — 15 November 2026

## Executive result

The latest source commit is `77c2f9c9303ec1f3373c647810282f930a5b9cc4`.

- GitHub exact-commit check suite: **7/7 successful** (backend, deployment configuration, CodeQL Python, CodeQL JavaScript, secret scanning, Python dependency audit, and free public synthetic demo acceptance).
- Backend workflow completed successfully: lint, seed, unit/API tests, PostgreSQL integration and tenant-isolation tests, encrypted PostgreSQL backup/restore and audit verification exercise, evaluation, demo, Python compilation, JavaScript syntax, browser routes, responsive behavior, accessibility basics, guided tour, and screenshot artifact.
- Vercel production deployment: **READY**, commit `77c2f9c9303ec1f3373c647810282f930a5b9cc4`, deployment `dpl_BMjSJvtQAPzb8irCE5pRbNmDe7ha`.
- Primary Render service `srv-dbev1ka9lscs738813t0`: deployment `dep-dbsbjjm1egvs73dd22eg` is **LIVE** on the same commit after a manual deploy was required because the configured commit auto-deploy had not advanced the service.
- Render's provider health-check path remains empty. Configure it in the Render dashboard as `/health/live`; do not use `/health/ready`.
- The public deployment remains a **synthetic-only demonstration**. It is not authorized for private/controlled participant genomic data or clinical use.

## Deployment references

- Public application: https://genome-guard.vercel.app
- Primary API/service: https://genomeguard.onrender.com
- Render dashboard: https://dashboard.render.com/web/srv-dbev1ka9lscs738813t0
- Vercel deployment: https://vercel.com/jyc-website/genome-guard/BMjSJvtQAPzb8irCE5pRbNmDe7ha
- Exact GitHub checks: https://github.com/kaustubhdua/GenomeGuard/commit/77c2f9c9303ec1f3373c647810282f930a5b9cc4/checks
- Backend workflow: https://github.com/kaustubhdua/GenomeGuard/actions/runs/43632848236

## What the green CI proves

The backend job passed all of the following on the exact source SHA:

1. Dependency setup, lint and deterministic synthetic seed.
2. Unit and API tests.
3. Real PostgreSQL integration and tenant-isolation tests using CI PostgreSQL.
4. Encrypted PostgreSQL backup/restore and audit-chain verification against disposable CI databases.
5. Evaluation smoke and full evaluation.
6. Demo workflow.
7. JavaScript syntax and Python compilation.
8. Browser route, responsive layout, accessibility basics and guided-tour tests, with screenshots preserved as a workflow artifact.

The other exact-SHA checks passed secret scanning, CodeQL Python and JavaScript, dependency vulnerability audit, deployment configuration and free public synthetic-demo acceptance.

These are meaningful automated verification results. They do not prove institutional authorization, actual hosted backup retention, external audit anchoring, independent penetration testing, or real participant consent.

## Remaining release gates

### P0 — Finish public synthetic-demo operations

- [ ] In Render Dashboard → service Settings → Health Check Path, set `/health/live`. The connected Render integration used for this audit can inspect and deploy the service but does not expose an update-service-settings operation.
- [ ] Verify the provider now reports `healthCheckPath=/health/live`.
- [ ] Run a fresh post-deploy live smoke against the exact Render SHA, including health, demo requester/donor metadata, session creation, request preview/submission, request retrieval, privacy-ledger behavior and audit verification. CI's hosted acceptance check passed, but repeat after the manual Render deploy.
- [ ] Complete a human browser walkthrough of requester, donor and steward experiences on the production URL. The CI browser suite is automated acceptance, not a substitute for operator review of the deployed experience.
- [ ] Verify restart/redeploy persistence on the actual configured database. The exact Render-to-Neon branch/role mapping must be confirmed without exposing secrets.

### P1 — Research prototype integrity

- [ ] Implement and test a complete private per-organization cohort lifecycle. Existing PostgreSQL RLS/tenant integration tests do not establish that every in-memory dataset, cache, query, background job and export path is tenant-scoped.
- [ ] Connect an actual institutional OIDC provider, organization allow-list, role provisioning and MFA policy; verify issuer, audience, signature, key rotation, expiry and organization claims.
- [ ] Integrate an authoritative consent issuer and signing-key custody. Simulated consent and public dataset-level terms are not participant-specific consent.
- [ ] Require verified dataset accession, artifact checksum, source release, licence/terms review, DUO mapping and data-access-committee decision before any controlled import.
- [ ] Verify the withdrawal lifecycle end-to-end, including subsequent query denial, exports, caches, queued jobs and audit records.
- [ ] Validate FHIR R4 Consent and GA4GH Beacon v2 against conformance suites and representative authorized fixtures; do not claim certification based only on schema checks.

### P1 — Hosted recovery and operations

- [ ] Select an approved durable database and retention plan with an institutional owner and budget.
- [ ] Configure scheduled encrypted backups and independent backup-key custody.
- [ ] Perform and document an isolated restore of the actual hosted database; verify schema, row counts, consent/withdrawal state and audit chain.
- [ ] Define and test RPO/RTO, recovery ownership and rollback.
- [ ] Configure application-level monitoring, alert delivery, incident response and log/trace correlation.
- [ ] Anchor audit checkpoints in a separately controlled service with independent credentials and key custody.

The CI backup/restore exercise is against disposable CI PostgreSQL databases. The manual Neon branch created before the synthetic provenance repair is a point-in-time safety copy, not a recurring production backup policy or restore drill.

### P2 — Independent assurance and release governance

- [ ] Complete an OWASP ASVS-based security assessment and independent penetration test; remediate and retest findings.
- [ ] Complete independent privacy, scientific, legal and institutional review appropriate to the intended data and jurisdiction.
- [ ] Generate and retain an SBOM and verifiable build provenance; scan container images and deployment configuration.
- [ ] Configure GitHub `main` ruleset/branch protection with pull requests and required checks. The repository was previously reported as `protected=false`; the connected GitHub integration did not expose repository-settings write access.
- [ ] Confirm licence and third-party data/component terms before claiming open-source reuse rights. The current LICENSE is All Rights Reserved, not an OSI-approved open-source licence.
- [ ] Publish versioned release notes, reproducible deployment instructions, operator/user guides and a signed acceptance record.

## Explicit non-goals for the public demo

Do not make the public demo appear production-ready by setting readiness flags to true, fabricating institutional identity, inventing participant consent, inserting fictional dataset approvals, or importing real participant data. Keep `/health/ready` fail-closed while the institutional gates are absent.

Do not claim clinical validity, formal differential privacy, Beacon certification, immutable audit, independent security assurance, or regulatory compliance without the corresponding evidence.

## Open-source standards and implementation references

- GA4GH Passports: https://www.ga4gh.org/product/passports/
- GA4GH AAI: https://www.ga4gh.org/product/authorisation-and-authentication-infrastructure-aai/
- GA4GH Data Use Ontology: https://www.ga4gh.org/product/data-use-ontology-duo/
- GA4GH Beacon v2: https://docs.genomebeacons.org/
- HL7 FHIR R4 Consent: https://hl7.org/fhir/R4/consent.html
- OWASP ASVS: https://owasp.org/www-project-application-security-verification-standard/
- NIST Secure Software Development Framework: https://csrc.nist.gov/pubs/sp/800/218/final
- SLSA build provenance: https://slsa.dev/
- Render health checks: https://render.com/docs/health-checks
- GitHub rulesets: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets

## Final acceptance statement

As of 15 November 2026, GenomeGuard has a green exact-SHA automated CI/security suite and matching Vercel/Render deployments for the public synthetic demo. It is suitable to present as a synthetic-data research prototype subject to the post-deploy smoke and operator walkthrough above. It is **not fully complete as an institutional production genomic-governance platform** until the outstanding technical, operational, independent-review and institutional authorization gates are evidenced.
