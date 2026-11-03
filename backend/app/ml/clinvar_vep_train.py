"""ClinVar + local Ensembl VEP annotation research training pipeline.

ClinVar may be downloaded from its public FTP distribution. Variant annotation is
consumed only from a local Ensembl VEP offline/cache JSONL export; no REST API is used.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import random
import urllib.request
from collections import Counter
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

CLINVAR_URL = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz"
VEP_OFFLINE_FILE = "ensembl_vep_offline.jsonl"
DNA = set("ACGTN")
NUMERIC = ["ref_length", "alt_length", "length_delta", "gc_ref", "gc_alt",
           "is_snv", "is_indel", "cadd_phred", "sift_score", "polyphen_score",
           "max_population_af", "transcript_consequence_count",
           "canonical_transcript_count", "mane_select_present"]
CATEGORICAL = ["variant_class", "most_severe_consequence", "impact"]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, path: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "GenomeGuard-research/0.2"})
    with urllib.request.urlopen(req, timeout=120) as response, path.open("wb") as out:
        while block := response.read(1 << 20):
            out.write(block)


def label(value: str) -> int | None:
    terms = {x.strip().lower() for x in value.replace("|", "/").split("/")}
    if terms == {"pathogenic"} or terms == {"likely pathogenic"} or terms == {"pathogenic", "likely pathogenic"}:
        return 1
    if terms == {"benign"} or terms == {"likely benign"} or terms == {"benign", "likely benign"}:
        return 0
    return None


def eligible_rows(path: Path, cap: int, seed: int) -> tuple[list[dict], Counter]:
    counts: Counter = Counter()
    by_class = {0: [], 1: []}
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        required = {"Assembly", "Chromosome", "Start", "ReferenceAllele",
                    "AlternateAllele", "ClinicalSignificance", "ReviewStatus", "GeneSymbol"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"ClinVar missing required columns: {sorted(missing)}")
        for row in reader:
            counts["source_rows"] += 1
            if row["Assembly"] != "GRCh38":
                counts["not_grch38"] += 1
                continue
            status = (row["ReviewStatus"] or "").lower()
            if "criteria provided" not in status or "conflict" in status:
                counts["review_excluded"] += 1
                continue
            y = label(row["ClinicalSignificance"] or "")
            chrom, pos = row["Chromosome"].strip(), row["Start"].strip()
            ref, alt = row["ReferenceAllele"].strip().upper(), row["AlternateAllele"].strip().upper()
            gene = row["GeneSymbol"].strip()
            if y is None or not gene or not pos.isdigit() or not ref or not alt or not set(ref + alt) <= DNA:
                counts["label_or_allele_excluded"] += 1
                continue
            if chrom not in {str(i) for i in range(1, 23)} | {"X", "Y"}:
                counts["contig_excluded"] += 1
                continue
            by_class[y].append({"chrom": chrom, "pos": int(pos), "ref": ref, "alt": alt,
                                "gene": gene, "label": y})
    rng = random.Random(seed)
    per_class = min(cap // 2, len(by_class[0]), len(by_class[1]))
    selected = []
    for y in (0, 1):
        rng.shuffle(by_class[y])
        selected.extend(by_class[y][:per_class])
    # Deduplicate exact genomic alleles before annotation.
    unique = {}
    for row in selected:
        unique[(row["chrom"], row["pos"], row["ref"], row["alt"])] = row
    rows = list(unique.values())
    counts["selected_balanced"] = len(rows)
    counts["selected_benign"] = sum(x["label"] == 0 for x in rows)
    counts["selected_pathogenic"] = sum(x["label"] == 1 for x in rows)
    return rows, counts


def variant_key(chrom: str, pos: int, ref: str, alt: str) -> str:
    chrom = str(chrom).removeprefix("chr").upper()
    if chrom == "M":
        chrom = "MT"
    return f"{chrom}:{int(pos)}:{ref.upper()}:{alt.upper()}"


def write_vep_vcf(rows: list[dict], path: Path) -> None:
    """Write selected variants for a local Ensembl VEP offline/cache run."""
    with path.open("w", encoding="utf-8") as out:
        out.write("##fileformat=VCFv4.2\n##reference=GRCh38\n")
        out.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")
        for row in rows:
            out.write(
                f'{row["chrom"]}\t{row["pos"]}\t.\t{row["ref"]}\t'
                f'{row["alt"]}\t.\t.\t.\n'
            )


def load_local_vep(path: Path) -> dict[str, dict]:
    """Read one JSON object per line from Ensembl VEP CLI --json output."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Local VEP JSONL not found: {path}. Generate it with Ensembl VEP "
            "--offline --cache --assembly GRCh38 --json using the generated VCF."
        )
    annotations: dict[str, dict] = {}
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                result = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid VEP JSON on line {line_number}") from exc
            fields = str(result.get("input", "")).split()
            if len(fields) < 5:
                continue
            chrom, pos, _identifier, ref, alt = fields[:5]
            annotations[variant_key(chrom, int(pos), ref, alt)] = result
    return annotations


