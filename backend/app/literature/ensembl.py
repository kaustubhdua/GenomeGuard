"""Ensembl REST gene lookup for source-backed gene identity resolution.

The adapter resolves a human gene symbol to its stable Ensembl gene identifier and
assembly-aware coordinates. It does not infer pathogenicity, phenotype association,
or clinical significance.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE_URL = "https://rest.ensembl.org"
SOURCE_URL = "https://www.ensembl.org"
SPECIES = "homo_sapiens"
GENE_SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.-]{0,19}$")
ENSEMBL_GENE_RE = re.compile(r"^ENSG[0-9]{11}$")
MAX_RESPONSE_BYTES = 1_000_000
TIMEOUT_SECONDS = 12
MIN_INTERVAL_SECONDS = 0.2
MAX_TRANSCRIPTS = 20

_rate_lock = threading.Lock()
_last_request_started = 0.0


class EnsemblProviderError(RuntimeError):
    """Ensembl was unavailable or returned an invalid response."""


class EnsemblEntityNotFound(EnsemblProviderError):
    """The requested gene symbol does not resolve in the selected species."""


def validate_gene_request(symbol: str, species: str = SPECIES) -> None:
    if not isinstance(symbol, str) or not GENE_SYMBOL_RE.fullmatch(symbol.strip()):
        raise ValueError("symbol must be a valid gene symbol containing 1 to 20 characters")
    if species != SPECIES:
        raise ValueError("only homo_sapiens gene lookup is currently supported")


def _wait_for_rate_slot() -> None:
    global _last_request_started
    with _rate_lock:
        delay = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_started)
        if delay > 0:
            time.sleep(delay)
        _last_request_started = time.monotonic()


def _fetch_json(url: str) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "GenomeGuard/0.1 (Ensembl gene identity lookup)",
        },
        method="GET",
    )
    _wait_for_rate_slot()
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise EnsemblProviderError(f"Ensembl returned HTTP {response.status}")
            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type.lower():
                raise EnsemblProviderError("Ensembl returned a non-JSON response")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise EnsemblProviderError("Ensembl response exceeded the 1 MB limit")
    except HTTPError as exc:
        if exc.code == 404:
            raise EnsemblEntityNotFound("Ensembl did not find the requested gene") from exc
        raise EnsemblProviderError(f"Ensembl returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise EnsemblProviderError("Ensembl is temporarily unavailable") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EnsemblProviderError("Ensembl returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise EnsemblProviderError("Ensembl returned a non-object JSON response")
    return payload


def lookup_gene(symbol: str, *, species: str = SPECIES) -> dict:
    """Resolve one exact gene symbol and preserve Ensembl's source identifiers."""
    validate_gene_request(symbol, species)
    clean_symbol = symbol.strip()
    url = (
        f"{BASE_URL}/lookup/symbol/{quote(species, safe='')}/"
        f"{quote(clean_symbol, safe='')}?expand=1"
    )
    payload = _fetch_json(url)
    gene_id = payload.get("id")
    display_name = payload.get("display_name")
    returned_species = payload.get("species")
    if not isinstance(gene_id, str) or not ENSEMBL_GENE_RE.fullmatch(gene_id):
        raise EnsemblProviderError("Ensembl returned a record without a valid stable gene identifier")
    if not isinstance(display_name, str) or not display_name.strip():
        raise EnsemblProviderError("Ensembl returned a gene without an approved display symbol")
    if returned_species != species or payload.get("object_type") != "Gene":
        raise EnsemblProviderError("Ensembl returned an unexpected entity or species")

    transcripts_raw = payload.get("Transcript")
    if transcripts_raw is None:
        transcripts_raw = payload.get("transcripts")
    transcripts_raw = transcripts_raw if isinstance(transcripts_raw, list) else []
    transcripts = []
    for item in transcripts_raw:
        if not isinstance(item, dict):
            continue
        transcript_id = item.get("id")
        if not isinstance(transcript_id, str) or not re.fullmatch(r"ENST[0-9]{11}", transcript_id):
            continue
        transcripts.append({
            "id": transcript_id,
            "version": item.get("version") if isinstance(item.get("version"), int) else None,
            "biotype": item.get("biotype") if isinstance(item.get("biotype"), str) else None,
            "is_canonical": item.get("is_canonical") == 1 or item.get("is_canonical") is True,
        })
    transcripts.sort(key=lambda row: (not row["is_canonical"], row["id"]))
    start, end = payload.get("start"), payload.get("end")
    if (isinstance(start, bool) or not isinstance(start, int) or start < 1
            or isinstance(end, bool) or not isinstance(end, int) or end < start):
        raise EnsemblProviderError("Ensembl returned invalid gene coordinates")
    strand = payload.get("strand")
    if strand not in (-1, 1):
        raise EnsemblProviderError("Ensembl returned an invalid gene strand")

    return {
        "provider": "Ensembl REST API",
        "provider_url": SOURCE_URL,
        "species": species,
        "query_symbol": clean_symbol,
        "gene": {
            "stable_id": gene_id,
            "symbol": display_name.strip(),
            "biotype": payload.get("biotype") if isinstance(payload.get("biotype"), str) else None,
            "gene_version": payload.get("version") if isinstance(payload.get("version"), int) else None,
            "assembly": payload.get("assembly_name") if isinstance(payload.get("assembly_name"), str) else None,
            "chromosome": str(payload.get("seq_region_name")) if payload.get("seq_region_name") is not None else None,
            "start": start,
            "end": end,
            "strand": strand,
            "canonical_transcript": payload.get("canonical_transcript")
                if isinstance(payload.get("canonical_transcript"), str) else None,
        },
        "transcript_count_returned": len(transcripts),
        "transcripts": transcripts[:MAX_TRANSCRIPTS],
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "interpretation": (
            "Source-backed gene identity and reference coordinates only; not a disease association, "
            "variant interpretation, pathogenicity assessment, or clinical recommendation."
        ),
    }
