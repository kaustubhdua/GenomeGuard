from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

from app.literature import uniprot


class FakeResponse:
    status = 200
    headers = {
        "Content-Type": "application/json",
        "X-UniProt-Release": "2026_04",
        "X-Total-Results": "1",
    }

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
        "results": [{
            "entryType": "UniProtKB reviewed (Swiss-Prot)",
            "primaryAccession": "P51587",
            "uniProtkbId": "BRCA2_HUMAN",
            "proteinDescription": {
                "recommendedName": {
                    "fullName": {"value": "Breast cancer type 2 susceptibility protein"},
                },
            },
            "genes": [{
                "geneName": {"value": "BRCA2"},
                "synonyms": [{"value": "FANCD1"}],
            }],
            "organism": {"scientificName": "Homo sapiens", "taxonId": 9606},
            "sequence": {"length": 3418},
            "comments": [{
                "commentType": "FUNCTION",
                "texts": [{"value": "Tumor suppressor protein involved in DNA repair."}],
            }],
            "uniProtKBCrossReferences": [{
                "database": "Ensembl",
                "id": "ENSP00000369497",
                "properties": [
                    {"key": "GeneId", "value": "ENSG00000139618"},
                    {"key": "ProteinId", "value": "ENSP00000369497"},
                ],
            }],
        }],
    }


def test_search_proteins_builds_exact_reviewed_human_query(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout, request.headers))
        return FakeResponse(payload())

    monkeypatch.setattr(uniprot, "_wait_for_rate_slot", lambda: None)
    monkeypatch.setattr(uniprot, "urlopen", fake_urlopen)
    result = uniprot.search_proteins("BRCA2")
    parsed = urlparse(calls[0][0])
    params = parse_qs(parsed.query)
    assert parsed.netloc == "rest.uniprot.org"
    assert params["query"] == ["gene_exact:BRCA2 AND organism_id:9606 AND reviewed:true"]
    assert params["format"] == ["json"]
    assert params["size"] == ["5"]
    assert "sequence" not in params["fields"][0]
    assert "reviewed" in params["fields"][0]
    assert result["release"] == "2026_04"
    assert result["total_results"] == 1
    protein = result["proteins"][0]
    assert protein["accession"] == "P51587"
    assert protein["reviewed"] is True
    assert protein["length_aa"] == 3418
    assert protein["gene_names"] == ["BRCA2", "FANCD1"]
    assert protein["ensembl_cross_references"][0] == {
        "gene_id": "ENSG00000139618", "protein_id": "ENSP00000369497",
    }
    assert "not establish variant pathogenicity" in result["interpretation"]


@pytest.mark.parametrize(("symbol", "size"), [
    ("", 5), ("BRCA2/../../", 5), ("A" * 21, 5), ("BRCA2", 0), ("BRCA2", 11), ("BRCA2", True),
])
def test_rejects_invalid_query_without_network(monkeypatch, symbol, size):
    monkeypatch.setattr(uniprot, "urlopen", lambda *a, **k: pytest.fail("network must not be called"))
    with pytest.raises(ValueError):
        uniprot.search_proteins(symbol, size=size)


def test_empty_result_is_a_valid_not_found_response(monkeypatch):
    monkeypatch.setattr(uniprot, "_wait_for_rate_slot", lambda: None)
    monkeypatch.setattr(uniprot, "urlopen", lambda *a, **k: FakeResponse({"results": []}))
    result = uniprot.search_proteins("NOTAREALGENE")
    assert result["returned"] == 0
    assert result["proteins"] == []


def test_rejects_malformed_provider_response(monkeypatch):
    monkeypatch.setattr(uniprot, "_wait_for_rate_slot", lambda: None)
    monkeypatch.setattr(uniprot, "urlopen", lambda *a, **k: FakeResponse({"unexpected": []}))
    with pytest.raises(uniprot.UniProtProviderError, match="results array"):
        uniprot.search_proteins("BRCA2")


def test_rejects_oversized_response(monkeypatch):
    class Oversized(FakeResponse):
        def read(self, limit):
            return b"x" * limit

    monkeypatch.setattr(uniprot, "_wait_for_rate_slot", lambda: None)
    monkeypatch.setattr(uniprot, "urlopen", lambda *a, **k: Oversized({}))
    with pytest.raises(uniprot.UniProtProviderError, match="2 MB"):
        uniprot.search_proteins("BRCA2")

def test_unreviewed_and_nonhuman_records_are_filtered(monkeypatch):
    records = payload()["results"]
    records[0]["entryType"] = "UniProtKB unreviewed (TrEMBL)"
    mouse = json.loads(json.dumps(payload()["results"][0]))
    mouse["entryType"] = "UniProtKB reviewed (Swiss-Prot)"
    mouse["primaryAccession"] = "P00001"
    mouse["organism"] = {"scientificName": "Mus musculus", "taxonId": 10090}

    monkeypatch.setattr(uniprot, "_wait_for_rate_slot", lambda: None)
    monkeypatch.setattr(
        uniprot, "urlopen",
        lambda *a, **k: FakeResponse({"results": [records[0], mouse]}),
    )
    result = uniprot.search_proteins("BRCA2")
    assert result["returned"] == 0
    assert result["proteins"] == []

