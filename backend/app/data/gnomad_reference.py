"""Import approved gnomAD aggregate frequencies and export them to Excel.

Input is a normalized TSV, one row per variant/population. This module never reads
sample columns or creates participant/genotype records.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import psycopg

REQUIRED_COLUMNS = (
    "chromosome", "position", "reference_allele", "alternate_allele",
    "population", "allele_count", "allele_number", "allele_frequency",
)
OPTIONAL_COLUMNS = ("homozygote_count",)
CHROMOSOMES = {str(i) for i in range(1, 23)} | {"X", "Y", "MT"}
ALLELE = re.compile(r"^[ACGTN]+$")
EXCEL_MAX_ROWS = 1_048_576
EXCEL_DATA_ROWS = EXCEL_MAX_ROWS - 1
BATCH_SIZE = 5_000


class ReferenceImportError(ValueError):
    """Raised when aggregate reference input or import state is invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_frequency_rows(path: Path) -> Iterator[tuple]:
    """Stream strict normalized TSV rows; rejects identifiers and unknown columns."""
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None:
            raise ReferenceImportError("input TSV is empty")
        fields = set(reader.fieldnames)
        required = set(REQUIRED_COLUMNS)
        allowed = required | set(OPTIONAL_COLUMNS)
        if not required.issubset(fields):
            raise ReferenceImportError(
                "TSV is missing required columns: " + ", ".join(sorted(required - fields))
            )
        if fields - allowed:
            raise ReferenceImportError(
                "TSV contains unsupported columns (sample/individual data is not accepted): "
                + ", ".join(sorted(fields - allowed))
            )
        count = 0
        for line_number, row in enumerate(reader, start=2):
            chrom = (row["chromosome"] or "").removeprefix("chr").upper()
            ref = row["reference_allele"] or ""
            alt = row["alternate_allele"] or ""
            pop = (row["population"] or "").strip()
            try:
                pos = int(row["position"])
                ac = int(row["allele_count"])
                an = int(row["allele_number"])
                af = float(row["allele_frequency"])
                nhom = (
                    int(row["homozygote_count"])
                    if row.get("homozygote_count") not in (None, "", ".") else None
                )
            except (TypeError, ValueError) as exc:
                raise ReferenceImportError(f"invalid numeric value on TSV line {line_number}") from exc
            if chrom == "M":
                chrom = "MT"
            if chrom not in CHROMOSOMES or pos < 1:
                raise ReferenceImportError(f"invalid chromosome/position on TSV line {line_number}")
            if not ALLELE.fullmatch(ref) or not ALLELE.fullmatch(alt) or ref == alt:
                raise ReferenceImportError(f"invalid REF/ALT on TSV line {line_number}")
            if not pop or len(pop) > 80:
                raise ReferenceImportError(f"invalid population on TSV line {line_number}")
            if ac < 0 or an <= 0 or ac > an or not 0 <= af <= 1:
                raise ReferenceImportError(f"invalid AC/AN/AF on TSV line {line_number}")
            if abs(af - ac / an) > 0.00001:
                raise ReferenceImportError(f"AF does not match AC/AN on TSV line {line_number}")
            if nhom is not None and nhom < 0:
                raise ReferenceImportError(f"invalid homozygote count on TSV line {line_number}")
            count += 1
            yield (chrom, pos, ref, alt, pop, ac, an, af, nhom)
        if count == 0:
            raise ReferenceImportError("TSV contains no aggregate frequency rows")




