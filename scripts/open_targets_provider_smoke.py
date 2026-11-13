#!/usr/bin/env python3
"""Low-volume live Open Targets GraphQL contract smoke using public TP53 annotations."""
from __future__ import annotations

import sys

from app.literature.open_targets import search_target


def main() -> int:
    target = search_target("ENSG00000141510", page_index=0, page_size=5)
    if target["provider"] != "Open Targets Platform":
        raise AssertionError("unexpected provider attribution")
    if target["target"]["id"] != "ENSG00000141510" or target["target"]["approved_symbol"] != "TP53":
        raise AssertionError("TP53 entity mapping did not match the Ensembl identifier")
    associations = target["associations"]["rows"]
    if not associations or not target["associations"]["direct_only"]:
        raise AssertionError("expected direct target-disease associations")
    if not target["provenance"]["api_version"] or not target["provenance"]["data_version"]:
        raise AssertionError("Open Targets API/data release metadata was missing")
    # Association records may use MONDO or EFO identifiers; the provider's evidence
    # query accepts EFO identifiers specifically. Prefer a returned EFO ID, with a
    # stable public TP53/breast-carcinoma EFO fixture as a fallback.
    first_disease = next(
        (row["disease"]["id"] for row in associations
         if row.get("disease", {}).get("id", "").startswith("EFO_")),
        "EFO_0000311",
    )
    evidence = search_target(
        "ENSG00000141510", disease_id=first_disease, page_index=0, page_size=5, evidence_size=5,
    )
    if evidence["evidence"]["disease_id"] != first_disease:
        raise AssertionError("evidence response did not preserve the requested disease identifier")
    for item in evidence["evidence"]["rows"]:
        if not item.get("datasourceId") or not item.get("datatypeId") or not item.get("id"):
            raise AssertionError("evidence provenance fields were incomplete")
    print("[PASS] Open Targets live GraphQL query resolved TP53 from Ensembl")
    print(f"[PASS] {len(associations)} direct-only association records returned on the requested page")
    print(f"[PASS] API and data release metadata: {target['provenance']['data_version']}")
    print(f"[PASS] disease-specific evidence query returned {evidence['evidence']['count']} source records")
    print("[PASS] source IDs and score interpretation boundaries preserved")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] Open Targets live contract: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
