import numpy as np

from app.agents.base import grounded
from app.service import ServiceError
from tests.helpers import ANON, ATTACKER, CONTROLLED, DEMO_REQ, RESEARCHER, make_service


def U(svc, key):
    return svc.authenticate(key)


def test_demo_step1_to_3_permit_with_transform_drops_planted_variants():
    svc = make_service()
    d = svc.submit(U(svc, RESEARCHER), DEMO_REQ)
    assert d["outcome"] == "permit_with_transform" and d["status"] == "released"
    c = d["risk"]["consent"]
    assert 20 < c["eligible"] < c["considered"] and c["excluded_by_reason"]
    assert d["transform"]["steps"][0]["step"] == "drop_rare_variants"
    assert d["transform"]["risk_before"]["band"] == "high"
    assert d["transform"]["risk_after"]["band"] == "low"
    planted_ids = {j + 1 for j in svc.ds.planted}
    assert not planted_ids & set(d["release"]["variant_ids"])
    assert "request" in d["explanation"].lower()


def test_release_matches_true_frequencies_when_no_noise():
    svc = make_service()
    d = svc.submit(U(svc, RESEARCHER), {**DEMO_REQ, "variant_filter": {"min_maf": 0.2, "limit": 5}})
    assert d["outcome"] == "permit" and d["transform"]["steps"] == []
    from app.core.consent import ConsentRequest, eligible_cohort
    ids = eligible_cohort(ConsentRequest("disease_research", "diabetes"), svc.ds.donors).donor_ids
    cols = [v - 1 for v in d["release"]["variant_ids"]]
    truth = svc.ds.genotypes[np.ix_(np.array(ids) - 1, cols)].sum(axis=0) / (2 * len(ids))
    assert np.allclose(d["release"]["values"], np.round(truth, 4))


def test_release_never_contains_genotype_rows_or_donor_ids():
    svc = make_service()
    d = svc.submit(U(svc, RESEARCHER), DEMO_REQ)
    blob = str(d)
    assert "genotype" not in blob.lower().replace("genotype rows", "")
    assert d["release"]["level"] != "record"
    assert "donor_ids" not in blob


def test_attack_sequence_blocked_then_frozen_with_403_and_audit():
    from tests.helpers import attack_queries
    svc = make_service()
    a = U(svc, ATTACKER)
    outs = []
    for i, q in enumerate(attack_queries(4)):
        outs.append(svc.submit(a, q, now=1000.0 + i))
    assert outs[0]["outcome"] in ("permit", "permit_with_transform")
    assert outs[1]["outcome"] == "deny" and outs[1]["reasons"] == ["differencing_guard"]
    assert outs[-1]["outcome"] == "escalate" and outs[-1]["needs_human"]
    assert "requester_frozen" in outs[-1]["reasons"]
    assert a["id"] in svc.monitor.frozen
    try:
        svc.submit(U(svc, ATTACKER), attack_queries(1)[0], now=1005.0)
        raise AssertionError("frozen account must get 403")
    except ServiceError as e:
        assert e.status == 403 and e.code == "requester_frozen"
    actions = [e["action"] for e in svc.audit.entries()]
    assert "alert.raised" in actions and "requester.frozen" in actions
    assert "request.refused_frozen" in actions
    assert svc.audit.verify()["ok"]


def test_human_unfreeze_via_review_of_account_escalation():
    from tests.helpers import attack_queries
    svc = make_service()
    a = U(svc, ATTACKER)
    last = None
    for i, q in enumerate(attack_queries(4)):
        last = svc.submit(a, q, now=1000.0 + i)
    out = svc.review(last["id"], "alice", approve=True)
    assert out["status"] == "reviewed" and not out["needs_human"]
    assert a["id"] not in svc.monitor.frozen
    assert svc.store.requester(a["id"])["frozen_at"] is None
    try:
        svc.review(last["id"], "alice", approve=True)
        raise AssertionError("double review must fail")
    except ServiceError as e:
        assert e.status == 409


