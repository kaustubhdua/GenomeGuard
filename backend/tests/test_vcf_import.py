import ast
import hashlib
from pathlib import Path

import pytest

from app.data import vcf_import
from app.data.vcf_import import ImportValidationError, iter_records, main, parse_gt, read_header


def _vcf(tmp_path: Path, reference: str = "GRCh37") -> Path:
    path = tmp_path / "small-test.vcf"
    path.write_text(
        "##fileformat=VCFv4.2\n"
        f"##reference={reference}\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE_A\tSAMPLE_B\n"
        "22\t100\t.\tA\tG\t.\tPASS\t.\tGT\t0/1\t1/1\n"
        "22\t200\t.\tC\tA,T\t.\tPASS\t.\tGT\t1|2\t0/2\n",
        encoding="utf-8",
    )
    return path


def test_parse_gt_handles_called_missing_and_phased_alleles():
    assert parse_gt("0/1", 1, 1) == (1, 2, False)
    assert parse_gt("1|1", 1, 1) == (2, 2, True)
    assert parse_gt("0/.", 1, 1) == (0, 1, False)
    assert parse_gt("./.", 1, 1) == (None, 0, False)


def test_parse_gt_rejects_allele_not_present_in_record():
    with pytest.raises(ImportValidationError):
        parse_gt("0/2", 1, 1)


def test_vcf_split_alt_records_have_unique_variant_indices(tmp_path):
    path = _vcf(tmp_path)
    _, samples = read_header(path, "GRCh37")
    rows = list(iter_records(path, samples, "GRCh37"))
    assert samples == ["SAMPLE_A", "SAMPLE_B"]
    assert [row["variant_index"] for row in rows] == [0, 1, 2]
    assert [row["variant_key"] for row in rows] == [
        "22:100:A:G", "22:200:C:A", "22:200:C:T"
    ]
    assert rows[0]["calls"] == [(1, 2, False), (2, 2, False)]
    assert rows[1]["calls"] == [(1, 2, True), (0, 2, False)]
    assert rows[2]["calls"] == [(1, 2, True), (1, 2, False)]
    # Independent hand calculation: 3 alternate copies / 4 called alleles = 0.75.
    assert rows[0]["alt_allele_frequency"] == pytest.approx(0.75)
    # For C>A,T, the A ALT has 1/4 copies and T has 2/4 copies.
    assert rows[1]["alt_allele_frequency"] == pytest.approx(0.25)
    assert rows[2]["alt_allele_frequency"] == pytest.approx(0.5)


def test_vcf_assembly_mismatch_fails_closed(tmp_path):
    path = _vcf(tmp_path, "GRCh37")
    with pytest.raises(ImportValidationError, match="assembly mismatch"):
        read_header(path, "GRCh38")


def test_vcf_rejects_coordinates_outside_declared_assembly(tmp_path):
    path = _vcf(tmp_path).with_name("out-of-range.vcf")
    path.write_text(
        _vcf(tmp_path).read_text(encoding="utf-8").replace("22\t200\t", "22\t51304567\t"),
        encoding="utf-8",
    )
    _, samples = read_header(path, "GRCh37")
    with pytest.raises(ImportValidationError, match="invalid position"):
        list(iter_records(path, samples, "GRCh37"))


