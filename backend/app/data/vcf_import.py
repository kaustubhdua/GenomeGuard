"""Provenance-gated VCF importer. Never inserts consent records or fabricated samples."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urlparse

import psycopg

ASSEMBLIES = {"GRCh37", "GRCh38"}
CHROM_LENGTHS = {
    "GRCh37": {
        "1": 249250621, "2": 243199373, "3": 198022430, "4": 191154276,
        "5": 180915260, "6": 171115067, "7": 159138663, "8": 146364022,
        "9": 141213431, "10": 135534747, "11": 135006516, "12": 133851895,
        "13": 115169878, "14": 107349540, "15": 102531392, "16": 90354753,
        "17": 81195210, "18": 78077248, "19": 59128983, "20": 63025520,
        "21": 48129895, "22": 51304566, "X": 155270560, "Y": 59373566, "MT": 16569,
    },
    "GRCh38": {
        "1": 248956422, "2": 242193529, "3": 198295559, "4": 190214555,
        "5": 181538259, "6": 170805979, "7": 159345973, "8": 145138636,
        "9": 138394717, "10": 133797422, "11": 135086622, "12": 133275309,
        "13": 114364328, "14": 107043718, "15": 101991189, "16": 90338345,
        "17": 83257441, "18": 80373285, "19": 58617616, "20": 64444167,
        "21": 46709983, "22": 50818468, "X": 156040895, "Y": 57227415, "MT": 16569,
    },
}
ALLELE_RE = re.compile(r"^[ACGTN]+$")


class ImportValidationError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_vcf(path: Path):
    with path.open("rb") as stream:
        compressed = stream.read(2) == b"\x1f\x8b"
    return gzip.open(path, "rt", encoding="utf-8") if compressed else path.open("rt", encoding="utf-8")


def bounded_lines(stream, max_line_bytes: int | None, max_total_bytes: int | None):
    total_bytes = 0
    while True:
        raw = stream.readline(max_line_bytes + 1 if max_line_bytes is not None else -1)
        if not raw:
            return
        line_bytes = len(raw.encode("utf-8"))
        if max_line_bytes is not None and line_bytes > max_line_bytes:
            raise ImportValidationError("VCF line exceeds the configured size limit")
        total_bytes += line_bytes
        if max_total_bytes is not None and total_bytes > max_total_bytes:
            raise ImportValidationError("decompressed VCF exceeds the configured size limit")
        yield raw


def infer_assembly(headers: list[str]) -> str | None:
    text = "\n".join(headers).lower()
    matches = set()
    if any(x in text for x in ("grch38", "hg38")):
        matches.add("GRCh38")
    if any(x in text for x in ("grch37", "hg19", "human_g1k_v37", "b37")):
        matches.add("GRCh37")
    if any(x in text for x in ("t2t-chm13", "chm13v2")):
        matches.add("T2T-CHM13")
    # Contradictory assembly labels are ambiguous and must never be resolved by precedence.
    return next(iter(matches)) if len(matches) == 1 else None


def parse_gt(gt: str, alt_index: int, max_allele_index: int) -> tuple[int | None, int, bool]:
    if not gt or gt == ".":
        return None, 0, False
    if "/" in gt and "|" in gt:
        raise ImportValidationError("mixed phased/unphased genotype separators")
    phased = "|" in gt
    alleles = re.split(r"[|/]", gt)
    if len(alleles) not in (1, 2):
        raise ImportValidationError("only haploid/diploid calls are supported")
    called = []
    for allele in alleles:
        if allele == ".":
            continue
        if (
            not allele.isdigit()
            or len(allele) > len(str(max_allele_index))
            or int(allele) > max_allele_index
        ):
            raise ImportValidationError("invalid genotype allele index")
        called.append(int(allele))
    if not called:
        return None, 0, phased
    return sum(a == alt_index for a in called), len(called), phased


def inspect_header(
    path: Path,
    expected_assembly: str,
    *,
    max_line_bytes: int | None = None,
    max_total_bytes: int | None = None,
    max_samples: int | None = None,
) -> tuple[list[str], list[str], dict]:
    headers: list[str] = []
    with open_vcf(path) as stream:
        for raw in bounded_lines(stream, max_line_bytes, max_total_bytes):
            line = raw.rstrip("\r\n")
            if line.startswith("##"):
                headers.append(line)
            elif line.startswith("#CHROM"):
                versions = [line.partition("=")[2] for line in headers if line.startswith("##fileformat=")]
                if len(versions) != 1 or not re.fullmatch(r"VCFv4\.[0-9]+", versions[0]):
                    raise ImportValidationError("VCF must declare exactly one supported fileformat version")
                if not headers or headers[0] != f"##fileformat={versions[0]}":
                    raise ImportValidationError("VCF fileformat declaration must be the first metadata line")
                actual = infer_assembly(headers)
                if actual is None:
                    raise ImportValidationError("VCF header lacks recognizable assembly metadata")
                if actual != expected_assembly:
                    raise ImportValidationError(f"assembly mismatch: expected {expected_assembly}, found {actual}")
                columns = line.split("\t")
                if len(columns) < 10 or columns[:8] != [
                    "#CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"
                ] or columns[8] != "FORMAT":
                    raise ImportValidationError("invalid VCF header; FORMAT and at least one sample are required")
                samples = columns[9:]
                if (
                    any(
                        not s or s in {".", "0"} or len(s) > 200 or s != s.strip()
                        or any(ord(char) < 32 or ord(char) == 127 for char in s)
                        for s in samples
                    )
                    or len(samples) != len(set(samples))
                ):
                    raise ImportValidationError("invalid, empty, or duplicate sample identifiers")
                if max_samples is not None and len(samples) > max_samples:
                    raise ImportValidationError("sample count exceeds the configured limit")
                definitions: dict[str, set[str]] = {"INFO": set(), "FORMAT": set(), "FILTER": set(), "contig": set()}
                for header in headers:
                    match = re.match(r"^##(INFO|FORMAT|FILTER|contig)=<ID=([^,>]+)", header)
                    if match:
                        section, identifier = match.groups()
                        if identifier in definitions[section]:
                            raise ImportValidationError(f"duplicate {section} header definition")
                        definitions[section].add(identifier)
                reference = [actual] if any(
                    header.startswith(("##reference=", "##assembly=")) for header in headers
                ) else []
                metadata = {
                    "vcf_version": versions[0],
                    "sample_count": len(samples),
                    "reference_declarations": reference,
                    "reference_declaration_present": bool(reference),
                    "metadata_line_count": len(headers),
                    "contig_definition_count": len(definitions["contig"]),
                    "info_definition_count": len(definitions["INFO"]),
                    "format_definition_count": len(definitions["FORMAT"]),
                    "filter_definition_count": len(definitions["FILTER"]),
                    "format_definitions": sorted(definitions["FORMAT"]),
                    "info_definitions": sorted(definitions["INFO"]),
                    "filter_definitions": sorted(definitions["FILTER"]),
                }
                return headers, samples, metadata
    raise ImportValidationError("VCF is missing a #CHROM header")


def read_header(path: Path, expected_assembly: str) -> tuple[list[str], list[str]]:
    headers, samples, _ = inspect_header(path, expected_assembly)
    return headers, samples


def _validate_info(info: str) -> None:
    if info == ".":
        return
    entries = info.split(";")
    if any(not entry or entry.count("=") > 1 for entry in entries):
        raise ImportValidationError("invalid INFO field structure")
    for entry in entries:
        key, separator, value = entry.partition("=")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", key) or (separator and not value):
            raise ImportValidationError("invalid INFO field structure")


def iter_records(
    path: Path,
    samples: list[str],
    assembly: str,
    *,
    max_line_bytes: int | None = None,
    max_total_bytes: int | None = None,
):
    # Keep duplicate-detection memory bounded: require coordinate-sorted VCF input and
    # retain only keys at the current chromosome/position, not every variant in the file.
    chrom_order = {str(i): i for i in range(1, 23)} | {"X": 23, "Y": 24, "MT": 25}
    last_coordinate: tuple[str, int] | None = None
    last_order: tuple[int, int] | None = None
    seen_at_coordinate: set[tuple[str, str]] = set()
    source_index = 0
    variant_index = 0
    header_seen = False
    with open_vcf(path) as stream:
        for raw in bounded_lines(stream, max_line_bytes, max_total_bytes):
            line = raw.rstrip("\r\n")
            if not line or line.startswith("#"):
                if line.startswith("#CHROM"):
                    if header_seen:
                        raise ImportValidationError("duplicate VCF column header")
                    header_seen = True
                continue
            fields = line.split("\t")
            if len(fields) != 9 + len(samples):
                raise ImportValidationError("VCF row has the wrong number of columns")
            chrom, pos_text, _, ref, alt_text, quality_text, filter_text, info_text, fmt = fields[:9]
            if filter_text != "." and (
                not filter_text or any(
                    not re.fullmatch(r"[A-Za-z0-9_.:]+", value)
                    for value in filter_text.split(";")
                ) or len(set(filter_text.split(";"))) != len(filter_text.split(";"))
            ):
                raise ImportValidationError("invalid FILTER field")
            _validate_info(info_text)
            if quality_text == ".":
                quality = None
            else:
                try:
                    quality = float(quality_text)
                except ValueError as exc:
                    raise ImportValidationError("invalid QUAL score") from exc
                if not math.isfinite(quality) or quality < 0:
                    raise ImportValidationError("invalid QUAL score")
            chrom = chrom.removeprefix("chr").upper()
            if chrom == "M":
                chrom = "MT"
            if not re.fullmatch(r"(?:[1-9]|1[0-9]|2[0-2]|X|Y|M|MT)", chrom):
                raise ImportValidationError(f"unsupported chromosome: {chrom}")
            if not re.fullmatch(r"[0-9]+", pos_text):
                raise ImportValidationError("invalid position")
            if len(pos_text) > 9:
                raise ImportValidationError("invalid position")
            pos = int(pos_text)
            if pos < 1 or pos > CHROM_LENGTHS[assembly].get(chrom, 0) or not ALLELE_RE.fullmatch(ref):
                raise ImportValidationError("invalid position/reference allele")
            alts = alt_text.split(",")
            if not alts or any(not ALLELE_RE.fullmatch(a) or a == ref for a in alts) or len(set(alts)) != len(alts):
                raise ImportValidationError("invalid, duplicate, symbolic, or reference-equal ALT allele")
            order = (chrom_order[chrom], pos)
            coordinate = (chrom, pos)
            if last_order is not None and order < last_order:
                raise ImportValidationError("VCF records must be sorted by chromosome and position")
            if coordinate != last_coordinate:
                seen_at_coordinate.clear()
                last_coordinate = coordinate
                last_order = order
            key = (ref, alt_text)
            if key in seen_at_coordinate:
                raise ImportValidationError("duplicate VCF record")
            seen_at_coordinate.add(key)
            formats = fmt.split(":")
            if (
                not fmt or any(not field for field in formats)
                or len(formats) != len(set(formats)) or formats.count("GT") != 1
            ):
                raise ImportValidationError("FORMAT must contain exactly one GT field and no duplicates")
            gt_index = formats.index("GT")
            gq_index = formats.index("GQ") if "GQ" in formats else None
            genotypes = []
            genotype_qualities: list[int] = []
            for sample_cell in fields[9:]:
                values = sample_cell.split(":")
                if sample_cell != "." and len(values) != len(formats):
                    raise ImportValidationError("sample FORMAT value count does not match FORMAT fields")
                if sample_cell == ".":
                    values = ["."] * len(formats)
                if gt_index >= len(values):
                    raise ImportValidationError("sample has no GT value")
                genotypes.append(values[gt_index])
                if gq_index is not None and values[gq_index] != ".":
                    if (
                        len(values[gq_index]) > 10
                        or not re.fullmatch(r"[0-9]+", values[gq_index])
                    ):
                        raise ImportValidationError("invalid genotype quality (GQ)")
                    quality_value = int(values[gq_index])
                    if quality_value > 2_147_483_647:
                        raise ImportValidationError("invalid genotype quality (GQ)")
                    genotype_qualities.append(quality_value)
            for alt_index, alt in enumerate(alts, start=1):
                calls = [parse_gt(gt, alt_index, len(alts)) for gt in genotypes]
                partial_missing_cells = 0
                missing_alleles = 0
                total_alleles = 0
                unknown_ploidy_cells = 0
                for gt, (_, called, _) in zip(genotypes, calls, strict=True):
                    ploidy = 0 if gt in {"", "."} else len(re.split(r"[|/]", gt))
                    if ploidy == 0:
                        unknown_ploidy_cells += 1
                    total_alleles += ploidy
                    missing_alleles += ploidy - called
                    if 0 < called < ploidy:
                        partial_missing_cells += 1
                called_alleles = sum(called for _, called, _ in calls)
                alt_copies = sum(dosage or 0 for dosage, called, _ in calls if called)
                yield {
                    "source_record_index": source_index,
                    "variant_index": variant_index,
                    "chromosome": chrom,
                    "position": pos,
                    "reference_allele": ref,
                    "alternate_allele": alt,
                    "quality_score": quality,
                    "filter": filter_text,
                    "info": info_text,
                    "variant_key": f"{chrom}:{pos}:{ref}:{alt}",
                    "alt_allele_frequency": alt_copies / called_alleles if called_alleles else None,
                    "called_allele_count": called_alleles,
                    "calls": calls,
                    "partially_missing_genotype_cells": partial_missing_cells,
                    "missing_alleles": missing_alleles,
                    "total_alleles": total_alleles,
                    "unknown_ploidy_genotype_cells": unknown_ploidy_cells,
                    "genotype_quality": {
                        "minimum": min(genotype_qualities) if genotype_qualities else None,
                        "sum": sum(genotype_qualities),
                        "mean": sum(genotype_qualities) / len(genotype_qualities) if genotype_qualities else None,
                        "maximum": max(genotype_qualities) if genotype_qualities else None,
                        "measured_cells": len(genotype_qualities),
                        "missing_cells": len(samples) - len(genotype_qualities) if gq_index is not None else None,
                    },
                }
                variant_index += 1
            source_index += 1
    if source_index == 0:
        raise ImportValidationError("VCF contains no variant records")


def validate_args(args) -> None:
    if not args.reviewed_public_research:
        raise ImportValidationError("explicit source reuse review is required")
    if not args.vcf.is_file() or args.vcf.stat().st_size == 0:
        raise ImportValidationError("VCF file is missing or empty")
    if not re.fullmatch(r"[0-9a-f]{64}", args.expected_sha256):
        raise ImportValidationError("expected SHA-256 must be 64 lowercase hex characters")
    for url in (args.source_url, args.reuse_statement_url):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ImportValidationError("source and reuse-statement URLs must be HTTPS")
    if not args.dataset_key.strip() or not args.source_name.strip() or not args.source_release.strip():
        raise ImportValidationError("dataset key, source name, and release are required")
    try:
        retrieved_at = datetime.fromisoformat(args.retrieved_at.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ImportValidationError("retrieval timestamp must be an ISO-8601 datetime with timezone") from exc
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ImportValidationError("retrieval timestamp must include an explicit timezone")
    if retrieved_at > datetime.now(UTC).replace(microsecond=0):
        raise ImportValidationError("retrieval timestamp cannot be in the future")


def import_to_database(args, digest: str, samples: list[str]) -> dict:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ImportValidationError("DATABASE_URL must be set in the trusted server environment")
    metadata = {
        "reuse_statement_url": args.reuse_statement_url,
        "citation": args.citation,
        "source_file_name": args.vcf.name,
        "source_file_bytes": args.vcf.stat().st_size,
        "retrieved_at": datetime.fromisoformat(args.retrieved_at.replace("Z", "+00:00")).astimezone(UTC).isoformat(),
        "importer_version": "1.0",
        "model": "normalized per-sample/per-ALT genotype calls",
    }
    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE genomeguard_importer")
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, source_name, source_url, source_release, reference_assembly,
                              file_sha256, data_use_review, consent_basis, import_status, metadata
                       FROM genomeguard.variant_dataset_manifest
                       WHERE dataset_key=%s FOR UPDATE""",
                    (args.dataset_key,),
                )
                row = cur.fetchone()
                if not row:
                    raise ImportValidationError(
                        "dataset must be registered and approved by a trusted data steward before import"
                    )
                (dataset_id, source_name, source_url, source_release, assembly,
                 registered_sha, review_status, consent_basis, import_status, reviewed_metadata) = row
                if (source_name != args.source_name or source_url != args.source_url
                        or source_release != args.source_release or assembly != args.assembly
                        or registered_sha != digest):
                    raise ImportValidationError("source metadata or checksum does not match the reviewed manifest")
                if review_status != "approved_public_research" or consent_basis != "dataset_policy":
                    raise ImportValidationError("manifest is not approved for dataset-policy public research")
                if isinstance(reviewed_metadata, str):
                    reviewed_metadata = json.loads(reviewed_metadata)
                if (reviewed_metadata.get("reuse_statement_url") != args.reuse_statement_url
                        or reviewed_metadata.get("citation") != args.citation):
                    raise ImportValidationError("reuse statement or citation differs from the reviewed manifest")
                if import_status == "loaded":
                    cur.execute(
                        """SELECT sample_count, variant_count, genotype_call_count
                           FROM genomeguard.variant_dataset_manifest WHERE id=%s""",
                        (dataset_id,),
                    )
                    counts = cur.fetchone()
                    cur.execute(
                        """SELECT
                             (SELECT count(*) FROM genomeguard.dataset_samples WHERE dataset_id=%s),
                             (SELECT count(*) FROM genomeguard.dataset_variants WHERE dataset_id=%s),
                             (SELECT count(*) FROM genomeguard.dataset_genotype_calls
                               WHERE dataset_id=%s AND called_alleles>0)""",
                        (dataset_id, dataset_id, dataset_id),
                    )
                    measured = cur.fetchone()
                    if not counts or tuple(counts) != tuple(measured or ()):
                        raise ImportValidationError(
                            "loaded manifest counts do not reconcile with normalized genotype tables"
                        )
                    if counts[0] != len(samples) or not all(counts):
                        raise ImportValidationError(
                            "loaded dataset sample set or counts do not match the source VCF"
                        )
                    return {
                        "dataset_id": str(dataset_id), "status": "loaded", "already_loaded": True,
                        "sample_count": counts[0], "variant_count": counts[1],
                        "genotype_call_count": counts[2],
                    }
                cur.execute(
                    """UPDATE genomeguard.variant_dataset_manifest
                       SET import_status='loading', updated_at=now(), metadata=metadata || %s::jsonb
                       WHERE id=%s AND data_use_review='approved_public_research'
                         AND consent_basis='dataset_policy' AND import_status <> 'loaded'""",
                    (json.dumps(metadata), dataset_id),
                )
                if cur.rowcount != 1:
                    raise ImportValidationError("manifest could not enter loading state")
                cur.execute("SELECT source_sample_id FROM genomeguard.dataset_samples WHERE dataset_id=%s",
                            (dataset_id,))
                existing_samples = [row[0] for row in cur.fetchall()]
                if existing_samples and set(existing_samples) != set(samples):
                    raise ImportValidationError("resumed import sample identifiers do not match the source VCF")
                if not existing_samples:
                    cur.executemany(
                        "INSERT INTO genomeguard.dataset_samples(dataset_id,source_sample_id) VALUES (%s,%s)",
                        [(dataset_id, sample) for sample in samples],
                    )
                cur.execute("SELECT id,source_sample_id FROM genomeguard.dataset_samples WHERE dataset_id=%s",
                            (dataset_id,))
                sample_map = {sample: sid for sid, sample in cur.fetchall()}
                if set(sample_map) != set(samples) or len(sample_map) != len(samples):
                    raise ImportValidationError("database sample set does not reconcile with source VCF")
                cur.execute("SELECT count(*),coalesce(max(variant_index),-1) FROM genomeguard.dataset_variants WHERE dataset_id=%s",
                            (dataset_id,))
                existing_variant_count, last_variant_index = cur.fetchone()
                if existing_variant_count != last_variant_index + 1:
                    raise ImportValidationError("existing variant checkpoint is not contiguous; manual recovery required")
                cur.execute("SELECT count(*) FROM genomeguard.dataset_genotype_calls WHERE dataset_id=%s AND called_alleles>0",
                            (dataset_id,))
                existing_call_count = cur.fetchone()[0]

        # Each committed batch is a durable checkpoint. A retry starts after the last
        # committed variant index instead of deleting/reloading the whole cohort.
        variant_count = existing_variant_count
        genotype_count = existing_call_count
        batch_size = 100
        batch = []
        for record in iter_records(args.vcf, samples, args.assembly):
            if record["variant_index"] <= last_variant_index:
                continue
            batch.append(record)
            if len(batch) >= batch_size:
                v, g = write_batch(conn, dataset_id, batch, sample_map, samples)
                variant_count += v
                genotype_count += g
                batch.clear()
        if batch:
            v, g = write_batch(conn, dataset_id, batch, sample_map, samples)
            variant_count += v
            genotype_count += g

        if sha256_file(args.vcf) != digest:
            raise ImportValidationError("source file changed during import; manifest remains unpublished")

        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM genomeguard.dataset_samples WHERE dataset_id=%s", (dataset_id,))
                sample_count = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM genomeguard.dataset_variants WHERE dataset_id=%s", (dataset_id,))
                measured_variants = cur.fetchone()[0]
                cur.execute("""SELECT count(*) FROM genomeguard.dataset_genotype_calls
                                WHERE dataset_id=%s AND called_alleles>0""", (dataset_id,))
                measured_calls = cur.fetchone()[0]
                if sample_count != len(samples) or measured_variants != variant_count or measured_calls != genotype_count:
                    raise ImportValidationError("database count reconciliation failed")
                if not sample_count or not measured_variants or not measured_calls:
                    raise ImportValidationError("refusing to publish an empty sample/variant/call set")
                cur.execute(
                    """UPDATE genomeguard.variant_dataset_manifest
                    SET sample_count=%s,variant_count=%s,genotype_call_count=%s,
                        import_status='loaded',imported_at=now(),updated_at=now()
                    WHERE id=%s AND import_status='loading'""",
                    (sample_count, measured_variants, measured_calls, dataset_id),
                )
                if cur.rowcount != 1:
                    raise ImportValidationError("manifest release transition failed")
        return {"dataset_id": str(dataset_id), "status": "loaded", "sample_count": sample_count,
                "variant_count": measured_variants, "genotype_call_count": measured_calls}


