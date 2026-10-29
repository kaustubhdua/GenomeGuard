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
