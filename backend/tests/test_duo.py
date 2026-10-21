from app.data import duo

OWL = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:obo="http://purl.obolibrary.org/obo/">
  <owl:Class rdf:about="http://purl.obolibrary.org/obo/DUO_0000042">
    <rdfs:label>general research use</rdfs:label>
    <obo:IAO_0000115>Use allowed for any research purpose.</obo:IAO_0000115>
  </owl:Class>
  <owl:Class rdf:about="http://purl.obolibrary.org/obo/DUO_0000046">
    <rdfs:label>non-commercial use only</rdfs:label>
  </owl:Class>
  <owl:Class rdf:about="http://purl.obolibrary.org/obo/DUO_0000099">
    <rdfs:label>old commercial thing</rdfs:label>
    <owl:deprecated>true</owl:deprecated>
  </owl:Class>
  <owl:Class rdf:about="http://purl.obolibrary.org/obo/NOT_A_DUO_TERM"><rdfs:label>x</rdfs:label></owl:Class>
</rdf:RDF>"""


def test_parse_terms():
    t = duo.parse_terms(OWL)
    assert set(t) == {"DUO:0000042", "DUO:0000046", "DUO:0000099"}
    assert t["DUO:0000042"]["definition"].startswith("Use allowed")
    assert t["DUO:0000099"]["deprecated"] is True


def test_match_codes_skips_deprecated_and_reports_gaps():
    m = duo.match_codes(duo.parse_terms(OWL))
    assert [h["id"] for h in m["GRU"]] == ["DUO:0000042"]
    assert [h["id"] for h in m["NCU"]] == ["DUO:0000046"]  # the deprecated 'commercial' is skipped
    assert m["NAGR"] == []  # unmatched codes are surfaced, not invented