def write_batch(conn, dataset_id, records, sample_map, samples):
    variants_written = 0
    calls_written = 0
    with conn.transaction():
        with conn.cursor() as cur:
            for record in records:
                cur.execute(
                    """INSERT INTO genomeguard.dataset_variants
                    (dataset_id,variant_index,variant_key,chromosome,position,reference_allele,
                     alternate_allele,alt_allele_frequency,called_allele_count)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (dataset_id, record["variant_index"], record["variant_key"],
                     record["chromosome"], record["position"], record["reference_allele"],
                     record["alternate_allele"], record["alt_allele_frequency"],
                     record["called_allele_count"]),
                )
                variant_id = cur.fetchone()[0]
                variants_written += 1
                rows = []
                for sample, (dosage, called, phased) in zip(samples, record["calls"], strict=True):
                    rows.append((dataset_id, sample_map[sample], variant_id, dosage, called, phased,
                                 record["source_record_index"]))
                    if called > 0:
                        calls_written += 1
                cur.executemany(
                    """INSERT INTO genomeguard.dataset_genotype_calls
                    (dataset_id,sample_id,variant_id,alt_dosage,called_alleles,phased,source_record_index)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""", rows
                )
    return variants_written, calls_written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vcf", required=True, type=Path)
    parser.add_argument("--dataset-key", required=True)
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--source-release", required=True)
    parser.add_argument("--retrieved-at", required=True, help="ISO-8601 retrieval timestamp including timezone, e.g. 2026-10-29T08:30:00Z")
    parser.add_argument("--assembly", required=True, choices=sorted(ASSEMBLIES))
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--reuse-statement-url", required=True)
    parser.add_argument("--citation", required=True)
    parser.add_argument("--reviewed-public-research", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        validate_args(args)
        digest = sha256_file(args.vcf)
        if digest != args.expected_sha256:
            raise ImportValidationError("SHA-256 mismatch")
        _, samples = read_header(args.vcf, args.assembly)
        variants = sum(1 for _ in iter_records(args.vcf, samples, args.assembly))
        if args.dry_run:
            print(json.dumps({"status": "validated_not_imported", "sha256": digest,
                              "sample_count": len(samples), "variant_count": variants,
                              "assembly": args.assembly}, indent=2))
            return 0
        print(json.dumps(import_to_database(args, digest, samples), indent=2))
        return 0
    except (ImportValidationError, OSError, psycopg.Error) as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
