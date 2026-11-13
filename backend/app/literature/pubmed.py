"""PubMed E-utilities adapter.

This adapter fetches public literature metadata only. It never stores search terms or
accepts participant identifiers as a special input type. Callers should send research
topics, not patient-identifying or private genomic information.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MAX_QUERY_LENGTH = 500
MAX_PAGE_SIZE = 50
MAX_OFFSET = 10_000
REQUEST_TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3
MIN_INTERVAL_SECONDS = 1 / 3  # NCBI's unauthenticated limit: at most 3 requests/second.

_rate_lock = threading.Lock()
_last_request_started = 0.0


class PubMedProviderError(RuntimeError):
    """The upstream PubMed provider failed or returned an invalid response."""


def _wait_for_rate_slot() -> None:
    global _last_request_started
    with _rate_lock:
        now = time.monotonic()
        delay = MIN_INTERVAL_SECONDS - (now - _last_request_started)
        if delay > 0:
            time.sleep(delay)
        _last_request_started = time.monotonic()


def _request_params(params: dict[str, str]) -> dict[str, str]:
    out = dict(params)
    out["tool"] = os.environ.get("GG_NCBI_TOOL", "GenomeGuard")
    email = os.environ.get("GG_NCBI_EMAIL", "").strip()
    if email:
        out["email"] = email
    api_key = os.environ.get("GG_NCBI_API_KEY", "").strip()
    if api_key:
        out["api_key"] = api_key
    return out


def _retry_delay(error: HTTPError, attempt: int) -> float:
    value = error.headers.get("Retry-After") if error.headers else None
    if value:
        try:
            return min(30.0, max(0.0, float(value)))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return min(30.0, max(0.0, (retry_at - datetime.now(UTC)).total_seconds()))
            except (TypeError, ValueError, OverflowError):
                pass
    return min(4.0, 0.5 * (2 ** attempt))


def _fetch_json(endpoint: str, params: dict[str, str]) -> dict:
    url = f"{BASE}/{endpoint}.fcgi?{urlencode(_request_params(params))}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "GenomeGuard/0.1 (PubMed literature discovery)",
        },
    )
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        _wait_for_rate_slot()
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                if response.status != 200:
                    raise PubMedProviderError(f"PubMed returned HTTP {response.status}")
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise PubMedProviderError("PubMed response exceeded the 2 MB limit")
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise PubMedProviderError("PubMed response was not a JSON object")
                if payload.get("error"):
                    raise PubMedProviderError("PubMed rejected the search request")
                return payload
        except HTTPError as exc:
            last_error = exc
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise PubMedProviderError(f"PubMed returned HTTP {exc.code}") from exc
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(_retry_delay(exc, attempt))
        except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(min(4.0, 0.5 * (2 ** attempt)))
        except PubMedProviderError:
            raise
    raise PubMedProviderError("PubMed is temporarily unavailable; please retry.") from last_error


def _normalize_article(uid: str, record: dict) -> dict:
    pmid = str(record.get("uid") or uid)
    article_ids = record.get("articleids") or []
    doi = next(
        (str(item.get("value")).strip() for item in article_ids
         if isinstance(item, dict) and item.get("idtype") == "doi" and item.get("value")),
        None,
    )
    pmcid = next(
        (str(item.get("value")).strip() for item in article_ids
         if isinstance(item, dict) and item.get("idtype") == "pmc" and item.get("value")),
        None,
    )
    authors = record.get("authors") or []
    author_names = [
        str(item.get("name")).strip()
        for item in authors
        if isinstance(item, dict) and item.get("name")
    ]
    title = record.get("title")
    if not isinstance(title, str) or not title.strip():
        raise PubMedProviderError("PubMed returned a record without a valid title")
    return {
        "source": "PubMed",
        "source_id": pmid,
        "pmid": pmid,
        "pmcid": pmcid,
        "doi": doi,
        "title": title.strip(),
        "authors": author_names,
        "journal": record.get("fulljournalname") or record.get("source"),
        "publication_date": record.get("pubdate"),
        "article_types": record.get("pubtype") or [],
        "abstract": None,
        "abstract_available": False,
        "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def search_pubmed(query: str, *, retstart: int = 0, retmax: int = 20) -> dict:
    """Search PubMed and fetch normalized summaries using ESearch + ESummary."""
    if not isinstance(query, str) or not query.strip() or len(query.strip()) > MAX_QUERY_LENGTH:
        raise ValueError(f"query must contain 1 to {MAX_QUERY_LENGTH} characters")
    if isinstance(retstart, bool) or not isinstance(retstart, int) or not 0 <= retstart <= MAX_OFFSET:
        raise ValueError(f"retstart must be between 0 and {MAX_OFFSET}")
    if isinstance(retmax, bool) or not isinstance(retmax, int) or not 1 <= retmax <= MAX_PAGE_SIZE:
        raise ValueError(f"retmax must be between 1 and {MAX_PAGE_SIZE}")

    search = _fetch_json("esearch", {
        "db": "pubmed",
        "term": query.strip(),
        "retmode": "json",
        "retstart": str(retstart),
        "retmax": str(retmax),
        "sort": "relevance",
    })
    result = search.get("esearchresult")
    if not isinstance(result, dict):
        raise PubMedProviderError("PubMed ESearch response was missing esearchresult")
    try:
        count = int(result.get("count", "0"))
        ids = result.get("idlist", [])
    except (TypeError, ValueError) as exc:
        raise PubMedProviderError("PubMed ESearch response contained invalid pagination metadata") from exc
    if count < 0 or not isinstance(ids, list) or any(not str(uid).isdigit() for uid in ids):
        raise PubMedProviderError("PubMed ESearch response contained invalid identifiers")
    if len(ids) > retmax:
        raise PubMedProviderError("PubMed ESearch returned more records than requested")

    papers: list[dict] = []
    if ids:
        summary = _fetch_json("esummary", {
            "db": "pubmed",
            "id": ",".join(str(uid) for uid in ids),
            "retmode": "json",
            "version": "2.0",
        })
        docs = summary.get("result")
        if not isinstance(docs, dict) or not isinstance(docs.get("uids"), list):
            raise PubMedProviderError("PubMed ESummary response was missing result.uids")
        for uid in ids:
            record = docs.get(str(uid))
            if not isinstance(record, dict):
                raise PubMedProviderError("PubMed ESummary omitted a requested record")
            papers.append(_normalize_article(str(uid), record))

    return {
        "provider": "PubMed",
        "query": query.strip(),
        "count": count,
        "retstart": retstart,
        "retmax": retmax,
        "returned": len(papers),
        "has_more": retstart + len(ids) < count,
        "papers": papers,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "provenance": {
            "provider": "NCBI PubMed",
            "api": "E-utilities ESearch + ESummary",
            "source_url": "https://pubmed.ncbi.nlm.nih.gov/",
            "abstracts_included": False,
        },
    }
