from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

from app.literature import ontology


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
        "response": {
            "numFound": 21,
            "docs": [{
                "label": "breast carcinoma",
                "iri": "http://purl.obolibrary.org/obo/MONDO_0007254",
                "obo_id": "MONDO:0007254",
                "short_form": "MONDO_0007254",
                "ontology_name": "mondo",
                "ontology_prefix": "MONDO",
                "description": ["A malignant breast neoplasm."],
                "synonym": ["breast cancer"],
                "is_obsolete": False,
            }],
        }
    }


def test_search_normalizes_source_terms_and_pagination(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout, request.headers))
        return FakeResponse(payload())

    monkeypatch.setattr(ontology, "urlopen", fake_urlopen)
    result = ontology.search_ontology("breast cancer", ontology="mondo", page=1, size=10)
    params = parse_qs(urlparse(calls[0][0]).query)
    assert params["ontology"] == ["mondo"]
    assert params["start"] == ["10"]
    assert params["obsoletes"] == ["false"]
    assert params["type"] == ["class"]
    assert result["has_more"] is True
    assert result["terms"][0]["obo_id"] == "MONDO:0007254"
    assert result["terms"][0]["synonyms"] == ["breast cancer"]
    assert result["terms"][0]["ontology"] == "mondo"
    assert result["interpretation"].startswith("Ontology term search results")


def test_all_searches_only_the_three_supported_ontologies(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(payload())

    monkeypatch.setattr(ontology, "urlopen", fake_urlopen)
    ontology.search_ontology("ataxia")
    params = parse_qs(urlparse(calls[0]).query)
    assert set(params["ontology"][0].split(",")) == {"mondo", "hp", "doid"}


@pytest.mark.parametrize(
    ("query", "ontology_id", "page", "size"),
    [
        ("", "all", 0, 10),
        ("x", "all", 0, 10),
        ("breast cancer", "unknown", 0, 10),
        ("breast cancer", "mondo", -1, 10),
        ("breast cancer", "mondo", 0, 21),
        ("breast cancer", "mondo", True, 10),
    ],
)
def test_rejects_invalid_input_without_network(monkeypatch, query, ontology_id, page, size):
    monkeypatch.setattr(ontology, "urlopen", lambda *a, **k: pytest.fail("network called"))
    with pytest.raises(ValueError):
        ontology.search_ontology(query, ontology=ontology_id, page=page, size=size)


def test_rejects_terms_outside_allowlist(monkeypatch):
    bad = payload()
    bad["response"]["docs"][0]["ontology_name"] = "do-not-trust"
    bad["response"]["docs"][0]["ontology_prefix"] = "UNTRUSTED"
    monkeypatch.setattr(ontology, "urlopen", lambda *a, **k: FakeResponse(bad))
    with pytest.raises(ontology.OntologyProviderError, match="outside"):
        ontology.search_ontology("breast cancer")


def test_rejects_malformed_provider_response(monkeypatch):
    monkeypatch.setattr(ontology, "urlopen", lambda *a, **k: FakeResponse({"unexpected": {}}))
    with pytest.raises(ontology.OntologyProviderError, match="response.docs"):
        ontology.search_ontology("breast cancer")


def test_rejects_oversized_response(monkeypatch):
    class Oversized(FakeResponse):
        def read(self, limit):
            return b"x" * limit

    monkeypatch.setattr(ontology, "urlopen", lambda *a, **k: Oversized({}))
    with pytest.raises(ontology.OntologyProviderError, match="1 MB"):
        ontology.search_ontology("breast cancer")
