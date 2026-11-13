from __future__ import annotations

from app.literature import ontology
from tests.helpers import make_client


def test_ontology_search_api_returns_source_provenance_and_no_store(monkeypatch):
    expected = {
        "provider": "EMBL-EBI Ontology Lookup Service",
        "provider_url": "https://www.ebi.ac.uk/ols4/",
        "query": "ataxia",
        "ontology_filter": "all",
        "page": 0,
        "size": 10,
        "total": 1,
        "returned": 1,
        "has_more": False,
        "terms": [{
            "label": "Ataxia",
            "iri": "http://purl.obolibrary.org/obo/MONDO_0000001",
            "obo_id": "MONDO:0000001",
            "ontology": "mondo",
            "ontology_prefix": "MONDO",
            "description": "A neurological finding.",
            "synonyms": [],
            "is_obsolete": False,
            "source_url": "https://www.ebi.ac.uk/ols4/",
        }],
        "retrieved_at": "2026-11-13T00:00:00+00:00",
        "interpretation": "candidate annotations only",
    }
    monkeypatch.setattr(ontology, "search_ontology", lambda *a, **kw: expected)
    _, client = make_client()
    response = client.post("/research/ontology/search", json={"query": "ataxia"})
    assert response.status_code == 200
    assert response.json() == expected
    assert response.headers["cache-control"] == "no-store"


def test_ontology_search_api_rejects_invalid_input(monkeypatch):
    monkeypatch.setattr(
        ontology, "search_ontology",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("provider must not be called")),
    )
    _, client = make_client()
    response = client.post("/research/ontology/search", json={"query": "x", "ontology": "unknown"})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_ontology_query"


def test_ontology_search_api_maps_provider_outage_to_safe_503(monkeypatch):
    def unavailable(*args, **kwargs):
        raise ontology.OntologyProviderError("upstream details must not leak")

    monkeypatch.setattr(ontology, "search_ontology", unavailable)
    _, client = make_client()
    response = client.post("/research/ontology/search", json={"query": "ataxia"})
    assert response.status_code == 503
    assert response.json()["error"] == "ontology_provider_unavailable"
    assert "upstream details" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_ontology_search_api_is_documented():
    _, client = make_client()
    endpoints = client.get("/openapi.json").json()["endpoints"]
    assert "POST /research/ontology/search" in {
        f"{entry['method']} {entry['path']}" for entry in endpoints
    }
