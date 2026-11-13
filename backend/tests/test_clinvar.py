from __future__ import annotations

import pytest

from app.literature import clinvar


def valid_summary(uid: str = "373892") -> dict:
    return {
        "result": {
            "uids": [uid],
            uid: {
                "uid": uid,
                "accession": "VCV000373892",
                "accession_version": "VCV000373892.1",
                "title": "NG_005905.2:g.(147057_150288)_(160933_166866)del",
                "obj_type": "Deletion",
                "genes": [{"symbol": "BRCA1", "geneid": 672, "source": "submitted"}],
                "variation_set": [{
                    "variation_name": "BRCA1 deletion",
                    "cdna_change": "c.100del",
                    "variant_type": "Deletion",
                    "canonical_spdi": "NC_000017.11:43051117:AA:A",
                    "variation_loc": [
                        {
                            "status": "current",
                            "assembly_name": "GRCh38",
                            "chr": "17",
                            "start": "43051118",
                            "stop": "43070927",
                            "assembly_acc_ver": "GCF_000001405.38",
                        },
                        {
                            "status": "previous",
                            "assembly_name": "GRCh37",
                            "chr": "17",
                            "start": "41203135",
                            "stop": "41222944",
                            "assembly_acc_ver": "GCF_000001405.25",
                        },
                    ],
                }],
                "germline_classification": {
                    "description": "Conflicting classifications of pathogenicity",
                    "last_evaluated": "2026/07/01 00:00",
                    "review_status": "criteria provided, conflicting interpretations",
                    "fda_recognized_database": "",
                    "trait_set": [{
                        "trait_name": "Inherited breast cancer",
                        "trait_xrefs": [{"db_source": "MedGen", "db_id": "C0006142"}],
                    }],
                },
                "clinical_impact_classification": {
                    "description": "Tier II - Potential",
                    "last_evaluated": "2026/06/01 00:00",
                    "review_status": "criteria provided, single submitter",
                    "trait_set": [],
                },
                "oncogenicity_classification": {
                    "description": "",
                    "last_evaluated": "1/01/01 00:00",
                    "review_status": "",
                    "trait_set": [],
                },
                "supporting_submissions": {
                    "scv": ["SCV000000001", "SCV000000002"],
                    "rcv": ["RCV000000001"],
                },
                "molecular_consequence_list": ["frameshift variant"],
                "protein_change": "R951fs",
            },
        }
    }


def test_clinvar_search_uses_gene_and_properties_filter_and_preserves_conflict(monkeypatch):
    calls = []

    def fake_fetch(endpoint, params):
        calls.append((endpoint, params))
        if endpoint == "esearch":
            return {"esearchresult": {"count": "42", "idlist": ["373892"]}}
        return valid_summary()

    monkeypatch.setattr(clinvar, "_fetch_json", fake_fetch)
    result = clinvar.search_clinvar("brca1", classification="pathogenic", retstart=0, retmax=1)

    assert calls[0][0] == "esearch"
    assert calls[0][1]["db"] == "clinvar"
    assert calls[0][1]["term"] == 'BRCA1[gene] AND "clinsig pathogenic"[Properties]'
    assert calls[1][0] == "esummary"
    assert calls[1][1]["id"] == "373892"
    assert calls[1][1]["version"] == "2.0"
    assert result["count"] == 42
    assert result["has_more"] is True
    assert result["records"][0]["accession"] == "VCV000373892"
    assert result["records"][0]["classifications"]["germline"]["description"] == (
        "Conflicting classifications of pathogenicity"
    )
    assert result["records"][0]["classifications"]["germline"]["review_status"] == (
        "criteria provided, conflicting interpretations"
    )
    assert result["records"][0]["classifications"]["germline"]["traits"][0]["xrefs"][0] == {
        "database": "MedGen", "id": "C0006142",
    }
    assert [x["assembly"] for x in result["records"][0]["variations"][0]["locations"]] == [
        "GRCh38", "GRCh37",
    ]
    assert result["records"][0]["supporting_submissions"]["scv_count"] == 2
    assert result["query"]["classification_filter_semantics"].startswith(
        "ClinVar Properties search for at least one report"
    )
    assert result["records"][0]["source_url"].endswith("/373892/")