def validate_input(args) -> dict:
    """Preflight a normalized TSV without database access or writes."""
    if not args.input.is_file() or args.input.stat().st_size == 0:
        raise ReferenceImportError("input TSV is missing or empty")
    digest = sha256_file(args.input)
    if args.expected_sha256 and digest != args.expected_sha256:
        raise ReferenceImportError("input TSV SHA-256 does not match --expected-sha256")
    chromosomes: Counter[str] = Counter()
    populations: Counter[str] = Counter()
    row_count = 0
    zero_frequency_rows = 0
    min_frequency = 1.0
    max_frequency = 0.0
    for row in iter_frequency_rows(args.input):
        chrom, _, _, _, population, _, _, frequency, _ = row
        row_count += 1
        chromosomes[chrom] += 1
        populations[population] += 1
        zero_frequency_rows += frequency == 0
        min_frequency = min(min_frequency, frequency)
        max_frequency = max(max_frequency, frequency)
    return {
        "report_status": "validated_input_only",
        "dataset_key": args.dataset_key,
        "reference_assembly": "GRCh38",
        "source_file": args.input.name,
        "source_sha256": digest,
        "file_bytes": args.input.stat().st_size,
        "format": "normalized aggregate-frequency TSV",
        "source_variant_population_rows": row_count,
        "chromosome_row_counts": dict(sorted(chromosomes.items())),
        "population_row_counts": dict(sorted(populations.items())),
        "allele_frequency": {
            "minimum": min_frequency, "maximum": max_frequency,
            "zero_frequency_rows": zero_frequency_rows,
        },
        "approval_or_import_performed": False,
    }


