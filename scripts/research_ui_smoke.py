#!/usr/bin/env python3
"""Browser acceptance for GenomeGuard's department, literature, and variant evidence discovery.

The provider is intercepted with source-shaped fixtures here so the UI test is
deterministic. A separate CI smoke test exercises the real Europe PMC service.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

PAGE_SIZE = 20


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--timeout", type=int, default=20_000)
    args = parser.parse_args()
    requests: list[dict[str, str]] = []
    failures: list[str] = []
    pubmed_requests: list[dict[str, object]] = []
    open_targets_requests: list[dict[str, object]] = []
    clinvar_requests: list[dict[str, object]] = []
    gwas_requests: list[dict[str, object]] = []
    provider_outages = {"europe": False, "pubmed": False}

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
        if not ok:
            failures.append(label)

    def response_record(page: int, index: int) -> dict:
        suffix = "one" if page == 1 else "two"
        return {
            "title": f"Verified provider-shaped publication {suffix}-{index + 1}",
            "authorString": "Example Research Group",
            "journalTitle": "Journal of Biomedical Research",
            "firstPublicationDate": "2026-01-15",
            "pmid": str(12345678 + page * 100 + index),
            "doi": f"10.1000/genomeguard.{suffix}.{index + 1}",
            "isOpenAccess": "Y",
            "abstractText": "A test fixture used only to verify the publication display contract.",
        }

    def handle_provider(route) -> None:
        if provider_outages["europe"]:
            route.fulfill(status=503, content_type="application/json", body=json.dumps({"error": "fixture outage"}))
            return
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        cursor = query.get("cursorMark", ["*"])[0]
        page = 1 if cursor == "*" else 2
        requests.append({"query": query.get("query", [""])[0], "cursorMark": cursor})
        records = ([response_record(1, index) for index in range(PAGE_SIZE)]
                   if page == 1 else [response_record(2, 0)])
        body = {
            "hitCount": PAGE_SIZE + 1,
            "nextCursorMark": "cursor-page-2" if page == 1 else "cursor-page-2",
            "resultList": {"result": records},
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def handle_pubmed(route) -> None:
        if provider_outages["pubmed"]:
            route.fulfill(status=503, content_type="application/json", body=json.dumps({"error": "fixture outage"}))
            return
        payload = json.loads(route.request.post_data or "{}")
        pubmed_requests.append(payload)
        if int(payload.get("retstart", 0)) == 0:
            papers = [
                {"source": "PubMed", "pmid": "12345778", "title": "Duplicate PubMed title one",
                 "authors": ["PubMed Test Author"], "journal": "PubMed Journal",
                 "publication_date": "2026", "doi": "10.1000/genomeguard.one",
                 "abstract": None, "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345778/"},
                {"source": "PubMed", "pmid": "12345779", "title": "Duplicate PubMed title two",
                 "authors": ["PubMed Test Author"], "journal": "PubMed Journal",
                 "publication_date": "2026", "doi": "10.1000/genomeguard.two",
                 "abstract": None, "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345779/"},
                {"source": "PubMed", "pmid": "99999999", "title": "PubMed-only verified publication",
                 "authors": ["NCBI Author"], "journal": "NCBI Journal",
                 "publication_date": "2026", "doi": "10.1000/genomeguard.pubmed",
                 "abstract": None, "source_url": "https://pubmed.ncbi.nlm.nih.gov/99999999/"},
            ]
            body = {"provider": "PubMed", "count": 4, "retstart": 0, "retmax": PAGE_SIZE,
                    "returned": 3, "has_more": True, "papers": papers}
        else:
            papers = [{
                "source": "PubMed", "pmid": "12345999", "title": "Unique PubMed second-page publication",
                "authors": ["NCBI Author"], "journal": "NCBI Journal", "publication_date": "2026",
                "doi": "10.1000/genomeguard.page2", "abstract": None,
                "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345999/"
            }]
            body = {"provider": "PubMed", "count": 4, "retstart": 3, "retmax": PAGE_SIZE,
                    "returned": 1, "has_more": False, "papers": papers}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def handle_open_targets(route) -> None:
        payload = json.loads(route.request.post_data or "{}")
        open_targets_requests.append(payload)
        page_index = int(payload.get("page_index", 0))
        evidence_cursor = payload.get("evidence_cursor")
        if page_index == 0:
            association_rows = [
                {"score": 0.91, "disease": {"id": "EFO_0000311", "name": "breast carcinoma"},
                 "datasourceScores": [{"id": "eva", "score": 0.8}],
                 "datatypeScores": [{"id": "genetic_association", "score": 0.7}]},
                {"score": 0.42, "disease": {"id": "EFO_0000616", "name": "lung carcinoma"},
                 "datasourceScores": [{"id": "ot_genetics_portal", "score": 0.4}],
                 "datatypeScores": [{"id": "genetic_association", "score": 0.3}]},
            ]
        else:
            association_rows = [
                {"score": 0.33, "disease": {"id": "EFO_0000408", "name": "ovarian carcinoma"},
                 "datasourceScores": [{"id": "ot_genetics_portal", "score": 0.33}],
                 "datatypeScores": [{"id": "genetic_association", "score": 0.2}]},
            ]
        if evidence_cursor:
            evidence_rows = [{
                "id": "evidence-3", "datasourceId": "ot_genetics_portal",
                "datatypeId": "genetic_association", "score": 0.55,
                "releaseVersion": "26.06", "releaseDate": "2026-06-01",
                "publicationDate": "2025-03-01", "publicationFirstAuthor": "Second Author",
                "literature": ["87654321"],
                "urls": [{"url": "https://example.org/evidence/3", "niceName": "Second source record"}],
                "studyId": "study-3", "studySampleSize": 2400,
                "cohortDescription": "Second public study cohort", "qualityControls": [],
                "warningMessage": None,
            }]
            evidence_next = None
        else:
            evidence_rows = [
                {"id": "evidence-1", "datasourceId": "eva",
                 "datatypeId": "genetic_association", "score": 0.8,
                 "releaseVersion": "26.06", "releaseDate": "2026-06-01",
                 "publicationDate": "2025-02-01", "publicationFirstAuthor": "Example",
                 "literature": ["12345678"],
                 "urls": [{"url": "https://example.org/evidence/1", "niceName": "Source record"}],
                 "studyId": "study-1", "studySampleSize": 1200,
                 "cohortDescription": "Public study cohort", "qualityControls": [],
                 "warningMessage": None},
                {"id": "evidence-2", "datasourceId": "ot_genetics_portal",
                 "datatypeId": "genetic_association", "score": 0.6,
                 "releaseVersion": "26.06", "releaseDate": "2026-06-01",
                 "publicationDate": "2025-02-15", "publicationFirstAuthor": "Another Author",
                 "literature": ["23456789"],
                 "urls": [{"url": "https://example.org/evidence/2", "niceName": "Another source record"}],
                 "studyId": "study-2", "studySampleSize": 1800,
                 "cohortDescription": "Another public study cohort", "qualityControls": [],
                 "warningMessage": None},
            ]
            evidence_next = "evidence-next"
        body = {
            "provider": "Open Targets Platform",
            "target": {"id": "ENSG00000141510", "approved_symbol": "TP53", "biotype": "protein_coding"},
            "associations": {"count": 3, "page_index": page_index, "page_size": 20,
                             "direct_only": True, "rows": association_rows},
            "evidence": {"disease_id": payload.get("disease_id"), "count": 3,
                         "cursor": evidence_next, "rows": evidence_rows},
            "provenance": {
                "provider": "Open Targets Platform",
                "api_version": {"x": "4", "y": "0", "z": "0", "suffix": None},
                "data_version": {"year": "2026", "month": "06", "iteration": "1"},
                "retrieved_at": "2026-11-13T09:30:00Z",
                "endpoint": "https://api.platform.opentargets.org/api/v4/graphql",
                "association_mode": "direct-only (enableIndirect=false)",
            },
            "interpretation": {
                "association_score": "Open Targets heuristic prioritisation score in [0,1]; not a probability or clinical validity assessment",
                "evidence_score": "Source/platform evidence score; not an independent GenomeGuard confidence estimate",
                "limitations": ["Review original evidence sources and publications before drawing conclusions."],
            },
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def handle_clinvar(route) -> None:
        payload = json.loads(route.request.post_data or "{}")
        clinvar_requests.append(payload)
        retstart = int(payload.get("retstart", 0))
        uid = "373892" if retstart == 0 else "267741"
        classification = (
            "Conflicting classifications of pathogenicity"
            if retstart == 0 else "Pathogenic"
        )
        review_status = (
            "criteria provided, conflicting interpretations"
            if retstart == 0 else "criteria provided, single submitter"
        )
        record = {
            "uid": uid,
            "accession": "VCV000373892" if retstart == 0 else "VCV000267741",
            "accession_version": "VCV000373892.1" if retstart == 0 else "VCV000267741.1",
            "title": "NM_007294.4(BRCA1):c.100del",
            "variation_type": "Deletion",
            "genes": [{"symbol": "BRCA1", "gene_id": "672"}],
            "variations": [{
                "name": "BRCA1 deletion",
                "type": "Deletion",
                "locations": [{
                    "status": "current", "assembly": "GRCh38", "chromosome": "17",
                    "start": "43051118", "stop": "43051119",
                }],
            }],
            "molecular_consequences": ["frameshift variant"],
            "classifications": {
                "germline": {
                    "description": classification, "review_status": review_status,
                    "last_evaluated": "2026/07/01 00:00", "traits": [],
                },
                "somatic_clinical_impact": {"description": None, "review_status": None, "traits": []},
                "somatic_oncogenicity": {"description": None, "review_status": None, "traits": []},
            },
            "supporting_submissions": {"scv_count": 2, "rcv_count": 1},
            "source_url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{uid}/",
        }
        query = {
            "gene_symbol": "BRCA1", "classification_filter": "pathogenic",
            "classification_filter_semantics": "ClinVar Properties search for at least one report.",
            "retstart": retstart, "retmax": PAGE_SIZE,
        }
        body = {
            "provider": "NCBI ClinVar", "query": query, "count": 2,
            "returned": 1, "has_more": retstart == 0, "records": [record],
            "retrieved_at": "2026-11-13T10:00:00Z",
            "provenance": {
                "provider": "NCBI ClinVar", "api": "E-utilities ESearch + ESummary v2.0",
                "query": 'BRCA1[gene] AND "clinsig pathogenic"[Properties]',
                "retrieved_at": "2026-11-13T10:00:00Z",
                "source_url": "https://www.ncbi.nlm.nih.gov/clinvar/",
                "classification_note": "Variant-level source assertions, not patient-specific interpretations.",
            },
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def handle_gwas(route) -> None:
        payload = json.loads(route.request.post_data or "{}")
        gwas_requests.append(payload)
        page_number = int(payload.get("page", 0))
        association_id = "218086295" if page_number == 0 else "218060208"
        trait_label = (
            "Hematological traits (multi-trait analysis)"
            if page_number == 0 else "Creatine kinase levels"
        )
        pubmed_id = "38627641" if page_number == 0 else "42066438"
        study = "GCST90838669" if page_number == 0 else "GCST90838680"
        record = {
            "association_id": association_id,
            "study_accession": study,
            "pubmed_id": pubmed_id,
            "first_author": "Troubat L" if page_number == 0 else "Chen G",
            "reported_traits": [trait_label],
            "efo_traits": [{"id": "EFO_0004503", "label": "hematological measurement"}],
            "p_value": 2.0e-24 if page_number == 0 else 2.0e-8,
            "pvalue_mantissa": 2,
            "pvalue_exponent": -24 if page_number == 0 else -8,
            "pvalue_description": "",
            "beta": "5.662 z score increase" if page_number else "-",
            "beta_numeric": 5.662 if page_number else None,
            "beta_unit": "z score",
            "beta_direction": "increase",
            "odds_ratio": None,
            "odds_ratio_text": None,
            "confidence_interval": {"text": "-", "lower": None, "upper": None},
            "risk_frequency": "NR",
            "locations": ["17:43100558"],
            "mapped_genes": ["BRCA1"],
            "snp_alleles": [{"rs_id": "rs10445316", "effect_allele": "?"}],
            "snp_effect_alleles": ["rs10445316-?"],
            "multi_snp_haplotype": False,
            "snp_interaction": False,
            "source_url": f"https://www.ebi.ac.uk/gwas/rest/api/v2/associations/{association_id}",
            "snp_url": "https://www.ebi.ac.uk/gwas/rest/api/v2/single-nucleotide-polymorphisms/rs10445316",
            "loci_url": f"https://www.ebi.ac.uk/gwas/rest/api/v2/associations/{association_id}/loci",
            "study_url": f"https://www.ebi.ac.uk/gwas/studies/{study}",
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/",
        }
        query = {
            "gene_symbol": payload.get("gene_symbol"),
            "rs_id": payload.get("rs_id"),
            "trait": payload.get("trait"),
            "show_child_traits": bool(payload.get("show_child_traits")),
            "extended_geneset": False,
            "page": page_number,
            "size": PAGE_SIZE,
        }
        body = {
            "provider": "GWAS Catalog",
            "api_version": "2.0",
            "query": query,
            "count": 2,
            "returned": 1,
            "has_more": page_number == 0,
            "next_page_url": (
                "https://www.ebi.ac.uk/gwas/rest/api/v2/associations?mapped_gene=BRCA1&page=1&size=20"
                if page_number == 0 else None
            ),
            "page": {
                "number": page_number, "size": PAGE_SIZE,
                "total_elements": 2, "total_pages": 2,
            },
            "records": [record],
            "retrieved_at": "2026-11-13T10:00:00Z",
            "provenance": {
                "provider": "GWAS Catalog", "api": "REST API v2", "api_version": "2.0",
                "data_release_date": "2026-10-29", "api_release_date": "2025-08-01",
                "dbsnp_build": "156", "gene_build": "GRCh38.p14",
                "efo_version": "v3.95.0", "ensembl_version": "116",
                "commit_hash": "c5e2dc9", "license": "Apache License 2.0",
                "license_url": "https://github.com/EBISPOT/gwas-rest-api/blob/master/LICENSE",
                "terms_of_service": "https://www.ebi.ac.uk/about/terms-of-use/",
                "source_url": "https://www.ebi.ac.uk/gwas/rest/api/v2/associations",
                "query_parameters": {"mapped_gene": "BRCA1", "page": str(page_number), "size": str(PAGE_SIZE)},
                "retrieved_at": "2026-11-13T10:00:00Z",
                "scope_note": "Literature-curated top associations; not full summary statistics.",
            },
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_default_timeout(args.timeout)
        page.route("https://www.ebi.ac.uk/europepmc/webservices/rest/search**", handle_provider)
        page.route("**/literature/pubmed/search", handle_pubmed)
        page.route("**/research/open-targets/target", handle_open_targets)
        page.route("**/research/clinvar/search", handle_clinvar)
        page.route("**/research/gwas/search", handle_gwas)
        page.goto(args.base.rstrip("/") + "/#/research", wait_until="domcontentloaded")
        page.get_by_role("heading", name="Research discovery").wait_for()
        page.get_by_role("link", name="Oncology Browse publications →").click()
        page.locator(".research-paper").first.wait_for()
        check("department hyperlink immediately performs a literature search",
              len(requests) == 1 and "oncology" in requests[0]["query"].lower()
              and len(pubmed_requests) == 1 and "oncology" in str(pubmed_requests[0].get("q", "")).lower(),
              str({"europe_pmc": requests, "pubmed": pubmed_requests}))
        check("department search renders source metadata",
              page.locator(".research-paper h3").first.inner_text() == "Verified provider-shaped publication one-1")
        check("first result page renders all 20 returned records",
              page.locator(".research-paper").count() == PAGE_SIZE + 1)
        first_page_count = page.locator(".research-paper").count()
        page.get_by_role("button", name="Load more publications").click()
        page.wait_for_function(
            "(before) => document.querySelectorAll('.research-paper').length > before",
            arg=first_page_count,
            timeout=args.timeout,
        )
        appended_count = page.locator(".research-paper").count()
        check("pagination appends the next provider page",
              len(requests) == 2 and requests[1]["cursorMark"] == "cursor-page-2"
              and len(pubmed_requests) == 2 and pubmed_requests[1].get("retstart") == 3
              and appended_count == first_page_count + 2,
              str({"before": first_page_count, "after": appended_count,
                   "europe_pmc": requests, "pubmed": pubmed_requests}))

        page.get_by_label("Research question or symptom description").fill("BRCA1 ovarian cancer symptoms")
        page.get_by_label("Research department", exact=True).select_option("oncology")
        page.get_by_role("button", name="Search publications").click()
        page.locator(".research-paper").first.wait_for()
        latest = requests[-1]["query"].lower()
        check("symptom/question search combines the selected department and user query",
              "oncology" in latest and "brca1 ovarian cancer symptoms" in latest, latest)
        check("publication links use HTTPS and open safely",
              page.locator(".research-paper a").first.get_attribute("href", timeout=args.timeout).startswith("https://")
              and page.locator(".research-paper a").first.get_attribute("rel") == "noopener noreferrer")

        page.get_by_label("Publication sources").select_option("pubmed")
        page.locator(".research-paper").first.wait_for()
        check("source selector can restrict results to PubMed",
              page.locator(".research-paper .tag").first.inner_text() == "PubMed"
              and page.locator(".research-paper").count() == 3)

        provider_outages["pubmed"] = True
        page.get_by_label("Publication sources").select_option("both")
        page.locator(".research-paper").first.wait_for()
        partial_status = page.locator("#research-status").inner_text()
        check("one-provider outage preserves the other provider's results",
              page.locator(".research-paper").count() == PAGE_SIZE
              and "One source was unavailable" in partial_status
              and "Europe PMC" in partial_status, partial_status)

        provider_outages["europe"] = True
        page.get_by_role("button", name="Search publications").click()
        page.get_by_text("No sample or fabricated papers are shown", exact=False).wait_for()
        check("both-provider outage shows an explicit failure and no fabricated records",
              page.locator(".research-paper").count() == 0
              and "No sample or fabricated papers are shown" in page.locator("#research-status").inner_text())

        provider_outages["europe"] = False
        provider_outages["pubmed"] = False

        page.get_by_label("Ensembl gene identifier").fill("ENSG00000141510")
        page.get_by_label("Optional EFO disease identifier").fill("EFO_0000311")
        page.get_by_role("button", name="Search Open Targets evidence").click()
        page.locator("#ot-association-results .research-paper").first.wait_for()
        page.locator("#ot-evidence-results .research-paper").first.wait_for()
        check("Open Targets query sends explicit Ensembl/EFO IDs and requests direct-only evidence",
              open_targets_requests[0].get("ensembl_id") == "ENSG00000141510"
              and open_targets_requests[0].get("disease_id") == "EFO_0000311"
              and open_targets_requests[0].get("page_index") == 0,
              str(open_targets_requests[0]))
        provenance_text = page.locator("#ot-provenance").inner_text()
        check("Open Targets UI shows API version, data release, retrieval timestamp and docs link",
              "4.0.0" in provenance_text and "2026.06.1" in provenance_text
              and "2026-11-13T09:30:00Z" in provenance_text
              and page.locator('#ot-provenance a[href="https://platform-docs.opentargets.org/data-access/graphql-api"]').count() == 1,
              provenance_text)
        page.get_by_label("Association source filter").select_option("eva")
        page.get_by_label("Evidence source filter").select_option("eva")
        check("Open Targets source filters isolate the selected datasource",
              page.locator("#ot-association-results .research-paper").count() == 1
              and page.locator("#ot-evidence-results .research-paper").count() == 1)
        source_link = page.locator("#ot-evidence-results a").first
        check("Open Targets evidence links are HTTPS and open safely",
              source_link.get_attribute("href", timeout=args.timeout).startswith("https://")
              and source_link.get_attribute("rel") == "noopener noreferrer")
        page.get_by_label("Association source filter").select_option("all")
        page.get_by_label("Evidence source filter").select_option("all")
        page.get_by_role("button", name="Load more associations").click()
        page.wait_for_function("document.querySelectorAll('#ot-association-results .research-paper').length === 3")
        page.get_by_role("button", name="Load more evidence").click()
        page.wait_for_function("document.querySelectorAll('#ot-evidence-results .research-paper').length === 3")
        check("Open Targets association and evidence pagination append source records",
              len(open_targets_requests) == 3
              and open_targets_requests[1].get("page_index") == 1
              and open_targets_requests[2].get("evidence_cursor") == "evidence-next")
        with page.expect_download() as json_download_info:
            page.get_by_role("button", name="Export evidence JSON").click()
        json_download = json_download_info.value
        exported = json.loads(Path(json_download.path()).read_text(encoding="utf-8"))
        check("Open Targets JSON export includes release, API, query and citation metadata",
              exported["provenance"]["data_version"]["month"] == "06"
              and exported["provenance"]["api_version"]["x"] == "4"
              and exported["associations"]["loaded_count"] == 3
              and any("Cite Open Targets Platform" in item for item in exported["citation_requirements"]))
        with page.expect_download() as markdown_download_info:
            page.get_by_role("button", name="Export Markdown report").click()
        markdown_download = markdown_download_info.value
        markdown_report = Path(markdown_download.path()).read_text(encoding="utf-8")
        check("Open Targets Markdown report includes data release and original evidence links",
              "Data release: 2026.06.1" in markdown_report
              and "https://example.org/evidence/1" in markdown_report
              and "Citation and reuse requirements" in markdown_report)

        page.locator("#clinvar-gene-symbol").fill("BRCA1")
        page.get_by_label("ClinVar report property filter").select_option("pathogenic")
        page.get_by_role("button", name="Search ClinVar variants").click()
        page.get_by_text("Conflicting classifications of pathogenicity", exact=True).wait_for()
        check("ClinVar displays source-provided aggregate conflicts and review status",
              len(clinvar_requests) == 1
              and clinvar_requests[0].get("gene_symbol") == "BRCA1"
              and clinvar_requests[0].get("classification") == "pathogenic"
              and "criteria provided, conflicting interpretations"
                  in page.locator("#clinvar-results").inner_text())
        clinvar_link = page.locator("#clinvar-results a").first
        check("ClinVar original record links are HTTPS and open safely",
              clinvar_link.get_attribute("href", timeout=args.timeout).startswith("https://")
              and clinvar_link.get_attribute("rel") == "noopener noreferrer")
        page.get_by_role("button", name="Load more ClinVar records").click()
        page.wait_for_function(
            "document.querySelectorAll('#clinvar-results .clinvar-record').length === 2"
        )
        check("ClinVar pagination requests the next source page without duplicating records",
              len(clinvar_requests) == 2 and clinvar_requests[1].get("retstart") == 1
              and page.locator("#clinvar-results .clinvar-record").count() == 2)
        with page.expect_download() as clinvar_download_info:
            page.get_by_role("button", name="Export ClinVar JSON").click()
        clinvar_download = clinvar_download_info.value
        clinvar_export = json.loads(Path(clinvar_download.path()).read_text(encoding="utf-8"))
        check("ClinVar JSON export preserves query and source-level conflict metadata",
              clinvar_export["query"]["gene_symbol"] == "BRCA1"
              and len(clinvar_export["records"]) == 2
              and clinvar_export["records"][0]["classifications"]["germline"]["description"]
                  == "Conflicting classifications of pathogenicity")

        page.get_by_label("Gene symbol (optional)").fill("BRCA1")
        page.get_by_role("button", name="Search GWAS Catalog").click()
        page.get_by_text("2026-10-29", exact=False).wait_for()
        check("GWAS Catalog search preserves data release and reported association metadata",
              len(gwas_requests) == 1
              and gwas_requests[0].get("gene_symbol") == "BRCA1"
              and "GCST90838669" in page.locator("#gwas-results").inner_text()
              and "2 × 10^-24" in page.locator("#gwas-results").inner_text())
        gwas_link = page.locator("#gwas-results a").first
        check("GWAS Catalog source links are HTTPS and open safely",
              gwas_link.get_attribute("href", timeout=args.timeout).startswith("https://")
              and gwas_link.get_attribute("rel") == "noopener noreferrer")
        page.get_by_role("button", name="Load more GWAS associations").click()
        page.wait_for_function(
            "document.querySelectorAll('#gwas-results .gwas-record').length === 2"
        )
        check("GWAS Catalog pagination requests the next page without duplicating associations",
              len(gwas_requests) == 2 and gwas_requests[1].get("page") == 1
              and page.locator("#gwas-results .gwas-record").count() == 2)
        with page.expect_download() as gwas_download_info:
            page.get_by_role("button", name="Export GWAS JSON").click()
        gwas_download = gwas_download_info.value
        gwas_export = json.loads(Path(gwas_download.path()).read_text(encoding="utf-8"))
        check("GWAS JSON export preserves release metadata and source records",
              gwas_export["source_response"]["provenance"]["data_release_date"] == "2026-10-29"
              and len(gwas_export["records"]) == 2
              and gwas_export["records"][0]["study_accession"] == "GCST90838669")

        page.get_by_label("Trait / phenotype (optional)").fill("breast cancer")
        page.get_by_label("Include more specific child ontology traits").check()
        page.get_by_role("button", name="Search GWAS Catalog").click()
        page.get_by_text("2026-10-29", exact=False).wait_for()
        check("GWAS Catalog trait search explicitly includes child ontology terms",
              len(gwas_requests) == 3
              and gwas_requests[-1].get("trait") == "breast cancer"
              and gwas_requests[-1].get("show_child_traits") is True)

        screenshot_dir = Path(os.environ.get("UI_SCREENSHOT_DIR", "/tmp/genomeguard-ui-screenshots"))
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_dir / "research-desktop.png"), full_page=True)

        mobile = browser.new_page(viewport={"width": 375, "height": 812})
        mobile.set_default_timeout(args.timeout)
        mobile.route("https://www.ebi.ac.uk/europepmc/webservices/rest/search**", handle_provider)
        mobile.route("**/literature/pubmed/search", handle_pubmed)
        mobile.route("**/research/open-targets/target", handle_open_targets)
        mobile.route("**/research/clinvar/search", handle_clinvar)
        mobile.route("**/research/gwas/search", handle_gwas)
        mobile.goto(args.base.rstrip("/") + "/#/research", wait_until="domcontentloaded")
        mobile.get_by_role("heading", name="Research discovery").wait_for()
        no_horizontal_overflow = mobile.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth + 1"
        )
        check("research discovery has no horizontal overflow at 375px", no_horizontal_overflow)
        mobile.get_by_label("Research question or symptom description").fill(
            "BRCA1 ovarian cancer symptoms"
        )
        mobile.get_by_label("Research department", exact=True).select_option("oncology")
        mobile.get_by_role("button", name="Search publications").click()
        mobile.locator(".research-paper").first.wait_for()
        check("mobile research search renders live-provider-shaped results",
              mobile.locator(".research-paper").count() == PAGE_SIZE + 1)
        mobile.locator("#clinvar-gene-symbol").fill("BRCA1")
        mobile.get_by_label("ClinVar report property filter").select_option("pathogenic")
        mobile.get_by_role("button", name="Search ClinVar variants").click()
        mobile.get_by_text("Conflicting classifications of pathogenicity", exact=True).wait_for()
        check("mobile ClinVar evidence has no horizontal overflow at 375px",
              mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
        mobile.get_by_label("Gene symbol (optional)").fill("BRCA1")
        mobile.get_by_role("button", name="Search GWAS Catalog").click()
        mobile.get_by_text("2026-10-29", exact=False).wait_for()
        check("mobile GWAS evidence has no horizontal overflow at 375px",
              mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
        mobile.screenshot(path=str(screenshot_dir / "research-mobile-375.png"), full_page=True)
        browser.close()

    print("\n" + ("RESEARCH UI SMOKE PASSED" if not failures else f"RESEARCH UI SMOKE FAILED ({len(failures)} checks)"))
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
