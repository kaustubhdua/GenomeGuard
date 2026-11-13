from __future__ import annotations

import csv
import hashlib
from types import SimpleNamespace

import pytest

from app.data.gnomad_reference import (
    ReferenceImportError,
    import_to_database,
    iter_frequency_rows,
    validate_manifest_checksum,
)


def _write_tsv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def test_iter_frequency_rows_normalizes_chromosome_and_mitochondrial_alias(tmp_path):
    path = tmp_path / "frequencies.tsv"
    columns = [
        "chromosome", "position", "reference_allele", "alternate_allele",
        "population", "allele_count", "allele_number", "allele_frequency",
    ]
    _write_tsv(path, columns, [{
        "chromosome": "chr1", "position": "123", "reference_allele": "A",
        "alternate_allele": "G", "population": "afr", "allele_count": "2",
        "allele_number": "100", "allele_frequency": "0.02",
    }])
    assert list(iter_frequency_rows(path)) == [("1", 123, "A", "G", "afr", 2, 100, 0.02, None)]


def test_rejects_individual_or_unknown_columns(tmp_path):
    path = tmp_path / "unsafe.tsv"
    columns = [
        "chromosome", "position", "reference_allele", "alternate_allele",
        "population", "allele_count", "allele_number", "allele_frequency", "sample_id",
    ]
    _write_tsv(path, columns, [{
        "chromosome": "1", "position": "1", "reference_allele": "A",
        "alternate_allele": "G", "population": "afr", "allele_count": "1",
        "allele_number": "2", "allele_frequency": "0.5", "sample_id": "S1",
    }])
    with pytest.raises(ReferenceImportError, match="unsupported columns"):
        list(iter_frequency_rows(path))


def test_rejects_frequency_that_does_not_match_counts(tmp_path):
    path = tmp_path / "bad.tsv"
    columns = [
        "chromosome", "position", "reference_allele", "alternate_allele",
        "population", "allele_count", "allele_number", "allele_frequency",
    ]
    _write_tsv(path, columns, [{
        "chromosome": "1", "position": "1", "reference_allele": "A",
        "alternate_allele": "G", "population": "afr", "allele_count": "1",
        "allele_number": "2", "allele_frequency": "0.8",
    }])
    with pytest.raises(ReferenceImportError, match="AF does not match"):
        list(iter_frequency_rows(path))


def test_manifest_checksum_must_be_present_and_match():
    digest = "a" * 64
    assert validate_manifest_checksum(digest, digest) is None


def test_manifest_checksum_rejects_missing_pin():
    with pytest.raises(ReferenceImportError, match="does not pin"):
        validate_manifest_checksum("a" * 64, None)


def test_manifest_checksum_rejects_malformed_pin():
    with pytest.raises(ReferenceImportError, match="invalid artifact SHA-256"):
        validate_manifest_checksum("a" * 64, "not-a-sha256")


def test_manifest_checksum_rejects_artifact_mismatch():
    with pytest.raises(ReferenceImportError, match="does not match the registered manifest"):
        validate_manifest_checksum("a" * 64, "b" * 64)


def test_import_fails_before_writes_when_manifest_checksum_differs(tmp_path, monkeypatch):
    path = tmp_path / "frequencies.tsv"
    columns = [
        "chromosome", "position", "reference_allele", "alternate_allele",
        "population", "allele_count", "allele_number", "allele_frequency",
    ]
    _write_tsv(path, columns, [{
        "chromosome": "1", "position": "1", "reference_allele": "A",
        "alternate_allele": "G", "population": "afr", "allele_count": "1",
        "allele_number": "2", "allele_frequency": "0.5",
    }])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_sha256 = "b" * 64
    assert digest != manifest_sha256

    class FakeCursor:
        rowcount = 0

        def __init__(self):
            self.executemany_called = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            return None

        def fetchone(self):
            return ("dataset-id", "GRCh38", "approved_public_research", "validated", manifest_sha256)

        def executemany(self, *_args):
            self.executemany_called = True
            raise AssertionError("no rows may be written for a manifest checksum mismatch")

    class FakeConnection:
        def __init__(self):
            self.fake_cursor = FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def transaction(self):
            return self

        def cursor(self):
            return self.fake_cursor

    connection = FakeConnection()
    monkeypatch.setenv("GG_IMPORT_DATABASE_URL", "postgresql://test.invalid/test")
    monkeypatch.setattr(
        "app.data.gnomad_reference.psycopg.connect",
        lambda *_args, **_kwargs: connection,
    )
    args = SimpleNamespace(input=path, dataset_key="fixture", expected_sha256=None)

    with pytest.raises(ReferenceImportError, match="does not match the registered manifest"):
        import_to_database(args)
    assert connection.fake_cursor.executemany_called is False
