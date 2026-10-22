import json

from tests.helpers import ADMIN, ANON, ATTACKER, DEMO_REQ, RESEARCHER, H, attack_queries, make_client


def test_health_and_docs_and_openapi():
    svc, c = make_client()
    h = c.get("/health").json()
    assert h["synthetic_data_only"] is True and h["audit_chain_ok"] is True
    assert h["provenance"]["genotypes"] == "synthetic" and h["provenance"]["consent"] == "simulated"
    assert c.get("/docs").status_code == 200
    eps = c.get("/openapi.json").json()["endpoints"]
    assert {"POST /requests", "GET /audit/verify"} <= {f"{e['method']} {e['path']}" for e in eps}


def test_auth_required():
    svc, c = make_client()
    assert c.post("/requests", json=DEMO_REQ).status_code == 401
    assert c.post("/requests", json=DEMO_REQ, headers=H("nope")).status_code == 401
    assert c.get("/audit").status_code == 401
    assert c.get("/audit", headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert c.get("/anomalies").status_code == 401


def test_submit_and_read_back_own_request_only():
    svc, c = make_client()
    r = c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER))
    assert r.status_code == 201 and r.json()["outcome"] == "permit_with_transform"
    rid = r.json()["id"]
    assert c.get(f"/requests/{rid}", headers=H(RESEARCHER)).json()["id"] == rid
    assert c.get(f"/requests/{rid}", headers=H(ATTACKER)).status_code == 403
    assert c.get(f"/requests/{rid}", headers=ADMIN).status_code == 200
    mine = c.get("/requests", headers=H(RESEARCHER)).json()["requests"]
    assert len(mine) == 1 and "release" not in mine[0]
    assert c.get("/requests", headers=H(ATTACKER)).json()["requests"] == []
    assert len(c.get("/requests", headers=ADMIN).json()["requests"]) == 1


def test_bad_inputs_are_422_or_400():
    svc, c = make_client()
    assert c.post("/requests", json={"purpose": "x"}, headers=H(RESEARCHER)).status_code == 422
    r = c.post("/requests", content=b"not json", headers=H(RESEARCHER))
    assert r.status_code == 400
    assert c.post("/requests", json=[1], headers=H(RESEARCHER)).status_code == 400


def test_consent_summary_returns_counts_only():
    svc, c = make_client()
    j = c.get("/consent/summary?purpose=disease_research&disease=diabetes",
              headers=H(RESEARCHER)).json()
    assert set(j) == {"eligible", "considered", "excluded_by_reason"} and j["eligible"] > 0


def test_frozen_account_gets_403_with_reason_and_admin_can_unfreeze():
    svc, c = make_client()
    codes = [c.post("/requests", json=q, headers=H(ATTACKER)).status_code
             for q in attack_queries(5)]
    assert codes[:4] == [201, 201, 201, 201] and codes[4] == 403
    r = c.post("/requests", json=attack_queries(1)[0], headers=H(ATTACKER))
    assert r.json()["error"] == "requester_frozen"
    an = c.get("/anomalies", headers=ADMIN).json()
    att = next(x for x in an["requesters"] if x["name"] == "Probe Account")
    assert att["frozen"] and att["timeline"] and an["alerts"]
    uid = att["id"]
    assert c.post(f"/requesters/{uid}/unfreeze").status_code == 401
    assert c.post(f"/requesters/{uid}/unfreeze", headers=ADMIN).status_code == 200
    assert c.post("/requests", json=attack_queries(1)[0], headers=H(ATTACKER)).status_code == 201


def test_review_endpoint_requires_admin_and_works():
    svc, c = make_client()
    req = {"purpose": "general_research", "data_level": "record",
           "variant_filter": {"min_maf": 0.2, "limit": 5}}
    d = c.post("/requests", json=req, headers=H("demo-controlled")).json()
    assert d["needs_human"]
    assert c.post(f"/requests/{d['id']}/review", json={"approve": True}).status_code == 401
    out = c.post(f"/requests/{d['id']}/review", json={"approve": True, "reviewer": "carol"},
                 headers=ADMIN).json()
    assert out["status"] == "released" and out["reviewed_by"] == "carol"
    assert c.post(f"/requests/{d['id']}/review", json={"approve": True},
                  headers=ADMIN).status_code == 409


