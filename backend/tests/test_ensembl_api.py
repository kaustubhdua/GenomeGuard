from __future__ import annotations

import threading

from tests.helpers import make_client


def payload():
    return {
        "provider": "Ensembl REST API",
        "provider_url": "https://www.ensembl.org",
        "species": "homo_sapiens",
        "query_symbol": "BRCA2",
        "gene": {
            "stable_id": "ENSG00000139618",
            "symbol": "BRCA2",
            "biotype": "protein_coding",
            "gene_version": 19,
            "assembly": "GRCh38",
            "chromosome": "13",
            "start": 32315086,
            "end": 32400266,
            "strand": 1,
            "canonical_transcript": "ENST00000380152",
        },
        "transcript_count_returned": 1,
        "transcripts": [{"id": "ENST00000380152", "version": 8, "biotype": "protein_coding", "is_canonical": True}],
        "retrieved_at": "2026-11-14T00:00:00+00:00",
        "interpretation": "source-backed gene identity only",
    }


def test_ensembl_api_returns_no_store_and_source_provenance(monkeypatch):
    import app.literature.ensembl as provider

    monkeypatch.setattr(provider, "lookup_gene", lambda *args, **kwargs: payload())
    _, client = make_client()
    response = client.post("/research/ensembl/gene", json={"symbol": "BRCA2"})
    assert response.status_code == 200
    assert response.json()["gene"]["stable_id"] == "ENSG00000139618"
    assert response.headers["cache-control"] == "no-store"


def test_ensembl_api_rejects_invalid_input_without_provider_call(monkeypatch):
    import app.literature.ensembl as provider

    monkeypatch.setattr(
        provider, "lookup_gene",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider must not be called")),
    )
    _, client = make_client()
    response = client.post("/research/ensembl/gene", json={"symbol": "BRCA2/../../"})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_ensembl_query"


def test_ensembl_api_maps_not_found_and_provider_outage(monkeypatch):
    import app.literature.ensembl as provider

    monkeypatch.setattr(
        provider, "lookup_gene",
        lambda *args, **kwargs: (_ for _ in ()).throw(provider.EnsemblEntityNotFound("private")),
    )
    _, client = make_client()
    response = client.post("/research/ensembl/gene", json={"symbol": "BRCA2"})
    assert response.status_code == 404
    assert response.json()["error"] == "ensembl_gene_not_found"

    monkeypatch.setattr(
        provider, "lookup_gene",
        lambda *args, **kwargs: (_ for _ in ()).throw(provider.EnsemblProviderError("private upstream details")),
    )
    response = client.post("/research/ensembl/gene", json={"symbol": "BRCA2"})
    assert response.status_code == 503
    assert response.json()["error"] == "ensembl_provider_unavailable"
    assert "private upstream details" not in response.text


def test_ensembl_api_bounds_concurrent_provider_calls(monkeypatch):
    import app.api as api_module
    import app.literature.ensembl as provider

    monkeypatch.setattr(api_module, "_ENSEMBL_SEARCH_SLOTS", threading.BoundedSemaphore(0))
    monkeypatch.setattr(provider, "lookup_gene", lambda *args, **kwargs: payload())
    _, client = make_client()
    response = client.post("/research/ensembl/gene", json={"symbol": "BRCA2"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "2"
    assert response.headers["cache-control"] == "no-store"


def test_ensembl_api_is_documented():
    _, client = make_client()
    endpoints = client.get("/openapi.json").json()["endpoints"]
    assert "POST /research/ensembl/gene" in {
        f"{entry['method']} {entry['path']}" for entry in endpoints
    }
