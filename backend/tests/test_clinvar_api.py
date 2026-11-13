from __future__ import annotations

from tests.helpers import make_client


def payload():
    return {
        "provider": "NCBI ClinVar",
        "query": {
            "gene_symbol": "BRCA1",
            "classification_filter": "pathogenic",
            "classification_filter_semantics": "ClinVar Properties search for at least one report.",
            "retstart": 0,
            "retmax": 20,
        },
        "count": 1,
        "returned": 1,
        "has_more": False,
        "records": [{
            "uid": "373892",
            "accession": "VCV000373892",
            "accession_version": "VCV000373892.1",
            "title": "BRCA1 variant",
            "variation_type": "Deletion",
            "genes": [{"symbol": "BRCA1", "gene_id": "672"}],
            "variations": [],
            "classifications": {
                "germline": {
                    "description": "Conflicting classifications of pathogenicity",
                    "review_status": "criteria provided, conflicting interpretations",
                },
            },
            "source_url": "https://www.ncbi.nlm.nih.gov/clinvar/variation/373892/",
        }],
        "retrieved_at": "2026-11-13T00:00:00+00:00",
        "provenance": {"provider": "NCBI ClinVar", "api": "E-utilities ESearch + ESummary v2.0"},
    }


def test_clinvar_api_returns_source_attributed_records_and_no_store(monkeypatch):
    import app.literature.clinvar as provider

    monkeypatch.setattr(provider, "search_clinvar", lambda *args, **kwargs: payload())
    _, client = make_client()
    response = client.post(
        "/research/clinvar/search",
        json={"gene_symbol": "BRCA1", "classification": "pathogenic"},
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "NCBI ClinVar"
    assert response.json()["records"][0]["classifications"]["germline"]["description"] == (
        "Conflicting classifications of pathogenicity"
    )
    assert response.headers["cache-control"] == "no-store"


def test_clinvar_api_rejects_invalid_gene_without_network(monkeypatch):
    import app.literature.clinvar as provider

    def fail_network(*args, **kwargs):
        raise AssertionError("invalid input must not call NCBI")

    monkeypatch.setattr(provider, "search_clinvar", fail_network)
    _, client = make_client()
    response = client.post(
        "/research/clinvar/search",
        json={"gene_symbol": "BRCA1 OR *"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_clinvar_query"


def test_clinvar_api_returns_safe_provider_error(monkeypatch):
    import app.literature.clinvar as provider

    def unavailable(*args, **kwargs):
        raise provider.ClinVarProviderError("private upstream details")

    monkeypatch.setattr(provider, "search_clinvar", unavailable)
    _, client = make_client()
    response = client.post("/research/clinvar/search", json={"gene_symbol": "BRCA1"})
    assert response.status_code == 503
    assert response.json()["error"] == "clinvar_provider_unavailable"
    assert "private upstream details" not in response.text


def test_clinvar_api_bounds_concurrent_provider_calls(monkeypatch):
    import app.api as api_module
    import app.literature.clinvar as provider

    monkeypatch.setattr(api_module, "_CLINVAR_SEARCH_SLOTS", __import__("threading").BoundedSemaphore(0))
    monkeypatch.setattr(provider, "search_clinvar", lambda *args, **kwargs: payload())
    _, client = make_client()
    response = client.post("/research/clinvar/search", json={"gene_symbol": "BRCA1"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "2"
    assert response.headers["cache-control"] == "no-store"