def test_audit_endpoints_and_tamper_demo_over_http():
    svc, c = make_client(allow_tamper_demo=True)
    c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER))
    head = c.get("/audit/head").json()
    assert len(head["head_hash"]) == 64 and head["length"] >= 8
    assert c.get("/audit/verify").json()["ok"] is True
    ok_anchor = c.get(f"/audit/verify?anchor_length={head['length']}&anchor_hash="
                      f"{head['head_hash']}").json()
    assert ok_anchor["ok"] is True
    view = c.get("/audit", headers=ADMIN).json()
    assert view["entries"][0]["idx"] == head["length"] and view["verify"]["ok"]
    assert c.post("/admin/tamper/4").status_code == 401
    bad = c.post("/admin/tamper/4", headers=ADMIN).json()
    assert bad["ok"] is False and bad["first_broken_index"] == 4
    assert c.get("/audit/verify").json()["first_broken_index"] == 4
    assert c.get(f"/audit/verify?anchor_length={head['length']}&anchor_hash={head['head_hash']}"
                 ).json()["ok"] is False


def test_tamper_endpoint_403_when_disabled():
    svc, c = make_client()
    c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER))
    assert c.post("/admin/tamper/1", headers=ADMIN).status_code == 403


def test_exposure_and_report_endpoints():
    svc, c = make_client()
    d = c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER)).json()
    g = c.get(f"/requests/{d['id']}/exposure", headers=ADMIN).json()
    assert "SIMULATED" in g["model"]
    # the exposure graph describes withheld variants and registry relatives: steward-only
    assert c.get(f"/requests/{d['id']}/exposure", headers=H(RESEARCHER)).status_code == 401
    rep = c.get("/reports/compliance", headers=ADMIN).json()
    assert rep["facts"]["requests"] == 1 and rep["report"]
    assert c.get("/reports/compliance").status_code == 401


def test_demo_accounts_endpoint_only_in_demo_mode():
    svc, c = make_client()
    j = c.get("/demo/requesters").json()
    assert {r["tier"] for r in j["requesters"]} == {"registered", "anonymous", "controlled"}
    assert j["admin_key"]


def test_no_response_ever_leaks_genotype_like_data():
    svc, c = make_client()
    texts = [c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER)).text,
             c.get("/requests", headers=ADMIN).text, c.get("/audit", headers=ADMIN).text,
             c.get("/anomalies", headers=ADMIN).text, c.get("/me", headers=H(RESEARCHER)).text]
    for t in texts:
        assert "genotype_blob" not in t and "consent_json" not in t and "donor_ids" not in t


def test_researcher_never_sees_carrier_counts_relatives_or_detector_scores():
    svc, c = make_client()
    d = c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER)).json()
    admin_view = c.get(f"/requests/{d['id']}", headers=ADMIN).json()
    # sanity: the sensitive fields exist server-side and the admin can see them
    assert admin_view["risk"]["before"]["min_carriers"] is not None
    assert admin_view["risk"]["before"]["relatives_exposed"]["total"] > 0
    assert "anomaly" in admin_view["transform"]["agent_notes"]
    for body in (d, c.get(f"/requests/{d['id']}", headers=H(RESEARCHER)).json(),
                 c.get("/requests", headers=H(RESEARCHER)).json()["requests"][0]):
        text = json.dumps(body)
        for forbidden in ("min_carriers", "carrier_families", "relatives_exposed",
                          "relatives_exposed_total", "Simulated model", "Behaviour score"):
            assert forbidden not in text, forbidden
        assert body["risk"]["consent"]["eligible"] > 0  # what they may know is still there
        assert body["risk"]["before"]["band"] == "high"


def test_he_endpoint_public_and_correct():
    svc, c = make_client()
    r = c.get("/federated/he")
    assert r.status_code == 200 and r.json()["matches_plaintext"] is True
    assert r.json()["aggregator_saw"]["plaintexts"] == "none"
