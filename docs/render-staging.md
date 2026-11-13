# Render staging setup

The synthetic-only staging service is provisioned separately from production:

- Public URL: https://genomeguard-staging.onrender.com
- Render dashboard: https://dashboard.render.com/web/srv-dbp41m5bedkc73fk4aug
- Branch: feat/remove-supabase-runtime
- Image: Dockerfile.staging (no public 1000 Genomes download or embedded real cohort)
- Plan/region: Render Free / Singapore
- Database: separate Neon Free PostgreSQL project in Singapore

The Render service is not the production service. The existing production service continues to deploy main and was not changed.

## Provider configuration verified

The Render service API currently reports:
- auto-deploy enabled on branch feat/remove-supabase-runtime;
- Dockerfile ./Dockerfile.staging;
- public network access enabled;
- no provider-side health-check path configured (empty string).

The checked-in Blueprint intentionally keeps auto-deploy disabled. The deployment-configuration CI gate requires this so a reviewed staging release is not implicitly promoted by every branch commit. The live service's existing auto-deploy setting therefore differs from the Blueprint and must be reconciled by an authorized Render operator before treating the Blueprint as an exact recreation of the live service.

The Blueprint declares /health/live as the liveness check. The live service dashboard currently has no health-check path; align it with /health/live separately. The Blueprint file alone does not update an already-provisioned Render service. Do not use /health/ready as the host liveness probe: readiness must remain fail-closed while production controls are absent.

The latest confirmed live staging deployment remains commit 395fdbc2177e98a6597fa468e9b5402aca713c89. The exact current PR head has not yet been confirmed live. Although the provider reports auto-deploy enabled, no later deployment was present in the provider deployment history at the last check. The acceptance workflow waits for the exact PR SHA and must pass before the staging release is considered verified.

## Staging environment and trust boundaries

The staging service uses a dedicated genomeguard_runtime database role, not the owner role. It has:
- USAGE and CREATE on genomeguard_runtime so the app can apply its versioned runtime migrations;
- read-only access to the normalized genomeguard reference schema;
- no owner or superuser privileges.

The database URL is a direct, non-pooled Neon connection string. Neon transaction-mode PgBouncer connections do not preserve session-level SET state such as search_path; this application retains a long-running psycopg connection and applies migrations, so use the direct hostname without -pooler.

Staging environment values are stored only in Render:
- GG_DATABASE_URL: direct connection as genomeguard_runtime.
- GG_MASTER_KEY: random base64-encoded 32-byte key.
- GG_ADMIN_API_KEY: unique rotated secret; never place it in Git or a browser variable.
- GG_DEMO_MODE=true
- GG_ALLOW_TAMPER_DEMO=false
- GG_REAL_COHORT_FILE=
- GG_DATASET_ID=synthetic-cohort-1

The public /demo/requesters and /demo/donors endpoints return persona metadata only, never static credentials. Browser users obtain 30-minute process-local requester/donor sessions through the corresponding POST endpoints. The hosted UI hides steward-only controls rather than exposing a privileged key. The in-memory session registry is single-process only; replace it with a shared session store before scaling to multiple workers or instances.

## Live staging acceptance already performed

- GET /health/live: HTTP 200.
- GET /health: HTTP 200 and storage_backend=postgresql.
- Synthetic cohort loads: 600 donors and 3,000 variants.
- GET /catalogue/sources and /catalogue/datasets: HTTP 200.
- GET /audit/verify: HTTP 200, valid chain.
- Public demo endpoint: no admin_key field.
- Old administrator key after rotation: HTTP 401.
- Missing administrator key: HTTP 401.
- Rotated administrator key: HTTP 200 on the protected audit route.
- Synthetic researcher request: HTTP 201, permit_with_transform; request history and audit chain show the write.

GET /health/ready returns HTTP 503 intentionally. This service is a synthetic demo; participant consent, real genotype provenance, external audit anchoring, institutional identity, and durable-storage verification are not established. Do not change staging to real-data mode or weaken these readiness gates.

A post-redeploy persistence check and provider-level backup/restore drill against this exact Neon staging project remain to be completed. CI's disposable PostgreSQL backup/restore integration tests do not substitute for those provider-level checks.

## Blueprint

render.staging.yaml is a reproducible Blueprint description for this separate service. It deliberately disables auto-deploy and declares /health/live. It is not a replacement for the live service's current dashboard settings. Review its plan before applying it to any other Render workspace or project.

## References

- Neon connection pooling and transaction-mode limitations: https://neon.com/docs/connect/connection-pooling
- Neon connection method guidance: https://neon.com/docs/connect/choose-connection
- Render staging dashboard: https://dashboard.render.com/web/srv-dbp41m5bedkc73fk4aug
