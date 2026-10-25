"""HTTP layer (Starlette): a thin adapter over GenomeGuardService. All decisions live in the
service; this file only parses requests, checks API keys and shapes responses.

Auth: `X-API-Key` = a requester's key (stored only as a SHA-256 hash) or the admin key
(`X-Admin-Key`) for reviewer actions. Responses never contain genotypes, donor ids or raw cohort
membership: only aggregates, transformed releases, counts and reason codes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from app.config import get_settings, validate_settings
from app.core.audit_chain import jsonable
from app.service import DEMO_REQUESTERS, GenomeGuardService, ServiceError, bootstrap

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
# GG_EVAL_JSON points the UI at docs/eval-results-real.json when you deploy on a real cohort
EVAL_JSON = Path(os.environ.get("GG_EVAL_JSON")
                 or Path(__file__).resolve().parents[2] / "docs" / "eval-results.json")

# (method, path, summary, who): drives both routing documentation and /docs
ROUTES_DOC: list[tuple[str, str, str, str]] = []


# What a RESEARCHER may not see, because it is itself the protected information or an oracle:
#  - exact carrier counts of rare variants, family/relative exposure (these describe withheld
#    variants and registry relatives, and are steward-only)
#  - detector scores and advisory notes (would let an attacker tune queries to stay under them)
_STEWARD_RISK_KEYS = ("min_carriers", "carrier_families", "relatives_exposed")
_STEWARD_BRIEF_KEYS = ("min_carriers", "relatives_exposed_total")
_STEWARD_NOTES = ("privacy", "anomaly", "access", "reviewer")


def requester_view(d: dict | None) -> dict | None:
    """Copy of a decision with steward-only detail removed. Admin responses skip this."""
    if not d:
        return d
    out = json.loads(json.dumps(d))
    risk = out.get("risk") or {}
    for part in ("assessment", "before"):
        for k in _STEWARD_RISK_KEYS:
            (risk.get(part) or {}).pop(k, None)
    tr = out.get("transform") or {}
    for part in ("risk_before", "risk_after"):
        for k in _STEWARD_BRIEF_KEYS:
            (tr.get(part) or {}).pop(k, None)
    for k in _STEWARD_NOTES:
        (tr.get("agent_notes") or {}).pop(k, None)
    tr.pop("agent_agrees", None)
    return out


def _j(data, status: int = 200) -> JSONResponse:
    return JSONResponse(jsonable(data), status_code=status)


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise ServiceError(400, "bad_json", "body must be a JSON object") from None
    if not isinstance(data, dict):
        raise ServiceError(400, "bad_json", "body must be a JSON object")
    return data


def create_app(svc: GenomeGuardService | None = None) -> Starlette:
    settings = get_settings()
    validate_settings(settings)
    state = {"svc": svc}

    def S() -> GenomeGuardService:
        if state["svc"] is None:
            state["svc"] = bootstrap(settings)
        return state["svc"]

    def requester(request: Request) -> dict:
        r = S().authenticate(request.headers.get("x-api-key"))
        if not r:
            raise ServiceError(401, "unauthorized", "missing or unknown X-API-Key")
        return r

    def admin(request: Request) -> None:
        if not S().is_admin(request.headers.get("x-admin-key")):
            raise ServiceError(401, "unauthorized", "admin key required (X-Admin-Key)")

    def route(method: str, path: str, summary: str, who: str):
        def deco(fn):
            ROUTES_DOC.append((method, path, summary, who))

            async def handler(request: Request):
                try:
                    return await fn(request)
                except ServiceError as e:
                    return _j(e.to_json(), e.status)
            handler.__name__ = fn.__name__
            return Route(path, handler, methods=[method])
        return deco

    routes: list = []
    ROUTES_DOC.clear()

    @route("GET", "/health", "Liveness and dataset facts", "public")
    async def health(request):
        v = S().audit.verify()
        prov = getattr(S(), "provenance", {})
        return _j({"status": "ok", "synthetic_data_only": prov.get("genotypes") == "synthetic",
                   "donors": S().ds.n_donors, "variants": S().ds.n_variants,
                   "k_min": S().p.k_min, "audit_chain_ok": v["ok"], "provenance": prov,
                   "agents_use_llm": S().team.agents["explainer"].llm.available,
                   "demo_mode": settings.demo_mode, "tamper_demo": settings.allow_tamper_demo})

    @route("GET", "/demo/requesters", "Demo accounts and keys (demo mode only)", "public")
    async def demo_requesters(request):
        if not settings.demo_mode:
            raise ServiceError(404, "not_found", "demo mode is off")
        reqs = {r["name"]: r for r in S().store.requesters()}
        return _j({"admin_key": settings.admin_api_key, "requesters": [
            {"id": reqs[n]["id"], "name": n, "role": ro, "tier": lv, "api_key": k,
             "frozen": reqs[n]["frozen_at"] is not None}
            for n, ro, lv, _i, k in DEMO_REQUESTERS if n in reqs]})

    @route("GET", "/me", "Who am I, my budget", "requester")
    async def me(request):
        r = requester(request)
        return _j({"id": r["id"], "name": r["name"], "tier": r["credential_level"],
                   "frozen": r["id"] in S().monitor.frozen, **S().budget(r["id"])})

    @route("POST", "/requests", "Submit a data request; returns decision, explanation, risk, "
           "transform summary and (if released) aggregate data", "requester")
    async def post_request(request):
        r = requester(request)
        body = await _body(request)
        d = await run_in_threadpool(S().submit, r, body)
        return _j(d if S().is_admin(request.headers.get("x-admin-key")) else requester_view(d), 201)

    @route("GET", "/beacon/g_variants", "GA4GH Beacon v2 style allele lookup, governed by the "
           "same consent, risk and audit pipeline", "requester")
    async def beacon_g_variants(request):
        q = request.query_params
        schema_url = ("https://raw.githubusercontent.com/ga4gh-beacon/beacon-v2/"
                      "c6558bf2e6494df3905f7b2df66e903dfe509500/models/json/"
                      "beacon-v2-default-model/genomicVariations/defaultSchema.json")
        schemas = [{"entityType": "genomicVariation", "schema": schema_url}]

        def response_meta(chrom=None, start=None, alt=None, gran="boolean"):
            parameters = {}
            if chrom is not None:
                parameters["referenceName"] = chrom
            if start is not None:
                parameters["start"] = [start]
            if alt is not None:
                parameters["alternateBases"] = alt
            received = {"apiVersion": "v2.0.0", "requestedSchemas": schemas,
                        "pagination": {"skip": 0, "limit": 10},
                        "requestedGranularity": gran}
            if parameters:
                received["requestParameters"] = {"g_variant": parameters}
            return {"beaconId": "org.genomeguard.demo", "apiVersion": "v2.0.0",
                    "returnedGranularity": gran, "returnedSchemas": schemas,
                    "receivedRequestSummary": received}

        raw_gran = q.get("requestedGranularity", "boolean")
        gran = raw_gran if raw_gran in ("boolean", "count") else "boolean"
        try:
            chrom, start = str(q["referenceName"]), int(q["start"])
        except (KeyError, ValueError):
            meta = response_meta(q.get("referenceName"), None, q.get("alternateBases"), gran)
            return _j({"meta": meta, "error": {"errorCode": 422,
                       "errorMessage": "referenceName and integer start are required"}}, 422)
        alt = q.get("alternateBases")
        meta = response_meta(chrom, start, alt, gran)
        if raw_gran not in ("boolean", "count"):
            return _j({"meta": meta, "error": {"errorCode": 422,
                       "errorMessage": "requestedGranularity must be boolean or count"},
                       "info": {"requestedGranularity": raw_gran}}, 422)
        try:
            r = requester(request)
        except ServiceError as exc:
            return _j({"meta": meta, "error": {"errorCode": exc.status,
                       "errorMessage": "Authentication required"}}, exc.status)

        hits = [i for i, (c, p, _ref, a) in enumerate(S().ds.coords)
                if c == chrom and p == start and (alt is None or a == alt)]
        if not hits:
            summary = {"exists": False}
            if gran == "count":
                summary["numTotalResults"] = 0
            return _j({"meta": meta, "responseSummary": summary,
                       "info": {"note": "no such variant is registered in this beacon"}})
        body = {"purpose": q.get("purpose", "general_research"), "disease": q.get("disease") or None,
                "data_level": gran, "is_commercial": q.get("commercial") == "true",
                "variant_filter": {"variant_ids": [hits[0] + 1]}}
        try:
            d = await run_in_threadpool(S().submit, r, body)
        except ServiceError as exc:
            message = ("Request not permitted by governance policy" if exc.status == 403
                       else "Request parameters failed governance validation")
            return _j({"meta": meta, "error": {"errorCode": exc.status,
                       "errorMessage": message}}, exc.status)
        rel = d.get("release") or {}
        vals = rel.get("values") or []
        if d["outcome"] in ("deny", "escalate") or not vals:
            code = 403 if d["outcome"] in ("deny", "escalate") else 503
            message = ("Request not permitted by governance policy" if code == 403
                       else "No aggregate result could be released under current controls")
            return _j({"meta": meta, "error": {"errorCode": code, "errorMessage": message},
                       "info": {"decision": d["outcome"], "request_id": d["id"]}}, code)
        v = vals[0]
        exists = bool(v) if isinstance(v, bool) else v > 0
        summary = {"exists": exists}
        if gran == "count":
            # Beacon numTotalResults counts matching records, not carriers/allele copies.
            summary["numTotalResults"] = 1 if exists else 0
        return _j({"meta": meta, "responseSummary": summary,
                   "info": {"decision": d["outcome"], "request_id": d["id"],
                            "note": "aggregate answer after consent, risk and noise checks"}})
    @route("GET", "/requests", "List requests (own; all with admin key)", "requester|admin")
    async def list_requests(request):
        if S().is_admin(request.headers.get("x-admin-key")):
            return _j({"requests": S().requests_for(None)})
        return _j({"requests": [requester_view(x) for x in S().requests_for(requester(request))]})

    @route("GET", "/requests/{id:int}", "One decision in detail", "requester|admin")
    async def get_request(request):
        rid = request.path_params["id"]
        is_admin = S().is_admin(request.headers.get("x-admin-key"))
        current = None if is_admin else requester(request)
        d = S().store.decision(rid)
        # Use the same response for missing and non-owned requests to prevent ID enumeration.
        if not d or (current is not None and d["requester_id"] != current["id"]):
            raise ServiceError(404, "not_found", "no such request")
        if is_admin:
            return _j(d)
        return _j(requester_view(d))

    @route("POST", "/requests/{id:int}/review", "Human approve/deny of an escalation", "admin")
    async def review(request):
        admin(request)
        b = await _body(request)
        if not isinstance(b.get("approve"), bool):
            raise ServiceError(422, "invalid_review", "approve must be a JSON boolean")
        who = str(b.get("reviewer", "reviewer"))[:32]
        d = await run_in_threadpool(S().review, request.path_params["id"], who, b["approve"])
        return _j(d)

    @route("POST", "/requests/{id:int}/copilot", "Steward copilot: a read-only, tool-using agent "
           "investigates one request and gives an advisory recommendation (?refresh=true to rerun)",
           "admin")
    async def copilot(request):
        admin(request)
        refresh = request.query_params.get("refresh", "false").lower() == "true"
        return _j(await run_in_threadpool(S().copilot_review, request.path_params["id"], refresh))

    @route("GET", "/requests/{id:int}/exposure", "Family-exposure graph (simulated model); "
           "steward-only because it describes withheld variants and registry relatives", "admin")
    async def exposure(request):
        admin(request)
        rid = request.path_params["id"]
        if not S().store.decision(rid, with_release=False):
            raise ServiceError(404, "not_found", "no such request")
        return _j(S().exposure(rid))

    @route("GET", "/consent/summary", "How many donors would be eligible (counts only)",
           "requester")
    async def consent_summary(request):
        r = requester(request)
        q = request.query_params
        pop = q.get("population")
        out = S().eligibility(
            r, q.get("purpose", "general_research"), q.get("disease") or None,
            q.get("commercial", "false").lower() == "true", q.get("data_level", "frequency"),
            {"population": pop} if pop else {})
        return _j(out)

    @route("GET", "/audit", "Audit log (newest first) with chain verification", "admin")
    async def audit(request):
        admin(request)
        return _j(S().audit_view(int(request.query_params.get("limit", 300))))

    @route("GET", "/audit/verify", "Recompute the hash chain; optional external anchor",
           "public")
    async def audit_verify(request):
        q = request.query_params
        anchor = None
        if q.get("anchor_length") and q.get("anchor_hash"):
            anchor = {"length": int(q["anchor_length"]), "head_hash": q["anchor_hash"]}
        return _j(S().audit.verify(anchor))

    @route("GET", "/audit/head", "Current head hash: copy it somewhere outside the system",
           "public")
    async def audit_head(request):
        return _j(S().audit.head())

    @route("POST", "/admin/tamper/{idx:int}", "DEMO ONLY: corrupt one audit entry", "admin")
    async def tamper(request):
        admin(request)
        return _j(S().tamper(request.path_params["idx"]))

    @route("GET", "/anomalies", "Per-requester timelines and alerts", "admin")
    async def anomalies(request):
        admin(request)
        return _j(S().anomalies())

    @route("POST", "/requesters/{id:int}/freeze", "Freeze an account", "admin")
    async def freeze(request):
        admin(request)
        return _j(S().freeze(request.path_params["id"]))

    @route("POST", "/requesters/{id:int}/unfreeze", "Human unfreeze", "admin")
    async def unfreeze(request):
        admin(request)
        return _j(S().unfreeze(request.path_params["id"]))

    @route("GET", "/reports/compliance", "Plain-language compliance report (from/to ISO dates)",
           "admin")
    async def compliance(request):
        admin(request)
        q = request.query_params
        return _j(await run_in_threadpool(S().compliance_report, q.get("from"), q.get("to")))

    @route("GET", "/eval/results", "Stored red-team evaluation metrics", "public")
    async def eval_results(request):
        if not EVAL_JSON.exists():
            raise ServiceError(404, "not_found", "run `make eval` first")
        return JSONResponse(json.loads(EVAL_JSON.read_text()))

    # ---- donor portal (patient side): authenticated by a per-donor key, never by the steward key
    def donor_auth(request: Request) -> int:
        did = request.path_params["id"]
        if not S().donor_authenticated(did, request.headers.get("x-donor-key")):
            raise ServiceError(401, "unauthorized", "donor key required (X-Donor-Key)")
        return did

    @route("GET", "/demo/donors", "Demo donor personas and keys (demo mode only)", "public")
    async def demo_donors(request):
        if not settings.demo_mode:
            raise ServiceError(404, "not_found", "demo mode is off")
        return _j({"donors": S().demo_donors()})

    @route("GET", "/donor/{id:int}", "A donor's own consent, status and who used their data",
           "donor")
    async def donor_get(request):
        return _j(S().donor_profile(donor_auth(request)))

    @route("GET", "/donor/{id:int}/consent.fhir.json", "Download your consent as a FHIR R4 Consent "
           "resource (pseudonymous; tagged as simulated demo data)", "donor")
    async def donor_fhir(request):
        return JSONResponse(jsonable(S().donor_consent_fhir(donor_auth(request))),
                            media_type="application/fhir+json")

    @route("POST", "/donor/{id:int}/withdraw", "Withdraw consent for all future requests", "donor")
    async def donor_withdraw(request):
        return _j(S().donor_set_withdrawn(donor_auth(request), True))

    @route("PUT", "/donor/{id:int}/consent", "Change what you agree to (use, disease, limits); "
           "applies to future requests", "donor")
    async def donor_consent(request):
        did = donor_auth(request)
        return _j(S().donor_set_consent(did, await _body(request)))

    @route("POST", "/donor/{id:int}/restore", "Give consent again after withdrawing", "donor")
    async def donor_restore(request):
        return _j(S().donor_set_withdrawn(donor_auth(request), False))

    @route("POST", "/donor/{id:int}/ask", "Ask the consent concierge one of a fixed set of "
           "questions (who_used, what_allowed, how_withdraw, relatives, security)", "donor")
    async def donor_ask(request):
        did = donor_auth(request)
        b = await _body(request)
        return _j(await run_in_threadpool(S().donor_ask, did, str(b.get("intent", ""))))

    @route("GET", "/federated/he", "Homomorphic (Paillier) allele-count aggregation demo "
           "(synthetic)", "public")
    async def federated_he(request):
        from app.core.federated import he_demo

        return _j(await run_in_threadpool(he_demo))

    @route("GET", "/federated/demo", "Simulated hospitals with secure aggregation (synthetic)",
           "public")
    async def federated_demo(request):
        from app.core.federated import demo
        return _j(await run_in_threadpool(demo))

    @route("GET", "/openapi.json", "Machine-readable endpoint list", "public")
    async def openapi(request):
        return _j({"openapi": "3.0.0-lite", "info": {"title": "GenomeGuard", "version": "0.2.0"},
                   "endpoints": [{"method": m, "path": p, "summary": s, "auth": w}
                                 for m, p, s, w in ROUTES_DOC]})

    @route("GET", "/docs", "Human-readable endpoint list", "public")
    async def docs(request):
        rows = "".join(f"<tr><td>{m}</td><td><code>{p}</code></td><td>{s}</td><td>{w}</td></tr>"
                       for m, p, s, w in ROUTES_DOC)
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>GenomeGuard API</title>"
            "<style>body{font:15px system-ui;margin:2rem;max-width:60rem}td,th{padding:.3rem .8rem;"
            "text-align:left;border-bottom:1px solid #ddd}</style><h1>GenomeGuard API</h1>"
            f"<p>{'Real 1000 Genomes genotypes with simulated consent.' if getattr(S(), 'provenance', {}).get('genotypes') == 'real_1000g' else 'All data is synthetic.'} "
            "Send <code>X-API-Key</code> (requester) or "
            f"<code>X-Admin-Key</code> (reviewer).</p><table><tr><th>Method<th>Path<th>What<th>Auth"
            f"</tr>{rows}</table>")

    async def index(request):
        f = FRONTEND / "index.html"
        return FileResponse(f) if f.exists() else HTMLResponse("<h1>GenomeGuard API</h1>")

    # collect routes declared with @route (they are the return values of the decorators)
    for obj in list(locals().values()):
        if isinstance(obj, Route):
            routes.append(obj)
    routes.append(Route("/", index))
    if (FRONTEND).exists():
        routes.append(Mount("/static", StaticFiles(directory=FRONTEND), name="static"))
    return Starlette(routes=routes)


app = None


def get_app() -> Starlette:
    global app
    if app is None:
        app = create_app()
    return app
