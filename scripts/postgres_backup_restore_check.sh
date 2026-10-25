#!/usr/bin/env bash
set -euo pipefail
: "${GG_DATABASE_URL:?Set GG_DATABASE_URL to the source PostgreSQL URL}"
: "${GG_RESTORE_TEST_URL:?Set GG_RESTORE_TEST_URL to a dedicated EMPTY restore-test database}"
command -v pg_dump >/dev/null || { echo "pg_dump is required" >&2; exit 2; }
command -v pg_restore >/dev/null || { echo "pg_restore is required" >&2; exit 2; }
command -v psql >/dev/null || { echo "psql is required" >&2; exit 2; }
if [[ "$GG_DATABASE_URL" == "$GG_RESTORE_TEST_URL" ]]; then
  echo "Refusing to restore over the source database." >&2
  exit 2
fi
umask 077
backup_dir="${TMPDIR:-/tmp}/genomeguard-pg-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$backup_dir"
trap 'rm -rf "$backup_dir"' EXIT
backup_file="$backup_dir/genomeguard.dump"
echo "Creating logical backup (temporary file is permission-restricted)..."
pg_dump --dbname="$GG_DATABASE_URL" --format=custom --no-owner --no-privileges --file="$backup_file"
echo "Restoring into the separately provisioned empty verification database..."
pg_restore --dbname="$GG_RESTORE_TEST_URL" --no-owner --no-privileges --exit-on-error "$backup_file"
echo "Checking restored schema and audit sequence..."
psql --no-psqlrc --set=ON_ERROR_STOP=1 --dbname="$GG_RESTORE_TEST_URL" <<'SQL'
DO $$
DECLARE
  migration_count integer;
  audit_count bigint;
  audit_min bigint;
  audit_max bigint;
BEGIN
  IF to_regclass('public.schema_migrations') IS NULL
     OR to_regclass('public.requests') IS NULL
     OR to_regclass('public.decisions') IS NULL
     OR to_regclass('public.requesters') IS NULL
     OR to_regclass('public.epsilon_ledger') IS NULL
     OR to_regclass('public.audit_log') IS NULL THEN
    RAISE EXCEPTION 'Required GenomeGuard tables missing after restore';
  END IF;
  SELECT count(*) INTO migration_count FROM schema_migrations WHERE version = 1;
  IF migration_count <> 1 THEN RAISE EXCEPTION 'Expected migration version 1'; END IF;
  SELECT count(*), min(idx), max(idx) INTO audit_count, audit_min, audit_max FROM audit_log;
  IF audit_count > 0 AND (audit_min <> 1 OR audit_max <> audit_count) THEN
    RAISE EXCEPTION 'Audit sequence is not contiguous: count %, min %, max %',
      audit_count, audit_min, audit_max;
  END IF;
END $$;
SELECT 'requesters' AS table_name, count(*) AS rows FROM requesters
UNION ALL SELECT 'requests', count(*) FROM requests
UNION ALL SELECT 'decisions', count(*) FROM decisions
UNION ALL SELECT 'epsilon_ledger', count(*) FROM epsilon_ledger
UNION ALL SELECT 'audit_log', count(*) FROM audit_log
ORDER BY table_name;
SQL
echo "Restore smoke check passed. The audit hash chain and application-level recovery must be verified separately."
