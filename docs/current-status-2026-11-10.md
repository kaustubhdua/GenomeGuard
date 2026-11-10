# GenomeGuard — current implementation and release status

Updated: 10 November 2026.

This is the concise entry point for the current implementation. See the [detailed release-readiness and validation record](release-readiness-2026-11-10.md), [institutional controls](institutional-production-controls.md), and [five-minute hackathon demo guide](hackathon-demo-guide.md).

## Current summary

GenomeGuard is a first-party Python/Starlette research workbench with a browser UI, synthetic/public-data workflows, PostgreSQL persistence, institutional-control foundations, and evaluation/interoperability tooling.

- PR #111 (Supabase-free runtime) is merged into `main`.
- PR #112 (institutional controls) was merged into the intermediate `feat/remove-supabase-runtime` branch.
- PR #113 remains the draft release candidate to bring the institutional controls into `main`.
- PR #116's focused steward-onboarding/CI follow-up was merged into PR #113's feature branch as commit `b7c0c508d46afa99a581d140d82fa4c8fa48928b`. It has not been merged into `main`.
- PostgreSQL migrations 001–012 are applied and validated on two disposable Neon branches.
- The dedicated Render synthetic staging service is live at https://genomeguard-staging-pr113.onrender.com. The last verified deployment is commit `3e46060327446f265b48156b6952480687133a3a`, with 600 synthetic donors, 3,000 variants, PostgreSQL storage, demo mode and simulated consent.
- Render's provider health-check path is now `/health/live`; both `/health` and `/health/live` returned HTTP 200 on the last verification.
- Exact-head CI run [42854944790](https://github.com/kaustubhdua/GenomeGuard/actions/runs/42854944790) was **cancelled by the 20-minute job timeout** while `pytest -q` was still running. It did not report an assertion failure; backup/restore, evaluations, compilation and browser/accessibility steps were skipped. The follow-up increases the job timeout to 45 minutes and enables verbose pytest progress and duration reporting.
- The exact PR head has advanced to `b7c0c508d46afa99a581d140d82fa4c8fa48928b`. Its CI and staging deployment/acceptance must be verified before the candidate can be considered validated.
- Separate exact-previous-head workflows for security verification, dependency audit, FHIR R4 Consent, Beacon v2 schema validation, deployment configuration and staging acceptance passed on `3e460603...`; those results do not automatically validate the new head.
- Production remains untouched and is not approved for controlled participant genomic data or clinical use.

## Security and data boundary

PostgreSQL RLS scopes request, identity, and cohort rows by organization. Donor/genotype/relationship foreign keys prevent cross-organization links; donor-access events can reference shared public donors while preventing access logs for another tenant's private donor. The web role cannot rewrite genotype, variant, relationship, or cohort-metadata tables. Audit and consent ledgers are append-only for runtime credentials.

The steward-onboarding follow-up now allows an organization-scoped steward to provision researchers/reviewers only within the steward's own organization, then bind the exact OIDC subject. It denies cross-organization provisioning, reviewer account provisioning, and steward self-promotion. This behavior has regression tests but still needs exact-head CI execution.

The hosted demo intentionally loads only the shared synthetic/public cohort into its in-memory dataset. A complete per-institution private-cohort ingestion and per-tenant in-memory processing lifecycle is not implemented. Do not load private or controlled-access participant data.

## Important limitations

The live demo uses synthetic data and simulated consent. No institution-specific OIDC issuer/client, authoritative consent source, independently operated immutable audit anchor, provider-approved PITR/offsite recovery plan, scheduled backup retention, monitoring/alert routing, or legal/ethics/security approval is configured. The Neon free staging branch has no scheduled snapshots; manual snapshots of non-root branches are not supported by the current Neon project.

The normalized VCF importer is a source-reviewed public-reference ingestion path, not a complete private institutional multi-tenant ingestion service. It must not be used for private cohorts until tenant ownership, sample-identifier protection, RLS, per-tenant processing and consent enforcement are implemented and independently validated.

Do not infer participant consent from dataset-level public-release terms, treat VCF QC as import approval, describe risk heuristics as certified differential privacy, or present a green CI run as production readiness.

See [release readiness](release-readiness-2026-11-10.md) for direct database checks, branch IDs, exact deployment state, remaining submission gates, and external production requirements.
