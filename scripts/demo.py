"""`make demo`: runs the 3-minute scripted scenario against a running server and checks each step.

    python scripts/demo.py [--base http://127.0.0.1:8000]

Uses only the standard library. It needs a FRESH database (the probe account freezes), so start
the server with GG_DB_PATH pointing at a new file and GG_ALLOW_TAMPER_DEMO=true. Exit code 0 means
every step behaved as the scripted demo expects.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

OK, BAD = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
failures = 0


def call(base, method, path, key=None, admin=None, body=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-API-Key"] = key
    if admin:
        headers["X-Admin-Key"] = admin
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def check(label, cond, detail=""):
    global failures
    failures += 0 if cond else 1
    print(f"  [{OK if cond else BAD}] {label}" + (f"  ({detail})" if detail else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    base = ap.parse_args().base
    st, demo = call(base, "GET", "/demo/requesters")
    if st != 200:
        sys.exit("demo accounts not available: is the server in demo mode?")
    admin = demo["admin_key"]

    print("\n1. Registered researcher asks for diabetes frequencies")
    st, c = call(base, "GET", "/consent/summary?disease=diabetes&purpose=disease_research",
                 key="demo-researcher")
    check("consent summary returns counts only", st == 200 and "donor_ids" not in json.dumps(c), str(c)[:120])
    body = {"purpose": "disease_research", "disease": "diabetes", "data_level": "frequency",
            "is_commercial": False, "cohort_filter": {},
            "variant_filter": {"min_maf": 0.1, "limit": 20, "include_planted": 2}}
    st, d = call(base, "POST", "/requests", key="demo-researcher", body=body)
    check("request accepted", st in (200, 201), f"HTTP {st}")
    dec = d.get("decision", d)
    print("   outcome:", dec.get("outcome"))
    check("permit_with_transform", dec.get("outcome") == "permit_with_transform")
    check("plain-language explanation present", len(str(dec.get("explanation", ""))) > 40)
    rid = dec.get("request_id") or d.get("id") or dec.get("id")

    print("\n2. Risk estimator flags rare variants; relatives exposed (steward view)")
    if rid:
        st, ex = call(base, "GET", f"/requests/{rid}/exposure", admin=admin)
        check("exposure graph available to steward", st == 200, f"HTTP {st}")
        st, ex2 = call(base, "GET", f"/requests/{rid}/exposure", key="demo-researcher")
        check("exposure graph hidden from researcher", st in (401, 403), f"HTTP {st}")

    print("\n3. Probe account sends many near-identical narrow queries")
    cell = {"cohort_id": "DIABETES-STUDY", "population": "POP_A"}
    diseases = ["diabetes", "cancer", "diabetes", "cardiovascular", "cancer", "diabetes"]
    frozen_at = None
    for i in range(14):
        q = {"purpose": "disease_research", "disease": diseases[i % 6], "is_commercial": i % 2 == 1,
             "data_level": "frequency", "cohort_filter": cell,
             "variant_filter": {"min_maf": 0.1, "limit": 20 + (i % 3)}}
        st, r = call(base, "POST", "/requests", key="demo-attacker", body=q)
        if st == 403:
            frozen_at = i + 1
            break
    check("probe account frozen with a clear 403", frozen_at is not None, f"after {frozen_at} queries")
    st, an = call(base, "GET", "/anomalies", admin=admin)
    check("anomaly alerts visible to steward", st == 200 and bool(an.get("alerts")))
    st, lst = call(base, "GET", "/requests", admin=admin)
    held = [r for r in lst.get("requests", []) if r.get("status") == "held"]
    check("an escalation is waiting for a human", bool(held), f"{len(held)} held")

    print("\n4. Audit log: valid, tamper, broken at that entry, anchor")
    st, head = call(base, "GET", "/audit/head", admin=admin)
    anchor = head.get("head_hash")
    check("head hash published", bool(anchor), (anchor or "")[:16] + "...")
    st, v = call(base, "GET", "/audit/verify", admin=admin)
    check("chain verifies", v.get("ok") is True, f"{v.get('length')} entries")
    st, t = call(base, "POST", "/admin/tamper/3", admin=admin)
    if st == 200:
        st, v2 = call(base, "GET", "/audit/verify", admin=admin)
        check("tamper detected at entry 3", v2.get("ok") is False and v2.get("first_broken_index") == 3,
              str(v2)[:120])
    else:
        check("tamper endpoint (start server with GG_ALLOW_TAMPER_DEMO=true)", False, f"HTTP {st}")

    print("\n5. Evaluation results available")
    st, ev = call(base, "GET", "/eval/results")
    check("eval results served", st == 200 and bool(ev))

    print("\n" + ("ALL DEMO STEPS PASSED" if not failures else f"{failures} CHECK(S) FAILED"))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
