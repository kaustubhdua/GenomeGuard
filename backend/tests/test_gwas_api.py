from __future__ import annotations

import threading

from tests.helpers import make_client


def response_payload():
    return {
        "provider": "GWAS Catalog",
        "api_version": "2.0",
        "query": {"gene_symbol": "BRCA1", "page": 0, "size": 20},
        "count": 1,
        "returned": 1,
        "has_more": False,
        "next_page_url": None,
        "page": {"number": 0, "size": 20, "total_elements": 1, "total_pages": 1},
        "records": [{
            "association_id": "218086295",
            "study_accession": "GCST90838669",
            "pubmed_id": "38627641",
            "p_value": 2.0e-24,
            "source_url": "https://www.ebi.ac.uk/gwas/rest/api/v2/associations/218086295",
        }],
        "retrieved_at": "2026-11-13T00:00:00+00:00",
        "provenance": {
            "provider": "GWAS Catalog", "api": "REST API v2",
            "data_release_date": "2026-10-29",
        },
    }


def test_gwas_api_returns_release_provenance_and_no_store(monkeypatch):
    import app.literature.gwas_catalog as provider

    monkeypatch.setattr(provider, "search_gwas_catalog", lambda **kwargs: response_payload())
    _, client = make_client()
    response = client.post("/research/gwas/search", json={"gene_symbol": "BRCA1"})
    assert response.status_code == 200
    assert response.json()["provenance"]["data_release_date"] == "2026-10-29"
    assert response.json()["records"][0]["study_accession"] == "GCST90838669"
    assert response.headers["cache-control"] == "no-store"


def test_gwas_api_requires_at_least_one_search_field():
    _, client = make_client()
    response = client.post("/research/gwas/search", json={})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_gwas_query"


def test_gwas_api_returns_safe_provider_error(monkeypatch):
    import app.literature.gwas_catalog as provider

    def unavailable(**kwargs):
        raise provider.GwasCatalogProviderError("private upstream details")

    monkeypatch.setattr(provider, "search_gwas_catalog", unavailable)
    _, client = make_client()
    response = client.post("/research/gwas/search", json={"gene_symbol": "BRCA1"})
    assert response.status_code == 503
    assert response.json()["error"] == "gwas_provider_unavailable"
    assert "private upstream details" not in response.text


def test_gwas_api_bounds_concurrent_provider_calls(monkeypatch):
    import app.api as api_module
    import app.literature.gwas_catalog as provider

    monkeypatch.setattr(api_module, "_GWAS_SEARCH_SLOTS", threading.BoundedSemaphore(0))
    monkeypatch.setattr(provider, "search_gwas_catalog", lambda **kwargs: response_payload())
    _, client = make_client()
    response = client.post("/research/gwas/search", json={"gene_symbol": "BRCA1"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "2"
    assert response.headers["cache-control"] == "no-store"
