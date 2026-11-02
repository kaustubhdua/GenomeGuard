from __future__ import annotations

import csv
from collections import Counter

import pytest

from app.data.clinvar_reference import ClinVarImportError, iter_annotation_rows

COLUMNS = [
    "Assembly", "Chromosome", "Start", "Stop", "ReferenceAllele", "AlternateAllele",
    "VariationID", "ClinicalSignificance", "ReviewStatus", "LastEvaluated",
    "PhenotypeList", "GeneSymbol", "NumberSubmitters",
]


def _write_tsv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _row(**overrides):
    row = {
        "Assembly": "GRCh38",
        "Chromosome": "chr1",
        "Start": "123",
        "Stop": "123",
        "ReferenceAllele": "A",
        "AlternateAllele": "G",
        "VariationID": "42",
        "ClinicalSignificance": "Conflicting classifications of pathogenicity",
        "ReviewStatus": "criteria provided, conflicting classifications",
        "LastEvaluated": "2026-10-01",
        "PhenotypeList": "Condition one|Condition two",
        "GeneSymbol": "GENE1|GENE2",
        "NumberSubmitters": "4",
    }
    row.update(overrides)
    return row


def test_import_rows_keep_conflicting_variant_evidence_and_provenance_fields(tmp_path):
    path = tmp_path / "clinvar.tsv"
    _write_tsv(path, [
        _row(),
        _row(VariationID="43", ClinicalSignificance="Uncertain significance",
             ReviewStatus="criteria provided, single submitter", LastEvaluated="-"),
        _row(Assembly="GRCh37", VariationID="44"),
        _row(ReferenceAllele="A", AlternateAllele="AT", Stop="123", VariationID="45"),
    ])
    counts = Counter()
    rows = list(iter_annotation_rows(path, counts))
    assert len(rows) == 2
    assert rows[0]["clinical_significance"].startswith("Conflicting")
    assert rows[0]["review_status"].endswith("conflicting classifications")
    assert rows[0]["conditions"] == ["Condition one", "Condition two"]
    assert rows[0]["gene_symbols"] == ["GENE1", "GENE2"]
    assert rows[0]["last_evaluated"].isoformat() == "2026-10-01"
    assert rows[1]["clinical_significance"] == "Uncertain significance"
    assert rows[1]["last_evaluated"] is None
    assert counts["source_rows"] == 4
    assert counts["eligible_rows"] == 2
    assert counts["other_assembly"] == 1
    assert counts["indel_or_complex_representation"] == 1


def test_import_rejects_unexpected_summary_schema(tmp_path):
    path = tmp_path / "unexpected.tsv"
    path.write_text("Assembly\tChromosome\nGRCh38\t1\n", encoding="utf-8")
    with pytest.raises(ClinVarImportError, match="missing columns"):
        list(iter_annotation_rows(path))

