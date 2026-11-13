"""GWAS Catalog REST API v2 adapter.

The GWAS Catalog exposes literature-curated top associations and metadata. This adapter
does not claim access to full genome-wide summary statistics or infer causality.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

API_BASE = "https://www.ebi.ac.uk/gwas/rest/api/v2"
API_ORIGIN = "www.ebi.ac.uk"
API_PREFIX = "/gwas/rest/api/v2/"
MAX_PAGE_SIZE = 50
MAX_PAGE = 10_000
MAX_RESPONSE_BYTES = 2_000_000
REQUEST_TIMEOUT_SECONDS = 15
MIN_REQUEST_INTERVAL_SECONDS = 1.0
METADATA_CACHE_SECONDS = 3600
GENE_SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.-]{0,19}$")
RS_ID_RE = re.compile(r"^rs[0-9]+$", re.IGNORECASE)

_request_lock = threading.Lock()
_next_request_at = 0.0
_metadata_lock = threading.Lock()
_metadata_cache: dict | None = None
_metadata_cached_at = 0.0


class GwasCatalogProviderError(RuntimeError):
    """The GWAS Catalog API was unavailable or returned an invalid response."""


def _wait_for_rate_slot() -> None:
    global _next_request_at
    with _request_lock:
        now = time.monotonic()
        delay = _next_request_at - now
        if delay > 0:
            time.sleep(delay)
        _next_request_at = time.monotonic() + MIN_REQUEST_INTERVAL_SECONDS


def _fetch_json(path: str, params: dict[str, str] | None = None) -> dict:
    if not isinstance(path, str) or not path.startswith("/"):
        raise GwasCatalogProviderError("GWAS Catalog request path was invalid")
    query = urllib.parse.urlencode(params or {})
    url = API_BASE + path + (("?" + query) if query else "")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "GenomeGuard/0.1 (https://github.com/kaustubhdua/GenomeGuard)",
        },
        method="GET",
    )
    _wait_for_rate_slot()
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise GwasCatalogProviderError(
                    f"GWAS Catalog returned HTTP {response.status}"
                )
            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type.lower():
                raise GwasCatalogProviderError("GWAS Catalog returned a non-JSON response")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise GwasCatalogProviderError("GWAS Catalog response exceeded the size limit")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise GwasCatalogProviderError(
                "GWAS Catalog rate limit reached. Please retry shortly."
            ) from exc
        raise GwasCatalogProviderError(
            f"GWAS Catalog returned HTTP {exc.code}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GwasCatalogProviderError(
            "GWAS Catalog is temporarily unavailable"
        ) from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GwasCatalogProviderError("GWAS Catalog returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise GwasCatalogProviderError("GWAS Catalog returned an unexpected response shape")
    return payload


def _get_metadata() -> dict:
    global _metadata_cache, _metadata_cached_at
    now = time.monotonic()
    with _metadata_lock:
        if _metadata_cache is not None and now - _metadata_cached_at < METADATA_CACHE_SECONDS:
            return _metadata_cache
        metadata = _fetch_json("/metadata")
        if metadata.get("version") != "2.0" or not metadata.get("data_release_date"):
            raise GwasCatalogProviderError(
                "GWAS Catalog metadata did not include a supported API version and data release"
            )
        license_info = metadata.get("license")
        if not isinstance(license_info, dict) or not license_info.get("name"):
            raise GwasCatalogProviderError("GWAS Catalog metadata omitted its license")
        _metadata_cache = metadata
        _metadata_cached_at = time.monotonic()
        return metadata


def validate_search_request(
    gene_symbol: str | None = None,
    rs_id: str | None = None,
    trait: str | None = None,
    show_child_traits: bool = False,
    page: int = 0,
    size: int = 20,
) -> None:
    if gene_symbol not in (None, "") and (
        not isinstance(gene_symbol, str)
        or not GENE_SYMBOL_RE.fullmatch(gene_symbol.strip())
    ):
        raise ValueError("gene_symbol must be a valid gene symbol")
    if rs_id not in (None, "") and (
        not isinstance(rs_id, str) or not RS_ID_RE.fullmatch(rs_id.strip())
    ):
        raise ValueError("rs_id must use the rs followed by digits format")
    if trait not in (None, "") and (
        not isinstance(trait, str)
        or len(trait.strip()) < 2
        or len(trait.strip()) > 100
        or any(ord(char) < 32 for char in trait)
    ):
        raise ValueError("trait must contain 2 to 100 printable characters")
    if not any(value not in (None, "") for value in (gene_symbol, rs_id, trait)):
        raise ValueError("provide at least one of gene_symbol, rs_id, or trait")
    if not isinstance(show_child_traits, bool):
        raise ValueError("show_child_traits must be a boolean")
    if show_child_traits and trait in (None, ""):
        raise ValueError("show_child_traits requires a trait search")
    if isinstance(page, bool) or not isinstance(page, int) or not 0 <= page <= MAX_PAGE:
        raise ValueError(f"page must be an integer between 0 and {MAX_PAGE}")
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_PAGE_SIZE:
        raise ValueError(f"size must be an integer between 1 and {MAX_PAGE_SIZE}")


def _optional_text(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _safe_api_link(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != API_ORIGIN
        or parsed.username
        or parsed.password
        or not parsed.path.startswith(API_PREFIX)
    ):
        return None
    return value


def _normalize_association(record: dict) -> dict:
    association_id = _optional_text(record.get("association_id"))
    if not association_id or not association_id.isdigit():
        raise GwasCatalogProviderError("GWAS Catalog returned an invalid association identifier")
    accession = _optional_text(record.get("accession_id"))
    pubmed_id = _optional_text(record.get("pubmed_id"))
    links = record.get("_links") if isinstance(record.get("_links"), dict) else {}
    self_link = links.get("self", {}).get("href") if isinstance(links.get("self"), dict) else None
    snp_link = links.get("snp", {}).get("href") if isinstance(links.get("snp"), dict) else None
    loci_link = links.get("loci", {}).get("href") if isinstance(links.get("loci"), dict) else None
    source_url = _safe_api_link(self_link) or (
        f"{API_BASE}/associations/{association_id}"
    )
    efo_traits = record.get("efo_traits")
    snp_alleles = record.get("snp_allele")
    return {
        "association_id": association_id,
        "study_accession": accession,
        "pubmed_id": pubmed_id,
        "first_author": _optional_text(record.get("first_author")),
        "reported_traits": [
            _optional_text(item) for item in record.get("reported_trait", [])
            if _optional_text(item)
        ] if isinstance(record.get("reported_trait"), list) else [],
        "efo_traits": [
            {
                "id": _optional_text(item.get("efo_id")),
                "label": _optional_text(item.get("efo_trait")),
            }
            for item in efo_traits if isinstance(item, dict)
        ] if isinstance(efo_traits, list) else [],
        "p_value": record.get("p_value") if isinstance(record.get("p_value"), (int, float)) else None,
        "pvalue_mantissa": record.get("pvalue_mantissa"),
        "pvalue_exponent": record.get("pvalue_exponent"),
        "pvalue_description": _optional_text(record.get("pvalue_description")),
        "beta": _optional_text(record.get("beta")),
        "beta_numeric": record.get("beta_num") if isinstance(record.get("beta_num"), (int, float)) else None,
        "beta_unit": _optional_text(record.get("beta_unit")),
        "beta_direction": _optional_text(record.get("beta_direction")),
        "odds_ratio": record.get("or_per_copy_num") if isinstance(record.get("or_per_copy_num"), (int, float)) else None,
        "odds_ratio_text": _optional_text(record.get("or_value")),
        "confidence_interval": {
            "text": _optional_text(record.get("range")),
            "lower": record.get("ci_lower") if isinstance(record.get("ci_lower"), (int, float)) else None,
            "upper": record.get("ci_upper") if isinstance(record.get("ci_upper"), (int, float)) else None,
        },
        "risk_frequency": _optional_text(record.get("risk_frequency")),
        "locations": [
            _optional_text(item) for item in record.get("locations", [])
            if _optional_text(item)
        ] if isinstance(record.get("locations"), list) else [],
        "mapped_genes": [
            _optional_text(item) for item in record.get("mapped_genes", [])
            if _optional_text(item)
        ] if isinstance(record.get("mapped_genes"), list) else [],
        "snp_alleles": [
            {
                "rs_id": _optional_text(item.get("rs_id")),
                "effect_allele": _optional_text(item.get("effect_allele")),
            }
            for item in snp_alleles if isinstance(item, dict)
        ] if isinstance(snp_alleles, list) else [],
        "snp_effect_alleles": [
            _optional_text(item) for item in record.get("snp_effect_allele", [])
            if _optional_text(item)
        ] if isinstance(record.get("snp_effect_allele"), list) else [],
        "multi_snp_haplotype": record.get("multi_snp_haplotype") if isinstance(record.get("multi_snp_haplotype"), bool) else None,
        "snp_interaction": record.get("snp_interaction") if isinstance(record.get("snp_interaction"), bool) else None,
        "last_mapping_date": _optional_text(record.get("last_mapping_date")),
        "last_update_date": _optional_text(record.get("last_update_date")),
        "source_url": source_url,
        "snp_url": _safe_api_link(snp_link),
        "loci_url": _safe_api_link(loci_link),
        "study_url": (
            f"https://www.ebi.ac.uk/gwas/studies/{accession}"
            if accession and re.fullmatch(r"GCST[0-9]+", accession) else None
        ),
        "pubmed_url": (
            f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/"
            if pubmed_id and pubmed_id.isdigit() else None
        ),
    }


def search_gwas_catalog(
    *,
    gene_symbol: str | None = None,
    rs_id: str | None = None,
    trait: str | None = None,
    show_child_traits: bool = False,
    page: int = 0,
    size: int = 20,
) -> dict:
    """Search GWAS Catalog v2 associations by gene, rsID, and/or EFO trait."""
    validate_search_request(gene_symbol, rs_id, trait, show_child_traits, page, size)
    metadata = _get_metadata()
    params = {
        "page": str(page),
        "size": str(size),
        "extended_geneset": "false",
    }
    if gene_symbol:
        params["mapped_gene"] = gene_symbol.strip().upper()
    if rs_id:
        params["rs_id"] = rs_id.strip().lower()
    if trait:
        params["efo_trait"] = trait.strip()
        params["show_child_trait"] = "true" if show_child_traits else "false"

    payload = _fetch_json("/associations", params)
    embedded = payload.get("_embedded")
    records = embedded.get("associations") if isinstance(embedded, dict) else []
    page_info = payload.get("page")
    if not isinstance(records, list) or not isinstance(page_info, dict):
        raise GwasCatalogProviderError("GWAS Catalog response omitted associations or pagination metadata")
    try:
        total_elements = int(page_info.get("totalElements", 0))
        total_pages = int(page_info.get("totalPages", 0))
        page_number = int(page_info.get("number", page))
        page_size = int(page_info.get("size", size))
    except (TypeError, ValueError) as exc:
        raise GwasCatalogProviderError("GWAS Catalog returned invalid pagination metadata") from exc
    if (
        total_elements < 0 or total_pages < 0 or page_number != page
        or page_size != size or len(records) > size
    ):
        raise GwasCatalogProviderError("GWAS Catalog returned inconsistent pagination metadata")
    if total_elements > 0 and not records:
        raise GwasCatalogProviderError("GWAS Catalog returned an empty non-terminal page")
    normalized = [
        _normalize_association(record) for record in records if isinstance(record, dict)
    ]
    if len(normalized) != len(records):
        raise GwasCatalogProviderError("GWAS Catalog returned a malformed association record")
    links = payload.get("_links") if isinstance(payload.get("_links"), dict) else {}
    next_link = links.get("next", {}).get("href") if isinstance(links.get("next"), dict) else None
    has_more = page_number + 1 < total_pages
    safe_next = _safe_api_link(next_link)
    if has_more and not safe_next:
        raise GwasCatalogProviderError("GWAS Catalog omitted a safe next-page link")
    retrieved_at = datetime.now(UTC).isoformat()
    return {
        "provider": "GWAS Catalog",
        "api_version": metadata.get("version"),
        "query": {
            "gene_symbol": gene_symbol.strip().upper() if gene_symbol else None,
            "rs_id": rs_id.strip().lower() if rs_id else None,
            "trait": trait.strip() if trait else None,
            "show_child_traits": show_child_traits,
            "extended_geneset": False,
            "page": page,
            "size": size,
        },
        "count": total_elements,
        "returned": len(normalized),
        "has_more": has_more,
        "next_page_url": safe_next,
        "page": {
            "number": page_number,
            "size": page_size,
            "total_elements": total_elements,
            "total_pages": total_pages,
        },
        "records": normalized,
        "retrieved_at": retrieved_at,
        "provenance": {
            "provider": "GWAS Catalog",
            "api": "REST API v2",
            "api_version": metadata.get("version"),
            "data_release_date": _optional_text(metadata.get("data_release_date")),
            "api_release_date": _optional_text(metadata.get("api_release_date")),
            "dbsnp_build": _optional_text(metadata.get("dbsnp_build")),
            "gene_build": _optional_text(metadata.get("gene_build")),
            "efo_version": _optional_text(metadata.get("efo_version")),
            "ensembl_version": _optional_text(metadata.get("ensembl_version")),
            "commit_hash": _optional_text(metadata.get("commit_hash")),
            "license": _optional_text(metadata.get("license", {}).get("name")),
            "license_url": _optional_text(metadata.get("license", {}).get("url")),
            "terms_of_service": _optional_text(metadata.get("terms_of_service")),
            "source_url": f"{API_BASE}/associations",
            "query_parameters": params,
            "retrieved_at": retrieved_at,
            "scope_note": (
                "The GWAS Catalog API provides literature-curated top associations and metadata; "
                "it does not provide full genome-wide summary statistics."
            ),
        },
    }
