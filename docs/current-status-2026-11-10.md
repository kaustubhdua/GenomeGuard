# GenomeGuard — current implementation and release status

Updated: 10 November 2026

## Executive status

GenomeGuard is a research prototype with a first-party Python/Starlette API and browser application. The Supabase-free runtime is implemented on [PR #111](https://github.com/kaustubhdua/GenomeGuard/pull/111), branch feat/remove-supabase-runtime.

**The Supabase-free research prototype is implemented and deployed to synthetic staging at the current reviewed branch head.** On 10 November 2026, staging API, authorization, provenance, audit, public UI, and mobile browser acceptance passed; the full backend/PostgreSQL, encrypted backup/restore, evaluation, demo, and static checks passed on the reviewed code head. The final browser/accessibility CI job is recorded below. Production is not ready. CI success does not prove lawful data use, participant consent, institutional identity, clinical validity, provider-level disaster recovery, or production readiness.

## Current source and validation snapshot

- Reviewed branch tip: c768a209a254905e60de37d2d1631cf21a74443e (PR #111 remains open and unmerged).
- Runtime reconnect hardening: 0ac6014eba7917b7aec82bcb4d50b23f3ce1687c; regression tests and lint correction are included in the current branch tip.
- Deployment configuration checks: [run 607](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42719959013) — success.
- GA4GH Beacon v2 schema validation: [run 297](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42719959217) — success.
- FHIR R4 Consent validation: [run 259](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42719959341) — success.
- Security verification: [run 617](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42719959259) — success, including secret scanning, CodeQL Python/JavaScript, and Python dependency audit.
- Real-data image build: [run 237](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42719959039) — success.
- Synthetic staging acceptance: [run 34](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42719959301) — success, including live API and hosted browser/mobile checks.
- Full CI: [run 967](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42719959038) — lint, seed, backend/PostgreSQL suite, encrypted backup/restore, eval-smoke, full eval, demo, JavaScript syntax, and Python compilation passed; hosted browser/accessibility steps were still running at this snapshot.

The latest exact-head checks supersede earlier in-progress snapshots. The staging deployment is dep-dbp5bgmgekts73e904pg and serves the current reviewed branch tip.

## Current architecture

- Browser frontend uses same-origin GenomeGuard routes.
- Python/Starlette is the single application API and policy engine.
- Local development uses synthetic data and SQLite.
- Hosted non-demo mode requires server-side PostgreSQL via GG_DATABASE_URL.
- Supabase Auth, Supabase browser keys, Supabase Edge Functions, and Supabase runtime calls are removed from the active frontend.
- Historical supabase/ migrations are inert archive records and must not be applied to new deployments.
- Agent explanations use offline deterministic templates and bounded rules; no hosted AI provider or API key is required.
- Steward API-key hash checks use constant-time comparison.

## Synthetic-only staging

- URL: https://genomeguard-staging.onrender.com
- Render service: srv-dbp41m5bedkc73fk4aug
- Branch: feat/remove-supabase-runtime
- Dockerfile: Dockerfile.staging; it does not embed or download the real 1000 Genomes cohort.
- Database: separate Neon PostgreSQL staging database.
- Last confirmed live deployment: c768a209a254905e60de37d2d1631cf21a74443e (dep-dbp5bgmgekts73e904pg, successful).
- Render reports provider auto-deploy enabled, but pushes did not reliably produce a deploy; the reviewed branch head was deployed manually to staging and then verified by the acceptance workflow.
- The live Render service has no provider-side health-check path configured; the checked-in Blueprint declares /health/live.
- The checked-in Blueprint deliberately keeps auto-deploy disabled, as required by the deployment-configuration CI gate. The live service's existing auto-deploy setting therefore differs from the Blueprint and should be reconciled through a reviewed infrastructure change.

The staging service is synthetic-only. Live Neon PostgreSQL checks confirmed 600 synthetic donors, 3,000 synthetic variants, 600 genotype rows, and 16 audit rows; normalized public-dataset manifests/samples/variants/genotype calls are all zero. The readiness endpoint must remain HTTP 503/not-ready because demo mode is enabled and participant consent, real genotype provenance, external audit anchoring, institutional identity, and durable-storage verification are not established. No Neon snapshot schedule or snapshots were configured at the time of inspection. CI's disposable PostgreSQL encrypted backup/restore test is not a substitute for a provider-level backup/restore drill or PITR verification.

The live staging connection currently authenticates as the database owner role (genomeguard_owner, which has database/role-creation privileges). A separate genomeguard_runtime role exists, but the deployed service is not yet using a restricted runtime credential. Split migration-owner and application-runtime credentials before any controlled-data or production deployment. GitHub branch protection could not be enabled on this plan because the account had reached its protected-branch limit; preserve review and required-check discipline manually until repository governance is resolved.

## Product capabilities and boundaries

- Research request, policy, risk, transformation, anomaly-monitoring, and human-review workflow foundations.
- Synthetic-data demonstration.
- VCF parsing and QC with an explicit distinction between QC success and import eligibility.
- Public-source discovery and catalogue provenance.
- Dataset-level public-release policy mapping for the public 1000 Genomes research mode.
- Simulated consent attributes only in local synthetic demo mode.
- Hash-chained audit trail, audit verification, and unsigned checkpoint integrity envelopes.
- PostgreSQL-backed store, native migrations, encrypted backup/restore tooling, and read-only audit verification.
- GA4GH Beacon v2 schema validation and synthetic FHIR R4 Consent validation.

These are research-software capabilities, not proof of lawful data import, participant-specific consent, clinical validity, or operational controls.

## Production release blockers

| Area | Current evidence | Required before controlled-data or production use |
|---|---|---|
| Production deployment | Existing Render production service still deploys main. | Review and deploy an exact tested commit only after production configuration is prepared. |
| Persistence | Production currently uses SQLite on an ephemeral filesystem. Staging uses PostgreSQL. | Dedicated production PostgreSQL, provider backups/PITR, retention, monitoring, and tested restore. |
| Identity | API keys authenticate application roles only. | Institutional OIDC, verified organization membership, role lifecycle, MFA policy, revocation, and cross-tenant tests. |
| Consent | Public research mode uses dataset-level terms; local demo uses synthetic consent. | Authoritative source-specific consent evidence, participant-level mapping where required, expiry/withdrawal enforcement at decision and release time, ethics/legal approval. |
| Real data | No production import/reconciliation is verified. | Steward-approved artifact, reuse terms, reference assembly, checksums, sample/variant/call-count reconciliation, provenance, and import approval. |
| Audit | Hash chain and unsigned checkpoint envelope. | Independently administered append-only anchor or signing service, key custody, trusted timestamps, monitoring, and verification drills. |
| Security/privacy governance | Automated scans and tests only. | Independent threat-model, privacy, legal, ethics, penetration, and cryptographic review. |
| Clinical validity | No clinically validated annotation/pathogenicity pipeline. | Qualified clinical validation, regulatory assessment, and expert oversight; never use prototype output for clinical decisions. |
| Accessibility | Automated browser and axe checks. | Manual keyboard, screen-reader, and assistive-technology testing. |
| Vercel preview | Provider returned build-rate-limit. | Resolve provider rate limit or use the verified same-origin Starlette deployment path for staging acceptance. |

## Standards and open-source alignment

The implementation validates Beacon v2 responses against pinned GA4GH schemas and synthetic FHIR R4 Consent resources against the HL7 validator. DUO is used as a vocabulary for dataset-use terms, not as proof of individual consent. GA4GH AAI/Passports, Machine-Readable Consent Guidance, and DAC review standards are relevant future integration points. Existing systems such as NIH/Broad DUOS should be evaluated as reference implementations rather than recreated without institutional requirements and license review.

## Release sequence

1. Finish exact-head CI and real-data image validation.
2. Deploy the exact reviewed commit to synthetic-only staging through the authorized Render deployment path.
3. Complete hosted route/UI acceptance and verify persistence across redeploy.
4. Run provider-level encrypted backup/restore and define RPO/RTO.
5. Implement and independently verify institutional identity and organization authorization before controlled data.
6. Complete dataset rights, ethics, consent, withdrawal, and import reconciliation before participant-specific data.
7. Add independent audit anchoring/signing and operational monitoring.
8. Complete independent security/privacy review and manual accessibility testing.
9. Only then consider production migration and release.

## Important limitations

- Do not upload private or controlled-access participant genomic data to the public research instance or synthetic staging.
- Do not infer participant consent from dataset-level open-data terms.
- Do not treat VCF QC as import approval or clinical validation.
- Do not treat API keys as institutional identity.
- Do not treat a green CI run, a successful schema validator, or a reachable frontend as production readiness.
- Production was not changed, no paid service was provisioned, and no clinical approval is claimed.

## Related records

- [PR #111](https://github.com/kaustubhdua/GenomeGuard/pull/111)
- [Supabase-free deployment](supabase-free-deployment.md)
- [Render staging setup](render-staging.md)
- [Production deployment record](production-deployment.md)
- [Genomic dataset provenance and import gate](genomic-dataset-provenance-import-gate.md)
- [Organization authorization and consent implementation status](organization-authorization-and-review.md)
- [OWASP ASVS verification register](asvs-verification.md)
- [Threat model](threat-model.md)
