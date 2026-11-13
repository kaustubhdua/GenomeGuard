from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from app.literature import pubmed


class FakeResponse:
    status = 200

    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _limit: int):
        return self.payload


def test_pubmed_search_normalizes_real_provider_contract(monkeypatch):
    calls = []
    responses = [
        {
            "esearchresult": {
                "count": "41",
                "retstart": "0",
                "retmax": "2",
                "idlist": ["12345678", "23456789"],
            }
        },
        {
            "header": {"type": "esummary", "version": "2.0"},
            "result": {
                "uids": ["12345678", "23456789"],
                "12345678": {
                    "uid": "12345678",
                    "title": "BRCA1 and ovarian cancer.",
                    "fulljournalname": "Journal of Oncology",
                    "pubdate": "2025 Jan",
                    "authors": [{"name": "A Researcher"}, {"name": "B Scientist"}],
                    "pubtype": ["Journal Article"],
                    "articleids": [
                        {"idtype": "pubmed", "value": "12345678"},
                        {"idtype": "doi", "value": "10.1000/example"},
                        {"idtype": "pmc", "value": "PMC12345"},
                    ],
                },
                "23456789": {
                    "uid": "23456789",
                    "title": "Genomic evidence in oncology",
                    "source": "Research Journal",
                    "pubdate": "2024",
                    "authors": [],
                    "articleids": [{"idtype": "pubmed", "value": "23456789"}],
                },
            },
        },
    ]

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout, request.headers))
        return FakeResponse(responses.pop(0))

    monkeypatch.setattr(pubmed, "urlopen", fake_urlopen)
    monkeypatch.setattr(pubmed, "_wait_for_rate_slot", lambda: None)
    result = pubmed.search_pubmed("BRCA1 ovarian cancer", retstart=0, retmax=2)

    assert len(calls) == 2
    first_params = parse_qs(urlparse(calls[0][0]).query)
    second_params = parse_qs(urlparse(calls[1][0]).query)
    assert first_params["db"] == ["pubmed"]
    assert first_params["term"] == ["BRCA1 ovarian cancer"]
    assert first_params["retmax"] == ["2"]
    assert second_params["id"] == ["12345678,23456789"]
    assert second_params["version"] == ["2.0"]
    assert result["count"] == 41
    assert result["has_more"] is True
    assert result["returned"] == 2
    assert result["papers"][0] == {
        "source": "PubMed",
        "source_id": "12345678",
        "pmid": "12345678",
        "pmcid": "PMC12345",
        "doi": "10.1000/example",
        "title": "BRCA1 and ovarian cancer.",
        "authors": ["A Researcher", "B Scientist"],
        "journal": "Journal of Oncology",
        "publication_date": "2025 Jan",
        "article_types": ["Journal Article"],
        "abstract": None,
        "abstract_available": False,
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
    }
    assert result["provenance"]["provider"] == "NCBI PubMed"
    assert result["provenance"]["abstracts_included"] is False


def test_pubmed_empty_search_skips_summary(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse({"esearchresult": {"count": "0", "idlist": []}})

    monkeypatch.setattr(pubmed, "urlopen", fake_urlopen)
    monkeypatch.setattr(pubmed, "_wait_for_rate_slot", lambda: None)
    result = pubmed.search_pubmed("nonexistent exact topic")
    assert result["count"] == 0
    assert result["papers"] == []
    assert result["has_more"] is False
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("query", "retstart", "retmax"),
    [
        ("", 0, 20),
        ("x" * 501, 0, 20),
        ("BRCA1", -1, 20),
        ("BRCA1", 0, 51),
        ("BRCA1", True, 20),
    ],
)
def test_pubmed_rejects_invalid_inputs_without_network(monkeypatch, query, retstart, retmax):
    def fail_network(*args, **kwargs):
        raise AssertionError("invalid input must be rejected before network access")

    monkeypatch.setattr(pubmed, "urlopen", fail_network)
    with pytest.raises(ValueError):
        pubmed.search_pubmed(query, retstart=retstart, retmax=retmax)


def test_pubmed_retries_rate_limit_and_honors_retry_after(monkeypatch):
    calls = []
    response = FakeResponse({"esearchresult": {"count": "0", "idlist": []}})

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 429, "rate limited", {"Retry-After": "0"}, None)
        return response

    monkeypatch.setattr(pubmed, "urlopen", fake_urlopen)
    monkeypatch.setattr(pubmed, "_wait_for_rate_slot", lambda: None)
    monkeypatch.setattr(pubmed.time, "sleep", lambda _: None)
    result = pubmed.search_pubmed("BRCA1")
    assert len(calls) == 2
    assert result["count"] == 0


def test_pubmed_rejects_malformed_provider_payload(monkeypatch):
    monkeypatch.setattr(pubmed, "urlopen", lambda *args, **kwargs: FakeResponse({"unexpected": {}}))
    monkeypatch.setattr(pubmed, "_wait_for_rate_slot", lambda: None)
    with pytest.raises(pubmed.PubMedProviderError, match="missing esearchresult"):
        pubmed.search_pubmed("BRCA1")


def test_pubmed_api_route_validates_and_disables_caching(monkeypatch):
    from tests.helpers import make_client

    expected = {
        "provider": "PubMed",
        "query": "BRCA1",
        "count": 1,
        "retstart": 0,
        "retmax": 20,
        "returned": 1,
        "has_more": False,
        "papers": [],
        "retrieved_at": "2026-01-01T00:00:00+00:00",
        "provenance": {"provider": "NCBI PubMed"},
    }
    monkeypatch.setattr(pubmed, "search_pubmed", lambda *args, **kwargs: expected)
    _, client = make_client()
    response = client.get("/literature/pubmed/search?q=BRCA1")
    assert response.status_code == 200
    assert response.json() == expected
    assert response.headers["cache-control"] == "no-store"

    invalid = client.get("/literature/pubmed/search?q=BRCA1&retmax=100")
    assert invalid.status_code == 400
    assert invalid.json()["error"] == "invalid_literature_query"


def test_pubmed_api_route_returns_safe_provider_error(monkeypatch):
    from tests.helpers import make_client

    def unavailable(*args, **kwargs):
        raise pubmed.PubMedProviderError("upstream detail must not leak")

    monkeypatch.setattr(pubmed, "search_pubmed", unavailable)
    _, client = make_client()
    response = client.get("/literature/pubmed/search?q=BRCA1")
    assert response.status_code == 503
    assert response.json()["error"] == "literature_provider_unavailable"
    assert "upstream detail" not in response.text
