"""Local, database-free QC reports for supported VCF files."""
from __future__ import annotations

import argparse
import json
import stat
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.data.vcf_import import (
    ASSEMBLIES,
    ImportValidationError,
    inspect_header,
    iter_records,
    sha256_file,
)

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_VCF_LINE_BYTES = 16 * 1024 * 1024
MAX_SAMPLE_COLUMNS = 10_000
MAX_GENOTYPE_CELLS = 10_000_000


def _check(checks: list[dict], check_id: str, status: str, detail: str) -> None:
    checks.append({"id": check_id, "status": status, "detail": detail})


def validate_vcf(
    path: Path,
    assembly: str,
    expected_sha256: str | None = None,
    *,
    display_name: str | None = None,
    max_file_bytes: int | None = None,
    max_genotype_cells: int | None = MAX_GENOTYPE_CELLS,
) -> dict:
    """Validate a local VCF and summarize measured QC without retaining sample identifiers."""
    checks: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []
    file_info: dict = {"name": display_name or path.name, "size_bytes": None, "sha256": None}
    statistics_report = None
    metadata_report = None
    try:
        input_stat = path.stat()
    except OSError:
        input_stat = None

    if assembly not in ASSEMBLIES:
        _check(checks, "assembly_argument", "failed", "Assembly must be GRCh37 or GRCh38.")
        errors.append("Unsupported reference assembly.")
    elif input_stat is None:
        _check(checks, "file_readable", "failed", "Could not access the input VCF.")
        errors.append("VCF file could not be accessed.")
    elif not stat.S_ISREG(input_stat.st_mode):
        _check(checks, "file_readable", "failed", "The input VCF does not exist or is not a regular file.")
        errors.append("VCF file is missing.")
    elif input_stat.st_size <= 0:
        file_info["size_bytes"] = input_stat.st_size
        _check(checks, "file_readable", "failed", "The input VCF is empty.")
        errors.append("VCF file is empty.")
    elif max_file_bytes is not None and input_stat.st_size > max_file_bytes:
        file_info["size_bytes"] = input_stat.st_size
        _check(checks, "file_readable", "failed", "The input VCF exceeds the configured file-size limit.")
        errors.append("VCF file exceeds the configured size limit.")
    else:
        file_info["size_bytes"] = input_stat.st_size
        _check(checks, "file_readable", "passed", "Input file exists and is non-empty.")
        try:
            digest = sha256_file(path)
            file_info["sha256"] = digest
        except OSError:
            _check(checks, "checksum", "failed", "Could not read the file to calculate SHA-256.")
            errors.append("Could not calculate the input checksum.")
        else:
            if expected_sha256 is None:
                _check(checks, "checksum", "warning", "SHA-256 was calculated, but no expected checksum was supplied.")
                warnings.append("Source checksum was not independently verified.")
            elif len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
                _check(checks, "checksum", "failed", "Expected checksum must be 64 lowercase hexadecimal characters.")
                errors.append("Expected SHA-256 is malformed.")
            elif digest == expected_sha256:
                _check(checks, "checksum", "passed", "Calculated SHA-256 matches the supplied expected checksum.")
            else:
                _check(checks, "checksum", "failed", "Calculated SHA-256 does not match the supplied expected checksum.")
                errors.append("SHA-256 does not match the expected value.")

        if not errors:
            try:
                _, samples, metadata_report = inspect_header(
                    path, assembly, max_line_bytes=MAX_VCF_LINE_BYTES,
                    max_total_bytes=MAX_DECOMPRESSED_BYTES, max_samples=MAX_SAMPLE_COLUMNS,
                )
                metadata_report.pop("_field_schemas", None)
            except (ImportValidationError, OSError, UnicodeError) as error:
                _check(checks, "header_and_assembly", "failed", str(error))
                errors.append("VCF header or assembly validation failed.")
            else:
                _check(checks, "header_and_assembly", "passed",
                       f"VCF declares {assembly}; {len(samples):,} unique sample columns are present.")
                _check(checks, "sample_columns", "passed",
                       f"{len(samples):,} unique sample columns passed identifier checks; identifiers are not included in this report.")
                metadata_keys = (
                    "info_definition_count", "format_definition_count",
                    "filter_definition_count", "contig_definition_count",
                )
                metadata_complete = all(metadata_report[key] > 0 for key in metadata_keys)
                _check(checks, "metadata_completeness",
                       "passed" if metadata_complete else "insufficient_evidence",
                       "INFO, FORMAT, FILTER, and contig definitions are present."
                       if metadata_complete else
                       "Header metadata counts are reported, but one or more definition groups are absent; completeness is not established.")
                counts = {
                    "source_record_count": 0,
                    "split_variant_count": 0,
                    "genotype_cells": 0,
                    "called_genotype_cells": 0,
                    "fully_missing_genotype_cells": 0,
                    "partially_missing_genotype_cells": 0,
                    "missing_alleles": 0,
                    "total_alleles": 0,
                    "unknown_ploidy_genotype_cells": 0,
                    "called_alleles": 0,
                    "alternate_allele_copies": 0,
                }
                chromosomes: Counter[str] = Counter()
                variant_types: Counter[str] = Counter()
                frequency_minimum: float | None = None
                frequency_maximum: float | None = None
                frequency_sum = 0.0
                frequency_count = 0
                quality_minimum: float | None = None
                quality_maximum: float | None = None
                quality_sum = 0.0
                quality_count = 0
                gq_minimum: int | None = None
                gq_maximum: int | None = None
                gq_sum = 0
                gq_count = 0
                gq_missing = 0
                last_source_record = -1
                try:
                    for record in iter_records(
                        path, samples, assembly, max_line_bytes=MAX_VCF_LINE_BYTES,
                        max_total_bytes=MAX_DECOMPRESSED_BYTES,
                    ):
                        source_index = record["source_record_index"]
                        if source_index != last_source_record:
                            counts["source_record_count"] += 1
                            last_source_record = source_index
                        counts["split_variant_count"] += 1
                        if (
                            max_genotype_cells is not None
                            and counts["genotype_cells"] + len(samples) > max_genotype_cells
                        ):
                            raise ImportValidationError(
                                "genotype-cell count exceeds the configured QC processing limit"
                            )
                        counts["partially_missing_genotype_cells"] += record[
                            "partially_missing_genotype_cells"
                        ]
                        counts["missing_alleles"] += record["missing_alleles"]
                        counts["total_alleles"] += record["total_alleles"]
                        counts["unknown_ploidy_genotype_cells"] += record[
                            "unknown_ploidy_genotype_cells"
                        ]
                        chromosomes[record["chromosome"]] += 1
                        ref, alt = record["reference_allele"], record["alternate_allele"]
                        if len(ref) == len(alt) == 1:
                            variant_types["SNP"] += 1
                        elif len(ref) == len(alt):
                            variant_types["MNP"] += 1
                        else:
                            variant_types["INDEL"] += 1
                        for dosage, called_alleles, _ in record["calls"]:
                            counts["genotype_cells"] += 1
                            counts["called_alleles"] += called_alleles
                            counts["alternate_allele_copies"] += dosage or 0
                            if called_alleles:
                                counts["called_genotype_cells"] += 1
                            else:
                                counts["fully_missing_genotype_cells"] += 1
                        frequency = record["alt_allele_frequency"]
                        if frequency is not None:
                            frequency_minimum = frequency if frequency_minimum is None else min(frequency_minimum, frequency)
                            frequency_maximum = frequency if frequency_maximum is None else max(frequency_maximum, frequency)
                            frequency_sum += frequency
                            frequency_count += 1
                        quality = record["quality_score"]
                        if quality is not None:
                            quality_minimum = quality if quality_minimum is None else min(quality_minimum, quality)
                            quality_maximum = quality if quality_maximum is None else max(quality_maximum, quality)
                            quality_sum += quality
                            quality_count += 1
                        gq = record["genotype_quality"]
                        if gq["measured_cells"]:
                            gq_minimum = gq["minimum"] if gq_minimum is None else min(gq_minimum, gq["minimum"])
                            gq_maximum = gq["maximum"] if gq_maximum is None else max(gq_maximum, gq["maximum"])
                            gq_sum += gq["sum"]
                            gq_count += gq["measured_cells"]
                        if gq["missing_cells"] is not None:
                            gq_missing += gq["missing_cells"]
                except (ImportValidationError, OSError, UnicodeError) as error:
                    _check(checks, "records_and_genotypes", "failed", str(error))
                    errors.append("VCF records or genotype validation failed.")
                else:
                    _check(checks, "records_and_genotypes", "passed",
                           "All records passed coordinate, allele, sort-order, duplicate, FORMAT, and genotype checks.")
                    try:
                        final_digest = sha256_file(path)
                    except OSError:
                        final_digest = None
                    if final_digest is None:
                        _check(checks, "checksum_stability", "failed",
                               "Could not reread the VCF to verify checksum stability.")
                        errors.append("Could not verify the source file remained unchanged.")
                    elif final_digest != file_info["sha256"]:
                        _check(checks, "checksum_stability", "failed",
                               "The VCF changed while it was being validated.")
                        errors.append("The source file changed during validation.")
                    else:
                        _check(checks, "checksum_stability", "passed",
                               "The file checksum was unchanged across validation.")
                    missing_rate = (
                        counts["fully_missing_genotype_cells"] / counts["genotype_cells"]
                        if counts["genotype_cells"] else None
                    )
                    missing_allele_rate = (
                        counts["missing_alleles"] / counts["total_alleles"]
                        if counts["total_alleles"] else None
                    )
                    statistics_report = {
                        **counts,
                        "chromosome_variant_counts": dict(sorted(
                            chromosomes.items(), key=lambda item: (
                                23 if item[0] == "X" else 24 if item[0] == "Y"
                                else 25 if item[0] == "MT" else int(item[0])
                            )
                        )),
                        "variant_type_counts": dict(sorted(variant_types.items())),
                        "fully_missing_genotype_cell_rate": missing_rate,
                        "partially_missing_genotype_cells": counts["partially_missing_genotype_cells"],
                        "missing_allele_rate": missing_allele_rate,
                        "alternate_allele_frequency": {
                            "minimum": frequency_minimum,
                            "mean": frequency_sum / frequency_count if frequency_count else None,
                            "maximum": frequency_maximum,
                            "measured_alternate_alleles": frequency_count,
                        },
                        "variant_quality_score": {
                            "minimum": quality_minimum,
                            "mean": quality_sum / quality_count if quality_count else None,
                            "maximum": quality_maximum,
                            "measured_split_variants": quality_count,
                            "missing_quality_count": counts["split_variant_count"] - quality_count,
                        },
                        "genotype_quality_score": {
                            "minimum": gq_minimum,
                            "mean": gq_sum / gq_count if gq_count else None,
                            "maximum": gq_maximum,
                            "measured_genotype_cells": gq_count,
                            "missing_genotype_cells": gq_missing if gq_count or gq_missing else None,
                            "available": bool(gq_count or gq_missing),
                        },
                    }

    if not any(item["id"] == "source_and_reuse_review" for item in checks):
        _check(checks, "source_and_reuse_review", "not_assessed",
               "This local QC report cannot determine licensing, consent, or permitted reuse.")
    if expected_sha256 is None:
        warnings.append("Source checksum was not independently verified.")
    warnings.append("A structurally valid VCF is not approved for import; source terms and a steward-reviewed manifest are still required.")

    failed = any(item["status"] == "failed" for item in checks)
    warned = any(item["status"] in {"warning", "insufficient_evidence"} for item in checks)
    return {
        "report_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "FAILED" if failed else "PASSED_WITH_WARNINGS" if warned else "PASSED",
        "import_eligibility": "NOT_ESTABLISHED",
        "file": file_info,
        "reference_assembly": assembly,
        "metadata": metadata_report,
        "checks": checks,
        "statistics": statistics_report,
        "warnings": list(dict.fromkeys(warnings)),
        "errors": errors,
        "recommendations": [
            "Verify the source terms, permitted reuse scope, and exact artifact provenance with a trusted steward.",
            "Treat aggregate metrics as descriptive QC; no universal acceptance thresholds are applied.",
            "Use the importer only after a separately reviewed manifest and approved workflow are in place.",
        ],
        "blocking_requirements": [
            "Independent review of the exact source and reuse terms.",
            "A trusted steward-approved manifest matching the file checksum and assembly.",
            "Authorized database role and successful import count reconciliation.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vcf", required=True, type=Path, help="Local .vcf or gzip-compressed .vcf.gz file")
    parser.add_argument("--assembly", required=True, choices=sorted(ASSEMBLIES))
    parser.add_argument("--expected-sha256", help="Optional independently obtained lowercase SHA-256")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this local path instead of stdout")
    args = parser.parse_args(argv)
    report = validate_vcf(args.vcf, args.assembly, args.expected_sha256)
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.resolve() == args.vcf.resolve():
            print("QC report output must not overwrite the source VCF.", file=sys.stderr)
            return 2
        try:
            args.output.write_text(serialized, encoding="utf-8")
        except OSError as error:
            print(f"could not write QC report: {error}", file=sys.stderr)
            return 2
        print(f"QC report written to {args.output}")
        print(f"Validation status: {report['status']}; import eligibility: NOT ESTABLISHED")
    else:
        print(serialized, end="")
    return 0 if report["status"] != "FAILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