def import_to_database(args) -> dict:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ReferenceImportError("DATABASE_URL must be configured in the trusted server environment")
    if not args.input.is_file() or args.input.stat().st_size == 0:
        raise ReferenceImportError("input TSV is missing or empty")
    digest = sha256_file(args.input)
    if args.expected_sha256 and digest != args.expected_sha256:
        raise ReferenceImportError("input TSV SHA-256 does not match --expected-sha256")
    inserted = 0
    input_rows = 0
    chromosome_counts: Counter[str] = Counter()
    population_counts: Counter[str] = Counter()
    batch: list[tuple] = []
    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE genomeguard_reference_importer")
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, reference_assembly, data_use_review, import_status
                       FROM genomeguard.population_reference_manifest
                       WHERE dataset_key = %s""",
                    (args.dataset_key,),
                )
                manifest = cur.fetchone()
                if not manifest:
                    raise ReferenceImportError("register the dataset manifest before importing")
                dataset_id, assembly, review, status = manifest
                if assembly != "GRCh38":
                    raise ReferenceImportError("gnomAD v4 input must use GRCh38")
                if review != "approved_public_research":
                    raise ReferenceImportError("manifest has not been approved for public research use")
                if status not in {"validated", "loading"}:
                    raise ReferenceImportError("manifest must be validated or loading before import")
                for row in iter_frequency_rows(args.input):
                    input_rows += 1
                    chromosome_counts[row[0]] += 1
                    population_counts[row[4]] += 1
                    batch.append((dataset_id, *row))
                    if len(batch) >= BATCH_SIZE:
                        cur.executemany(
                            """INSERT INTO genomeguard.population_variant_frequency
                               (dataset_id, chromosome, position, reference_allele,
                                alternate_allele, population, allele_count, allele_number,
                                allele_frequency, homozygote_count)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (dataset_id, chromosome, position, reference_allele,
                                            alternate_allele, population) DO NOTHING""",
                            batch,
                        )
                        inserted += max(cur.rowcount, 0)
                        batch.clear()
                if batch:
                    cur.executemany(
                        """INSERT INTO genomeguard.population_variant_frequency
                           (dataset_id, chromosome, position, reference_allele,
                            alternate_allele, population, allele_count, allele_number,
                            allele_frequency, homozygote_count)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (dataset_id, chromosome, position, reference_allele,
                                        alternate_allele, population) DO NOTHING""",
                        batch,
                    )
                    inserted += max(cur.rowcount, 0)
                cur.execute(
                    """SELECT count(*) FROM genomeguard.population_variant_frequency
                       WHERE dataset_id = %s""",
                    (dataset_id,),
                )
                database_rows = int(cur.fetchone()[0])
    return {
        "report_status": "imported_pending_steward_reconciliation",
        "dataset_key": args.dataset_key,
        "reference_assembly": assembly,
        "source_file": args.input.name,
        "source_sha256": digest,
        "source_variant_population_rows": input_rows,
        "inserted_rows": inserted,
        "rows_not_inserted_due_to_conflict": max(input_rows - inserted, 0),
        "database_rows_after_import": database_rows,
        "chromosome_row_counts": dict(sorted(chromosome_counts.items())),
        "population_row_counts": dict(sorted(population_counts.items())),
        "manifest_updated": False,
    }


def export_to_excel(args) -> dict:
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise ReferenceImportError(
            "Excel export requires the optional dependency: pip install .[reference]"
        ) from exc
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ReferenceImportError("DATABASE_URL must be configured in the trusted server environment")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    headers = (
        "chromosome", "position", "reference_allele", "alternate_allele",
        "population", "allele_count", "allele_number", "allele_frequency", "homozygote_count",
    )
    workbook = Workbook(write_only=True)
    sheet_number = 0
    sheet = None
    sheet_rows = 0
    total = 0

    def new_sheet():
        nonlocal sheet_number, sheet, sheet_rows
        sheet_number += 1
        sheet = workbook.create_sheet(f"Frequencies_{sheet_number:03d}")
        sheet.append(headers)
        sheet_rows = 0

    with psycopg.connect(database_url) as conn:
        with conn.cursor(name="gnomad_excel_export") as cur:
            cur.execute(
                """SELECT f.chromosome, f.position, f.reference_allele,
                          f.alternate_allele, f.population, f.allele_count,
                          f.allele_number, f.allele_frequency, f.homozygote_count
                   FROM genomeguard.population_variant_frequency f
                   JOIN genomeguard.population_reference_manifest m ON m.id=f.dataset_id
                   WHERE m.dataset_key=%s AND m.data_use_review='approved_public_research'
                         AND m.import_status='loaded'
                   ORDER BY f.chromosome, f.position, f.reference_allele,
                            f.alternate_allele, f.population""",
                (args.dataset_key,),
            )
            while True:
                rows = cur.fetchmany(BATCH_SIZE)
                if not rows:
                    break
                for row in rows:
                    if sheet is None or sheet_rows >= EXCEL_DATA_ROWS:
                        new_sheet()
                    sheet.append(row)
                    sheet_rows += 1
                    total += 1
    if total == 0:
        raise ReferenceImportError(
            "no approved, loaded aggregate rows found; export is not generated"
        )
    workbook.save(args.output)
    return {"output": str(args.output), "rows": total, "sheets": sheet_number}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="gnomAD aggregate frequency import/export")
    commands = parser.add_subparsers(dest="command", required=True)
    val = commands.add_parser("validate", help="validate a normalized aggregate TSV without database writes")
    val.add_argument("--input", type=Path, required=True)
    val.add_argument("--dataset-key", required=True)
    val.add_argument("--expected-sha256")
    val.add_argument("--report", type=Path, help="also write the aggregate validation report as JSON")
    val.set_defaults(func=validate_input)
    imp = commands.add_parser("import", help="import a normalized aggregate TSV")
    imp.add_argument("--input", type=Path, required=True)
    imp.add_argument("--dataset-key", required=True)
    imp.add_argument("--expected-sha256")
    imp.add_argument("--report", type=Path, help="also write the aggregate reconciliation report as JSON")
    imp.set_defaults(func=import_to_database)
    exp = commands.add_parser("export-xlsx", help="export an approved loaded dataset to Excel")
    exp.add_argument("--dataset-key", required=True)
    exp.add_argument("--output", type=Path, required=True)
    exp.add_argument("--report", type=Path, help="also write the export summary as JSON")
    exp.set_defaults(func=export_to_excel)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        import json
        result = args.func(args)
        serialized = json.dumps(result, indent=2, sort_keys=True)
        if getattr(args, "report", None):
            report_path = args.report.resolve()
            protected_paths = [
                path.resolve() for path in (
                    getattr(args, "input", None), getattr(args, "output", None)
                ) if path is not None
            ]
            if report_path in protected_paths:
                raise ReferenceImportError("report path must not overwrite an input or export file")
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(serialized + "\n", encoding="utf-8")
        print(serialized)
    except (ReferenceImportError, OSError, psycopg.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
