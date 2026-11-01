"""End-to-end journeys over HTTP, the same paths the UI and the guided tour take.

Each test states the expected outcome first, then checks what the API actually did, including that
nothing was released when it should not have been and that the audit chain recorded each step.
"""

import json

from tests.helpers import (
    ADMIN,
    ANON,
    ATTACKER,
    CONTROLLED,
    DEMO_REQ,
    RESEARCHER,
    H,
    attack_queries,
    make_client,
)


def _audit_actions(c):
    rows = c.get("/audit", headers=ADMIN).json()["entries"]
    return [r["action"] for r in rows][::-1]


def test_permitted_request_is_released_protected_and_audited():
    svc, c = make_client()
    d = c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER)).json()
    assert d["outcome"] == "permit_with_transform" and d["status"] == "released"
    assert d["release"]["n_donors"] >= svc.p.k_min  # never a release below the minimum cohort
    assert d["transform"]  # the protections that were applied are reported
    assert d["risk"]["consent"]["eligible"] < d["risk"]["consent"]["considered"]  # consent filtered
    assert c.get("/audit/verify").json()["ok"] is True
    assert any(a.startswith("request") or "decision" in a for a in _audit_actions(c))


def test_disallowed_requests_release_nothing():
    svc, c = make_client()
    cases = [({**DEMO_REQ, "cohort_filter": {"population": "NOPE"}}, RESEARCHER),   # empty cohort
             ({**DEMO_REQ, "data_level": "record"}, RESEARCHER),                    # tier too low
             ({**DEMO_REQ, "data_level": "record"}, ANON)]
    for body, key in cases:
        r = c.post("/requests", json=body, headers=H(key))
        d = r.json()
        assert d["outcome"] == "deny" and d["status"] == "denied", body
        assert d.get("release") in (None, {}), body
        assert "values" not in json.dumps(d.get("release") or {}), body
        # the stored record agrees, and a researcher cannot fetch a release for a denied request
        got = c.get(f"/requests/{d['id']}", headers=H(key)).json()
        assert got["outcome"] == "deny" and not got.get("release")
    assert c.get("/audit/verify").json()["ok"] is True


def test_high_risk_request_is_held_then_human_decision_is_recorded():
    svc, c = make_client()
    held = c.post("/requests", json={**DEMO_REQ, "data_level": "record"},
                  headers=H(CONTROLLED)).json()
    assert held["outcome"] == "escalate" and held["status"] == "held" and held["needs_human"]
    assert not held.get("release")
    rid = held["id"]
    # the advisory copilot can recommend but changes nothing
    rec = c.post(f"/requests/{rid}/copilot", headers=ADMIN)
    assert rec.status_code == 200
    after = c.get(f"/requests/{rid}", headers=ADMIN).json()
    assert after["status"] == "held" and after["needs_human"] and not after["reviewed_by"]
    # malformed approvals are rejected and do not change state
    for bad in ({"approve": "yes"}, {"approve": 1}, {}):
        assert c.post(f"/requests/{rid}/review", json=bad, headers=ADMIN).status_code == 422
    assert c.get(f"/requests/{rid}", headers=ADMIN).json()["status"] == "held"
    # the steward denies; the decision, reviewer and time are stored and audited
    done = c.post(f"/requests/{rid}/review", json={"approve": False, "reviewer": "Dr. Rao"},
                  headers=ADMIN).json()
    assert done["outcome"] == "deny" and done["reviewed_by"] == "Dr. Rao" and done["reviewed_at"]
    assert not done.get("release")
    assert "review.denied" in _audit_actions(c)
    # a second decision on the same request is refused
    assert c.post(f"/requests/{rid}/review", json={"approve": True}, headers=ADMIN).status_code == 409
    assert c.get("/audit/verify").json()["ok"] is True


def test_probing_account_is_frozen_and_stays_locked_out():
    svc, c = make_client()
    codes = []
    for q in attack_queries(30):
        r = c.post("/requests", json=q, headers=H(ATTACKER))
        codes.append(r.status_code)
        if r.status_code == 403:
            assert "frozen" in r.text.lower() or "freeze" in r.text.lower()
            break
    assert codes[-1] == 403, "the monitor never froze the probing account"
    # a frozen account gets nothing, including on a perfectly ordinary request
    assert c.post("/requests", json=DEMO_REQ, headers=H(ATTACKER)).status_code == 403
    # an honest researcher is unaffected
    assert c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER)).status_code == 201
    # a steward can see the alert, and the freeze is in the audit log
    alerts = c.get("/anomalies", headers=ADMIN).json()
    assert alerts
    assert "requester.frozen" in _audit_actions(c) and "alert.raised" in _audit_actions(c)


def test_tamper_is_detected_at_the_exact_entry_and_undo_restores_the_demo():
    svc, c = make_client(allow_tamper_demo=True)
    c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER))
    assert c.get("/audit/verify").json()["ok"] is True
    c.post("/admin/tamper/2", headers=ADMIN)
    v = c.get("/audit/verify").json()
    assert v["ok"] is False and v["first_broken_index"] == 2
    assert c.post("/admin/untamper", headers=ADMIN).json()["ok"] is True
    assert c.get("/audit/verify").json()["ok"] is True
