"""Safety contracts for the PostgreSQL backup/restore drill script."""
from pathlib import Path
import subprocess

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "postgres_backup_restore_check.sh"
SCRIPT = SCRIPT_PATH.read_text(encoding="utf-8")


def test_backup_restore_script_has_valid_bash_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT_PATH)], check=True, capture_output=True, text=True)


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



def test_restore_drill_runs_the_application_audit_chain_verifier():
    assert "scripts/verify_postgres_audit.py" in SCRIPT
    assert 'GG_DATABASE_URL="$GG_RESTORE_TEST_URL"' in SCRIPT
    assert "GG_AUDIT_CHECKPOINT_FILE" in SCRIPT



def test_audit_verifier_is_read_only_and_does_not_run_migrations():
    verifier = (
        Path(__file__).resolve().parents[2] / "scripts" / "verify_postgres_audit.py"
    ).read_text(encoding="utf-8")
    assert 'options="-c default_transaction_read_only=on"' in verifier
    assert "PostgresStore" not in verifier
    assert "genomeguard_runtime.audit_log" in verifier
    assert "from app.core.audit_chain import canonical_json, verify" in verifier
