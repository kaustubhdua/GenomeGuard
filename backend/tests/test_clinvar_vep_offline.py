import csv
import gzip
import json
import sys

import pytest

pytest.importorskip("sklearn")
pytest.importorskip("pandas")

from app.ml.clinvar_vep_train import load_local_vep, main, variant_key, write_vep_vcf


def test_variant_key_normalizes_chromosome_and_alleles():
    assert variant_key("chr1", 123, "a", "t") == "1:123:A:T"
    assert variant_key("M", 9, "c", "g") == "MT:9:C:G"


def test_write_vep_vcf_emits_valid_header_and_variant(tmp_path):
    path = tmp_path / "input.vcf"
    write_vep_vcf(
        [{"chrom": "1", "pos": 123, "ref": "A", "alt": "T"}],
        path,
    )
    lines = path.read_text().splitlines()
    assert lines[:3] == [
        "##fileformat=VCFv4.2",
        "##reference=GRCh38",
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
    ]
    assert lines[3] == "1\t123\t.\tA\tT\t.\t.\t."


def test_load_local_vep_maps_jsonl_input_to_exact_allele(tmp_path):
    path = tmp_path / "vep.jsonl"
    path.write_text(json.dumps({
        "input": "1 123 . A T . . .",
        "most_severe_consequence": "missense_variant",
        "transcript_consequences": [],
    }) + "\n")
    loaded = load_local_vep(path)
    assert loaded["1:123:A:T"]["most_severe_consequence"] == "missense_variant"


def test_load_local_vep_rejects_invalid_json(tmp_path):
    path = tmp_path / "vep.jsonl"
    path.write_text("{not-json}\n")
    with pytest.raises(ValueError, match="Invalid VEP JSON"):
        load_local_vep(path)


def test_load_local_vep_requires_local_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="Local VEP JSONL not found"):
        load_local_vep(tmp_path / "missing.jsonl")


def test_prepare_only_creates_vcf_without_requiring_vep_annotations(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "out"
    data_dir.mkdir()
    source = data_dir / "variant_summary.txt.gz"
    fields = [
        "Assembly", "Chromosome", "Start", "ReferenceAllele", "AlternateAllele",
        "ClinicalSignificance", "ReviewStatus", "GeneSymbol",
    ]
    rows = [
        {"Assembly": "GRCh38", "Chromosome": "1", "Start": "101",
         "ReferenceAllele": "A", "AlternateAllele": "T",
         "ClinicalSignificance": "Pathogenic",
         "ReviewStatus": "criteria provided, single submitter", "GeneSymbol": "GENE1"},
        {"Assembly": "GRCh38", "Chromosome": "2", "Start": "202",
         "ReferenceAllele": "C", "AlternateAllele": "G",
         "ClinicalSignificance": "Benign",
         "ReviewStatus": "criteria provided, single submitter", "GeneSymbol": "GENE2"},
    ]
    with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\\t")
        writer.writeheader()
        writer.writerows(rows)

    monkeypatch.setattr(sys, "argv", [
        "clinvar_vep_train", "--data-dir", str(data_dir),
        "--output-dir", str(output_dir), "--max-variants", "1000", "--prepare-only",
    ])
    assert main() == 0
    vcf = data_dir / "clinvar_selected_for_vep.vcf"
    assert vcf.is_file()
    assert len([line for line in vcf.read_text().splitlines() if not line.startswith("#")]) == 2
    assert not (data_dir / "ensembl_vep_offline.jsonl").exists()
