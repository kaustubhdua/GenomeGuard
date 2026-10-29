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
