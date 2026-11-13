from __future__ import annotations

import pytest

from app.literature import gwas_catalog


def metadata():
    return {
        "title": "GWAS Catalog Rest API 2.0",
        "version": "2.0",
        "data_release_date": "2026-10-29",
        "api_release_date": "2025-08-01",
        "dbsnp_build": "156",
        "gene_build": "GRCh38.p14",
        "efo_version": "v3.95.0",
        "ensembl_version": "116",
        "commit_hash": "c5e2dc9",
        "terms_of_service": "https://www.ebi.ac.uk/about/terms-of-use/",
        "license": {
            "name": "Apache License 2.0",
            "url": "https://github.com/EBISPOT/gwas-rest-api/blob/master/LICENSE",
        },
    }


def association_payload():
    return {
        "_embedded": {
            "associations": [{
                "association_id": 218086295,
                "risk_frequency": "NR",
                "pvalue_description": "",
                "pvalue_mantissa": 2,
                "pvalue_exponent": -24,
                "multi_snp_haplotype": False,
                "snp_interaction": False,
                "range": "-",
                "beta": "-",
                "p_value": 2.0e-24,
                "efo_traits": [{"efo_id": "EFO_0004503", "efo_trait": "hematological measurement"}],
                "reported_trait": ["Hematological traits (multi-trait analysis)"],
                "accession_id": "GCST90838669",
                "locations": ["17:43100558"],
                "mapped_genes": ["BRCA1"],
                "pubmed_id": 38627641,
                "first_author": "Troubat L",
                "snp_effect_allele": ["rs10445316-?"],
                "snp_allele": [{"rs_id": "rs10445316", "effect_allele": "?"}],
                "_links": {
                    "self": {"href": "https://www.ebi.ac.uk/gwas/rest/api/v2/associations/218086295"},
                    "loci": {"href": "https://www.ebi.ac.uk/gwas/rest/api/v2/associations/218086295/loci"},
                    "snp": {"href": "https://www.ebi.ac.uk/gwas/rest/api/v2/single-nucleotide-polymorphisms/rs10445316"},
                },
            }],
        },
        "_links": {
            "first": {"href": "https://www.ebi.ac.uk/gwas/rest/api/v2/associations?mapped_gene=BRCA1&page=0&size=3"},
            "self": {"href": "https://www.ebi.ac.uk/gwas/rest/api/v2/associations?mapped_gene=BRCA1&page=0&size=3"},
            "next": {"href": "https://www.ebi.ac.uk/gwas/rest/api/v2/associations?mapped_gene=BRCA1&page=1&size=3"},
            "last": {"href": "https://www.ebi.ac.uk/gwas/rest/api/v2/associations?mapped_gene=BRCA1&page=10&size=3"},
        },
        "page": {"size": 3, "totalElements": 31, "totalPages": 11, "number": 0},
    }


def test_gwas_v2_search_preserves_release_effect_and_source_provenance(monkeypatch):
    calls = []
    monkeypatch.setattr(gwas_catalog, "_get_metadata", metadata)

    def fake_fetch(path, params=None):
        calls.append((path, params))
        return association_payload()

    monkeypatch.setattr(gwas_catalog, "_fetch_json", fake_fetch)
    result = gwas_catalog.search_gwas_catalog(
        gene_symbol="brca1", rs_id="RS10445316", trait="breast cancer",
        show_child_traits=True, page=0, size=3,
    )

    assert calls[0][0] == "/associations"
    assert calls[0][1] == {
        "page": "0", "size": "3", "extended_geneset": "false",
        "mapped_gene": "BRCA1", "rs_id": "rs10445316",
        "efo_trait": "breast cancer", "show_child_trait": "true",
    }
    record = result["records"][0]
    assert result["provider"] == "GWAS Catalog"
    assert result["api_version"] == "2.0"
    assert result["provenance"]["data_release_date"] == "2026-10-29"
    assert result["provenance"]["license"] == "Apache License 2.0"
    assert result["count"] == 31 and result["has_more"] is True
    assert result["next_page_url"].endswith("page=1&size=3")
    assert record["association_id"] == "218086295"
    assert record["study_accession"] == "GCST90838669"
    assert record["pubmed_url"] == "https://pubmed.ncbi.nlm.nih.gov/38627641/"
    assert record["p_value"] == 2.0e-24
    assert record["pvalue_mantissa"] == 2 and record["pvalue_exponent"] == -24
    assert record["mapped_genes"] == ["BRCA1"]
    assert record["snp_alleles"][0]["rs_id"] == "rs10445316"
    assert record["source_url"].endswith("/associations/218086295")
    assert record["study_url"].endswith("/GCST90838669")


def test_gwas_v2_empty_result_is_a_valid_empty_state(monkeypatch):
    monkeypatch.setattr(gwas_catalog, "_get_metadata", metadata)
    monkeypatch.setattr(
        gwas_catalog, "_fetch_json",
        lambda *args, **kwargs: {
            "_embedded": {"associations": []},
            "_links": {"self": {"href": "https://www.ebi.ac.uk/gwas/rest/api/v2/associations?page=0&size=20"}},
            "page": {"size": 20, "totalElements": 0, "totalPages": 0, "number": 0},
        },
    )
    result = gwas_catalog.search_gwas_catalog(gene_symbol="NO_SUCH_GENE")
    assert result["count"] == 0
    assert result["records"] == []
    assert result["has_more"] is False


@pytest.mark.parametrize("kwargs", [
    {},
    {"gene_symbol": "BRCA1 OR *"},
    {"rs_id": "rs12 OR *"},
    {"trait": "x"},
    {"trait": "asthma\nOR cancer"},
    {"show_child_traits": "true", "gene_symbol": "BRCA1"},
    {"show_child_traits": True, "gene_symbol": "BRCA1"},
    {"page": -1, "gene_symbol": "BRCA1"},
    {"page": True, "gene_symbol": "BRCA1"},
    {"size": 51, "gene_symbol": "BRCA1"},
    {"size": False, "gene_symbol": "BRCA1"},
])
def test_gwas_v2_rejects_invalid_search_inputs(kwargs):
    with pytest.raises(ValueError):
        gwas_catalog.validate_search_request(**kwargs)


def test_gwas_v2_rejects_unsafe_pagination_link(monkeypatch):
    monkeypatch.setattr(gwas_catalog, "_get_metadata", metadata)
    payload = association_payload()
    payload["_links"]["next"]["href"] = "https://attacker.example/steal"
    monkeypatch.setattr(gwas_catalog, "_fetch_json", lambda *args, **kwargs: payload)
    with pytest.raises(gwas_catalog.GwasCatalogProviderError, match="safe next-page link"):
        gwas_catalog.search_gwas_catalog(gene_symbol="BRCA1", size=3)


def test_gwas_v2_rejects_malformed_association_identifier(monkeypatch):
    monkeypatch.setattr(gwas_catalog, "_get_metadata", metadata)
    payload = association_payload()
    payload["_embedded"]["associations"][0]["association_id"] = "not-an-id"
    monkeypatch.setattr(gwas_catalog, "_fetch_json", lambda *args, **kwargs: payload)
    with pytest.raises(gwas_catalog.GwasCatalogProviderError, match="invalid association identifier"):
        gwas_catalog.search_gwas_catalog(gene_symbol="BRCA1", size=3)
