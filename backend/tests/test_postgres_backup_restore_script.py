"""Safety contracts for the PostgreSQL backup/restore drill script."""
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "postgres_backup_restore_check.sh"
).read_text(encoding="utf-8")


def test_backup_restore_targets_the_actual_postgres_runtime_schema():
    assert "genomeguard_runtime.schema_migrations" not in SCRIPT  # looked up dynamically below
    assert "runtime_schema text := 'genomeguard_runtime'" in SCRIPT
    assert "genomeguard_runtime.requesters" in SCRIPT
    assert "genomeguard_runtime.requests" in SCRIPT
    assert "genomeguard_runtime.decisions" in SCRIPT
    assert "genomeguard_runtime.epsilon_ledger" in SCRIPT
    assert "genomeguard_runtime.audit_log" in SCRIPT
    assert "public.schema_migrations" not in SCRIPT
    assert "public.audit_log" not in SCRIPT


def test_backup_restore_refuses_source_database_and_nonempty_target():
    assert "source_identity" in SCRIPT and "target_identity" in SCRIPT
    assert "Refusing to restore into the source database" in SCRIPT
    assert "target_objects" in SCRIPT
    assert "Refusing restore: target database contains" in SCRIPT


def test_backup_is_encrypted_before_persisting_and_plaintext_is_not_written_to_disk():
    assert "pg_dump --dbname=" in SCRIPT
    assert "| age --encrypt" in SCRIPT
    assert "age --decrypt" in SCRIPT
    assert "pg_restore --dbname=" in SCRIPT
    assert "umask 077" in SCRIPT
    assert "trap 'rm -rf \"$backup_dir\"' EXIT" in SCRIPT


def test_restore_check_keeps_audit_chain_validation_boundary_explicit():
    assert "audit_min <> 1 OR audit_max <> audit_count" in SCRIPT
    assert "Verify the full audit hash chain with the application verifier" in SCRIPT
