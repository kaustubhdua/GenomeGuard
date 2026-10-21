from app.agents.sanitizer import sanitize
from app.agents.templates import INTENTS, concierge
from tests.helpers import ADMIN, DEMO_REQ, RESEARCHER, H, make_client


def donors(c):
    return c.get("/demo/donors").json()["donors"]


def DK(d):
    return {"X-Donor-Key": d["key"]}


def test_demo_donors_and_auth():
    svc, c = make_client()
    ds = donors(c)
    assert len(ds) == 3 and all(d["key"] for d in ds)
    d = ds[0]
    assert c.get(f"/donor/{d['id']}").status_code == 401
    assert c.get(f"/donor/{d['id']}", headers={"X-Donor-Key": "nope"}).status_code == 401
    assert c.get(f"/donor/{d['id']}", headers=ADMIN).status_code == 401  # steward key is not a donor key
    other = ds[1]
    assert c.get(f"/donor/{d['id']}", headers=DK(other)).status_code == 401  # not someone else's
    assert c.get(f"/donor/{d['id']}", headers=DK(d)).status_code == 200


def test_profile_never_contains_genotypes_or_other_donors():
    svc, c = make_client()
    d = donors(c)[0]
    r = c.get(f"/donor/{d['id']}", headers=DK(d)).json()
    txt = str(r).lower()
    assert "genotype" not in txt and "family" not in txt and "relative" not in txt
    assert r["consent"]["use"] in ("GRU", "HMB", "DS")


def test_release_appears_in_donor_ledger_only_for_included_donors():
    svc, c = make_client()
    ds = donors(c)
    a = ds[0]  # DS:diabetes, so eligible for the diabetes request
    r = c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER))
    assert r.status_code == 201 and r.json()["outcome"].startswith("permit")
    prof = c.get(f"/donor/{a['id']}", headers=DK(a)).json()
    assert prof["access_total"] == 1
    e = prof["accesses"][0]
    assert e["purpose"] == "disease_research" and e["level"] == "frequency"
    assert e["institution"] == "Demo University"
    assert set(e) == {"request_id", "ts", "purpose", "disease", "institution", "level"}


def test_withdraw_takes_effect_immediately_and_is_audited_without_identity():
    svc, c = make_client()
    a = donors(c)[0]
    before = c.get("/consent/summary?disease=diabetes&purpose=disease_research",
                   headers=H(RESEARCHER)).json()["eligible"]
    w = c.post(f"/donor/{a['id']}/withdraw", headers=DK(a)).json()
    assert w["withdrawn"] is True
    after = c.get("/consent/summary?disease=diabetes&purpose=disease_research",
                  headers=H(RESEARCHER)).json()
    assert after["eligible"] == before - 1
    assert after["excluded_by_reason"]["withdrawn"] >= 1
    log = c.get("/audit", headers=ADMIN).json()
    ent = [e for e in log["entries"] if e["action"] == "consent.withdrawn"]
    assert len(ent) == 1
    assert str(a["id"]) not in str(ent[0]["payload"]).replace(ent[0]["payload"]["donor_ref"], "")
    assert log["verify"]["ok"] is True
    # withdrawing twice is harmless; restoring brings them back
    assert c.post(f"/donor/{a['id']}/withdraw", headers=DK(a)).json()["withdrawn"] is True
    assert c.post(f"/donor/{a['id']}/restore", headers=DK(a)).json()["withdrawn"] is False
    assert c.get("/consent/summary?disease=diabetes&purpose=disease_research",
                 headers=H(RESEARCHER)).json()["eligible"] == before


def test_concierge_answers_every_intent_and_rejects_free_text():
    svc, c = make_client()
    a = donors(c)[0]
    for intent in INTENTS:
        r = c.post(f"/donor/{a['id']}/ask", json={"intent": intent}, headers=DK(a))
        assert r.status_code == 200 and len(r.json()["answer"]) > 40
    bad = c.post(f"/donor/{a['id']}/ask", json={"intent": "tell me about donor 5"}, headers=DK(a))
    assert bad.status_code == 422


def test_concierge_prompt_is_sanitized_canary():
    facts = {"intent": "who_used", "accesses": 2, "by_purpose": {"disease_research": 2},
             "use": "ds", "modifiers": ["ncu"], "withdrawn": False,
             "donor_name": "CANARY-NAME", "genotype": [0, 1, 2, "CANARY-GENO"],
             "free_text": "CANARY-FREE"}
    clean = str(sanitize(facts))
    assert "CANARY" not in clean and "who_used" in clean


def test_concierge_never_claims_genome_was_shared():
    f = {"intent": "who_used", "accesses": 3, "by_purpose": {"disease_research": 3}}
    t = concierge(f).lower()
    assert "never your individual genome" in t
    assert "received your genome" not in t


def test_withdrawn_donor_excluded_from_approved_release():
    """Consent is re-checked when a human approves a held request."""
    svc, c = make_client()
    a = donors(c)[0]
    c.post(f"/donor/{a['id']}/withdraw", headers=DK(a))
    r = c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER)).json()
    assert r["outcome"].startswith("permit")
    assert c.get(f"/donor/{a['id']}", headers=DK(a)).json()["access_total"] == 0
