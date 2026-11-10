# GenomeGuard — current implementation and release status

Updated: 10 November 2026.

This is the concise entry point for the current implementation. See the [detailed release-readiness and validation record](release-readiness-2026-11-10.md), [institutional controls](institutional-production-controls.md), and [five-minute hackathon demo guide](hackathon-demo-guide.md).

## Current summary

GenomeGuard is a first-party Python/Starlette research workbench with a browser UI, synthetic/public-data workflows, PostgreSQL persistence, institutional-control foundations, and evaluation/interoperability tooling.

- PR #111 (Supabase-free runtime) and PR #113 (institutional-control implementation) are merged into `main`; PR #113's merge commit is `088eaa9adde25cf95b748c31bad365880fe95343`.
- PRs #116, #117 and #118 were merged into `feat/institutional-production-controls` before PR #113 was merged, so their code and researcher-to-steward workflow tests are included in the PR #113 merge.
- PR #119 was merged into `feat/institutional-production-controls` **after** PR #113 had merged. It adds the positive steward-approval and separate governed-release safety test in `backend/tests/test_identity_bindings.py`; that test-only change is not yet in `main`.
- Current refs at this audit: `main` = `088eaa9adde25cf95b748c31bad365880fe95343`; `feat/institutional-production-controls` = `2866b967de21cf35d5d5881f62371aedefb73189`. The feature branch differs from main by the PR #119 test addition (49 lines in one file); its ahead/behind counts also include merge ancestry.
- GitHub's branch listing reports `main` as unprotected (`protected: false`). Required status checks and branch protection have not been verified or configured.
- PostgreSQL migrations 001–012 are applied and validated on two disposable Neon branches. The Render staging Neon branch contains 600 synthetic donors, 600 encrypted genotype records, 3,000 variants, 959 relationships, four demo requesters and audit events.
- The dedicated Render synthetic staging service is running at https://genomeguard-staging-pr113.onrender.com, but its latest live deployment remains commit `3e46060327446f265b48156b6952480687133a3a`. It has not deployed the current feature head `2866b967...`.
- The live Render service reports `/health/live` as its provider health-check path. Recent logs show `/health` and `/health/live` returning HTTP 200; `/health/ready` intentionally returns 503 for the synthetic-only demo.
- Earlier read-only live checks against the old staging deployment passed 15/15 endpoint checks and 9/9 authorization/catalogue checks. Those results do not validate the current code head.
- Latest exact-head GitHub Actions: main CI run [42870532217](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42870532217) on `088eaa9...` and feature CI run [42870551577](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42870551577) on `2866b967...` are in progress. Lint and seed passed; PostgreSQL integration tests were still running at the audit snapshot.
- Staging acceptance run [42870552058](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42870552058) is still polling for exact commit `2866b967...`; Render has not produced a deployment for it. Do not mark hosted acceptance complete until the exact SHA is live and browser/mobile checks finish.
- Render reports commit-based auto-deploy enabled, but no commit-triggered deployment event appeared after the feature-branch pushes. The available Render integration does not expose a safe service-update action to repair the Git provider trigger; no manual deployment was forced.
- The PR #119 Vercel preview bot reported the account's daily deployment quota was exhausted. This is a hosting quota failure, not a failing application test.
- Production remains untouched. The production Render service is still on its older `main` deployment (commit `42c1bb0f...`, last observed 29 October 2026); no production deployment event appeared after the PR #113 merge. It is not verified against current main and is not approved for controlled participant genomic data or clinical use.

## Security and data boundary

PostgreSQL RLS scopes request, identity, and cohort rows by organization. Donor/genotype/relationship foreign keys prevent cross-organization links; donor-access events can reference shared public donors while preventing access logs for another tenant's private donor. The web role cannot rewrite genotype, variant, relationship, or cohort-metadata tables. Audit and consent ledgers are append-only for runtime credentials.

The steward-onboarding follow-up allows an organization-scoped steward to provision researchers/reviewers only within the steward's own organization, then bind the exact OIDC subject. It denies cross-organization provisioning, reviewer account provisioning, and steward self-promotion. The researcher-to-steward request/review tests from PR #118 are in main; PR #119 adds the positive approval/separate-release safety case on the feature branch. Exact-head CI remains pending.

The hosted demo intentionally loads only the shared synthetic/public cohort into its in-memory dataset. A complete per-institution private-cohort ingestion and per-tenant in-memory processing lifecycle is not implemented. Do not load private or controlled-access participant data.

## Important limitations

The live demo uses synthetic data and simulated consent. No institution-specific OIDC issuer/client, authoritative consent source, independently operated immutable audit anchor, provider-approved PITR/offsite recovery plan, scheduled backup retention, monitoring/alert routing, or legal/ethics/security approval is configured. The Neon free staging branch has no scheduled snapshots; manual snapshots of non-root branches are not supported by the current Neon project.

The normalized VCF importer is a source-reviewed public-reference ingestion path, not a complete private institutional multi-tenant ingestion service. It must not be used for private cohorts until tenant ownership, sample-identifier protection, RLS, per-tenant processing and consent enforcement are implemented and independently validated.

Do not infer participant consent from dataset-level public-release terms, treat VCF QC as import approval, describe risk heuristics as certified differential privacy, or present a green CI run as production readiness.

See [release readiness](release-readiness-2026-11-10.md) for direct database checks, branch IDs, exact deployment state, remaining submission gates, and external production requirements.
