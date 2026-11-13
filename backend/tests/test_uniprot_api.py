from __future__ import annotations

import threading

from tests.helpers import make_client


def payload():
    return {
        "provider": "UniProtKB",
        "provider_url": "https://www.uniprot.org",
        "query": {"gene_symbol": "BRCA2", "organism_taxonomy_id": 9606, "reviewed_only": True},
        "release": "2026_04",
        "total_results": 1,
        "returned": 1,
        "proteins": [{
            "accession": "P51587", "entry_name": "BRCA2_HUMAN",
            "protein_name": "Breast cancer type 2 susceptibility protein",
            "gene_names": ["BRCA2", "FANCD1"], "organism": "Homo sapiens",
            "length_aa": 3418, "reviewed": True, "function": "DNA repair",
            "ensembl_cross_references": [{"gene_id": "ENSG00000139618", "protein_id": "ENSP00000369497"}],
            "source_url": "https://www.uniprot.org/uniprotkb/P51587",
        }],
        "retrieved_at": "2026-11-14T00:00:00+00:00",
        "interpretation": "reviewed protein annotation only",
    }


def test_uniprot_api_returns_source_provenance_and_no_store(monkeypatch):
    import app.literature.uniprot as provider

    monkeypatch.setattr(provider, "search_proteins", lambda *args, **kwargs: payload())
    _, client = make_client()
    response = client.post("/research/uniprot/search", json={"symbol": "BRCA2"})
    assert response.status_code == 200
    assert response.json()["proteins"][0]["accession"] == "P51587"
    assert response.headers["cache-control"] == "no-store"


def test_uniprot_api_rejects_invalid_input_without_provider_call(monkeypatch):
    import app.literature.uniprot as provider

    monkeypatch.setattr(
        provider, "search_proteins",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider must not be called")),
    )
    _, client = make_client()
    response = client.post("/research/uniprot/search", json={"symbol": "BRCA2/../../"})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_uniprot_query"


def test_uniprot_api_maps_provider_outage_to_safe_503(monkeypatch):
    import app.literature.uniprot as provider

    monkeypatch.setattr(
        provider, "search_proteins",
        lambda *args, **kwargs: (_ for _ in ()).throw(provider.UniProtProviderError("private upstream details")),
    )
    _, client = make_client()
    response = client.post("/research/uniprot/search", json={"symbol": "BRCA2"})
    assert response.status_code == 503
    assert response.json()["error"] == "uniprot_provider_unavailable"
    assert "private upstream details" not in response.text


def test_uniprot_api_bounds_concurrent_provider_calls(monkeypatch):
    import app.api as api_module
    import app.literature.uniprot as provider

    monkeypatch.setattr(api_module, "_UNIPROT_SEARCH_SLOTS", threading.BoundedSemaphore(0))
    monkeypatch.setattr(provider, "search_proteins", lambda *args, **kwargs: payload())
    _, client = make_client()
    response = client.post("/research/uniprot/search", json={"symbol": "BRCA2"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "2"
    assert response.headers["cache-control"] == "no-store"


def test_uniprot_api_is_documented():
    _, client = make_client()
    endpoints = client.get("/openapi.json").json()["endpoints"]
    assert "POST /research/uniprot/search" in {
        f"{entry['method']} {entry['path']}" for entry in endpoints
    }
