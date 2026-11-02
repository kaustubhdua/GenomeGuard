"""Import a reviewed ClinVar variant-summary snapshot for exact GRCh38 allele lookups.

Only aggregate variant-level assertions are stored. This module never imports genotypes,
participant records, or raw sample data.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import psycopg

CHROMOSOMES = {str(i) for i in range(1, 23)} | {"X", "Y", "MT"}
ALLELE = re.compile(r"^[ACGTN]+$")
BATCH_SIZE = 2_000
SOURCE_NAME = "NCBI ClinVar"
SOURCE_URL = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz"
REQUIRED_COLUMNS = {
    "Assembly", "Chromosome", "Start", "Stop", "ReferenceAllele", "AlternateAllele",
    "VariationID", "ClinicalSignificance", "ReviewStatus", "LastEvaluated",
    "PhenotypeList", "GeneSymbol", "NumberSubmitters",
}


class ClinVarImportError(ValueError):
    """Raised when a ClinVar snapshot or manifest is not importable."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def _text_list(value: str | None) -> list[str]:
    if not value or value.strip() in {"", "-", "not provided", "not specified"}:
        return []
    return list(dict.fromkeys(part.strip() for part in value.split("|") if part.strip()))


def _optional_date(value: str | None, counts: Counter) -> date | None:
    value = (value or "").strip()
    if not value or value == "-":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        counts["invalid_last_evaluated"] += 1
        return None


def iter_annotation_rows(path: Path, counts: Counter | None = None) -> Iterator[dict]:
    """Stream exact GRCh38 substitutions; indels are excluded to avoid HGVS/VCF shifts."""
    stats = counts if counts is not None else Counter()
    with open_text(path) as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None:
            raise ClinVarImportError("ClinVar summary is empty")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ClinVarImportError(
                "ClinVar summary is missing columns: " + ", ".join(sorted(missing))
            )
        for line_number, row in enumerate(reader, start=2):
            stats["source_rows"] += 1
            if (row.get("Assembly") or "").strip() != "GRCh38":
                stats["other_assembly"] += 1
                continue
            chromosome = (row.get("Chromosome") or "").strip().upper().removeprefix("CHR")
            if chromosome == "M":
                chromosome = "MT"
            reference = (row.get("ReferenceAllele") or "").strip().upper()
            alternate = (row.get("AlternateAllele") or "").strip().upper()
            try:
                position = int(row.get("Start") or "")
                stop = int(row.get("Stop") or "")
                variation_id = int(row.get("VariationID") or "")
            except ValueError:
                stats["invalid_coordinates_or_id"] += 1
                continue
            if (chromosome not in CHROMOSOMES or position < 1 or variation_id < 1
                    or stop < position or len(reference) > 50 or len(alternate) > 50
                    or not ALLELE.fullmatch(reference) or not ALLELE.fullmatch(alternate)
                    or reference == alternate):
                stats["invalid_or_unsupported_allele"] += 1
                continue
            # ClinVar variant_summary coordinates follow HGVS conventions, while VCF
            # coordinates use left-normalized alleles. Equal-length substitutions have
            # unambiguous matching positions; defer indels until a canonical normalizer exists.
            if len(reference) != len(alternate) or stop - position + 1 != len(reference):
                stats["indel_or_complex_representation"] += 1
                continue
            significance = (row.get("ClinicalSignificance") or "").strip()
            if not significance or significance == "-":
                stats["no_classification"] += 1
                continue
            submitters_text = (row.get("NumberSubmitters") or "").strip()
            try:
                submitters = int(submitters_text) if submitters_text not in {"", "-"} else None
            except ValueError:
                submitters = None
                stats["invalid_submitter_count"] += 1
            if submitters is not None and submitters < 0:
                submitters = None
                stats["invalid_submitter_count"] += 1
            stats["eligible_rows"] += 1
            yield {
                "chromosome": chromosome,
                "position": position,
                "reference_allele": reference,
                "alternate_allele": alternate,
                "variation_id": variation_id,
                "clinical_significance": significance,
                "review_status": (row.get("ReviewStatus") or "").strip(),
                "last_evaluated": _optional_date(row.get("LastEvaluated"), stats),
                "conditions": _text_list(row.get("PhenotypeList")),
                "gene_symbols": _text_list(row.get("GeneSymbol")),
                "submitter_count": submitters,
                "source_line": line_number,
            }


def validate_input(args) -> dict:
    """Validate a snapshot without database access or writes."""
    if not args.input.is_file() or args.input.stat().st_size == 0:
        raise ClinVarImportError("ClinVar summary file is missing or empty")
    digest = sha256_file(args.input)
    if args.expected_sha256 and digest != args.expected_sha256.lower():
        raise ClinVarImportError("ClinVar summary SHA-256 does not match --expected-sha256")
    counts: Counter = Counter()
    for _ in iter_annotation_rows(args.input, counts):
        pass
    return {
        "report_status": "validated_input_only",
        "dataset_key": args.dataset_key,
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "reference_assembly": "GRCh38",
        "source_file": args.input.name,
        "source_sha256": digest,
        "file_bytes": args.input.stat().st_size,
        "counts": dict(sorted(counts.items())),
        "approval_or_import_performed": False,
        "indel_support": "excluded until VCF/HGVS allele normalization is implemented",
    }


