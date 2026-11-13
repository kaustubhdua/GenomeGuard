"""Open Targets Platform GraphQL adapter.

This provider returns source-attributed target/disease associations and, when a stable
EFO identifier is supplied, evidence records. It does not interpret scores as probabilities
or clinical validity. Queries are made server-side using fixed GraphQL documents.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"
TIMEOUT_SECONDS = 20
MAX_RESPONSE_BYTES = 2_000_000
MAX_ATTEMPTS = 3
MAX_PAGE_SIZE = 50
MAX_EVIDENCE_SIZE = 50
MAX_PAGE_INDEX = 100
MAX_EVIDENCE_CURSOR_LENGTH = 2048
MIN_INTERVAL_SECONDS = 0.5
_rate_lock = threading.Lock()
_last_request_started = 0.0
TARGET_ID_RE = re.compile(r"^ENSG[0-9]{11}$")
DISEASE_ID_RE = re.compile(r"^EFO_[0-9]{7,}$")

_QUERY = """
query GenomeGuardTargetEvidence(
  $ensemblId: String!,
  $pageIndex: Int!,
  $pageSize: Int!,
  $diseaseId: String!,
  $includeEvidence: Boolean!,
  $evidenceSize: Int!,
  $evidenceCursor: String
) {
  meta {
    product
    apiVersion { x y z suffix }
    dataVersion { year month iteration }
  }
  target(ensemblId: $ensemblId) {
    id
    approvedSymbol
    biotype
    associatedDiseases(
      page: { index: $pageIndex, size: $pageSize },
      enableIndirect: false
    ) {
      count
      rows {
        score
        disease { id name }
        datasourceScores { id score }
        datatypeScores { id score }
      }
    }
    evidences(efoIds: [$diseaseId], size: $evidenceSize, cursor: $evidenceCursor)
      @include(if: $includeEvidence) {
      count
      cursor
      rows {
        id
        datasourceId
        datatypeId
        score
        releaseVersion
        releaseDate
        publicationDate
        publicationFirstAuthor
        literature
        urls { url niceName }
        studyId
        studySampleSize
        cohortDescription
        qualityControls
        warningMessage
      }
    }
  }
}
"""


class OpenTargetsProviderError(RuntimeError):
    """Open Targets was unavailable or returned an invalid GraphQL response."""


def _validate(ensembl_id: str, disease_id: str | None, page_index: int, page_size: int, evidence_size: int) -> None:
    if not isinstance(ensembl_id, str) or not TARGET_ID_RE.fullmatch(ensembl_id):
        raise ValueError("ensembl_id must be an Ensembl gene identifier (ENSG followed by 11 digits)")
    if disease_id is not None and (
        not isinstance(disease_id, str) or not DISEASE_ID_RE.fullmatch(disease_id)
    ):
        raise ValueError("disease_id must be a stable ontology identifier")
    if isinstance(page_index, bool) or not isinstance(page_index, int) or not 0 <= page_index <= MAX_PAGE_INDEX:
        raise ValueError(f"page_index must be between 0 and {MAX_PAGE_INDEX}")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    if isinstance(evidence_size, bool) or not isinstance(evidence_size, int) or not 1 <= evidence_size <= MAX_EVIDENCE_SIZE:
        raise ValueError(f"evidence_size must be between 1 and {MAX_EVIDENCE_SIZE}")

def validate_target_request(
    ensembl_id: str,
    disease_id: str | None = None,
    page_index: int = 0,
    page_size: int = 20,
    evidence_size: int = 25,
    evidence_cursor: str | None = None,
) -> None:
    _validate(ensembl_id, disease_id, page_index, page_size, evidence_size)
    if evidence_cursor is not None and (
        not isinstance(evidence_cursor, str) or len(evidence_cursor) > MAX_EVIDENCE_CURSOR_LENGTH
    ):
        raise ValueError(f"evidence_cursor must be a string of at most {MAX_EVIDENCE_CURSOR_LENGTH} characters")


def _wait_for_rate_slot() -> None:
    """Conservatively pace public API requests within this application process."""
    global _last_request_started
    with _rate_lock:
        delay = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_started)
        if delay > 0:
            time.sleep(delay)
        _last_request_started = time.monotonic()


def _fetch_graphql(variables: dict) -> dict:
    body = json.dumps({"query": _QUERY, "variables": variables}).encode("utf-8")
    request = Request(
        ENDPOINT,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "GenomeGuard/0.1 (Open Targets evidence discovery)",
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        _wait_for_rate_slot()
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                if response.status != 200:
                    raise OpenTargetsProviderError(f"Open Targets returned HTTP {response.status}")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise OpenTargetsProviderError("Open Targets response exceeded the 2 MB limit")
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise OpenTargetsProviderError("Open Targets returned a non-object JSON response")
                if payload.get("errors"):
                    # GraphQL may return partial data alongside errors. Do not silently
                    # present a partial scientific evidence set as complete.
                    raise OpenTargetsProviderError("Open Targets returned GraphQL errors")
                data = payload.get("data")
                if not isinstance(data, dict):
                    raise OpenTargetsProviderError("Open Targets response was missing data")
                return data
        except HTTPError as exc:
            last_error = exc
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise OpenTargetsProviderError(f"Open Targets returned HTTP {exc.code}") from exc
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(min(4.0, 0.5 * (2 ** attempt)))
        except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(min(4.0, 0.5 * (2 ** attempt)))
        except OpenTargetsProviderError:
            raise
    raise OpenTargetsProviderError("Open Targets is temporarily unavailable; please retry.") from last_error


def search_target(
    ensembl_id: str,
    *,
    disease_id: str | None = None,
    page_index: int = 0,
    page_size: int = 20,
    evidence_size: int = 25,
    evidence_cursor: str | None = None,
) -> dict:
    """Fetch direct target-disease associations and optional disease-specific evidence."""
    validate_target_request(ensembl_id, disease_id, page_index, page_size, evidence_size, evidence_cursor)
    data = _fetch_graphql({
        "ensemblId": ensembl_id,
        "pageIndex": page_index,
        "pageSize": page_size,
        "diseaseId": disease_id or "",
        "includeEvidence": disease_id is not None,
        "evidenceSize": evidence_size,
        "evidenceCursor": evidence_cursor,
    })
    meta = data.get("meta")
    target = data.get("target")
    if not isinstance(meta, dict):
        raise OpenTargetsProviderError("Open Targets response was missing API/data release metadata")
    if target is None:
        raise LookupError("Open Targets did not find the supplied Ensembl gene identifier")
    if not isinstance(target, dict) or target.get("id") != ensembl_id:
        raise OpenTargetsProviderError("Open Targets returned an unexpected target entity")
    associations = target.get("associatedDiseases")
    if not isinstance(associations, dict) or not isinstance(associations.get("rows"), list):
        raise OpenTargetsProviderError("Open Targets response was missing target-disease associations")
    rows = associations["rows"]
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("disease"), dict)
        or not isinstance(row["disease"].get("id"), str)
        or not isinstance(row["disease"].get("name"), str)
        or not isinstance(row.get("score"), (int, float))
        for row in rows
    ):
        raise OpenTargetsProviderError("Open Targets returned malformed association records")

    evidence = target.get("evidences") if disease_id is not None else None
    if disease_id is not None and (
        not isinstance(evidence, dict) or not isinstance(evidence.get("rows"), list)
    ):
        raise OpenTargetsProviderError("Open Targets response was missing requested evidence records")
    evidence_rows = evidence["rows"] if evidence else []
    for item in evidence_rows:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise OpenTargetsProviderError("Open Targets returned malformed evidence records")

    return {
        "provider": "Open Targets Platform",
        "target": {
            "id": target["id"],
            "approved_symbol": target.get("approvedSymbol"),
            "biotype": target.get("biotype"),
        },
        "associations": {
            "count": int(associations.get("count", 0)),
            "page_index": page_index,
            "page_size": page_size,
            "direct_only": True,
            "rows": rows,
        },
        "evidence": {
            "disease_id": disease_id,
            "count": int(evidence.get("count", 0)) if evidence else 0,
            "cursor": evidence.get("cursor") if evidence else None,
            "rows": evidence_rows,
        },
        "provenance": {
            "provider": "Open Targets Platform",
            "api_version": meta.get("apiVersion"),
            "data_version": meta.get("dataVersion"),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "endpoint": ENDPOINT,
            "association_mode": "direct-only (enableIndirect=false)",
        },
        "interpretation": {
            "association_score": "Open Targets heuristic prioritisation score in [0,1]; not a probability or clinical validity assessment",
            "evidence_score": "Source/platform evidence score; not an independent GenomeGuard confidence estimate",
            "limitations": [
                "Association scores depend on Open Targets data release and configured aggregation.",
                "Direct-only associations are returned; indirect ontology-propagated evidence is excluded.",
                "Evidence records can include conflicting, indirect, predicted or source-specific findings.",
                "Review original evidence sources and publications before drawing scientific conclusions.",
            ],
        },
    }
