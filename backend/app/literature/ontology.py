"""Biomedical ontology discovery via the EMBL-EBI Ontology Lookup Service (OLS4).

Only MONDO, Human Phenotype Ontology (HP), and Disease Ontology (DOID) are
queried. Returned terms are source annotations, not clinical diagnoses or
automatically asserted mappings. OLS does not establish equivalence between
terms merely because their labels are similar.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://www.ebi.ac.uk/ols4/api/search"
SOURCE_URL = "https://www.ebi.ac.uk/ols4/"
ALLOWED_ONTOLOGIES = {"mondo", "hp", "doid"}
MAX_QUERY_LENGTH = 120
MAX_PAGE_SIZE = 20
MAX_OFFSET = 1000
MAX_RESPONSE_BYTES = 1_000_000
TIMEOUT_SECONDS = 12
MIN_INTERVAL_SECONDS = 0.25
QUERY_RE = re.compile(r"^[^\x00-\x1f\x7f]+$")

_rate_lock = threading.Lock()
_last_request_started = 0.0


def _wait_for_rate_slot() -> None:
    global _last_request_started
    with _rate_lock:
        delay = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_started)
        if delay > 0:
            time.sleep(delay)
        _last_request_started = time.monotonic()


class OntologyProviderError(RuntimeError):
    """OLS4 was unavailable or returned an invalid response."""


def validate_search(query: str, *, ontology: str = "all", page: int = 0, size: int = 10) -> None:
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= MAX_QUERY_LENGTH:
        raise ValueError(f"query must contain 2 to {MAX_QUERY_LENGTH} characters")
    if not QUERY_RE.fullmatch(query.strip()):
        raise ValueError("query contains unsupported control characters")
    if ontology != "all" and ontology not in ALLOWED_ONTOLOGIES:
        raise ValueError("ontology must be all, mondo, hp, or doid")
    if isinstance(page, bool) or not isinstance(page, int) or not 0 <= page <= MAX_OFFSET // MAX_PAGE_SIZE:
        raise ValueError(f"page must be between 0 and {MAX_OFFSET // MAX_PAGE_SIZE}")
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_PAGE_SIZE:
        raise ValueError(f"size must be between 1 and {MAX_PAGE_SIZE}")


def _fetch_json(params: dict[str, str]) -> dict:
    request = Request(
        ENDPOINT + "?" + urlencode(params),
        headers={"Accept": "application/json", "User-Agent": "GenomeGuard/0.1 (OLS4 ontology discovery)"},
        method="GET",
    )
    _wait_for_rate_slot()
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise OntologyProviderError(f"OLS4 returned HTTP {response.status}")
            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type.lower():
                raise OntologyProviderError("OLS4 returned a non-JSON response")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise OntologyProviderError("OLS4 response exceeded the 1 MB limit")
    except HTTPError as exc:
        raise OntologyProviderError(f"OLS4 returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise OntologyProviderError("OLS4 is temporarily unavailable") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OntologyProviderError("OLS4 returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise OntologyProviderError("OLS4 returned a non-object JSON response")
    return payload


def _first_text(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, str) and item.strip()), None)
    return None


def _normalize_doc(doc: dict) -> dict:
    raw_ontology = str(doc.get("ontology_prefix") or doc.get("ontology_name") or "").strip().lower()
    aliases = {
        "mondo": "mondo", "hp": "hp", "doid": "doid",
        "human phenotype ontology": "hp", "disease ontology": "doid",
        "mondo disease ontology": "mondo",
    }
    ontology = aliases.get(raw_ontology, raw_ontology)
    if ontology not in ALLOWED_ONTOLOGIES:
        raise OntologyProviderError("OLS4 returned a term outside the requested ontology set")
    iri = doc.get("iri")
    if not isinstance(iri, str) or not iri.startswith("https://") and not iri.startswith("http://"):
        raise OntologyProviderError("OLS4 returned a term without a valid IRI")
    label = doc.get("label")
    if not isinstance(label, str) or not label.strip():
        raise OntologyProviderError("OLS4 returned a term without a label")
    synonyms = doc.get("synonym") or doc.get("synonyms") or []
    if isinstance(synonyms, str):
        synonyms = [synonyms]
    if not isinstance(synonyms, list):
        synonyms = []
    return {
        "label": label.strip(),
        "iri": iri,
        "obo_id": _first_text(doc.get("obo_id")) or _first_text(doc.get("short_form")),
        "ontology": ontology,
        "ontology_prefix": str(doc.get("ontology_prefix") or ontology).upper(),
        "description": _first_text(doc.get("description")),
        "synonyms": [item.strip() for item in synonyms if isinstance(item, str) and item.strip()][:10],
        "is_obsolete": doc.get("is_obsolete") is True or str(doc.get("is_obsolete", "")).lower() == "true",
        "source_url": SOURCE_URL,
    }


def search_ontology(query: str, *, ontology: str = "all", page: int = 0, size: int = 10) -> dict:
    """Search OLS4 for source-backed MONDO, HP, and DOID terms."""
    validate_search(query, ontology=ontology, page=page, size=size)
    params = {
        "q": query.strip(),
        "ontology": ",".join(sorted(ALLOWED_ONTOLOGIES)) if ontology == "all" else ontology,
        "rows": str(size),
        "start": str(page * size),
        "obsoletes": "false",
        "queryFields": "label,synonym,description,short_form,obo_id",
    }
    payload = _fetch_json(params)
    response = payload.get("response")
    if not isinstance(response, dict) or not isinstance(response.get("docs"), list):
        raise OntologyProviderError("OLS4 response was missing response.docs")
    docs = response["docs"]
    if len(docs) > size or any(not isinstance(doc, dict) for doc in docs):
        raise OntologyProviderError("OLS4 returned malformed or excessive term records")
    terms = [_normalize_doc(doc) for doc in docs]
    try:
        total = max(0, int(response.get("numFound", 0)))
    except (TypeError, ValueError) as exc:
        raise OntologyProviderError("OLS4 returned invalid result-count metadata") from exc
    return {
        "provider": "EMBL-EBI Ontology Lookup Service",
        "provider_url": SOURCE_URL,
        "query": query.strip(),
        "ontology_filter": ontology,
        "page": page,
        "size": size,
        "total": total,
        "returned": len(terms),
        "has_more": (page + 1) * size < total,
        "terms": terms,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "interpretation": (
            "Ontology term search results are candidate annotations. Similar labels do not prove "
            "equivalence, clinical relevance, diagnosis, or a validated cross-ontology mapping."
        ),
    }
