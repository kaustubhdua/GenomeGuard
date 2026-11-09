# Render staging setup

The separate Render Blueprint in `render.staging.yaml` is a synthetic-only staging service for the Supabase-free branch. It does not replace or adopt the production Render service.

## Required environment values

In the new Render staging service, set the required manual values under **Environment**:

- `GG_DATABASE_URL`: use a **direct, non-pooled Neon PostgreSQL connection string** for the `genomeguard` database and `genomeguard_owner` role. The hostname must not contain `-pooler`.
- `GG_MASTER_KEY`: base64-encoded random 32-byte key. Generate one locally with:

  ```bash
  python -c 'import os,base64; print(base64.b64encode(os.urandom(32)).decode())'
  ```

Render generates `GG_ADMIN_API_KEY` from the Blueprint. The Blueprint sets `GG_DEMO_MODE=true`, disables the tamper demo, clears `GG_REAL_COHORT_FILE`, and uses `GG_DATASET_ID=synthetic-cohort-1`. Do not change staging to real-data mode.

## Why the Neon connection must be direct

GenomeGuard's PostgreSQL adapter retains a long-running psycopg connection, sets `search_path`, and applies versioned migrations. Neon documents that its pooled endpoint uses PgBouncer in transaction mode and does not preserve session-level `SET` state such as `search_path`; Neon recommends direct connections for schema migrations and workloads needing session state.

In the Neon Console, open **Connect** for the staging branch, database, and role, then switch **Connection pooling** off before copying the connection string. A pooled URI contains `-pooler` in its hostname; do not use it for this adapter.

References:
- [Neon connection pooling and transaction-mode limitations](https://neon.com/docs/connect/connection-pooling)
- [Neon connection method guidance](https://neon.com/docs/connect/choose-connection)

## First deployment acceptance

After supplying the two manual values and approving the Render Blueprint plan:

1. Wait for the separate staging deployment to build and become live.
2. Check `/health/live`, then `/health` and `/health/ready`.
3. Confirm the reported storage backend is PostgreSQL and schema migration versions 1 and 2 are recorded.
4. Verify that the synthetic cohort seeds successfully and that request/audit rows persist across a staging restart.
5. Exercise same-origin catalogue, request, decision, audit, export, and browser workflows against the staging service.

A green build or successful schema creation is not proof of provider-level backup/restore, participant consent, institutional identity, or clinical readiness. Keep the existing production service unchanged until a separate reviewed release decision.
