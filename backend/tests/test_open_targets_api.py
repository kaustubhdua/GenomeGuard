from __future__ import annotations

import threading

from tests.helpers import make_client


def payload():
    return {
        "provider": "Open Targets Platform",
        "target": {"id": "ENSG00000141510", "approved_symbol": "TP53", "biotype": "protein_coding"},
        "associations": {"count": 1, "page_index": 0, "page_size": 20, "direct_only": True, "rows": []},
        "evidence": {"disease_id": "EFO_0000311", "count": 0, "cursor": None, "rows": []},
        "provenance": {"provider": "Open Targets Platform", "data_version": {"year": "2026", "month": "06"}},
        "interpretation": {"association_score": "not a probability"},
    }


def test_open_targets_api_returns_no_store_and_source_provenance(monkeypatch):
    import app.literature.open_targets as provider

    monkeypatch.setattr(provider, "search_target", lambda *args, **kwargs: payload())
    _, client = make_client()
    response = client.post(
        "/research/open-targets/target",
        json={"ensembl_id": "ENSG00000141510", "disease_id": "EFO_0000311"},
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "Open Targets Platform"
    assert response.json()["provenance"]["data_version"]["month"] == "06"
    assert response.headers["cache-control"] == "no-store"


def test_open_targets_api_rejects_invalid_identifier(monkeypatch):
    import app.literature.open_targets as provider

    def fail_network(*args, **kwargs):
        raise AssertionError("invalid input must not call provider")

    monkeypatch.setattr(provider, "search_target", fail_network)
    _, client = make_client()
    response = client.post("/research/open-targets/target", json={"ensembl_id": "TP53"})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_open_targets_query"


def test_open_targets_api_returns_safe_provider_error(monkeypatch):
    import app.literature.open_targets as provider

    def unavailable(*args, **kwargs):
        raise provider.OpenTargetsProviderError("private upstream details")

    monkeypatch.setattr(provider, "search_target", unavailable)
    _, client = make_client()
    response = client.post("/research/open-targets/target", json={"ensembl_id": "ENSG00000141510"})
    assert response.status_code == 503
    assert response.json()["error"] == "open_targets_provider_unavailable"
    assert "private upstream details" not in response.text


def test_open_targets_api_bounds_concurrent_provider_calls(monkeypatch):
    import app.api as api_module
    import app.literature.open_targets as provider

    monkeypatch.setattr(api_module, "_OPEN_TARGETS_SEARCH_SLOTS", threading.BoundedSemaphore(0))
    monkeypatch.setattr(provider, "search_target", lambda *args, **kwargs: payload())
    _, client = make_client()
    response = client.post("/research/open-targets/target", json={"ensembl_id": "ENSG00000141510"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "2"
    assert response.headers["cache-control"] == "no-store"
