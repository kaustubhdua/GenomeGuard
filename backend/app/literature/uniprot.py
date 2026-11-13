"""UniProtKB protein search for exact human gene symbols.

Returns reviewed UniProtKB protein annotations and provenance. It never returns
protein sequences and does not infer clinical significance.
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

BASE_URL = "https://rest.uniprot.org/uniprotkb/search"
SOURCE_URL = "https://www.uniprot.org"
TAXONOMY_ID = 9606
GENE_SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.-]{0,19}$")
ACCESSION_RE = re.compile(r"^[A-Z0-9]{6,10}$")
MAX_RESPONSE_BYTES = 2_000_000
TIMEOUT_SECONDS = 20
MIN_INTERVAL_SECONDS = 0.2
MAX_RESULTS = 10
FIELDS = ",".join((
    "accession", "id", "gene_names", "protein_name", "organism_name",
    "length", "cc_function", "xref_ensembl",
))

_rate_lock = threading.Lock()
_last_request_started = 0.0


class UniProtProviderError(RuntimeError):
    """UniProtKB was unavailable or returned an invalid response."""


def validate_gene_request(symbol: str, size: int = 5) -> None:
    if not isinstance(symbol, str) or not GENE_SYMBOL_RE.fullmatch(symbol.strip()):
        raise ValueError("gene symbol must contain 1 to 20 letters, digits, dots or hyphens")
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_RESULTS:
        raise ValueError(f"size must be an integer between 1 and {MAX_RESULTS}")


def _wait_for_rate_slot() -> None:
    global _last_request_started
    with _rate_lock:
        delay = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_started)
        if delay > 0:
            time.sleep(delay)
        _last_request_started = time.monotonic()


def _text(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _protein_name(record: dict) -> str | None:
    description = record.get("proteinDescription")
    if not isinstance(description, dict):
        return None
    for key in ("recommendedName", "submissionNames"):
        candidates = description.get(key)
        if isinstance(candidates, dict):
            candidates = [candidates]
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            full = candidate.get("fullName")
            if isinstance(full, dict) and _text(full.get("value")):
                return _text(full["value"])
    return None


def _gene_names(record: dict) -> list[str]:
    names = []
    genes = record.get("genes")
    if not isinstance(genes, list):
        return names
    for gene in genes:
        if not isinstance(gene, dict):
            continue
        primary = gene.get("geneName")
        if isinstance(primary, dict) and _text(primary.get("value")):
            names.append(primary["value"].strip())
        synonyms = gene.get("synonyms")
        if isinstance(synonyms, list):
            names.extend(
                item["value"].strip() for item in synonyms
                if isinstance(item, dict) and _text(item.get("value"))
            )
    return list(dict.fromkeys(names))


def _function(record: dict) -> str | None:
    comments = record.get("comments")
    if not isinstance(comments, list):
        return None
    for comment in comments:
        if not isinstance(comment, dict) or comment.get("commentType") != "FUNCTION":
            continue
        texts = comment.get("texts")
        if isinstance(texts, list):
            values = [_text(item.get("value")) for item in texts if isinstance(item, dict)]
            values = [value for value in values if value]
            if values:
                return " ".join(values)[:1200]
    return None


def _ensembl_xrefs(record: dict) -> list[dict]:
    crossrefs = record.get("uniProtKBCrossReferences")
    if not isinstance(crossrefs, list):
        return []
    output = []
    for item in crossrefs:
        if not isinstance(item, dict) or item.get("database") != "Ensembl":
            continue
        properties = item.get("properties")
        properties = properties if isinstance(properties, list) else []
        values = {
            prop.get("key"): prop.get("value")
            for prop in properties if isinstance(prop, dict)
        }
        gene_id = _text(values.get("GeneId"))
        protein_id = _text(values.get("ProteinId")) or _text(item.get("id"))
        if gene_id and re.fullmatch(r"ENSG[0-9]{11}", gene_id):
            output.append({"gene_id": gene_id, "protein_id": protein_id})
    return output


def search_proteins(symbol: str, *, size: int = 5) -> dict:
    """Search reviewed human UniProtKB records for an exact gene symbol."""
    validate_gene_request(symbol, size)
    clean_symbol = symbol.strip()
    query = f"gene_exact:{clean_symbol} AND organism_id:{TAXONOMY_ID} AND reviewed:true"
    params = urlencode({
        "query": query,
        "fields": FIELDS,
        "format": "json",
        "size": size,
    })
    url = f"{BASE_URL}?{params}"
    request = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "GenomeGuard/0.1 (UniProtKB protein annotation lookup)",
    }, method="GET")
    _wait_for_rate_slot()
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise UniProtProviderError(f"UniProtKB returned HTTP {response.status}")
            if "json" not in response.headers.get("Content-Type", "").lower():
                raise UniProtProviderError("UniProtKB returned a non-JSON response")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise UniProtProviderError("UniProtKB response exceeded the 2 MB limit")
            release = _text(response.headers.get("X-UniProt-Release"))
            total = response.headers.get("X-Total-Results")
    except HTTPError as exc:
        raise UniProtProviderError(f"UniProtKB returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise UniProtProviderError("UniProtKB is temporarily unavailable") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UniProtProviderError("UniProtKB returned invalid JSON") from exc
    records = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise UniProtProviderError("UniProtKB response did not contain a results array")

    proteins = []
    for record in records:
        if not isinstance(record, dict):
            continue
        accession = _text(record.get("primaryAccession"))
        if not accession or not ACCESSION_RE.fullmatch(accession):
            continue
        organism = record.get("organism")
        organism_name = _text(organism.get("scientificName")) if isinstance(organism, dict) else None
        sequence = record.get("sequence")
        length = sequence.get("length") if isinstance(sequence, dict) else None
        proteins.append({
            "accession": accession,
            "entry_name": _text(record.get("uniProtkbId")),
            "protein_name": _protein_name(record),
            "gene_names": _gene_names(record),
            "organism": organism_name,
            "length_aa": length if isinstance(length, int) and not isinstance(length, bool) else None,
            "reviewed": str(record.get("entryType", "")).lower().startswith("uniprotkb reviewed"),
            "function": _function(record),
            "ensembl_cross_references": _ensembl_xrefs(record),
            "source_url": f"{SOURCE_URL}/uniprotkb/{accession}",
        })
    try:
        total_results = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_results = None
    return {
        "provider": "UniProtKB",
        "provider_url": SOURCE_URL,
        "query": {"gene_symbol": clean_symbol, "organism_taxonomy_id": TAXONOMY_ID, "reviewed_only": True},
        "release": release,
        "total_results": total_results,
        "returned": len(proteins),
        "proteins": proteins,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "interpretation": (
            "Reviewed protein annotations from UniProtKB. These records describe protein identity and "
            "function; they do not establish variant pathogenicity, disease causality, diagnosis, or treatment."
        ),
    }
