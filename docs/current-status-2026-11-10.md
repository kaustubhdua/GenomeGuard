# GenomeGuard — current implementation and release status

Updated: 10 November 2026

This page is the stable entry point for the current status. The detailed, evidence-based report is maintained in [Release readiness and validation record](release-readiness-2026-11-10.md).

## Current summary

GenomeGuard is a first-party Python/Starlette research application with a browser UI, synthetic/public-data workflows, PostgreSQL support, evaluation tooling, and institutional-control foundations.

- PR #111 (Supabase-free runtime) is merged into `main`.
- PR #112 (institutional controls) was merged into the intermediate `feat/remove-supabase-runtime` branch, not directly into `main`.
- PR #113 is the current draft proposal to bring those controls and the follow-up database fixes into `main`.
- Migrations 003–009 have been applied and directly validated on a disposable Neon child branch. The migration ledger on that branch reports versions 001–009.
- The Render synthetic staging service remains on the earlier `feat/remove-supabase-runtime` branch. It has not yet been deployed from PR #113.
- The exact-head CI for PR #113 must finish successfully before the project is called a verified hackathon release.
- Production remains untouched and is not approved for controlled participant genomic data or clinical use.

## Important limitations

The synthetic/public-data demonstration is distinct from a real institutional deployment. No institution-specific OIDC provider, trusted consent authority, external immutable audit anchor, approved provider recovery plan, or legal/ethics/clinical approval has been configured. The current tenant RLS protects operational request/identity records; shared cohort tables still need an explicit tenant ownership/access model before institution-supplied controlled cohorts are accepted.

Do not upload private or controlled-access participant genomic data to the public research instance or synthetic staging. Do not infer participant consent from dataset-level public-release terms, treat VCF QC as import approval, or treat a green CI run as production readiness.

See the [release-readiness report](release-readiness-2026-11-10.md) for the exact source topology, validation branch, database permission checks, staging state, CI evidence, and remaining release gates.
