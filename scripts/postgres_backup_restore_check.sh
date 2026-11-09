#!/usr/bin/env bash
set -euo pipefail

: "${GG_DATABASE_URL:?Set GG_DATABASE_URL to the source PostgreSQL URL}"
: "${GG_RESTORE_TEST_URL:?Set GG_RESTORE_TEST_URL to a dedicated EMPTY restore-test database}"
: "${GG_BACKUP_AGE_RECIPIENT:?Set an age public recipient for encrypting the temporary backup}"
: "${GG_BACKUP_AGE_IDENTITY_FILE:?Set a path to the age identity file used to decrypt the backup}"

for tool in pg_dump pg_restore psql age python3; do
  command -v "$tool" >/dev/null || { echo "$tool is required" >&2; exit 2; }
done
if [[ ! -r "$GG_BACKUP_AGE_IDENTITY_FILE" ]]; then
  echo "The age identity file is not readable." >&2
  exit 2
fi

# Compare server/database identity, not just URL strings: aliases can point to the same database.
source_identity="$(psql --no-psqlrc --tuples-only --no-align --set=ON_ERROR_STOP=1 \
  --dbname="$GG_DATABASE_URL" \
  --command="SELECT current_database() || '|' || COALESCE(inet_server_addr()::text, 'local') || '|' || COALESCE(inet_server_port()::text, '')")"
target_identity="$(psql --no-psqlrc --tuples-only --no-align --set=ON_ERROR_STOP=1 \
  --dbname="$GG_RESTORE_TEST_URL" \
  --command="SELECT current_database() || '|' || COALESCE(inet_server_addr()::text, 'local') || '|' || COALESCE(inet_server_port()::text, '')")"
if [[ "$source_identity" == "$target_identity" ]]; then
  echo "Refusing to restore into the source database (database identity matches)." >&2
  exit 2
fi

# Refuse any non-empty target before pg_restore can partially overwrite it.
target_objects="$(psql --no-psqlrc --tuples-only --no-align --set=ON_ERROR_STOP=1 \
  --dbname="$GG_RESTORE_TEST_URL" --command="
    SELECT count(*)
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
      AND n.nspname <> 'pg_toast'")"
if [[ "$target_objects" != "0" ]]; then
  echo "Refusing restore: target database contains $target_objects user objects; use a dedicated empty database." >&2
  exit 2
fi

umask 077
backup_dir="${TMPDIR:-/tmp}/genomeguard-pg-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$backup_dir"
trap 'rm -rf "$backup_dir"' EXIT
encrypted_file="$backup_dir/genomeguard.dump.age"

echo "Creating encrypted logical backup; plaintext is streamed directly to age..."
pg_dump --dbname="$GG_DATABASE_URL" --format=custom --no-owner --no-privileges \
  | age --encrypt --recipient "$GG_BACKUP_AGE_RECIPIENT" --output "$encrypted_file"

echo "Restoring encrypted backup into the separately provisioned empty verification database..."
age --decrypt --identity "$GG_BACKUP_AGE_IDENTITY_FILE" "$encrypted_file" \
  | pg_restore --dbname="$GG_RESTORE_TEST_URL" --no-owner --no-privileges --exit-on-error -

echo "Checking restored GenomeGuard runtime schema and audit sequence..."
psql --no-psqlrc --set=ON_ERROR_STOP=1 --dbname="$GG_RESTORE_TEST_URL" <<'SQL'
DO $$
DECLARE
  runtime_schema text := 'genomeguard_runtime';
  migration_count integer;
  audit_count bigint;
  audit_min bigint;
  audit_max bigint;
BEGIN
  IF to_regclass(format('%I.%I', runtime_schema, 'schema_migrations')) IS NULL
     OR to_regclass(format('%I.%I', runtime_schema, 'requests')) IS NULL
     OR to_regclass(format('%I.%I', runtime_schema, 'decisions')) IS NULL
     OR to_regclass(format('%I.%I', runtime_schema, 'requesters')) IS NULL
     OR to_regclass(format('%I.%I', runtime_schema, 'epsilon_ledger')) IS NULL
     OR to_regclass(format('%I.%I', runtime_schema, 'audit_log')) IS NULL THEN
    RAISE EXCEPTION 'Required GenomeGuard runtime tables missing after restore';
  END IF;
  EXECUTE format('SELECT count(*) FROM %I.schema_migrations WHERE version = 1', runtime_schema)
    INTO migration_count;
  IF migration_count <> 1 THEN RAISE EXCEPTION 'Expected native migration version 1'; END IF;
  EXECUTE format(
    'SELECT count(*), min(idx), max(idx) FROM %I.audit_log', runtime_schema
  ) INTO audit_count, audit_min, audit_max;
  IF audit_count > 0 AND (audit_min <> 1 OR audit_max <> audit_count) THEN
    RAISE EXCEPTION 'Audit sequence is not contiguous: count %, min %, max %',
      audit_count, audit_min, audit_max;
  END IF;
END $$;
SELECT 'requesters' AS table_name, count(*) AS rows FROM genomeguard_runtime.requesters
UNION ALL SELECT 'requests', count(*) FROM genomeguard_runtime.requests
UNION ALL SELECT 'decisions', count(*) FROM genomeguard_runtime.decisions
UNION ALL SELECT 'epsilon_ledger', count(*) FROM genomeguard_runtime.epsilon_ledger
UNION ALL SELECT 'audit_log', count(*) FROM genomeguard_runtime.audit_log
ORDER BY table_name;
SQL

echo "Verifying the restored PostgreSQL audit hash chain..."
if [[ -n "${GG_AUDIT_CHECKPOINT_FILE:-}" ]]; then
  PYTHONPATH=backend GG_DATABASE_URL="$GG_RESTORE_TEST_URL" \
    python3 scripts/verify_postgres_audit.py --checkpoint "$GG_AUDIT_CHECKPOINT_FILE"
else
  PYTHONPATH=backend GG_DATABASE_URL="$GG_RESTORE_TEST_URL" \
    python3 scripts/verify_postgres_audit.py
fi

echo "Restore smoke check and audit-chain verification passed. External checkpoint verification is required to detect valid-prefix truncation."