def import_to_database(args) -> dict:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ClinVarImportError("DATABASE_URL must be configured in the trusted server environment")
    if not args.input.is_file() or args.input.stat().st_size == 0:
        raise ClinVarImportError("ClinVar summary file is missing or empty")
    digest = sha256_file(args.input)
    if args.expected_sha256 and digest != args.expected_sha256.lower():
        raise ClinVarImportError("ClinVar summary SHA-256 does not match --expected-sha256")
    counts: Counter = Counter()
    inserted = 0
    batch: list[tuple] = []
    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE genomeguard_clinvar_importer")
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, reference_assembly, data_use_review, import_status,
                              source_name, source_url, source_release, file_sha256
                       FROM genomeguard.clinvar_annotation_manifest
                       WHERE dataset_key = %s""",
                    (args.dataset_key,),
                )
                manifest = cur.fetchone()
                if not manifest:
                    raise ClinVarImportError("register the ClinVar manifest before importing")
                (dataset_id, assembly, review, status, source_name, source_url,
                 manifest_release, manifest_sha256) = manifest
                if assembly != "GRCh38":
                    raise ClinVarImportError("this ClinVar importer supports GRCh38 snapshots only")
                if review != "approved_public_research":
                    raise ClinVarImportError("manifest has not been approved for public research use")
                if status not in {"validated", "loading"}:
                    raise ClinVarImportError("manifest must be validated or loading before import")
                if source_name != SOURCE_NAME or source_url != SOURCE_URL:
                    raise ClinVarImportError("manifest source must match the official NCBI ClinVar summary")
                if manifest_release != args.source_release:
                    raise ClinVarImportError("source release does not match the registered manifest")
                if manifest_sha256 != digest:
                    raise ClinVarImportError("source SHA-256 does not match the registered manifest")
                for row in iter_annotation_rows(args.input, counts):
                    batch.append((
                        dataset_id, row["chromosome"], row["position"], row["reference_allele"],
                        row["alternate_allele"], row["variation_id"], row["clinical_significance"],
                        row["review_status"], row["last_evaluated"],
                        json.dumps(row["conditions"]), json.dumps(row["gene_symbols"]),
                        row["submitter_count"],
                    ))
                    if len(batch) >= BATCH_SIZE:
                        cur.executemany(
                            """INSERT INTO genomeguard.clinvar_variant_annotation
                               (dataset_id, chromosome, position, reference_allele, alternate_allele,
                                variation_id, clinical_significance, review_status, last_evaluated,
                                conditions, gene_symbols, submitter_count)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                               ON CONFLICT (dataset_id, chromosome, position, reference_allele,
                                            alternate_allele, variation_id) DO NOTHING""",
                            batch,
                        )
                        inserted += max(cur.rowcount, 0)
                        batch.clear()
                if batch:
                    cur.executemany(
                        """INSERT INTO genomeguard.clinvar_variant_annotation
                           (dataset_id, chromosome, position, reference_allele, alternate_allele,
                            variation_id, clinical_significance, review_status, last_evaluated,
                            conditions, gene_symbols, submitter_count)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                           ON CONFLICT (dataset_id, chromosome, position, reference_allele,
                                        alternate_allele, variation_id) DO NOTHING""",
                        batch,
                    )
                    inserted += max(cur.rowcount, 0)
                cur.execute(
                    """SELECT count(*) FROM genomeguard.clinvar_variant_annotation
                       WHERE dataset_id = %s""",
                    (dataset_id,),
                )
                database_rows = int(cur.fetchone()[0])
    return {
        "report_status": "imported_pending_steward_reconciliation",
        "dataset_key": args.dataset_key,
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "source_release": args.source_release,
        "reference_assembly": assembly,
        "source_file": args.input.name,
        "source_sha256": digest,
        "counts": dict(sorted(counts.items())),
        "inserted_rows": inserted,
        "rows_not_inserted_due_to_conflict": max(counts["eligible_rows"] - inserted, 0),
        "database_rows_after_import": database_rows,
        "manifest_updated": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import reviewed ClinVar variant-level annotations")
    commands = parser.add_subparsers(dest="command", required=True)
    val = commands.add_parser("validate", help="validate a ClinVar summary without database writes")
    val.add_argument("--input", type=Path, required=True)
    val.add_argument("--dataset-key", required=True)
    val.add_argument("--expected-sha256")
    val.add_argument("--report", type=Path)
    val.set_defaults(func=validate_input)
    imp = commands.add_parser("import", help="import a steward-approved GRCh38 snapshot")
    imp.add_argument("--input", type=Path, required=True)
    imp.add_argument("--dataset-key", required=True)
    imp.add_argument("--source-release", required=True)
    imp.add_argument("--expected-sha256")
    imp.add_argument("--report", type=Path)
    imp.set_defaults(func=import_to_database)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.func(args)
        serialized = json.dumps(result, indent=2, sort_keys=True)
        if args.report:
            report_path = args.report.resolve()
            if report_path == args.input.resolve():
                raise ClinVarImportError("report path must not overwrite the ClinVar source file")
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(serialized + "\n", encoding="utf-8")
        print(serialized)
    except (ClinVarImportError, OSError, psycopg.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

