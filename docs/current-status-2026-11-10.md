# GenomeGuard — current implementation and release status

Updated: 10 November 2026

## Executive status

GenomeGuard is a research prototype with a first-party Python/Starlette API and browser application. The Supabase-free runtime is implemented on [PR #111](https://github.com/kaustubhdua/GenomeGuard/pull/111), branch feat/remove-supabase-runtime.

**The code-level implementation is under exact-head validation. The synthetic staging service is not yet confirmed on the current branch head. Production is not ready.** CI success does not prove lawful data use, participant consent, institutional identity, clinical validity, provider-level disaster recovery, or production readiness.

## Current source and validation snapshot

- Current branch head: 4587941f4ed0c20bda71e1927e72442732876e32
- PR: https://github.com/kaustubhdua/GenomeGuard/pull/111
- Deployment configuration checks: [run 597](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42715541556) — success on current head.
- GA4GH Beacon v2 schema validation: [run 287](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42715541604) — success on current head.
- FHIR R4 Consent validation: [run 249](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42715541578) — success on current head.
- Security verification: [run 607](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42715541832) — success on current head, including secret scanning, CodeQL Python/JavaScript, and Python dependency audit.
- Full CI: [run 957](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42715541579) — lint and seed completed successfully; backend suite including PostgreSQL integration tests was still running at this snapshot.
- Real-data image build: [run 227](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42715541584) — running.
- Synthetic staging acceptance: [run 24](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42715541730) — running; waiting for the exact branch head to be deployed.

Earlier implementation head 395fdbc2177e98a6597fa468e9b5402aca713c89 passed the complete CI suite, staging acceptance, security verification, GA4GH Beacon v2 validation, FHIR R4 validation, and real-data image build. Do not treat that prior-head result as proof for the current head.

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
- Last confirmed live deployment: 395fdbc2177e98a6597fa468e9b5402aca713c89.
- Current PR head has not been confirmed live. The Render provider currently reports auto-deploy enabled, but no deployment newer than 395fdbc appeared in the provider deployment history at the last check.
- The live Render service has no provider-side health-check path configured; the checked-in Blueprint declares /health/live.
- The checked-in Blueprint deliberately keeps auto-deploy disabled, as required by the deployment-configuration CI gate. The live service's existing auto-deploy setting therefore differs from the Blueprint.

The staging service is synthetic-only. Its readiness endpoint must remain HTTP 503/not-ready because demo mode is enabled and participant consent, real genotype provenance, external audit anchoring, institutional identity, and durable-storage verification are not established. A post-redeploy persistence check and provider-level backup/restore drill against this exact Neon staging project remain outstanding. CI's disposable PostgreSQL backup/restore test is not a substitute.

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
