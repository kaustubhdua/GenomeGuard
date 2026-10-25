# PostgreSQL operations and recovery

## Scope and safety boundary

GenomeGuard now has an opt-in PostgreSQL storage adapter. Set `GG_DATABASE_URL` to select it;
when unset, local demo/test environments continue to use SQLite. The adapter runs the versioned
schema in `backend/migrations/001_initial_postgres.sql`, parameterizes SQL, uses database
constraints for request/decision relationships, and serializes audit sequence allocation with a
transaction-scoped PostgreSQL advisory lock.

**This code change does not provision a database, change the Render plan, prove backups are enabled,
or make the public service production-ready.** Do not point it at another application's database.
Use a dedicated database and least-privilege credentials. Never commit the connection URL.

## Configure a dedicated database

1. Create a dedicated PostgreSQL database in the hosting provider's dashboard, in the same region
   as the application where possible. Choose a plan with supported backups and recovery; do not use
   Render's expiring Free Postgres for durable production data.
2. Configure `GG_DATABASE_URL` as a secret environment variable for the GenomeGuard service.
   Prefer the provider's private connection string. Require TLS when connecting across an untrusted
   network.
3. Deploy to an isolated staging service first. Confirm the application logs show successful
   migration and that `GET /health` succeeds.
4. Submit a request using a provisioned test identity, read it back, restart/redeploy staging, and
   verify request, decision, privacy-ledger, requester, and audit rows remain present.
5. Keep `/health/ready` fail-closed until identity, authorization, external audit anchoring,
   backup/restore and the other production gates are independently verified.

The initial migration is applied once and recorded in `schema_migrations`. Back up before future
schema changes. Schema migrations should be additive where practical and must be reviewed against
the current database before deployment.


## Migrating existing SQLite records

Use this only for an offline migration to a dedicated empty PostgreSQL database. Stop the app first,
make a consistent copy of the SQLite file, and preserve the exact existing `GG_MASTER_KEY`. The
migration copies cohort metadata, encrypted genotype blobs, requesters, requests, decisions,
privacy-budget ledger, audit events, donor-access ledger, alerts, and relationship/variant records.
It refuses a source with an invalid audit chain and a target with any application rows.

```bash
PYTHONPATH=backend python scripts/migrate_sqlite_to_postgres.py \
  --sqlite /path/to/stopped-service-snapshot.sqlite3
```

The script reads `GG_DATABASE_URL` from the environment unless `--database-url` is passed. Do not
perform the cutover until the row counts, audit verification, restored service behavior, and a
backup/restore drill have been independently reviewed. This is a one-time copy, not ongoing
replication or a zero-downtime migration.

## Backup and restore policy

Recommended starting policy for a dedicated production deployment:

- Daily encrypted logical backup to a separately controlled storage account.
- Retain daily backups for 35 days and monthly recovery points for 12 months, subject to approved
  legal, privacy, data-subject, and institutional retention requirements.
- Enable provider point-in-time recovery where available; target a recovery point objective (RPO)
  of 24 hours or better and a recovery time objective (RTO) of 4 hours or better, then validate
  these targets with drills.
- Restrict backup access separately from application credentials. Encrypt backup objects, audit
  reads/deletions, and test key recovery.
- Never include private genomic records in issue reports or CI artifacts. Use an isolated database
  containing authorized test fixtures for restore drills.

No retention schedule or backup job is automatically enabled by this repository. Operators must
configure, monitor, and evidence it. The script
`scripts/postgres_backup_restore_check.sh` creates a logical backup and restores it into a
separately provisioned **empty** verification database; it intentionally refuses identical source
and target URLs.

## Manual verification

Install PostgreSQL client tools compatible with the server version, then set these secret values in
your shell (do not paste them into tickets or commit them):

- `GG_DATABASE_URL`: source database connection URL.
- `GG_RESTORE_TEST_URL`: connection URL for a dedicated empty restore-test database.

Run:

```bash
bash scripts/postgres_backup_restore_check.sh
```

The script verifies the restored schema, migration version, core row counts, and audit index
continuity. It does not certify that a backup is encrypted offsite, that the provider's PITR works,
or that the full application audit hash chain verifies. Run the application audit verifier against
the restored database as a separate recovery acceptance step.

## Concurrency and audit semantics

The PostgreSQL audit append path takes a transaction-scoped advisory lock before allocating the
next sequence number and inserts the hash-linked entry in the same transaction. The primary key on
`audit_log.idx` is a second guard against duplicate sequence numbers. A failed audit insert must
surface as a failed operation; it must not be swallowed and reported as a successful decision.

The service now wraps request submission, review, requester provisioning, consent changes, withdrawal,
and account freeze/unfreeze in a PostgreSQL unit of work. The adapter uses a transaction-scoped
advisory lock to serialize these mutation units across instances; this is deliberately conservative
and may limit write throughput. Integration tests exercise transaction rollback. The exact deployed
release must pass the full PostgreSQL integration suite before this can be treated as verified.
External audit anchoring and production restore drills remain separate release gates.

## Still required before private/controlled genomic data

- Institution-selected OIDC issuer, client registration, redirect URI, claim mapping, MFA and
  account deprovisioning policy; use Authorization Code flow with PKCE and server-side sessions.
- Tenant/institution membership and server-enforced role/ownership policies, with database-level
  isolation where appropriate.
- Authorized, source-matched consent data and revocation handling; public-release dataset terms are
  not individual consent.
- Independently controlled audit anchoring and alerting.
- Verified production backup schedule, offsite retention, clean restore drill and restart/deploy test.
- Human screen-reader review, threat-model review and independent security/privacy assessment.

See [Render's backup and recovery documentation](https://render.com/docs/postgresql-backups),
[Render's free service limitations](https://render.com/docs/free), [Keycloak OIDC guidance](https://www.keycloak.org/securing-apps/oidc-layers),
and [OWASP ASVS 5.0.0](https://asvs.owasp.org/).
