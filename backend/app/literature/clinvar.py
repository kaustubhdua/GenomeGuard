"""ClinVar E-utilities adapter.

ClinVar is a public archive of submitter-provided variant classifications. Aggregate
classifications, review status, dates, and conflicts are preserved as source data;
they are never converted into patient-specific interpretations or clinical advice.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime

from app.literature import pubmed as _ncbi_eutils

MAX_GENE_SYMBOL_LENGTH = 20
MAX_PAGE_SIZE = 50
MAX_OFFSET = 10_000
GENE_SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.-]{0,19}$")

# These are ClinVar Properties terms, not GenomeGuard classifications.
CLASSIFICATION_PROPERTIES = {
    "pathogenic": "clinsig pathogenic",
    "likely_pathogenic": "clinsig likely pathogenic",
    "uncertain_significance": "clinsig vus",
    "likely_benign": "clinsig likely benign",
    "benign": "clinsig benign",
    "conflicting": "clinsig has conflicts",
}


class ClinVarProviderError(RuntimeError):
    """ClinVar was unavailable or returned an invalid provider response."""


def _fetch_json(endpoint: str, params: dict[str, str]) -> dict:
    """Use the shared NCBI E-utilities rate limiter and retry policy."""
    try:
        return _ncbi_eutils._fetch_json(endpoint, params)
    except _ncbi_eutils.PubMedProviderError as exc:
        raise ClinVarProviderError(
            "ClinVar is temporarily unavailable or returned an invalid response."
        ) from exc


def validate_search_request(
    gene_symbol: str,
    classification: str | None = None,
    retstart: int = 0,
    retmax: int = 20,
) -> None:
    if (
        not isinstance(gene_symbol, str)
        or not gene_symbol.strip()
        or len(gene_symbol.strip()) > MAX_GENE_SYMBOL_LENGTH
        or not GENE_SYMBOL_RE.fullmatch(gene_symbol.strip())
    ):
        raise ValueError(
            "gene_symbol must be a valid gene symbol containing 1 to "
            f"{MAX_GENE_SYMBOL_LENGTH} letters, digits, dots, or hyphens"
        )
    if classification not in (None, "") and (
        not isinstance(classification, str) or classification not in CLASSIFICATION_PROPERTIES
    ):
        raise ValueError(
            "classification must be one of: " + ", ".join(CLASSIFICATION_PROPERTIES)
        )
    if isinstance(retstart, bool) or not isinstance(retstart, int) or not 0 <= retstart <= MAX_OFFSET:
        raise ValueError(f"retstart must be an integer between 0 and {MAX_OFFSET}")
    if isinstance(retmax, bool) or not isinstance(retmax, int) or not 1 <= retmax <= MAX_PAGE_SIZE:
        raise ValueError(f"retmax must be an integer between 1 and {MAX_PAGE_SIZE}")


def _optional_text(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _normalize_traits(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    traits = []
    for item in value:
        if not isinstance(item, dict):
            continue
        xrefs = item.get("trait_xrefs")
        traits.append({
            "name": _optional_text(item.get("trait_name")),
            "xrefs": [
                {
                    "database": _optional_text(xref.get("db_source")),
                    "id": _optional_text(xref.get("db_id")),
                }
                for xref in xrefs
                if isinstance(xref, dict)
            ] if isinstance(xrefs, list) else [],
        })
    return traits


def _normalize_classification(value) -> dict:
    source = value if isinstance(value, dict) else {}
    return {
        "description": _optional_text(source.get("description")),
        "review_status": _optional_text(source.get("review_status")),
        "last_evaluated": _optional_text(source.get("last_evaluated")),
        "fda_recognized_database": _optional_text(source.get("fda_recognized_database")),
        "traits": _normalize_traits(source.get("trait_set")),
    }


def _normalize_record(uid: str, record: dict) -> dict:
    if not uid.isdigit() or str(record.get("uid") or uid) != uid:
        raise ClinVarProviderError("ClinVar returned an unexpected variation identifier")
    variation_sets = record.get("variation_set")
    normalized_variations = []
    if isinstance(variation_sets, list):
        for variation in variation_sets:
            if not isinstance(variation, dict):
                continue
            locations = variation.get("variation_loc")
            normalized_variations.append({
                "name": _optional_text(variation.get("variation_name")),
                "cdna_change": _optional_text(variation.get("cdna_change")),
                "type": _optional_text(variation.get("variant_type")),
                "canonical_spdi": _optional_text(variation.get("canonical_spdi")),
                "locations": [
                    {
                        "status": _optional_text(location.get("status")),
                        "assembly": _optional_text(location.get("assembly_name")),
                        "chromosome": _optional_text(location.get("chr")),
                        "start": _optional_text(location.get("start")),
                        "stop": _optional_text(location.get("stop")),
                        "assembly_accession": _optional_text(location.get("assembly_acc_ver")),
                    }
                    for location in locations
                    if isinstance(location, dict)
                ] if isinstance(locations, list) else [],
            })

    genes = record.get("genes")
    normalized_genes = [
        {
            "symbol": _optional_text(gene.get("symbol")),
            "gene_id": _optional_text(str(gene.get("geneid"))) if gene.get("geneid") is not None else None,
            "relationship_source": _optional_text(gene.get("source")),
        }
        for gene in genes
        if isinstance(gene, dict)
    ] if isinstance(genes, list) else []

    supporting = record.get("supporting_submissions")
    supporting = supporting if isinstance(supporting, dict) else {}
    scv = supporting.get("scv") if isinstance(supporting.get("scv"), list) else []
    rcv = supporting.get("rcv") if isinstance(supporting.get("rcv"), list) else []

    accession = _optional_text(record.get("accession"))
    return {
        "uid": uid,
        "accession": accession,
        "accession_version": _optional_text(record.get("accession_version")),
        "title": _optional_text(record.get("title")),
        "variation_type": _optional_text(record.get("obj_type")),
        "record_status": _optional_text(record.get("record_status")),
        "genes": normalized_genes,
        "variations": normalized_variations,
        "molecular_consequences": [
            _optional_text(item) for item in record.get("molecular_consequence_list", [])
            if _optional_text(item)
        ] if isinstance(record.get("molecular_consequence_list"), list) else [],
        "protein_change": _optional_text(record.get("protein_change")),
        "classifications": {
            "germline": _normalize_classification(record.get("germline_classification")),
            "somatic_clinical_impact": _normalize_classification(
                record.get("clinical_impact_classification")
            ),
            "somatic_oncogenicity": _normalize_classification(
                record.get("oncogenicity_classification")
            ),
        },
        "supporting_submissions": {
            "scv_accessions": [str(item) for item in scv if isinstance(item, str)],
            "rcv_accessions": [str(item) for item in rcv if isinstance(item, str)],
            "scv_count": len(scv),
            "rcv_count": len(rcv),
        },
        "source_url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{uid}/",
    }


def search_clinvar(
    gene_symbol: str,
    *,
    classification: str | None = None,
    retstart: int = 0,
    retmax: int = 20,
) -> dict:
    """Search ClinVar by gene and optional ClinVar Properties filter."""
    validate_search_request(gene_symbol, classification, retstart, retmax)
    gene = gene_symbol.strip().upper()
    property_term = CLASSIFICATION_PROPERTIES.get(classification or "")
    query = f"{gene}[gene]"
    if property_term:
        query += f' AND "{property_term}"[Properties]'

    search = _fetch_json("esearch", {
        "db": "clinvar",
        "term": query,
        "retmode": "json",
        "retstart": str(retstart),
        "retmax": str(retmax),
        "sort": "relevance",
    })
    result = search.get("esearchresult")
    if not isinstance(result, dict):
        raise ClinVarProviderError("ClinVar ESearch response was missing esearchresult")
    try:
        count = int(result.get("count", "0"))
        ids = result.get("idlist", [])
    except (TypeError, ValueError) as exc:
        raise ClinVarProviderError("ClinVar ESearch returned invalid pagination metadata") from exc
    if count < 0 or not isinstance(ids, list) or any(
        not isinstance(uid, str) or not uid.isdigit() for uid in ids
    ):
        raise ClinVarProviderError("ClinVar ESearch returned invalid variation identifiers")
    if len(ids) > retmax:
        raise ClinVarProviderError("ClinVar ESearch returned more records than requested")

    records = []
    if ids:
        summary = _fetch_json("esummary", {
            "db": "clinvar",
            "id": ",".join(ids),
            "retmode": "json",
            "version": "2.0",
        })
        docs = summary.get("result")
        if not isinstance(docs, dict) or not isinstance(docs.get("uids"), list):
            raise ClinVarProviderError("ClinVar ESummary response was missing result.uids")
        returned_uids = docs["uids"]
        if (
            any(not isinstance(uid, str) or not uid.isdigit() for uid in returned_uids)
            or len(returned_uids) != len(ids)
            or set(returned_uids) != set(ids)
        ):
            raise ClinVarProviderError("ClinVar ESummary returned an unexpected identifier set")
        for uid in ids:
            record = docs.get(uid)
            if not isinstance(record, dict):
                raise ClinVarProviderError("ClinVar ESummary omitted a requested variation")
            records.append(_normalize_record(uid, record))

    retrieved_at = datetime.now(UTC).isoformat()
    return {
        "provider": "NCBI ClinVar",
        "query": {
            "gene_symbol": gene,
            "classification_filter": classification or None,
            "classification_filter_semantics": (
                "ClinVar Properties search for at least one report matching the selected term; "
                "the aggregate classification shown on each record is returned separately."
                if property_term else "No ClinVar Properties filter was applied."
            ),
            "retstart": retstart,
            "retmax": retmax,
        },
        "count": count,
        "returned": len(records),
        "has_more": retstart + len(ids) < min(count, MAX_OFFSET),
        "records": records,
        "retrieved_at": retrieved_at,
        "provenance": {
            "provider": "NCBI ClinVar",
            "api": "E-utilities ESearch + ESummary v2.0",
            "source_url": "https://www.ncbi.nlm.nih.gov/clinvar/",
            "query": query,
            "retrieved_at": retrieved_at,
            "classification_note": (
                "VCV aggregate classifications and review status are displayed as supplied by "
                "ClinVar. They are not patient-specific interpretations or clinical advice."
            ),
        },
    }