def test_tier_rules():
    svc = make_service()
    # anonymous cannot get frequencies
    d = svc.submit(U(svc, ANON), DEMO_REQ)
    assert d["outcome"] == "deny" and d["reasons"] == ["credential_insufficient"]
    # registered cannot get record level
    d = svc.submit(U(svc, RESEARCHER), {**DEMO_REQ, "data_level": "record"})
    assert d["outcome"] == "deny" and d["reasons"] == ["credential_insufficient"]
    # anonymous counts of a small cohort are refused
    d = svc.submit(U(svc, ANON), {**DEMO_REQ, "data_level": "count", "disease": "diabetes",
                                  "cohort_filter": {"population": "POP_A",
                                                    "cohort_id": "DIABETES-STUDY"}})
    assert d["outcome"] == "deny" and "cohort_too_small_for_tier" in d["reasons"]
    # anonymous counts of a big cohort are fine
    d = svc.submit(U(svc, ANON), {"purpose": "general_research", "data_level": "count",
                                  "variant_filter": {"min_maf": 0.2, "limit": 5}})
    assert d["outcome"].startswith("permit")


def test_controlled_record_level_needs_human_and_releases_only_aggregates():
    svc = make_service()
    req = {"purpose": "general_research", "data_level": "record",
           "variant_filter": {"min_maf": 0.2, "limit": 10}}
    d = svc.submit(U(svc, CONTROLLED), req)
    assert d["outcome"] == "escalate" and d["needs_human"] and "release" not in d
    assert "record_level_needs_approval" in d["reasons"]
    out = svc.review(d["id"], "bob", approve=True)
    assert out["status"] == "released" and out["release"]["level"] != "record"
    assert all(isinstance(v, (int, float)) for v in out["release"]["values"])


def test_review_deny():
    svc = make_service()
    d = svc.submit(U(svc, CONTROLLED), {"purpose": "general_research", "data_level": "record",
                                        "variant_filter": {"min_maf": 0.2, "limit": 10}})
    out = svc.review(d["id"], "bob", approve=False)
    assert out["outcome"] == "deny" and out["status"] == "denied" and "release" not in out


def test_withdrawal_after_decision_is_respected_on_approval():
    svc = make_service()
    d = svc.submit(U(svc, CONTROLLED), {"purpose": "general_research", "data_level": "record",
                                        "cohort_filter": {"population": "POP_A"},
                                        "variant_filter": {"min_maf": 0.2, "limit": 10}})
    n0 = d["risk"]["consent"]["eligible"]
    # everyone in POP_A withdraws while the request waits
    svc.ds.donors[:] = [type(x)(x.id, x.population, x.cohort_id, x.family_id, x.consent,
                                True if x.population == "POP_A" else x.withdrawn)
                        for x in svc.ds.donors]
    out = svc.review(d["id"], "bob", approve=True)
    assert n0 >= 20 and out["outcome"] == "deny" and out["reasons"] == ["below_k_min"]


def test_epsilon_budget_is_charged_and_refuses_when_spent():
    svc = make_service(n_donors=60, n_variants=300, n_families=12)
    svc.p = svc.p.__class__(max_variants_noised=60, k_min=20)
    svc.monitor.cfg = svc.monitor.cfg.__class__(k_min=20)
    r = U(svc, RESEARCHER)
    req = {"purpose": "general_research", "data_level": "frequency",
           "variant_filter": {"min_maf": 0.05, "limit": 120}}
    d1 = svc.submit(r, req, now=10.0)
    d2 = svc.submit(r, {**req, "variant_filter": {"min_maf": 0.05, "limit": 121}}, now=4000.0)
    spent = svc.budget(r["id"])["epsilon_spent"]
    noised = [d for d in (d1, d2) if d["transform"].get("final", {}).get("epsilon")]
    assert noised and abs(spent - 0.5 * len(
        [d for d in noised if d["status"] == "released"])) < 1e-9


def test_validation_errors():
    svc = make_service()
    r = U(svc, RESEARCHER)
    for bad in ({"purpose": "marketing"}, {**DEMO_REQ, "data_level": "everything"},
                {**DEMO_REQ, "cohort_filter": {"genotype": "x"}},
                {**DEMO_REQ, "disease": "Robert'); DROP TABLE"},
                {**DEMO_REQ, "variant_filter": {"variant_ids": [0]}}):
        try:
            svc.submit(r, bad)
            raise AssertionError(f"should reject {bad}")
        except ServiceError as e:
            assert e.status == 422


