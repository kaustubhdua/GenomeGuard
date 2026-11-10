# PostgreSQL operations and recovery

## Scope and safety boundary

Non-demo deployments use a dedicated PostgreSQL database. The production-controls branch separates the ordinary application role from the migration owner:

- `GG_DATABASE_URL`: restricted runtime URL. It must not own application tables, be superuser, have BYPASSRLS, or have CREATE on GenomeGuard schemas.
- `GG_MIGRATION_DATABASE_URL`: separate owner URL used only while applying numbered migrations. The migration connection is closed and the variable is removed from process configuration after successful startup migration.

Never expose either URL to a browser, commit either secret, or reuse another application's database. See [institutional production controls](institutional-production-controls.md) for OIDC, tenant RLS, consent and audit requirements.

## Configure a dedicated database

1. Provision a dedicated managed PostgreSQL project with an approved retention, backup and recovery plan.
2. Create a database owner/migration principal and a separate runtime principal with only required DML on the GenomeGuard schemas. The runtime principal must not have BYPASSRLS, superuser, schema CREATE or ownership privileges.
3. Configure the two URLs as separate server-side secrets.
4. Deploy to isolated synthetic staging. Verify migrations, RLS, cross-tenant denial, concurrent writes, audit ordering, consent-ledger immutability, restart persistence and API/UI behavior against the exact deployed SHA.
5. Keep readiness fail-closed until identity, consent, audit anchoring, recovery and other production gates are independently verified.

The numbered migrations are applied once and recorded in `schema_migrations`. The migration runner executes complete SQL scripts with PostgreSQL's simple-query protocol so dollar-quoted trigger/function bodies are not corrupted by semicolon splitting.

## Tenant RLS

Migrations 003 and 005 add OIDC identity bindings, organization IDs and forced RLS on requests, decisions, epsilon-ledger and alerts. The API sets transaction-local organization scope only after verifying an OIDC token and resolving the exact active binding. Admin routes use a separate context after authenticating a reviewer/steward. A missing context sees no tenant rows. The synthetic demo compatibility scope is permitted only when demo mode is enabled.

The database role used in staging, `gg_app_runtime`, was directly checked: no superuser, no BYPASSRLS, and no CREATE privilege on either GenomeGuard schema. The live staging Render service has not yet been switched to this role; do not assume the test role is already the deployed role.

## Migrating existing SQLite records

Use only for an offline migration to a dedicated empty PostgreSQL database. Stop the app, make a consistent copy of SQLite, preserve the exact existing `GG_MASTER_KEY`, and verify the audit chain before cutover.

```bash
PYTHONPATH=backend python scripts/migrate_sqlite_to_postgres.py \
  --sqlite /path/to/stopped-service-snapshot.sqlite3
```

The script refuses an invalid source audit chain or a non-empty target. This is a one-time copy, not ongoing replication or zero-downtime migration.

## Backups, PITR and recovery

Recommended production baseline, subject to institutional retention policy:
- Daily encrypted logical backup to separately controlled storage.
- 35-day daily and 12-month monthly recovery points, unless the approved retention schedule requires otherwise.
- Provider PITR with a documented retention window and RPO/RTO targets, verified by recurring restore drills.
- Backup encryption keys and deletion permissions held separately from application credentials.
- Recovery drills on isolated databases with authorized synthetic/test fixtures only.

A provider restore drill was completed on the synthetic staging project: a manual snapshot was restored into a separate Neon branch; donor, variant, genotype, audit-row counts and hash-link continuity were checked. The restore branch is retained as evidence. This is not a production recovery drill.

The staging Neon project is on Free v3: history retention is 6 hours and no scheduled snapshot policy is configured. Neon documents that Free projects default to 6-hour history and scheduled snapshots require an eligible paid plan. Do not claim a 30-day PITR window or automated snapshots for this project. Production needs an approved plan and configured recovery policy.

The CI backup/restore test uses a disposable PostgreSQL database and encrypted temporary dump; it does not prove provider-level backups, offsite retention, key custody, PITR or production RPO/RTO.

## Manual encrypted logical backup verification

Set `GG_DATABASE_URL`, `GG_RESTORE_TEST_URL`, `GG_BACKUP_AGE_RECIPIENT`, and `GG_BACKUP_AGE_IDENTITY_FILE` in a trusted operator shell, then run:

```bash
bash scripts/postgres_backup_restore_check.sh
```

The script refuses a non-empty restore target, verifies server/database identity, checks the `genomeguard_runtime` schema and verifies the restored audit chain.
