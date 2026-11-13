from __future__ import annotations

import json
from urllib.parse import urlparse

import pytest

from app.literature import ensembl


class FakeResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.payload


def payload():
    return {
        "id": "ENSG00000139618",
        "display_name": "BRCA2",
        "object_type": "Gene",
        "species": "homo_sapiens",
        "biotype": "protein_coding",
        "version": 19,
        "assembly_name": "GRCh38",
        "seq_region_name": "13",
        "start": 32315086,
        "end": 32400266,
        "strand": 1,
        "canonical_transcript": "ENST00000380152",
        "Transcript": [
            {"id": "ENST00000380152", "version": 8, "biotype": "protein_coding", "is_canonical": 1},
            {"id": "ENST00000544455", "version": 3, "biotype": "retained_intron", "is_canonical": 0},
        ],
    }


def test_lookup_gene_normalizes_stable_ids_assembly_and_transcripts(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout, request.headers))
        return FakeResponse(payload())

    monkeypatch.setattr(ensembl, "_wait_for_rate_slot", lambda: None)
    monkeypatch.setattr(ensembl, "urlopen", fake_urlopen)
    result = ensembl.lookup_gene("BRCA2")
    parsed = urlparse(calls[0][0])
    assert parsed.netloc == "rest.ensembl.org"
    assert parsed.path == "/lookup/symbol/homo_sapiens/BRCA2"
    assert calls[0][1] == ensembl.TIMEOUT_SECONDS
    assert result["gene"]["stable_id"] == "ENSG00000139618"
    assert result["gene"]["assembly"] == "GRCh38"
    assert result["gene"]["gene_version"] == 19
    assert result["transcripts"][0]["is_canonical"] is True
    assert result["transcript_count_returned"] == 2
    assert "not a disease association" in result["interpretation"]


@pytest.mark.parametrize(("symbol", "species"), [
    ("", "homo_sapiens"), ("BRCA2/../lookup", "homo_sapiens"),
    ("BRCA2", "mus_musculus"), ("A" * 21, "homo_sapiens"),
])
def test_rejects_invalid_gene_lookup_without_network(monkeypatch, symbol, species):
    monkeypatch.setattr(ensembl, "urlopen", lambda *a, **k: pytest.fail("network must not be called"))
    with pytest.raises(ValueError):
        ensembl.lookup_gene(symbol, species=species)


def test_rejects_unexpected_gene_or_species(monkeypatch):
    bad = payload()
    bad["id"] = "ENST00000380152"
    monkeypatch.setattr(ensembl, "_wait_for_rate_slot", lambda: None)
    monkeypatch.setattr(ensembl, "urlopen", lambda *a, **k: FakeResponse(bad))
    with pytest.raises(ensembl.EnsemblProviderError, match="stable gene"):
        ensembl.lookup_gene("BRCA2")


def test_rejects_oversized_response(monkeypatch):
    class Oversized(FakeResponse):
        def read(self, limit):
            return b"x" * limit

    monkeypatch.setattr(ensembl, "_wait_for_rate_slot", lambda: None)
    monkeypatch.setattr(ensembl, "urlopen", lambda *a, **k: Oversized({}))
    with pytest.raises(ensembl.EnsemblProviderError, match="1 MB"):
        ensembl.lookup_gene("BRCA2")
