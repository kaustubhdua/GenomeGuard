"""Provenance-gated VCF importer. Never inserts consent records or fabricated samples."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
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


def infer_assembly(headers: list[str]) -> str | None:
    text = "\n".join(headers).lower()
    if any(x in text for x in ("grch38", "hg38")):
        return "GRCh38"
    if any(x in text for x in ("grch37", "hg19", "human_g1k_v37", "b37")):
        return "GRCh37"
    if any(x in text for x in ("t2t-chm13", "chm13v2")):
        return "T2T-CHM13"
    return None


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
        if not allele.isdigit() or int(allele) > max_allele_index:
            raise ImportValidationError("invalid genotype allele index")
        called.append(int(allele))
    if not called:
        return None, 0, phased
    return sum(a == alt_index for a in called), len(called), phased


def read_header(path: Path, expected_assembly: str) -> tuple[list[str], list[str]]:
    headers: list[str] = []
    with open_vcf(path) as stream:
        for raw in stream:
            line = raw.rstrip("\r\n")
            if line.startswith("##"):
                headers.append(line)
            elif line.startswith("#CHROM"):
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
                if any(not s or s in {".", "0"} or len(s) > 200 for s in samples) or len(samples) != len(set(samples)):
                    raise ImportValidationError("empty or duplicate sample identifiers")
                return headers, samples
    raise ImportValidationError("VCF is missing a #CHROM header")


def iter_records(path: Path, samples: list[str], assembly: str):
    seen: set[tuple[str, int, str, str]] = set()
    source_index = 0
    variant_index = 0
    with open_vcf(path) as stream:
        for raw in stream:
            line = raw.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) != 9 + len(samples):
                raise ImportValidationError("VCF row has the wrong number of columns")
            chrom, pos_text, _, ref, alt_text, _, _, _, fmt = fields[:9]
            chrom = chrom.removeprefix("chr").upper()
            if chrom == "M":
                chrom = "MT"
            if not re.fullmatch(r"(?:[1-9]|1[0-9]|2[0-2]|X|Y|M|MT)", chrom):
                raise ImportValidationError(f"unsupported chromosome: {chrom}")
            try:
                pos = int(pos_text)
            except ValueError as exc:
                raise ImportValidationError("invalid position") from exc
            if pos < 1 or pos > CHROM_LENGTHS[assembly].get(chrom, 0) or not ALLELE_RE.fullmatch(ref):
                raise ImportValidationError("invalid position/reference allele")
            alts = alt_text.split(",")
            if not alts or any(not ALLELE_RE.fullmatch(a) or a == ref for a in alts) or len(set(alts)) != len(alts):
                raise ImportValidationError("invalid, duplicate, symbolic, or reference-equal ALT allele")
            key = (chrom, pos, ref, alt_text)
            if key in seen:
                raise ImportValidationError("duplicate VCF record")
            seen.add(key)
            formats = fmt.split(":")
            if "GT" not in formats:
                raise ImportValidationError("GT is missing from FORMAT")
            gt_index = formats.index("GT")
            genotypes = []
            for sample_cell in fields[9:]:
                values = sample_cell.split(":")
                if gt_index >= len(values):
                    raise ImportValidationError("sample has no GT value")
                genotypes.append(values[gt_index])
            for alt_index, alt in enumerate(alts, start=1):
                calls = [parse_gt(gt, alt_index, len(alts)) for gt in genotypes]
                called_alleles = sum(called for _, called, _ in calls)
                alt_copies = sum(dosage or 0 for dosage, called, _ in calls if called)
                yield {
                    "source_record_index": source_index,
                    "variant_index": variant_index,
                    "chromosome": chrom,
                    "position": pos,
                    "reference_allele": ref,
                    "alternate_allele": alt,
                    "variant_key": f"{chrom}:{pos}:{ref}:{alt}",
                    "alt_allele_frequency": alt_copies / called_alleles if called_alleles else None,
                    "called_allele_count": called_alleles,
                    "calls": calls,
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


def import_to_database(args, digest: str, samples: list[str]) -> dict:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ImportValidationError("DATABASE_URL must be set in the trusted server environment")
    metadata = {
        "reuse_statement_url": args.reuse_statement_url,
        "citation": args.citation,
        "source_file_name": args.vcf.name,
        "source_file_bytes": args.vcf.stat().st_size,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "importer_version": "1.0",
        "model": "normalized per-sample/per-ALT genotype calls",
    }
    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO genomeguard.variant_dataset_manifest
                    (dataset_key,source_name,source_url,source_release,reference_assembly,file_sha256,
                     data_use_review,consent_basis,import_status,metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,'approved_public_research','dataset_policy','loading',%s)
                    ON CONFLICT (dataset_key) DO UPDATE SET import_status='loading',
                      variant_count=0,genotype_call_count=0,sample_count=0,imported_at=NULL,
                      updated_at=now(),metadata=excluded.metadata
                    WHERE genomeguard.variant_dataset_manifest.file_sha256=excluded.file_sha256
                      AND genomeguard.variant_dataset_manifest.source_url=excluded.source_url
                      AND genomeguard.variant_dataset_manifest.source_release=excluded.source_release
                      AND genomeguard.variant_dataset_manifest.reference_assembly=excluded.reference_assembly
                      AND genomeguard.variant_dataset_manifest.data_use_review='approved_public_research'
                      AND genomeguard.variant_dataset_manifest.import_status <> 'loaded'
                    RETURNING id""",
                    (args.dataset_key, args.source_name, args.source_url, args.source_release,
                     args.assembly, digest, json.dumps(metadata)),
                )
                row = cur.fetchone()
                if not row:
                    raise ImportValidationError("dataset key already exists with another checksum or is already loaded")
                dataset_id = row[0]
                cur.execute("DELETE FROM genomeguard.dataset_genotype_calls WHERE dataset_id=%s", (dataset_id,))
                cur.execute("DELETE FROM genomeguard.dataset_variants WHERE dataset_id=%s", (dataset_id,))
                cur.execute("DELETE FROM genomeguard.dataset_samples WHERE dataset_id=%s", (dataset_id,))
                cur.executemany(
                    "INSERT INTO genomeguard.dataset_samples(dataset_id,source_sample_id) VALUES (%s,%s)",
                    [(dataset_id, sample) for sample in samples],
                )
                cur.execute("SELECT id,source_sample_id FROM genomeguard.dataset_samples WHERE dataset_id=%s",
                            (dataset_id,))
                sample_map = {sample: sid for sid, sample in cur.fetchall()}

        variant_count = 0
        genotype_count = 0
        batch_size = 100
        batch = []
        for record in iter_records(args.vcf, samples, args.assembly):
            batch.append(record)
            if len(batch) >= batch_size:
                v, g = write_batch(conn, dataset_id, batch, sample_map, samples)
                variant_count += v
                genotype_count += g
                batch.clear()
        if batch:
            v, g = write_batch(conn, dataset_id, batch, sample_map)
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
        variants = sum(1 for _ in iter_records(args.vcf, samples))
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