@pytest.mark.parametrize("classification,property_term", [
    ("pathogenic", "clinsig pathogenic"),
    ("likely_pathogenic", "clinsig likely pathogenic"),
    ("uncertain_significance", "clinsig vus"),
    ("likely_benign", "clinsig likely benign"),
    ("benign", "clinsig benign"),
    ("conflicting", "clinsig has conflicts"),
])
def test_clinvar_supported_classification_filters(monkeypatch, classification, property_term):
    calls = []

    def fake_fetch(endpoint, params):
        calls.append((endpoint, params))
        if endpoint == "esearch":
            return {"esearchresult": {"count": "0", "idlist": []}}
        raise AssertionError("ESummary must not be called for an empty result set")

    monkeypatch.setattr(clinvar, "_fetch_json", fake_fetch)
    result = clinvar.search_clinvar("TP53", classification=classification)
    assert calls[0][1]["term"] == f'TP53[gene] AND "{property_term}"[Properties]'
    assert result["records"] == []
    assert result["count"] == 0


def test_clinvar_search_without_filter_uses_gene_only(monkeypatch):
    monkeypatch.setattr(
        clinvar, "_fetch_json",
        lambda endpoint, params: {"esearchresult": {"count": "0", "idlist": []}},
    )
    result = clinvar.search_clinvar("TP53")
    assert result["provenance"]["query"] == "TP53[gene]"
    assert result["query"]["classification_filter"] is None


@pytest.mark.parametrize("gene,classification,retstart,retmax", [
    ("", None, 0, 20),
    ("BRCA1 OR *", None, 0, 20),
    ("BRCA1", "invented", 0, 20),
    ("BRCA1", None, -1, 20),
    ("BRCA1", None, True, 20),
    ("BRCA1", None, 0, 51),
    ("BRCA1", None, 0, False),
])
def test_clinvar_rejects_invalid_inputs_before_network(monkeypatch, gene, classification, retstart, retmax):
    def fail_network(*args, **kwargs):
        raise AssertionError("invalid input must not call NCBI")

    monkeypatch.setattr(clinvar, "_fetch_json", fail_network)
    with pytest.raises(ValueError):
        clinvar.search_clinvar(
            gene, classification=classification, retstart=retstart, retmax=retmax,
        )


def test_clinvar_rejects_malformed_esearch_payload(monkeypatch):
    monkeypatch.setattr(clinvar, "_fetch_json", lambda *args, **kwargs: {"unexpected": {}})
    with pytest.raises(clinvar.ClinVarProviderError, match="missing esearchresult"):
        clinvar.search_clinvar("BRCA1")


def test_clinvar_rejects_missing_esummary_record(monkeypatch):
    monkeypatch.setattr(
        clinvar, "_fetch_json",
        lambda endpoint, params: (
            {"esearchresult": {"count": "1", "idlist": ["373892"]}}
            if endpoint == "esearch" else {"result": {"uids": ["373892"]}}
        ),
    )
    with pytest.raises(clinvar.ClinVarProviderError, match="omitted a requested variation"):
        clinvar.search_clinvar("BRCA1")


def test_clinvar_rejects_unexpected_esummary_uid_set(monkeypatch):
    monkeypatch.setattr(
        clinvar, "_fetch_json",
        lambda endpoint, params: (
            {"esearchresult": {"count": "1", "idlist": ["373892"]}}
            if endpoint == "esearch" else {"result": {"uids": ["999999"]}}
        ),
    )
    with pytest.raises(clinvar.ClinVarProviderError, match="unexpected identifier set"):
        clinvar.search_clinvar("BRCA1")
