import hashlib
from pathlib import Path

import pytest

from app.data.vcf_import import ImportValidationError, iter_records, parse_gt, read_header


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



def test_reimport_of_identical_loaded_dataset_is_idempotent(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.data import vcf_import

    vcf = _vcf(tmp_path)
    args = SimpleNamespace(
        vcf=vcf,
        dataset_key="public-phase3-chr22",
        source_name="1000 Genomes Project",
        source_url="https://example.org/source.vcf.gz",
        source_release="phase3-v5b",
        assembly="GRCh37",
        reuse_statement_url="https://example.org/reuse",
        citation="1000 Genomes Project",
    )

    class Cursor:
        def __init__(self):
            self.statements = []
            self.result = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=None):
            self.statements.append(sql)
            if "SELECT id,sample_count,variant_count,genotype_call_count" in sql:
                self.result = (77, 2, 3, 5)
            elif "INSERT INTO genomeguard.variant_dataset_manifest" in sql or "DELETE FROM genomeguard." in sql:
                raise AssertionError("identical loaded artifact must not be reset or rewritten")

        def fetchone(self):
            return self.result

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

    connection = Connection()
    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")
    monkeypatch.setattr(vcf_import.psycopg, "connect", lambda *_args, **_kwargs: connection)

    result = vcf_import.import_to_database(args, "a" * 64, ["SAMPLE_A", "SAMPLE_B"])
    assert result == {
        "dataset_id": "77",
        "status": "loaded",
        "already_loaded": True,
        "sample_count": 2,
        "variant_count": 3,
        "genotype_call_count": 5,
    }
    assert len(connection.cursor_instance.statements) == 1



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
            if "INSERT INTO genomeguard.variant_dataset_manifest" in sql:
                self.last_row = (42,)
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