def numeric_af(colocated: list[dict], alternate_allele: str) -> float:
    """Return AF for the queried ALT allele, never a REF or unrelated allele."""
    values = []
    for item in colocated:
        allele_string = item.get("allele_string")
        if isinstance(allele_string, str) and alternate_allele not in allele_string.split("/"):
            continue
        allele_map = (item.get("frequencies") or {}).get(alternate_allele)
        if not isinstance(allele_map, dict):
            continue
        for value in allele_map.values():
            if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
                values.append(float(value))
    return max(values) if values else float("nan")


def annotate(rows: list[dict], vep_jsonl: Path, cache_path: Path) -> list[dict]:
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            item = json.loads(line)
            cache[item["key"]] = item["annotation"]
    vep_results = load_local_vep(vep_jsonl) if vep_jsonl.is_file() else {}
    missing = [
        variant_key(row["chrom"], row["pos"], row["ref"], row["alt"])
        for row in rows
        if variant_key(row["chrom"], row["pos"], row["ref"], row["alt"]) not in cache
        and variant_key(row["chrom"], row["pos"], row["ref"], row["alt"]) not in vep_results
    ]
    if missing:
        raise ValueError(
            f"{len(missing)} selected variants are absent from local VEP output; "
            "regenerate the VCF and run offline VEP for the complete input."
        )
    for row in rows:
        key = variant_key(row["chrom"], row["pos"], row["ref"], row["alt"])
        if key in cache:
            continue
        result = vep_results[key]
        consequences = result.get("transcript_consequences") or []
        impacts = [x.get("impact") for x in consequences if x.get("impact")]
        cadds = [x.get("cadd_phred") for x in consequences if isinstance(x.get("cadd_phred"), (int, float))]
        sift = [x.get("sift_score") for x in consequences if isinstance(x.get("sift_score"), (int, float))]
        polyphen = [x.get("polyphen_score") for x in consequences if isinstance(x.get("polyphen_score"), (int, float))]
        annotation = {
            "most_severe_consequence": result.get("most_severe_consequence", "unknown"),
            "impact": max(impacts, key=lambda x: {"HIGH": 3, "MODERATE": 2, "LOW": 1, "MODIFIER": 0}.get(x, -1), default="unknown"),
            "cadd_phred": max(cadds) if cadds else None,
            "sift_score": min(sift) if sift else None,
            "polyphen_score": max(polyphen) if polyphen else None,
            "max_population_af": numeric_af(result.get("colocated_variants") or [], row["alt"]),
            "transcript_consequence_count": len(consequences),
            "canonical_transcript_count": sum(bool(x.get("canonical")) for x in consequences),
            "mane_select_present": int(any(x.get("mane_select") for x in consequences)),
        }
        cache[key] = annotation
        with cache_path.open("a", encoding="utf-8") as out:
            out.write(json.dumps({"key": key, "annotation": annotation}) + "\n")
    result_rows = []
    for row in rows:
        key = variant_key(row["chrom"], row["pos"], row["ref"], row["alt"])
        ann = cache.get(key)
        if ann is None:
            continue
        ref, alt = row["ref"], row["alt"]
        snv = len(ref) == len(alt) == 1
        result_rows.append({
            "gene": row["gene"], "label": row["label"],
            "ref_length": len(ref), "alt_length": len(alt),
            "length_delta": len(alt) - len(ref),
            "gc_ref": sum(x in "GC" for x in ref) / len(ref),
            "gc_alt": sum(x in "GC" for x in alt) / len(alt),
            "is_snv": int(snv), "is_indel": int(len(ref) != len(alt)),
            "variant_class": "SNV" if snv else ("MNV" if len(ref) == len(alt) else "INDEL"),
            **ann,
        })
    return result_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path(".training-data/public-annotations"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/clinvar-vep"))
    parser.add_argument("--max-variants", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--vep-jsonl", type=Path, default=None, help="local Ensembl VEP --json output; no REST endpoint is called")
    args = parser.parse_args()
    if args.max_variants < 1000 or args.max_variants > 20000:
        parser.error("--max-variants must be between 1000 and 20000")
    args.data_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    clinvar = args.data_dir / "variant_summary.txt.gz"
    if not clinvar.exists():
        print("Downloading public NCBI ClinVar summary...", flush=True)
        download(CLINVAR_URL, clinvar)
    selected, counts = eligible_rows(clinvar, args.max_variants, args.seed)
    input_vcf = args.data_dir / "clinvar_selected_for_vep.vcf"
    write_vep_vcf(selected, input_vcf)
    vep_jsonl = args.vep_jsonl or (args.data_dir / VEP_OFFLINE_FILE)
    cache = args.data_dir / "ensembl_vep_annotations.jsonl"
    records = annotate(selected, vep_jsonl, cache)
    if len(records) < 500 or len({x["gene"] for x in records}) < 20 or len({x["label"] for x in records}) != 2:
        raise SystemExit(f"Not enough annotated records for a meaningful run: {len(records)}")
    frame = pd.DataFrame(records)
    numeric = NUMERIC
    categorical = CATEGORICAL
    X, y, groups = frame[numeric + categorical], frame["label"].astype(int), frame["gene"]
    train_idx, test_idx = next(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=args.seed).split(X, y, groups))
    if set(groups.iloc[train_idx]) & set(groups.iloc[test_idx]):
        raise SystemExit("Gene leakage detected in holdout")
    pre = ColumnTransformer([
        ("numeric", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)), ("scale", StandardScaler())]), numeric),
        ("categorical", Pipeline([("impute", SimpleImputer(strategy="constant", fill_value="unknown")),
                                  ("encode", OneHotEncoder(handle_unknown="ignore"))]), categorical),
    ])
    candidates = {
        "logistic_regression": LogisticRegression(
            class_weight="balanced", max_iter=3000, random_state=args.seed),
        "random_forest": RandomForestClassifier(
            n_estimators=400, min_samples_leaf=2, class_weight="balanced_subsample",
            n_jobs=-1, random_state=args.seed),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=400, min_samples_leaf=2, class_weight="balanced",
            n_jobs=-1, random_state=args.seed),
    }
    models = {}
    yt = y.iloc[test_idx]
    all_metrics = {}
    for name, estimator in candidates.items():
        candidate = Pipeline([("features", clone(pre)), ("classifier", estimator)])
        candidate.fit(X.iloc[train_idx], y.iloc[train_idx])
        probs = candidate.predict_proba(X.iloc[test_idx])[:, 1]
        pred = (probs >= .5).astype(int)
        all_metrics[name] = {
            "accuracy": float(accuracy_score(yt, pred)),
            "balanced_accuracy": float(balanced_accuracy_score(yt, pred)),
            "precision": float(precision_score(yt, pred, zero_division=0)),
            "recall": float(recall_score(yt, pred, zero_division=0)),
            "f1": float(f1_score(yt, pred, zero_division=0)),
            "auroc": float(roc_auc_score(yt, probs)),
            "average_precision": float(average_precision_score(yt, probs)),
            "brier_score": float(brier_score_loss(yt, probs)),
            "confusion_matrix_tn_fp_fn_tp": confusion_matrix(yt, pred).ravel().tolist(),
        }
        models[name] = candidate
    # Keep all candidates: do not pick a winner from a single holdout.
    model_path = args.output_dir / "clinvar_vep_research_models.joblib"
    joblib.dump(models, model_path)
    (args.output_dir / "metrics.json").write_text(json.dumps({"models": all_metrics}, indent=2) + "\n")
    metrics = {"models": all_metrics}
    metadata = {
        "model": "clinvar_vep_research", "version": "0.2.0",
        "sources": [
            {"name": "NCBI ClinVar variant_summary", "url": CLINVAR_URL, "sha256": digest(clinvar)},
            {"name": "Ensembl VEP offline CLI/cache", "annotation_file": str(vep_jsonl), "annotation_file_sha256": digest(vep_jsonl), "annotation_cache_sha256": digest(cache)},
        ],
        "assembly": "GRCh38", "max_variants_requested": args.max_variants,
        "annotated_rows": len(frame), "train_rows": len(train_idx), "test_rows": len(test_idx),
        "train_genes": int(groups.iloc[train_idx].nunique()), "test_genes": int(groups.iloc[test_idx].nunique()),
        "features": numeric + categorical,
        "feature_coverage": {column: float(frame[column].notna().mean()) for column in numeric + categorical},
        "feature_policy": "REF/ALT shape plus locally generated Ensembl VEP consequence, impact, CADD and colocated population-frequency annotations; clinical labels, coordinates and gene identifiers are excluded from features",
        "split_policy": "first fold of 5-fold stratified gene-disjoint split; not external cohort or ancestry validation",
        "counts": dict(counts), "scikit_learn_version": sklearn.__version__,
        "model_sha256": digest(model_path),
        "limitations": ["VEP annotation coverage is incomplete; missing values are imputed with explicit numeric missingness indicators.",
            "Colocated frequency values are not guaranteed to be gnomAD-specific; interpreted only as generic population-frequency annotations.",
            "Research-only; not for diagnosis or clinical decision-making."]
    }
    (args.output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"metrics": metrics, "metadata": metadata}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