def test_vcf_dry_run_validates_and_reports_real_counts(tmp_path, capsys):
    path = _vcf(tmp_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = main([
        "--vcf", str(path),
        "--dataset-key", "test-release-chr22",
        "--source-name", "Test fixture only",
        "--source-url", "https://data.example.org/test.vcf",
        "--source-release", "fixture-v1",
        "--retrieved-at", "2026-10-28T12:00:00Z",
        "--assembly", "GRCh37",
        "--expected-sha256", digest,
        "--reuse-statement-url", "https://data.example.org/reuse",
        "--citation", "Test fixture citation",
        "--reviewed-public-research",
        "--dry-run",
    ])
    assert result == 0
    output = capsys.readouterr().out
    assert '"status": "validated_not_imported"' in output
    assert '"sample_count": 2' in output
    assert '"variant_count": 3' in output
    assert digest in output


def test_vcf_import_requires_timezone_aware_retrieval_timestamp(tmp_path, capsys):
    path = _vcf(tmp_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = main([
        "--vcf", str(path),
        "--dataset-key", "test-release-chr22",
        "--source-name", "Test fixture only",
        "--source-url", "https://data.example.org/test.vcf",
        "--source-release", "fixture-v1",
        "--retrieved-at", "2026-10-28T12:00:00",
        "--assembly", "GRCh37",
        "--expected-sha256", digest,
        "--reuse-statement-url", "https://data.example.org/reuse",
        "--citation", "Test fixture citation",
        "--reviewed-public-research",
        "--dry-run",
    ])
    assert result == 2
    assert "retrieval timestamp must include an explicit timezone" in capsys.readouterr().err


def test_vcf_duplicate_detection_is_bounded_and_rejects_duplicate_records(tmp_path):
    original = _vcf(tmp_path).read_text(encoding="utf-8").splitlines()
    duplicate = tmp_path / "duplicate.vcf"
    duplicate.write_text("\n".join(original[:3] + [original[3], original[3], original[4]]) + "\n", encoding="utf-8")
    _, samples = read_header(duplicate, "GRCh37")
    with pytest.raises(ImportValidationError, match="duplicate VCF record"):
        list(iter_records(duplicate, samples, "GRCh37"))


def test_vcf_rejects_unsorted_coordinates(tmp_path):
    original = _vcf(tmp_path).read_text(encoding="utf-8").splitlines()
    unsorted = tmp_path / "unsorted.vcf"
    unsorted.write_text("\n".join(original[:3] + [original[4], original[3]]) + "\n", encoding="utf-8")
    _, samples = read_header(unsorted, "GRCh37")
    with pytest.raises(ImportValidationError, match="sorted by chromosome and position"):
        list(iter_records(unsorted, samples, "GRCh37"))



# A repeat of an already-loaded, byte-identical dataset must be a no-op.
def test_loaded_manifest_import_is_idempotent_without_deleting_or_reimporting(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.data import vcf_import

    path = _vcf(tmp_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    args = SimpleNamespace(
        dataset_key="test-release-chr22",
        source_name="Test source",
        source_url="https://data.example.org/test.vcf",
        source_release="fixture-v1",
        assembly="GRCh37",
        vcf=path,
        retrieved_at="2026-10-28T12:00:00Z",
        reuse_statement_url="https://data.example.org/reuse",
        citation="Test fixture citation",
    )

    class Cursor:
        def __init__(self):
            self.last_row = None
            self.statements = []
            self.call_count_queries = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=None):
            self.statements.append(sql)
            if "SELECT id, source_name, source_url, source_release, reference_assembly" in sql:
                self.last_row = (
                    42, args.source_name, args.source_url, args.source_release, args.assembly,
                    digest, "approved_public_research", "dataset_policy", "loaded",
                    {"reuse_statement_url": args.reuse_statement_url, "citation": args.citation},
                )
            elif "SELECT sample_count, variant_count, genotype_call_count" in sql:
                self.last_row = (2, 3, 5)
            elif "DELETE FROM genomeguard." in sql:
                raise AssertionError("idempotent import must not delete existing data")

        def fetchone(self):
            return self.last_row

        def executemany(self, *_args, **_kwargs):
            raise AssertionError("idempotent import must not insert samples again")

    class Transaction:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def transaction(self):
            return Transaction()

        def cursor(self):
            return self.cursor_instance

    conn = Connection()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")
    monkeypatch.setattr(vcf_import.psycopg, "connect", lambda *_args, **_kwargs: conn)

    result = vcf_import.import_to_database(args, digest, ["SAMPLE_A", "SAMPLE_B"])
    assert result == {
        "dataset_id": "42",
        "status": "loaded",
        "already_loaded": True,
        "sample_count": 2,
        "variant_count": 3,
        "genotype_call_count": 5,
    }



def test_every_vcf_import_batch_passes_source_sample_order():
    tree = ast.parse(Path(vcf_import.__file__).read_text(encoding="utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "write_batch"
    ]
    assert calls
    assert all(len(node.args) == 5 for node in calls)



def test_interrupted_import_resumes_after_last_committed_batch(tmp_path, monkeypatch):
    from types import SimpleNamespace

    path = _vcf(tmp_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    args = SimpleNamespace(
        dataset_key="test-release-chr22",
        source_name="Test source",
        source_url="https://data.example.org/test.vcf",
        source_release="fixture-v1",
        assembly="GRCh37",
        vcf=path,
        retrieved_at="2026-10-28T12:00:00Z",
        reuse_statement_url="https://data.example.org/reuse",
        citation="Test fixture citation",
    )

    class Cursor:
        def __init__(self):
            self.last_row = None
            self.rows = []
            self.rowcount = -1
            self.statements = []
            self.call_count_queries = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=None):
            self.statements.append(sql)
            if "SELECT id, source_name, source_url, source_release, reference_assembly" in sql:
                self.last_row = (
                    42, args.source_name, args.source_url, args.source_release, args.assembly,
                    digest, "approved_public_research", "dataset_policy", "loading",
                    {"reuse_statement_url": args.reuse_statement_url, "citation": args.citation},
                )
            elif "SELECT source_sample_id FROM genomeguard.dataset_samples" in sql:
                self.rows = [("SAMPLE_A",), ("SAMPLE_B",)]
            elif "SELECT id,source_sample_id FROM genomeguard.dataset_samples" in sql:
                self.rows = [(1, "SAMPLE_A"), (2, "SAMPLE_B")]
            elif "coalesce(max(variant_index),-1)" in sql:
                self.last_row = (2, 1)
            elif "SELECT count(*) FROM genomeguard.dataset_genotype_calls" in sql:
                self.call_count_queries += 1
                self.last_row = (3 if self.call_count_queries == 1 else 5,)
            elif "SELECT count(*) FROM genomeguard.dataset_samples" in sql:
                self.last_row = (2,)
            elif "SELECT count(*) FROM genomeguard.dataset_variants" in sql:
                self.last_row = (3,)
            elif "UPDATE genomeguard.variant_dataset_manifest" in sql:
                self.rowcount = 1
            elif "DELETE FROM genomeguard." in sql:
                raise AssertionError("resume must preserve committed batches")

        def fetchone(self):
            return self.last_row

        def fetchall(self):
            return self.rows

        def executemany(self, *_args, **_kwargs):
            raise AssertionError("resume must not reinsert existing samples")

    class Transaction:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def __init__(self):
            self.cur = Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def transaction(self):
            return Transaction()

        def cursor(self):
            return self.cur

    conn = Connection()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")
    monkeypatch.setattr(vcf_import.psycopg, "connect", lambda *_args, **_kwargs: conn)
    records = [
        {"variant_index": 0, "source_record_index": 0},
        {"variant_index": 1, "source_record_index": 1},
        {"variant_index": 2, "source_record_index": 2},
    ]
    monkeypatch.setattr(vcf_import, "iter_records", lambda *_args: iter(records))
    written = []

    def write_batch(_conn, _dataset_id, batch, _sample_map, _samples):
        written.extend(record["variant_index"] for record in batch)
        return len(batch), 2

    monkeypatch.setattr(vcf_import, "write_batch", write_batch)
    result = vcf_import.import_to_database(args, digest, ["SAMPLE_A", "SAMPLE_B"])

    assert written == [2]
    assert result["status"] == "loaded"
    assert result["variant_count"] == 3
    assert result["genotype_call_count"] == 5
    assert not any("DELETE FROM genomeguard." in sql for sql in conn.cur.statements)

def test_import_refuses_to_create_or_self_approve_a_manifest(tmp_path, monkeypatch):
    from types import SimpleNamespace

    path = _vcf(tmp_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    args = SimpleNamespace(
        dataset_key="unreviewed-release",
        source_name="Unreviewed source",
        source_url="https://data.example.org/unreviewed.vcf",
        source_release="fixture-v1",
        assembly="GRCh37",
        vcf=path,
        retrieved_at="2026-10-28T12:00:00Z",
        reuse_statement_url="https://data.example.org/reuse",
        citation="Test fixture citation",
    )

    class Cursor:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=None):
            self.statements.append(sql)
            if "INSERT INTO genomeguard.variant_dataset_manifest" in sql:
                raise AssertionError("importer must never create or self-approve its manifest")

        def fetchone(self):
            return None

    class Transaction:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def __init__(self):
            self.cur = Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def transaction(self):
            return Transaction()

        def cursor(self):
            return self.cur

    conn = Connection()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")
    monkeypatch.setattr(vcf_import.psycopg, "connect", lambda *_args, **_kwargs: conn)

    with pytest.raises(ImportValidationError, match="trusted data steward"):
        vcf_import.import_to_database(args, digest, ["SAMPLE_A", "SAMPLE_B"])
    assert any("SELECT id, source_name, source_url" in sql for sql in conn.cur.statements)
    assert not any("INSERT INTO genomeguard.variant_dataset_manifest" in sql for sql in conn.cur.statements)

