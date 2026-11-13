"""Authorization matrix, driven by the route table itself.

For every route the API publishes at /openapi.json, call it with the credentials it should NOT
accept and require a refusal. A new route that forgets its guard, or whose documented access level
changes, fails here. Complements the per-feature tests (ownership, donor keys, review input).
"""

import re
from pathlib import Path

from tests.helpers import ADMIN, ATTACKER, DEMO_REQ, RESEARCHER, H, make_client

DOC = (Path(__file__).resolve().parents[2] / "docs" / "api.md").read_text()
FILL = {"{id:int}": "1", "{idx:int}": "1"}


def _url(path: str) -> str:
    for k, v in FILL.items():
        path = path.replace(k, v)
    return path


def _routes(c):
    return c.get("/openapi.json").json()["endpoints"]


def _call(c, method, url, headers=None):
    body = DEMO_REQ if method in ("POST", "PUT") else None
    return c.request(method, url, headers=headers or {}, json=body)


def _admin_headers_variants():
    return [{}, H(RESEARCHER), H(ATTACKER), {"X-Admin-Key": "wrong"}, {"X-Admin-Key": ""},
            {"X-Admin-Key": "demo-admin-kez"}]


def test_every_admin_route_refuses_everyone_without_the_admin_key():
    svc, c = make_client(allow_tamper_demo=True)
    c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER))
    admin_routes = [r for r in _routes(c) if r["auth"] == "admin"]
    assert len(admin_routes) >= 9
    for r in admin_routes:
        for hdr in _admin_headers_variants():
            res = _call(c, r["method"], _url(r["path"]), hdr)
            assert res.status_code in (401, 403), (r["method"], r["path"], hdr, res.status_code)
            assert "release" not in res.text and "genotype" not in res.text.lower()
    # and the same routes are reachable with the key (so the refusals above are about auth)
    assert c.get("/audit", headers=ADMIN).status_code == 200


def test_every_requester_route_refuses_missing_and_unknown_keys():
    svc, c = make_client()
    req_routes = [r for r in _routes(c) if r["auth"] == "requester"]
    assert req_routes
    for r in req_routes:
        for hdr in ({}, H("nope"), H(""), {"X-Donor-Key": "demo"}):
            res = _call(c, r["method"], _url(r["path"]), hdr)
            assert res.status_code == 401, (r["path"], hdr, res.status_code)


def test_every_donor_route_refuses_missing_other_donor_and_researcher_keys():
    svc, c = make_client()
    donors = c.get("/demo/donors").json()["donors"]
    a, b = donors[0], donors[1]
    session_a = c.post("/demo/donor-session", json={"donor_id": a["id"]}).json()["session_token"]
    session_b = c.post("/demo/donor-session", json={"donor_id": b["id"]}).json()["session_token"]
    donor_routes = [r for r in _routes(c) if r["auth"] == "donor"]
    assert len(donor_routes) >= 5
    for r in donor_routes:
        url = _url(r["path"]).replace("/donor/1", f"/donor/{a['id']}")
        for hdr in ({}, {"X-Demo-Donor-Session": session_b},
                    {"X-Demo-Donor-Session": "invalid"}, {"X-Donor-Key": "demo"},
                    H(RESEARCHER), ADMIN):
            res = _call(c, r["method"], url, hdr)
            assert res.status_code == 401, (r["method"], url, hdr, res.status_code)
        assert _call(c, r["method"], url, {"X-Demo-Donor-Session": session_a}).status_code != 401
    # donor B's session must not read donor A's FHIR export or ledger either
    assert c.get(f"/donor/{a['id']}/consent.fhir.json",
                 headers={"X-Demo-Donor-Session": session_b}).status_code == 401


def test_requester_cannot_use_admin_actions_on_another_requesters_request():
    svc, c = make_client()
    rid = c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER)).json()["id"]
    for path, method in ((f"/requests/{rid}/review", "POST"), (f"/requests/{rid}/copilot", "POST"),
                         (f"/requests/{rid}/exposure", "GET"), ("/requesters/1/freeze", "POST"),
                         ("/requesters/1/unfreeze", "POST")):
        res = _call(c, method, path, H(ATTACKER))
        assert res.status_code in (401, 403), (path, res.status_code)
    # the other account cannot tell a real id from a missing one
    assert c.get(f"/requests/{rid}", headers=H(ATTACKER)).status_code == 404
    assert c.get("/requests/987654", headers=H(ATTACKER)).status_code == 404


def test_api_reference_lists_every_route_the_server_exposes():
    svc, c = make_client()
    for r in _routes(c):
        assert f"| {r['method']} | `{r['path']}` |" in DOC, (r["method"], r["path"])
    assert re.search(r"X-Admin-Key", DOC) and re.search(r"X-Donor-Key", DOC)
