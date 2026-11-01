from __future__ import annotations

import csv

import pytest

from app.data.gnomad_reference import ReferenceImportError, iter_frequency_rows


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
