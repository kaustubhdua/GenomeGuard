"""Fetch the official GA4GH Data Use Ontology (duo.owl, CC BY 4.0) and compare it with the
meanings GenomeGuard's consent engine implements.

    python -m app.data.duo                 # downloads https://purl.obolibrary.org/obo/duo.owl
    python -m app.data.duo --owl duo.owl   # use a local copy

Writes docs/duo-terms.json and prints, for each code we use, the OFFICIAL id and label next to
OUR meaning. If they disagree (NAGR and NCTRL are the likeliest), fix the engine or keep calling it
"DUO-inspired": never claim DUO compatibility for a rule that means something else.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from app.core.consent import DUO_REFERENCE

PURL = "https://purl.obolibrary.org/obo/duo.owl"
NS = {"rdfs": "http://www.w3.org/2000/01/rdf-schema#",
      "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
      "owl": "http://www.w3.org/2002/07/owl#",
      "oboInOwl": "http://www.geneontology.org/formats/oboInOwl#"}
RDF_ABOUT = "{%s}about" % NS["rdf"]

# Words we expect in the official label for each code (a hint for matching, not a claim).
LABEL_HINTS = {
    "GRU": ["general research use"], "HMB": ["health", "medical", "biomedical"],
    "DS": ["disease specific"], "NPU": ["not for profit"], "NCU": ["commercial"],
    "NMDS": ["methods"], "NAGR": ["aggregate"], "NCTRL": ["control"],
}


def parse_terms(owl_xml: str) -> dict[str, dict]:
    """Return {DUO:0000046: {"label": ..., "definition": ..., "deprecated": bool}}."""
    root = ET.fromstring(owl_xml)
    out = {}
    for cls in root.iter("{%s}Class" % NS["owl"]):
        about = cls.get(RDF_ABOUT, "")
        m = re.search(r"DUO_(\d{7})$", about)
        label = cls.find("rdfs:label", NS)
        if not m or label is None:
            continue
        defn = cls.find("{http://purl.obolibrary.org/obo/}IAO_0000115")
        dep = cls.find("owl:deprecated", NS)
        out["DUO:" + m.group(1)] = {
            "label": (label.text or "").strip(),
            "definition": (defn.text or "").strip() if defn is not None else "",
            "deprecated": dep is not None and (dep.text or "").strip().lower() == "true"}
    return out


def match_codes(terms: dict[str, dict]) -> dict[str, list[dict]]:
    """For each of our codes, official terms whose label contains every hint word."""
    res = {}
    for code, hints in LABEL_HINTS.items():
        hits = [{"id": i, **t} for i, t in terms.items()
                if all(h in t["label"].lower() for h in hints) and not t["deprecated"]]
        res[code] = hits
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--owl")
    ap.add_argument("--out", default="docs/duo-terms.json")
    a = ap.parse_args()
    if a.owl:
        xml = Path(a.owl).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(PURL, timeout=120) as r:
            xml = r.read().decode("utf-8")
    terms = parse_terms(xml)
    matches = match_codes(terms)
    Path(a.out).write_text(json.dumps({"source": PURL, "license": "CC BY 4.0",
                                       "n_terms": len(terms), "matches": matches,
                                       "terms": terms}, indent=1))
    print(f"{len(terms)} DUO terms parsed -> {a.out}\n")
    for code, ours in DUO_REFERENCE.items():
        print(f"{code:6} ours: {ours['meaning']}  (id {ours['id'] or 'unset'})")
        for h in matches.get(code, [])[:3]:
            print(f"         official {h['id']}: {h['label']}")
        if not matches.get(code):
            print("         official: NO label match: check by hand")


if __name__ == "__main__":
    main()
