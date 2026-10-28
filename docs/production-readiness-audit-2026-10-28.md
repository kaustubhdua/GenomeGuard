# GenomeGuard production-readiness audit — 28 October 2026

## Decision

**Current release: public-genotype research prototype. Not production-ready for private, controlled-access, or clinical genomic data.**

This audit records verified provider and repository state. It does not equate a successful merge, CI run, or hosting deployment status with end-to-end product readiness.

## What is verified

- Repository: https://github.com/kaustubhdua/GenomeGuard
- Main commit checked: a100921c98dbb194e365f76d32f9340700b2c196 (PR #43 merge).
- Render service genomeguard: https://genomeguard.onrender.com
- Render reports deployment dep-dbg42osipgvc73eesutg as live for the main commit above.
- GitHub CI passed for this commit, including backend lint/tests, PostgreSQL integration tests, evaluation smoke/full evaluations, demo checks, JavaScript/Python syntax checks, browser routes, responsive layouts and automated axe-core accessibility checks.
- Deployment-configuration checks passed. They applied migrations to a clean PostgreSQL instance and checked schema isolation and fail-closed deployment status.
- Security verification passed: dependency audit, CodeQL for Python and JavaScript, and repository secret scanning.
- The live research dataset is public 1000 Genomes / IGSR chromosome 22 genotype calls (600 samples × 3,000 variants), according to the deployment record. The public data are real; this does not make the records private, consented for every use, or suitable for clinical decisions.
- The product documentation clearly identifies synthetic fixtures as local demo/test artifacts, not real people or real consent.

## Live checks that are still not verified

- The Render service reports an empty health-check path even though render.yaml declares /health. Provider-side configuration drift remains open.
- The available HTTP verifier could not fetch the public app or health endpoints, and recent Render logs query returned no entries for the inspected window. Therefore route-level live acceptance has not been proven.
- Vercel project configuration has been updated for a static frontend rooted at frontend, and a PR preview was reported READY. A production deployment and public route-by-route acceptance test are not independently verified; the connected deployment API has returned access errors.
- A READY build is evidence of build completion, not proof that UI assets, API proxy routes, auth, or data operations work in production.

## Supabase common 1 state

- Project: hkyieaovolkethovyenb; GenomeGuard tables are isolated in schema genomeguard.
- Direct SQL currently finds 13 application tables and 0 of 13 with RLS enabled.
- The migration supabase/migrations/20261027010000_private_schema_rls.sql is merged in PR #43 and passes clean-PostgreSQL migration CI, but it has not been applied to the live database.
- The Supabase security advisor has surfaced RLS-enabled/no-policy notices for seven tables in the separate bharatsim schema. Those are not GenomeGuard tables; do not change that other application's policies as part of GenomeGuard remediation.
- Direct privilege checks previously confirmed anon and authenticated lack schema USAGE and direct table access to GenomeGuard's private schema. This reduces immediate Data API exposure but does not replace enabling and verifying RLS.
- The GenomeGuard cohort, donor, genotype, request, decision and audit tables are empty. No synthetic cohort or participant records were inserted.
- Render still has no verified GG_DATABASE_URL; the deployed backend is not connected to Supabase. The current SQLite path is on ephemeral storage, so durable request/audit persistence is not established.

## Blockers before a production claim

1. **Database security:** review and approve the private-schema RLS migration and server-side access model; apply the reviewed migration through the controlled migration process; re-check RLS and role grants live.
2. **Durable persistence:** configure the actual Supabase PostgreSQL connection string as Render secret GG_DATABASE_URL. Copy/reset it in the Supabase dashboard and set it in Render; never paste it into chat, GitHub, Vercel, or browser code.
3. **End-to-end acceptance:** configure Render's actual health-check path to /health; run the read-only research-mode and UI/API smoke tests against the exact deployed commit and inspect the results. Keep readiness fail-closed.
4. **Persistence proof:** against a controlled, non-sensitive test identity, verify request/decision/audit writes, concurrent ordering, and read-back; restart/redeploy and verify persistence.
5. **Backup and restore:** choose a supported backup/retention plan, define RPO/RTO, restore into an isolated database, and run integrity/application checks. Do not call durability complete until the restore succeeds.
6. **Identity and consent:** integrate institutional OIDC/SSO and verified organization membership; do not treat API keys as human identity. Do not invent participant consent. An authoritative consent/withdrawal source and institution/legal/ethics review are required before private participant data.
7. **Audit integrity:** add independently administered append-only audit anchoring or signed checkpoints with trusted timestamps and tested key custody. A local hash chain alone is not immutable against a database administrator.
8. **Independent assurance:** complete scoped penetration testing, privacy impact and legal/ethics review, cryptographic review, and manual assistive-technology testing.
9. **Operations:** configure monitoring/alerting, incident ownership, secret rotation, retention/deletion controls, recovery drills, concurrency and multi-instance consistency.
10. **Release:** verify the actual production Vercel deployment, public route/API proxy behavior, security headers, and all core flows; publish evidence tied to the exact release commit.

## Safe release boundary

Until the above controls are proven, use GenomeGuard only for the public-genotype research prototype. Do not upload private participant data, identifiable genomic data, controlled-access cohorts, or clinical records.

Risk scores are heuristic and not independently validated privacy guarantees. The privacy-budget ledger is not a formally audited differential-privacy implementation. Dataset-level public-release policy mapping is not participant-specific consent or legal authorization. FHIR fixtures are synthetic validation artifacts; selected Beacon-style checks are not full conformance certification. No live LLM is configured. These boundaries must remain visible in the UI and exported results.

## Reproduce the existing checks

From a local clone with Python 3.11+, dependencies, and Playwright Chromium installed:

```bash
make test
make lint
make eval-smoke
make demo
python scripts/live_research_mode_smoke.py --base https://genomeguard.onrender.com
python scripts/live_ui_smoke.py --base https://genomeguard.onrender.com
```

Run live checks from a network-enabled environment. Use only read-only checks against production; write-enabled persistence tests belong in an isolated staging environment.

## Official guidance

- [Supabase production checklist](https://supabase.com/docs/guides/deployment/going-into-prod)
- [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [1000 Genomes / IGSR data portal](https://www.internationalgenome.org/data/)
- [Render free-plan limitations](https://render.com/docs/free)
- [Render PostgreSQL backups and recovery](https://render.com/docs/postgresql-backups)
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)
