# GenomeGuard — current implementation and release status

Updated: 10 November 2026

This is the concise entry point for the current implementation. See the [detailed release-readiness and validation record](release-readiness-2026-11-10.md) and the [five-minute hackathon demo guide](hackathon-demo-guide.md).

## Current summary

GenomeGuard is a first-party Python/Starlette research workbench with a browser UI, synthetic/public-data workflows, PostgreSQL persistence, institutional-control foundations, and evaluation/interoperability tooling.

- PR #111 (Supabase-free runtime) is merged into `main`.
- PR #112 (institutional controls) was merged into the intermediate `feat/remove-supabase-runtime` branch, not directly into `main`.
- PR #113 is the current draft proposal to bring the institutional controls and follow-up fixes into `main`.
- PostgreSQL migrations 001–012 are applied and validated on disposable Neon branches.
- The dedicated Render synthetic staging service is live at https://genomeguard-staging-pr113.onrender.com. It starts with 600 synthetic donors, encrypted genotype records, 3,000 variants, 959 relationships, and four demo personas.
- The live staging deployment is not yet the latest PR head; exact-head deployment and full staging acceptance remain release gates.
- The current CI run passed lint and seed, and static analysis, dependency, FHIR R4, Beacon v2, and image-build checks passed. PostgreSQL integration, backup/restore, evaluation, and browser/accessibility checks must finish on the exact final head.
- Production remains untouched and is not approved for controlled participant genomic data or clinical use.

## Security and data boundary

PostgreSQL RLS now scopes request, identity, and cohort rows by organization. Donor/genotype/relationship foreign keys prevent cross-organization links; donor-access events can reference shared public donors while preventing access logs for another tenant's private donor. The web role cannot rewrite genotype, variant, relationship, or cohort-metadata tables. Audit and consent ledgers are append-only for runtime credentials.

The hosted demo intentionally loads only the shared synthetic/public cohort into its in-memory dataset. A complete per-institution private-cohort ingestion and per-tenant processing lifecycle is not yet implemented. Do not load private or controlled-access participant data.

## Important limitations

The live demo uses synthetic data and simulated consent. No institution-specific OIDC issuer/client, authoritative consent source, external immutable audit anchor, provider-approved PITR/offsite recovery plan, or legal/ethics/clinical approval is configured. The Neon free staging branch has no scheduled snapshots. The Render health-check path also needs reconciliation with the checked-in Blueprint.

Do not infer participant consent from dataset-level public-release terms, treat VCF QC as import approval, describe risk heuristics as certified differential privacy, or present a green CI run as production readiness.

See [release readiness](release-readiness-2026-11-10.md) for the direct database checks, branch IDs, exact deployment state, remaining submission gates, and external production requirements.
