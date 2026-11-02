from __future__ import annotations

import gzip
import hashlib
import json

from app.data.vcf_qc import main, validate_vcf

HEADER = """##fileformat=VCFv4.2
##reference=GRCh38
##contig=<ID=1,length=248956422>
##INFO=<ID=DP,Number=1,Type=Integer,Description="Read depth">
##FILTER=<ID=PASS,Description="All filters passed">
##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE_A\tSAMPLE_B
"""


def _vcf(path):
    path.write_text(
        HEADER
        + "1\t100\t.\tA\tG,T\t50\tPASS\t.\tGT\t0/1\t1/2\n"
        + "1\t101\t.\tAC\tA\t30\tPASS\t.\tGT\t./.\t1/1\n",
        encoding="utf-8",
    )
    return path


def test_local_qc_reports_real_counts_and_does_not_expose_sample_identifiers(tmp_path):
    path = _vcf(tmp_path / "cohort.vcf")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    report = validate_vcf(path, "GRCh38", digest)

    assert report["status"] == "PASSED"
    assert report["import_eligibility"] == "NOT_ESTABLISHED"
    assert report["file"]["sha256"] == digest
    assert report["statistics"]["source_record_count"] == 2
    assert report["statistics"]["split_variant_count"] == 3
    assert report["statistics"]["genotype_cells"] == 6
    assert report["statistics"]["called_genotype_cells"] == 5
    assert report["statistics"]["fully_missing_genotype_cells"] == 1
    assert report["statistics"]["fully_missing_genotype_cell_rate"] == 1 / 6
    assert report["statistics"]["partially_missing_genotype_cells"] == 0
    assert report["statistics"]["missing_allele_rate"] == 1 / 6
    assert report["statistics"]["chromosome_variant_counts"] == {"1": 3}
    assert report["statistics"]["variant_type_counts"] == {"INDEL": 1, "SNP": 2}
    assert report["statistics"]["variant_quality_score"] == {
        "minimum": 30.0, "mean": 130 / 3, "maximum": 50.0,
        "measured_split_variants": 3, "missing_quality_count": 0,
    }
    assert all(check["status"] in {"passed", "not_assessed"} for check in report["checks"])
    assert report["metadata"]["vcf_version"] == "VCFv4.2"
    assert report["metadata"]["format_definition_count"] == 1
    assert "SAMPLE_A" not in json.dumps(report)
    assert "SAMPLE_B" not in json.dumps(report)


def test_local_qc_reads_gzip_vcf_without_external_tools(tmp_path):
    path = tmp_path / "cohort.vcf.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write(HEADER + "2\t20\t.\tC\tT\t.\tPASS\t.\tGT\t0/1\t./.\n")

    report = validate_vcf(path, "GRCh38")

    assert report["status"] == "PASSED_WITH_WARNINGS"
    assert report["statistics"]["source_record_count"] == 1
    assert report["statistics"]["split_variant_count"] == 1
    assert report["statistics"]["fully_missing_genotype_cell_rate"] == 0.5
    assert next(check for check in report["checks"] if check["id"] == "checksum")["status"] == "warning"


def test_local_qc_fails_checksum_assembly_and_malformed_records(tmp_path):
    path = _vcf(tmp_path / "invalid.vcf")
    path.write_text(
        HEADER
        + "1\t100\t.\tA\tG\t50\tPASS\t.\tGT\t0/1\t0/0\n"
        + "1\t100\t.\tA\tG\t50\tPASS\t.\tGT\t0/1\t0/0\n",
        encoding="utf-8",
    )

    checksum_mismatch = validate_vcf(path, "GRCh38", "0" * 64)
    assert checksum_mismatch["status"] == "FAILED"
    assert "SHA-256 does not match the expected value." in checksum_mismatch["errors"]

    assembly_mismatch = validate_vcf(path, "GRCh37")
    assert assembly_mismatch["status"] == "FAILED"
    assert "VCF header or assembly validation failed." in assembly_mismatch["errors"]

    malformed = validate_vcf(path, "GRCh38")
    assert malformed["status"] == "FAILED"
    assert "VCF records or genotype validation failed." in malformed["errors"]
    record_check = next(check for check in malformed["checks"] if check["id"] == "records_and_genotypes")
    assert record_check["status"] == "failed"


def test_local_qc_cli_writes_downloadable_json_report(tmp_path, capsys):
    source = _vcf(tmp_path / "cohort.vcf")
    output = tmp_path / "qc-report.json"

    result = main([
        "--vcf", str(source), "--assembly", "GRCh38",
        "--expected-sha256", hashlib.sha256(source.read_bytes()).hexdigest(),
        "--output", str(output),
    ])

    assert result == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "PASSED"
    assert "import eligibility: NOT ESTABLISHED" in capsys.readouterr().out
    assert main(["--vcf", str(source), "--assembly", "GRCh38", "--output", str(source)]) == 2


def test_local_qc_missing_file_returns_structured_failure(tmp_path):
    report = validate_vcf(tmp_path / "missing.vcf", "GRCh38")

    assert report["status"] == "FAILED"
    assert report["statistics"] is None
    assert next(check for check in report["checks"] if check["id"] == "file_readable")["status"] == "failed"


def test_local_qc_reports_partial_missingness_and_genotype_quality(tmp_path):
    path = tmp_path / "gq.vcf"
    path.write_text(
        HEADER.replace(
            "##FORMAT=<ID=GT,Number=1,Type=String,Description=\"Genotype\">",
            "##FORMAT=<ID=GT,Number=1,Type=String,Description=\"Genotype\">\n"
            "##FORMAT=<ID=GQ,Number=1,Type=Integer,Description=\"Genotype quality\">",
        ) + "1\t100\t.\tA\tG\t40\tPASS\t.\tGT:GQ\t0/.:30\t.:.\n",
        encoding="utf-8",
    )

    report = validate_vcf(path, "GRCh38")

    stats = report["statistics"]
    assert stats["partially_missing_genotype_cells"] == 1
    assert stats["fully_missing_genotype_cells"] == 1
    assert stats["missing_allele_rate"] == 0.5
    assert stats["unknown_ploidy_genotype_cells"] == 1
    assert stats["genotype_quality_score"] == {
        "minimum": 30, "mean": 30, "maximum": 30,
        "measured_genotype_cells": 1, "missing_genotype_cells": 1, "available": True,
    }


def test_local_qc_enforces_genotype_cell_and_decompressed_input_limits(tmp_path, monkeypatch):
    import app.data.vcf_qc as qc

    path = _vcf(tmp_path / "bounded.vcf")
    too_many_cells = validate_vcf(path, "GRCh38", max_genotype_cells=1)
    assert too_many_cells["status"] == "FAILED"
    assert "configured QC processing limit" in next(
        check["detail"] for check in too_many_cells["checks"]
        if check["id"] == "records_and_genotypes"
    )

    compressed = tmp_path / "expanded.vcf.gz"
    with gzip.open(compressed, "wt", encoding="utf-8") as stream:
        stream.write(HEADER + "1\t100\t.\tA\tG\t.\tPASS\t.\tGT\t0/1\t0/0\n")
    monkeypatch.setattr(qc, "MAX_DECOMPRESSED_BYTES", 200)
    decompression_limited = validate_vcf(compressed, "GRCh38")
    assert decompression_limited["status"] == "FAILED"
    assert "configured size limit" in next(
        check["detail"] for check in decompression_limited["checks"]
        if check["id"] == "header_and_assembly"
    )