def test_audit_covers_the_pipeline_and_tamper_is_detected_at_exact_index():
    svc = make_service(allow_tamper_demo=True)
    svc.submit(U(svc, RESEARCHER), DEMO_REQ)
    acts = [e["action"] for e in svc.audit.entries()]
    for a in ("request.received", "consent.evaluated", "risk.estimated", "transform.step",
              "anomaly.assessed", "release.issued", "agent.output", "decision.made"):
        assert a in acts, a
    assert svc.audit.verify()["ok"]
    head = svc.audit.head()
    bad = svc.tamper(5)
    assert not bad["ok"] and bad["first_broken_index"] == 5
    # an anchor published earlier also flags the damage
    assert not svc.audit.verify({"length": head["length"], "head_hash": head["head_hash"]})["ok"]


def test_tamper_disabled_by_default():
    svc = make_service()
    svc.submit(U(svc, RESEARCHER), DEMO_REQ)
    try:
        svc.tamper(1)
        raise AssertionError("must be disabled")
    except ServiceError as e:
        assert e.status == 403


def test_exposure_graph_has_no_ids_and_lights_up_relatives():
    svc = make_service()
    d = svc.submit(U(svc, RESEARCHER), {**DEMO_REQ, "variant_filter": {
        "min_maf": 0.1, "limit": 20, "include_planted": 2}})
    g = svc.exposure(d["id"])
    assert g["totals"]["subjects"] >= 1 and "SIMULATED" in g["model"]
    text = str(g)
    assert "donor" not in text.replace("Rare-variant carrier", "")
    kinds = {n["kind"] for f in g["families"] for n in f["nodes"]}
    assert "carrier" in kinds


def test_compliance_report_is_grounded_and_not_a_compliance_claim():
    svc = make_service()
    svc.submit(U(svc, RESEARCHER), DEMO_REQ)
    rep = svc.compliance_report()
    assert rep["facts"]["requests"] == 1 and "not a certification" in rep["report"]
    assert "DPDP" in rep["report"] and "compliant" not in rep["report"].lower().replace(
        "not a statement of legal compliance", "")


def test_audit_entries_for_agents_record_model_and_prompt_hash():
    svc = make_service()
    svc.submit(U(svc, RESEARCHER), DEMO_REQ)
    ag = [e for e in svc.audit.entries() if e["action"] == "agent.output"]
    assert ag and all(len(e["payload"]["prompt_sha256"]) == 64 and e["payload"]["model"]
                      == "template" for e in ag)


def test_llm_path_accepts_grounded_and_rejects_ungrounded_text():
    from app.agents.llm import LLM
    from app.config import Settings
    from app.service import bootstrap

    s = Settings()
    s.db_path = ":memory:"
    s.n_donors, s.n_variants, s.n_families = 300, 800, 60
    seen = {}

    def good(url, headers, body, timeout):
        seen["user"] = body["messages"][0]["content"]
        return {"content": [{"type": "text", "text": "Approved with protections."}]}

    svc = bootstrap(s, llm=LLM("k", "claude-test", transport=good))
    d = svc.submit(U(svc, RESEARCHER), DEMO_REQ)
    assert d["explanation"] == "Approved with protections."
    assert "GENOTYPE" not in seen["user"]

    def bad(url, headers, body, timeout):
        return {"content": [{"type": "text", "text": "Exactly 987654 donors were affected."}]}

    svc2 = bootstrap(s, llm=LLM("k", "claude-test", transport=bad))
    d2 = svc2.submit(U(svc2, RESEARCHER), DEMO_REQ)
    assert "987654" not in d2["explanation"] and d2["explanation"].startswith("Your request")
    rej = [e for e in svc2.audit.entries() if e["action"] == "agent.output"
           and e["payload"]["rejected"]]
    assert rej and grounded("5 of 5", {"a": 5}) and not grounded("6", {"a": 5})


def test_llm_failure_falls_back_to_template():
    from app.agents.llm import LLM
    from app.config import Settings
    from app.service import bootstrap

    def boom(*a, **k):
        raise TimeoutError("network down")

    s = Settings()
    s.db_path = ":memory:"
    s.n_donors, s.n_variants, s.n_families = 300, 800, 60
    svc = bootstrap(s, llm=LLM("k", "m", transport=boom))
    d = svc.submit(U(svc, RESEARCHER), DEMO_REQ)
    assert d["explanation"].startswith("Your request")
