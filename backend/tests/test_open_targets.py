from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from app.literature import open_targets


class FakeResponse:
    status = 200

    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _limit: int):
        return self.payload


def valid_payload(include_evidence: bool = True) -> dict:
    target = {
        "id": "ENSG00000141510",
        "approvedSymbol": "TP53",
        "biotype": "protein_coding",
        "associatedDiseases": {
            "count": 2,
            "rows": [
                {
                    "score": 0.91,
                    "disease": {"id": "EFO_0000311", "name": "breast carcinoma"},
                    "datasourceScores": [{"id": "eva", "score": 0.8}],
                    "datatypeScores": [{"id": "genetic_association", "score": 0.7}],
                },
                {
                    "score": 0.42,
                    "disease": {"id": "EFO_0000616", "name": "lung carcinoma"},
                    "datasourceScores": [],
                    "datatypeScores": [],
                },
            ],
        },
    }
    if include_evidence:
        target["evidences"] = {
            "count": 1,
            "cursor": None,
            "rows": [{
                "id": "evidence-1",
                "datasourceId": "eva",
                "datatypeId": "genetic_association",
                "score": 0.8,
                "releaseVersion": "26.06",
                "releaseDate": "2026-06-01",
                "publicationDate": "2025-02-01",
                "publicationFirstAuthor": "Example",
                "literature": ["12345678"],
                "urls": [{"url": "https://example.org/evidence/1", "niceName": "Source record"}],
                "studyId": "study-1",
                "studySampleSize": 1200,
                "cohortDescription": "Public study cohort",
                "qualityControls": [],
                "warningMessage": None,
            }],
        }
    return {
        "data": {
            "meta": {
                "product": "Open Targets Platform",
                "apiVersion": {"x": "4", "y": "0", "z": "0", "suffix": None},
                "dataVersion": {"year": "2026", "month": "06", "iteration": "1"},
            },
            "target": target,
        }
    }


def test_open_targets_returns_direct_associations_and_source_evidence(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout, json.loads(request.data)))
        return FakeResponse(valid_payload())

    monkeypatch.setattr(open_targets, "urlopen", fake_urlopen)
    result = open_targets.search_target(
        "ENSG00000141510", disease_id="EFO_0000311", page_index=0, page_size=20, evidence_size=25,
    )
    assert len(calls) == 1
    request, timeout, body = calls[0]
    assert request.full_url == open_targets.ENDPOINT
    assert request.method == "POST"
    assert request.headers["Content-type"] == "application/json"
    assert timeout == open_targets.TIMEOUT_SECONDS
    assert body["variables"]["ensemblId"] == "ENSG00000141510"
    assert body["variables"]["includeEvidence"] is True
    assert body["variables"]["diseaseId"] == "EFO_0000311"
    assert "enableIndirect: false" in body["query"]
    assert result["target"]["approved_symbol"] == "TP53"
    assert result["associations"]["direct_only"] is True
    assert result["associations"]["rows"][0]["disease"]["id"] == "EFO_0000311"
    assert result["evidence"]["rows"][0]["literature"] == ["12345678"]
    assert result["provenance"]["data_version"]["month"] == "06"
    assert "not a probability" in result["interpretation"]["association_score"]


def test_open_targets_skips_evidence_when_no_disease_filter(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(json.loads(request.data))
        return FakeResponse(valid_payload(include_evidence=False))

    monkeypatch.setattr(open_targets, "urlopen", fake_urlopen)
    result = open_targets.search_target("ENSG00000141510")
    assert calls[0]["variables"]["includeEvidence"] is False
    assert result["evidence"]["rows"] == []
    assert result["evidence"]["count"] == 0


@pytest.mark.parametrize(
    ("ensembl_id", "disease_id", "page_index", "page_size", "evidence_size"),
    [
        ("TP53", None, 0, 20, 25),
        ("ENSG00000141510", "not an ontology id with spaces", 0, 20, 25),
        ("ENSG00000141510", None, -1, 20, 25),
        ("ENSG00000141510", None, 0, 51, 25),
        ("ENSG00000141510", None, 0, 20, 51),
        ("ENSG00000141510", None, True, 20, 25),
    ],
)
def test_open_targets_rejects_invalid_inputs_without_network(
    monkeypatch, ensembl_id, disease_id, page_index, page_size, evidence_size,
):
    def fail_network(*args, **kwargs):
        raise AssertionError("invalid input must be rejected before network access")

    monkeypatch.setattr(open_targets, "urlopen", fail_network)
    with pytest.raises(ValueError):
        open_targets.search_target(
            ensembl_id, disease_id=disease_id, page_index=page_index,
            page_size=page_size, evidence_size=evidence_size,
        )


def test_open_targets_rejects_graphql_partial_data(monkeypatch):
    monkeypatch.setattr(
        open_targets, "urlopen",
        lambda *args, **kwargs: FakeResponse({"data": {"target": None}, "errors": [{"message": "partial"}]}),
    )
    with pytest.raises(open_targets.OpenTargetsProviderError, match="GraphQL errors"):
        open_targets.search_target("ENSG00000141510")


def test_open_targets_rejects_malformed_association_rows(monkeypatch):
    payload = valid_payload(include_evidence=False)
    payload["data"]["target"]["associatedDiseases"]["rows"] = [{"score": 0.5, "disease": None}]
    monkeypatch.setattr(open_targets, "urlopen", lambda *args, **kwargs: FakeResponse(payload))
    with pytest.raises(open_targets.OpenTargetsProviderError, match="malformed association"):
        open_targets.search_target("ENSG00000141510")


def test_open_targets_retries_transient_http_failure(monkeypatch):
    calls = []
    payload = FakeResponse(valid_payload(include_evidence=False))

    def fake_urlopen(request, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 503, "temporary", {"Retry-After": "0"}, None)
        return payload

    monkeypatch.setattr(open_targets, "urlopen", fake_urlopen)
    monkeypatch.setattr(open_targets.time, "sleep", lambda _: None)
    result = open_targets.search_target("ENSG00000141510")
    assert result["target"]["approved_symbol"] == "TP53"
    assert len(calls) == 2
