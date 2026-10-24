from tests.helpers import ANON, RESEARCHER, H, make_client


def _common_variant(svc):
    j = next(i for i in range(svc.ds.n_variants)
             if svc.ds.maf[i] >= 0.2 and i not in set(svc.ds.planted))
    chrom, pos, _ref, alt = svc.ds.coords[j]
    return {"referenceName": chrom, "start": pos, "alternateBases": alt}


def test_beacon_boolean_answer_goes_through_the_pipeline():
    svc, c = make_client()
    r = c.get("/beacon/g_variants", params=_common_variant(svc), headers=H(RESEARCHER))
    assert r.status_code == 200
    j = r.json()
    assert j["meta"]["apiVersion"] == "v2.0.0" and j["meta"]["returnedGranularity"] == "boolean"
    assert j["responseSummary"]["exists"] is True
    assert j["info"]["decision"] in ("permit", "permit_with_transform")
    # it was a governed request: it is listed and audited like any other
    assert len(c.get("/requests", headers=H(RESEARCHER)).json()["requests"]) == 1


def test_beacon_requires_key_and_coordinates():
    svc, c = make_client()
    assert c.get("/beacon/g_variants", params=_common_variant(svc)).status_code == 401
    assert c.get("/beacon/g_variants", headers=H(RESEARCHER)).status_code == 422
    bad = {**_common_variant(svc), "requestedGranularity": "record"}
    assert c.get("/beacon/g_variants", params=bad, headers=H(RESEARCHER)).status_code == 422


def test_beacon_unknown_variant_and_never_leaks_genotypes():
    svc, c = make_client()
    r = c.get("/beacon/g_variants", params={"referenceName": "99", "start": 1},
              headers=H(RESEARCHER))
    assert r.json()["responseSummary"] == {"exists": False}
    q = {**_common_variant(svc), "requestedGranularity": "count"}
    body = c.get("/beacon/g_variants", params=q, headers=H(RESEARCHER)).text
    assert "genotype" not in body and "donor" not in body.lower()


def test_beacon_variant_scanning_is_caught():
    """A beacon is probed one variant at a time; scanning many variants quickly must trip the
    anomaly monitor (rate, cumulative exposure) instead of being answered forever."""
    svc, c = make_client()
    common = [j for j in range(svc.ds.n_variants)
              if svc.ds.maf[j] >= 0.2 and j not in set(svc.ds.planted)][:60]
    outcomes = []
    for j in common:
        chrom, pos, _ref, alt = svc.ds.coords[j]
        r = c.get("/beacon/g_variants", headers=H(ANON),
                  params={"referenceName": chrom, "start": pos, "alternateBases": alt})
        outcomes.append(r.json().get("info", {}).get("decision") or r.status_code)
    print(outcomes)
    assert set(outcomes) - {"permit", "permit_with_transform"}, outcomes
