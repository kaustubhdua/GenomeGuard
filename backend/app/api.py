"""HTTP layer (Starlette): a thin adapter over GenomeGuardService. All decisions live in the
service; this file only parses requests, checks API keys and shapes responses.

Auth: `X-API-Key` = a requester's key (stored only as a SHA-256 hash) or the admin key
(`X-Admin-Key`) for reviewer actions. Responses never contain genotypes, donor ids or raw cohort
membership: only aggregates, transformed releases, counts and reason codes.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import unquote

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from app.config import get_settings, validate_settings
from app.core.audit_chain import jsonable
from app.data.vcf_qc import MAX_UPLOAD_BYTES, validate_vcf
from app.service import DEMO_REQUESTERS, GenomeGuardService, ServiceError, bootstrap
from app.store import CatalogueUnavailableError

log = logging.getLogger(__name__)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
# GG_EVAL_JSON points the UI at docs/eval-results-real.json when you deploy on a real cohort
EVAL_JSON = Path(os.environ.get("GG_EVAL_JSON")
                 or Path(__file__).resolve().parents[2] / "docs" / "eval-results.json")

# (method, path, summary, who): drives both routing documentation and /docs
ROUTES_DOC: list[tuple[str, str, str, str]] = []
_PUBMED_SEARCH_SLOTS = threading.BoundedSemaphore(2)
_DEMO_SESSION_TTL_SECONDS = 1800
_MAX_DEMO_SESSIONS = 5000
_MAX_DEMO_SESSIONS_PER_PERSONA = 5
_OPEN_TARGETS_SEARCH_SLOTS = threading.BoundedSemaphore(2)


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


def _deployment_info() -> dict[str, str | None]:
    commit = os.environ.get("RENDER_GIT_COMMIT", "")
    return {
        "platform": "render" if os.environ.get("RENDER") == "true" else None,
        "git_commit": commit.lower() if re.fullmatch(r"[0-9a-fA-F]{40}", commit) else None,
    }


def _reported_consent_provenance(
    provenance: dict, sample_count: int,
) -> tuple[dict, int, int, bool]:
    reported = dict(provenance)

    def count(value) -> tuple[int, bool]:
        if value is None:
            return 0, True
        if isinstance(value, bool):
            return 0, False
        if isinstance(value, int) and value >= 0:
            return value, True
        if isinstance(value, str) and value.isdecimal():
            return int(value), True
        return 0, False

    matched, matched_valid = count(provenance.get("consent_records_matched"))
    scoped, scoped_valid = count(provenance.get("dataset_policy_samples_scoped"))
    is_dataset_policy = (
        provenance.get("consent_basis") == "dataset_policy"
        or provenance.get("consent") == "source_policy"
    )
    consistent = matched_valid and scoped_valid
    if is_dataset_policy:
        consistent = (
            consistent
            and matched == 0
            and not provenance.get("consent_source")
            and not provenance.get("consent_records_sha256")
            and scoped == sample_count
        )
        matched = 0
        reported["consent_records_matched"] = 0
        reported["consent_source"] = None
        reported["consent_records_sha256"] = None
    else:
        reported["consent_records_matched"] = matched
    reported["dataset_policy_samples_scoped"] = scoped
    return reported, matched, scoped, consistent


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

    demo_sessions: dict[str, dict] = {}
    demo_donor_sessions: dict[str, dict] = {}
    demo_session_lock = threading.RLock()

    def issue_demo_session(registry: dict[str, dict], payload: dict) -> tuple[str, float]:
        now = time.time()
        with demo_session_lock:
            expired = [token for token, session in registry.items() if session["expires_at"] <= now]
            for token in expired:
                registry.pop(token, None)
            identity_field = "requester_id" if "requester_id" in payload else "donor_id"
            identity_value = payload[identity_field]
            same_persona = sorted(
                (
                    (token, session) for token, session in registry.items()
                    if session.get(identity_field) == identity_value
                ),
                key=lambda item: item[1]["expires_at"],
            )
            while len(same_persona) >= _MAX_DEMO_SESSIONS_PER_PERSONA:
                expired_token, _ = same_persona.pop(0)
                registry.pop(expired_token, None)
            if len(registry) >= _MAX_DEMO_SESSIONS:
                raise ServiceError(
                    503, "demo_session_capacity",
                    "The synthetic demo session capacity is temporarily full. Please retry later.",
                )
            token = secrets.token_urlsafe(32)
            expires_at = now + _DEMO_SESSION_TTL_SECONDS
            registry[token] = {**payload, "expires_at": expires_at}
        return token, expires_at

    def requester(request: Request) -> dict:
        cached = getattr(request.state, "authenticated_requester", None)
        if cached is not None:
            return cached
        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            if not (settings.oidc_issuer and settings.oidc_audience and settings.oidc_jwks_url
                    and settings.oidc_allowed_organizations):
                raise ServiceError(503, "oidc_not_configured",
                                   "institutional OIDC is not configured on this instance")
            from app.identity import OIDCAuthenticationError, verify_access_token

            try:
                identity = verify_access_token(
                    authorization[7:].strip(),
                    issuer=settings.oidc_issuer,
                    audience=settings.oidc_audience,
                    jwks_url=settings.oidc_jwks_url,
                    organization_claim=settings.oidc_organization_claim,
                    allowed_organizations=settings.oidc_allowed_organizations,
                )
            except OIDCAuthenticationError:
                raise ServiceError(401, "unauthorized", "invalid institutional bearer token") from None
            r = scoped_identity_lookup(
                identity.organization_id, S().authenticate_oidc,
                identity.issuer, identity.subject, identity.organization_id,
            )
            if not r:
                raise ServiceError(403, "identity_not_provisioned",
                                   "verified identity is not provisioned for this organization")
            if r.get("role") != "researcher":
                raise ServiceError(403, "role_not_allowed",
                                   "this identity is not provisioned for researcher access")
            request.state.authenticated_requester = r
            return r
        demo_token = request.headers.get("x-demo-session")
        if (settings.demo_mode and not settings.oidc_required
                and not settings.tenant_isolation_required and demo_token):
            with demo_session_lock:
                session = demo_sessions.get(demo_token)
                if session and session["expires_at"] <= time.time():
                    demo_sessions.pop(demo_token, None)
                    session = None
            if not session:
                raise ServiceError(401, "demo_session_expired", "demo session is invalid or expired")
            with S().store.transaction():
                set_demo = getattr(S().store, "set_allow_unscoped_demo", None)
                if set_demo is not None:
                    set_demo()
                r = S().store.requester(session["requester_id"])
            if not r or r.get("id") != session["requester_id"]:
                raise ServiceError(401, "demo_session_invalid", "demo session is no longer valid")
            r = {key: value for key, value in r.items() if key != "api_key_hash"}
            r = {**r, "_allow_unscoped_demo": True}
            request.state.authenticated_requester = r
            return r
        if settings.demo_mode and not settings.allow_static_demo_keys:
            raise ServiceError(
                401, "demo_session_required",
                "use a short-lived synthetic demo session; static demo API keys are disabled",
            )
        if settings.oidc_required:
            raise ServiceError(401, "unauthorized", "institutional bearer token required")
        if settings.demo_mode:
            with S().store.transaction():
                set_demo = getattr(S().store, "set_allow_unscoped_demo", None)
                if set_demo is not None:
                    set_demo()
                r = S().authenticate(request.headers.get("x-api-key"))
        else:
            r = S().authenticate(request.headers.get("x-api-key"))
        if not r:
            raise ServiceError(401, "unauthorized", "missing or unknown X-API-Key")
        if settings.tenant_isolation_required:
            raise ServiceError(403, "tenant_identity_required",
                               "a verified organization-bound OIDC identity is required")
        if settings.demo_mode and not r.get("organization_id"):
            r = {**r, "_allow_unscoped_demo": True}
        request.state.authenticated_requester = r
        return r

    def scoped_identity_lookup(organization_id: str, fn, *args, **kwargs):
        """Resolve OIDC bindings inside the same tenant scope enforced by PostgreSQL RLS."""
        with S().store.transaction():
            set_tenant = getattr(S().store, "set_tenant", None)
            if set_tenant is not None:
                set_tenant(organization_id)
            elif settings.tenant_isolation_required and not settings.demo_mode:
                raise ServiceError(
                    503, "tenant_store_unsupported",
                    "tenant-isolated identity lookup requires PostgreSQL RLS",
                )
            return fn(*args, **kwargs)

    def scoped_requester_call(identity: dict, fn, *args, **kwargs):
        with S().store.transaction():
            if identity.get("organization_id"):
                S().store.set_tenant(identity["organization_id"])
            elif identity.get("_allow_unscoped_demo") and settings.demo_mode:
                S().store.set_allow_unscoped_demo()
            elif settings.tenant_isolation_required:
                raise ServiceError(403, "tenant_identity_required",
                                   "verified organization scope is required")
            return fn(*args, **kwargs)

    def apply_admin_scope(principal: dict) -> None:
        """Apply the narrowest RLS scope for the authenticated reviewer principal."""
        organization_id = principal.get("organization_id")
        if organization_id:
            set_tenant = getattr(S().store, "set_tenant", None)
            if set_tenant is None:
                if settings.tenant_isolation_required and not settings.demo_mode:
                    raise ServiceError(
                        503, "tenant_store_unsupported",
                        "organization-scoped reviewer access requires PostgreSQL RLS",
                    )
                # Local/demo SQLite has no database RLS. It is never accepted in non-demo mode.
                return
            set_tenant(organization_id)
            return
        set_admin = getattr(S().store, "set_admin_access", None)
        if set_admin is not None:
            set_admin()
        elif settings.tenant_isolation_required and not settings.demo_mode:
            raise ServiceError(
                503, "tenant_store_unsupported",
                "tenant-isolated admin access requires PostgreSQL RLS",
            )

    def admin_call(principal: dict, fn, *args, **kwargs):
        with S().store.transaction():
            apply_admin_scope(principal)
            return fn(*args, **kwargs)

    def admin(request: Request) -> dict:
        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            if not (settings.oidc_issuer and settings.oidc_audience and settings.oidc_jwks_url
                    and settings.oidc_allowed_organizations):
                raise ServiceError(503, "oidc_not_configured",
                                   "institutional OIDC is not configured on this instance")
            from app.identity import OIDCAuthenticationError, verify_access_token

            try:
                identity = verify_access_token(
                    authorization[7:].strip(),
                    issuer=settings.oidc_issuer,
                    audience=settings.oidc_audience,
                    jwks_url=settings.oidc_jwks_url,
                    organization_claim=settings.oidc_organization_claim,
                    allowed_organizations=settings.oidc_allowed_organizations,
                )
            except OIDCAuthenticationError:
                raise ServiceError(401, "unauthorized", "invalid institutional bearer token") from None
            principal = scoped_identity_lookup(
                identity.organization_id, S().authenticate_oidc,
                identity.issuer, identity.subject, identity.organization_id,
            )
            if not principal or principal.get("role") not in {"reviewer", "steward", "admin"}:
                raise ServiceError(403, "steward_identity_required",
                                   "a provisioned reviewer or steward identity is required")
            # Every OIDC identity, including an organization-level "admin", remains
            # bound to the organization asserted by the verified token. Global database
            # access is reserved for the separately controlled X-Admin-Key credential.
            scoped_principal = {
                "role": principal["role"],
                "organization_id": identity.organization_id,
                "auth_organization_id": identity.organization_id,
                "issuer": identity.issuer,
                "subject": identity.subject,
                "global": False,
            }
            path = request.url.path
            global_only = (
                path == "/audit" or path.startswith("/audit/")
                or path.startswith("/reports/compliance")
                or path in {
                    "/admin/consent-events", "/admin/dataset-qc", "/admin/untamper",
                }
                or path.startswith("/admin/tamper/")
            )
            if global_only:
                raise ServiceError(
                    403, "global_steward_access_required",
                    "this operation requires the separately controlled global administrator credential",
                )
            if scoped_principal["role"] == "reviewer" and (
                path.endswith("/release") or path.endswith("/copilot")
                or path.endswith("/exposure") or path == "/admin/vcf-qc"
                or path.startswith("/admin/oidc-bindings")
                or path == "/admin/requesters"
                or (path.startswith("/requesters/") and
                    (path.endswith("/freeze") or path.endswith("/unfreeze")))
            ):
                raise ServiceError(
                    403, "steward_role_required",
                    "this operation requires an organization steward role",
                )
            request.state.admin_principal = scoped_principal
            return scoped_principal
        if settings.oidc_admin_required:
            raise ServiceError(401, "unauthorized", "institutional reviewer bearer token required")
        if not S().is_admin(request.headers.get("x-admin-key")):
            raise ServiceError(401, "unauthorized", "admin key required (X-Admin-Key)")
        global_principal = {"role": "admin", "organization_id": None, "global": True}
        request.state.admin_principal = global_principal
        return global_principal

    def require_governed_data(svc: GenomeGuardService) -> None:
        # Request evaluation and consent previews may run against an initialized cohort
        # even when this deployment is not authorized to release its data. Release
        # eligibility is enforced separately by the service after the policy pipeline.
        if svc.ds.n_donors < 1 or svc.ds.n_variants < 1:
            raise ServiceError(
                503, "governed_data_unavailable",
                "The active decision engine has no initialized cohort to evaluate.",
            )

    def route(method: str, path: str, summary: str, who: str):
        def deco(fn):
            ROUTES_DOC.append((method, path, summary, who))

            async def handler(request: Request):
                try:
                    # Admin routes establish an authenticated, transaction-local RLS context
                    # for every database operation in the handler. The handler's own admin()
                    # call remains as defense in depth and preserves route-local validation.
                    if who == "admin":
                        principal = admin(request)
                        with S().store.transaction():
                            apply_admin_scope(principal)
                            return await fn(request)
                    # Other routes authenticate inside their handlers so protocol-specific
                    # error envelopes (for example GA4GH Beacon) remain intact.
                    response = await fn(request)
                    if method == "GET" and path.startswith("/catalogue/"):
                        # These endpoints expose only public reference metadata and
                        # verified dataset manifests. Edge caches may revalidate, but
                        # browsers must not retain stale catalogue state.
                        response.headers["Cache-Control"] = (
                            "public, max-age=0, s-maxage=60, stale-while-revalidate=300"
                        )
                        response.headers["Vary"] = "Accept"
                    return response
                except ServiceError as e:
                    return _j(e.to_json(), e.status)
                except CatalogueUnavailableError:
                    return _j({
                        "error": "catalogue_unavailable",
                        "message": "The verified normalized dataset catalogue is unavailable.",
                    }, 503)
            handler.__name__ = fn.__name__
            return Route(path, handler, methods=[method])
        return deco

    routes: list = []
    ROUTES_DOC.clear()

    def readiness_checks(svc: GenomeGuardService) -> dict[str, bool]:
        provenance = getattr(svc, "provenance", {})
        _, consent_records_matched, _, consent_provenance_consistent = (
            _reported_consent_provenance(provenance, svc.ds.n_donors)
        )
        return {
            "demo_mode_disabled": not settings.demo_mode,
            "real_genotype_provenance": provenance.get("genotypes") == "real_vcf",
            "participant_consent_records_verified": (
                provenance.get("consent") == "source_records"
                and consent_records_matched == int(svc.ds.n_donors)
                and consent_provenance_consistent
            ),
            "destructive_tamper_demo_disabled": not settings.allow_tamper_demo,
            "postgres_storage_configured": getattr(svc.store, "backend", "sqlite") == "postgresql",
            "durable_storage_verified": False,
            "backup_retention_and_restore_verified": False,
            "monitoring_and_alerting_verified": False,
            "external_audit_anchor_verified": False,
            "institutional_identity_provider_verified": False,
            # The normalized public-reference importer is not a private,
            # organization-isolated ingestion and processing lifecycle.
            "private_cohort_ingestion_verified": False,
            "tenant_processing_isolation_verified": False,
            "participant_consent_authority_configured": bool(
                settings.consent_authority_required
                and settings.consent_authority_issuer.startswith("https://")
                and settings.consent_authority_public_key
            ),
        }

    @route("GET", "/health/live", "Cheap process liveness probe; does not initialize the cohort or database", "public")
    async def liveness(request):
        # Hosting health checks must not trigger the expensive, lazy service bootstrap.
        # This endpoint confirms only that the ASGI process can answer HTTP requests.
        return _j({"status": "ok", "deployment": _deployment_info()})

    @route("GET", "/health", "Liveness and non-authoritative dataset/readiness facts", "public")
    async def health(request):
        svc = S()
        raw_provenance = getattr(svc, "provenance", {})
        provenance, consent_records_matched, policy_samples_scoped, consent_provenance_consistent = (
            _reported_consent_provenance(raw_provenance, svc.ds.n_donors)
        )
        checks = readiness_checks(svc)
        participant_consent_verified = (
            raw_provenance.get("consent") == "source_records"
            and consent_records_matched == int(svc.ds.n_donors)
            and consent_provenance_consistent
        )
        return _j({
            "status": "ok",
            "synthetic_data_only": raw_provenance.get("genotypes") == "synthetic",
            "provenance_known": raw_provenance.get("genotypes") != "unknown",
            "consent_simulated": raw_provenance.get("consent") == "simulated",
            "participant_consent_records_verified": participant_consent_verified,
            "participant_consent_records_matched": consent_records_matched,
            "dataset_policy_samples_scoped": policy_samples_scoped,
            "consent_provenance_consistent": consent_provenance_consistent,
            "donors": svc.ds.n_donors, "variants": svc.ds.n_variants,
            "k_min": svc.p.k_min, "audit_chain_ok": None, "provenance": provenance,
            "agents_use_llm": svc.team.agents["explainer"].llm.available,
            "demo_mode": settings.demo_mode, "tamper_demo": settings.allow_tamper_demo,
            "storage_backend": getattr(svc.store, "backend", "sqlite"),
            "governed_data_release_enabled": svc.release_enabled,
            "deployment": _deployment_info(),
            "readiness": {"ready": all(checks.values()), "checks": checks},
        })

    @route("GET", "/health/ready", "Production readiness gate; distinguishes service availability from safe real-data operation", "public")
    async def readiness(request):
        checks = readiness_checks(S())
        ready = all(checks.values())
        return _j({"status": "ready" if ready else "not_ready", "ready": ready,
                   "checks": checks, "note": (
                       "Readiness is not clinical or legal approval; independent security, "
                       "privacy, and governance review remains required."
                   )}, 200 if ready else 503)

    @route("GET", "/demo/requesters", "Synthetic demo personas (no credentials)", "public")
    async def demo_requesters(request):
        if not settings.demo_mode:
            raise ServiceError(404, "not_found", "demo mode is off")
        with S().store.transaction():
            set_demo = getattr(S().store, "set_allow_unscoped_demo", None)
            if set_demo is not None:
                set_demo()
            reqs = S().store.requesters()
        payload = {"requesters": [
            {
                "id": r["id"],
                "name": r["name"],
                "role": next((ro for n, ro, _tier, _institution, _key in DEMO_REQUESTERS if n == r["name"]), "researcher"),
                "tier": next((tier for n, _ro, tier, _institution, _key in DEMO_REQUESTERS if n == r["name"]), "anonymous"),
                "frozen": r["frozen_at"] is not None,
            }
            for r in reqs if any(n == r["name"] for n, _ro, _tier, _institution, _key in DEMO_REQUESTERS)
        ]}
        return _j(payload)

    @route("POST", "/demo/session", "Issue a short-lived, in-memory synthetic demo requester session", "public")
    async def demo_session(request):
        if not settings.demo_mode or settings.oidc_required or settings.tenant_isolation_required:
            raise ServiceError(404, "not_found", "demo sessions are not enabled on this instance")
        data = await _body(request)
        requester_id = data.get("requester_id")
        if isinstance(requester_id, bool) or not isinstance(requester_id, int) or requester_id < 1:
            raise ServiceError(400, "invalid_demo_requester", "requester_id must be a positive integer")
        with S().store.transaction():
            set_demo = getattr(S().store, "set_allow_unscoped_demo", None)
            if set_demo is not None:
                set_demo()
            record = next((r for r in S().store.requesters() if r["id"] == requester_id), None)
            if not record:
                raise ServiceError(404, "demo_requester_not_found", "demo requester was not found")
            persona = next((p for p in DEMO_REQUESTERS if p[0] == record["name"]), None)
            if not persona:
                raise ServiceError(404, "demo_requester_not_found", "demo requester was not found")
        token, _expires_at = issue_demo_session(demo_sessions, {"requester_id": requester_id})
        return _j({
            "session_token": token,
            "expires_in": _DEMO_SESSION_TTL_SECONDS,
            "requester": {"id": requester_id, "name": persona[0], "role": persona[1], "tier": persona[2]},
        })

    @route("GET", "/auth/oidc", "Institutional OIDC API configuration (no secrets)", "public")
    async def oidc_configuration(request):
        configured = bool(
            settings.oidc_issuer and settings.oidc_audience and settings.oidc_client_id
            and settings.oidc_redirect_uri and settings.oidc_jwks_url
            and settings.oidc_allowed_organizations
        )
        return _j({
            "enabled": configured,
            "required": settings.oidc_required,
            "issuer": settings.oidc_issuer if configured else None,
            "audience": settings.oidc_audience if configured else None,
            "client_id": settings.oidc_client_id if configured else None,
            "redirect_uri": settings.oidc_redirect_uri if configured else None,
            "jwks_url": settings.oidc_jwks_url if configured else None,
            "scopes": settings.oidc_scopes if configured else None,
            "organization_claim": settings.oidc_organization_claim if configured else None,
        })

    @route("POST", "/admin/oidc-bindings", "Bind a provisioned requester to a verified OIDC subject", "admin")
    async def oidc_bind(request):
        admin(request)
        if not settings.oidc_issuer or not settings.oidc_allowed_organizations:
            raise ServiceError(503, "oidc_not_configured", "institutional OIDC is not configured")
        body = await _body(request)
        requester_id = body.get("requester_id")
        subject = body.get("subject")
        organization_id = body.get("organization_id")
        if isinstance(requester_id, bool) or not isinstance(requester_id, int) or requester_id < 1:
            raise ServiceError(422, "invalid_request", "requester_id must be a positive integer")
        if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
            raise ServiceError(422, "invalid_request", "subject must contain 1 to 255 characters")
        if organization_id not in settings.oidc_allowed_organizations:
            raise ServiceError(403, "organization_not_allowed", "organization is not enabled")
        reviewer_scope = request.state.admin_principal.get("organization_id")
        if reviewer_scope and organization_id != reviewer_scope:
            raise ServiceError(
                403, "cross_organization_binding_forbidden",
                "an organization-scoped reviewer may only provision identities in their own organization",
            )
        try:
            S().bind_oidc_identity(
                requester_id, settings.oidc_issuer, subject, organization_id,
            )
        except ValueError as exc:
            raise ServiceError(409, "identity_binding_conflict", str(exc)) from None
        return _j({"bound": True, "requester_id": requester_id,
                   "organization_id": organization_id}, 201)

    @route("POST", "/admin/consent-events", "Apply an externally signed participant consent event", "admin")
    async def signed_consent_event(request):
        admin(request)
        if not settings.consent_authority_required or not (
            settings.consent_authority_issuer and settings.consent_authority_public_key
        ):
            raise ServiceError(503, "consent_authority_not_configured",
                               "a trusted participant consent authority is not configured")
        body = await _body(request)
        result = admin_call(
            request.state.admin_principal, S().apply_signed_consent_event,
            body,
            public_key_b64=settings.consent_authority_public_key,
            trusted_issuer=settings.consent_authority_issuer,
        )
        return _j({"applied": True, "participant": result}, 200)

    @route("POST", "/admin/oidc-bindings/revoke", "Revoke an OIDC identity binding", "admin")
    async def oidc_revoke(request):
        admin(request)
        if not settings.oidc_issuer:
            raise ServiceError(503, "oidc_not_configured", "institutional OIDC is not configured")
        body = await _body(request)
        subject = body.get("subject")
        organization_id = body.get("organization_id")
        if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
            raise ServiceError(422, "invalid_request", "subject must contain 1 to 255 characters")
        if organization_id not in settings.oidc_allowed_organizations:
            raise ServiceError(403, "organization_not_allowed", "organization is not enabled")
        reviewer_scope = request.state.admin_principal.get("organization_id")
        if reviewer_scope and organization_id != reviewer_scope:
            raise ServiceError(
                403, "cross_organization_binding_forbidden",
                "an organization-scoped reviewer may only revoke identities in their own organization",
            )
        S().revoke_oidc_identity(settings.oidc_issuer, subject, organization_id)
        return _j({"revoked": True, "organization_id": organization_id})

    @route("POST", "/admin/requesters", "Provision a requester API key (returned once)", "admin")
    async def provision_requester(request):
        admin(request)
        if settings.demo_mode:
            raise ServiceError(404, "not_found", "requester provisioning is disabled in demo mode")
        body = await _body(request)
        name = body.get("name")
        institution = body.get("institution")
        level = body.get("credential_level", "registered")
        role = body.get("role", "researcher")
        organization_id = body.get("organization_id")
        if settings.oidc_required and organization_id not in settings.oidc_allowed_organizations:
            raise ServiceError(
                422, "organization_required",
                "organization_id must identify an enabled organization when institutional OIDC is required",
            )
        if organization_id is not None and organization_id not in settings.oidc_allowed_organizations:
            raise ServiceError(403, "organization_not_allowed", "organization is not enabled")
        reviewer_scope = request.state.admin_principal.get("organization_id")
        if reviewer_scope and organization_id != reviewer_scope:
            raise ServiceError(
                403, "cross_organization_requester_forbidden",
                "an organization-scoped steward may only provision identities in their own organization",
            )
        if reviewer_scope and role == "steward":
            raise ServiceError(
                403, "steward_role_provisioning_forbidden",
                "an organization-scoped steward cannot grant another steward role",
            )
        if not isinstance(name, str) or not 2 <= len(name.strip()) <= 120:
            raise ServiceError(422, "invalid_request", "name must contain 2 to 120 characters")
        if not isinstance(institution, str) or not 2 <= len(institution.strip()) <= 200:
            raise ServiceError(422, "invalid_request", "institution must contain 2 to 200 characters")
        if level not in ("registered", "controlled"):
            raise ServiceError(422, "invalid_request",
                               "credential_level must be registered or controlled")
        if role not in ("researcher", "reviewer", "steward"):
            raise ServiceError(422, "invalid_request",
                               "role must be researcher, reviewer or steward")
        key = secrets.token_urlsafe(32)
        requester_id = S().create_requester(
            name.strip(), role, level, institution.strip(), key, organization_id=organization_id,
        )
        result = {"id": requester_id, "name": name.strip(), "institution": institution.strip(),
                  "role": role, "credential_level": level, "organization_id": organization_id}
        if not settings.oidc_required:
            result.update(api_key=key, shown_once=True)
        else:
            result["identity_binding_required"] = True
        return _j(result, 201)

    @route("GET", "/me", "Who am I, my budget", "requester")
    async def me(request):
        r = requester(request)
        budget = scoped_requester_call(r, S().budget, r["id"])
        return _j({"id": r["id"], "name": r["name"], "role": r["role"],
                   "institution": r["institution"], "tier": r["credential_level"],
                   "frozen": r["id"] in S().monitor.frozen, **budget})

    @route("POST", "/requests", "Submit a data request; returns decision, explanation, risk, "
           "transform summary and (if released) aggregate data", "requester")
    async def post_request(request):
        r = requester(request)
        svc = S()
        require_governed_data(svc)
        body = await _body(request)
        try:
            d = await run_in_threadpool(scoped_requester_call, r, svc.submit, r, body)
        except ServiceError as exc:
            if exc.code == "requester_frozen":
                # scoped_requester_call owns an outer transaction, so the service's
                # rejected request and its provisional audit event have rolled back.
                # Record the security refusal now, in a fresh tenant-scoped transaction.
                with svc.store.transaction():
                    if r.get("organization_id"):
                        svc.store.set_tenant(r["organization_id"])
                    elif r.get("_allow_unscoped_demo") and settings.demo_mode:
                        svc.store.set_allow_unscoped_demo()
                    svc.audit.append(
                        "system", "request.refused_frozen",
                        {"request_id": exc.extra.get("request_id")},
                    )
            raise
        return _j(d if svc.is_admin(request.headers.get("x-admin-key")) else requester_view(d), 201)

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

        # authenticate before looking at parameters, so an anonymous caller learns nothing
        try:
            r = requester(request)
        except ServiceError as exc:
            return _j({"meta": response_meta(), "error": {"errorCode": exc.status,
                       "errorMessage": "Authentication required"}}, exc.status)
        svc = S()
        try:
            require_governed_data(svc)
        except ServiceError as exc:
            return _j({"meta": response_meta(), "error": {"errorCode": exc.status,
                       "errorMessage": exc.message}}, exc.status)

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
        hits = [i for i, (c, p, _ref, a) in enumerate(svc.ds.coords)
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
            d = await run_in_threadpool(scoped_requester_call, r, svc.submit, r, body)
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
        if request.headers.get("authorization", "").startswith("Bearer "):
            try:
                identity = requester(request)
            except ServiceError as exc:
                if exc.code != "role_not_allowed":
                    raise
                admin(request)
                rows = admin_call(request.state.admin_principal, S().requests_for, None)
                return _j({"requests": rows})
        elif S().is_admin(request.headers.get("x-admin-key")):
            admin(request)
            rows = admin_call(request.state.admin_principal, S().requests_for, None)
            return _j({"requests": rows})
        else:
            identity = requester(request)
        rows = scoped_requester_call(identity, S().requests_for, identity)
        return _j({"requests": [requester_view(x) for x in rows]})

    @route("GET", "/requests/{id:int}", "One decision in detail", "requester|admin")
    async def get_request(request):
        rid = request.path_params["id"]
        is_admin = S().is_admin(request.headers.get("x-admin-key"))
        current = None
        if request.headers.get("authorization", "").startswith("Bearer "):
            try:
                current = requester(request)
            except ServiceError as exc:
                if exc.code != "role_not_allowed":
                    raise
                admin(request)
                is_admin = True
        elif not is_admin:
            current = requester(request)
        elif is_admin:
            admin(request)
        d = (
            admin_call(request.state.admin_principal, S().store.decision, rid) if is_admin
            else scoped_requester_call(current, S().store.decision, rid)
        )
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
        action = b.get("action")
        approve = b.get("approve")
        if action is None and not isinstance(approve, bool):
            raise ServiceError(422, "invalid_review", "approve must be a JSON boolean")
        if action is not None and action not in {"approve", "deny", "request_information"}:
            raise ServiceError(422, "invalid_review", "unsupported steward review action")
        if action is not None:
            approve = action == "approve"
        who = str(b.get("reviewer", "reviewer"))[:32]
        # The admin route wrapper already owns the transaction on this event-loop
        # thread. Keep this short database mutation on the same thread; moving it
        # to a worker would block on the transaction-scoped lock.
        d = admin_call(
            request.state.admin_principal, S().review,
            request.path_params["id"], who, approve, action,
        )
        return _j(d)

    @route("POST", "/requests/{id:int}/release", "Recheck and perform a separately approved governed release", "admin")
    async def release_approved(request):
        admin(request)
        body = await _body(request)
        who = str(body.get("reviewer", "reviewer"))[:32]
        result = admin_call(
            request.state.admin_principal, S().release_approved,
            request.path_params["id"], who,
        )
        return _j(result)

    @route("POST", "/requests/{id:int}/copilot", "Steward copilot: a read-only, tool-using agent "
           "investigates one request and gives an advisory recommendation (?refresh=true to rerun)",
           "admin")
    async def copilot(request):
        admin(request)
        refresh = request.query_params.get("refresh", "false").lower() == "true"
        return _j(admin_call(
            request.state.admin_principal, S().copilot_review,
            request.path_params["id"], refresh,
        ))

    @route("GET", "/requests/{id:int}/exposure", "Family-exposure graph (simulated model); "
           "steward-only because it describes withheld variants and registry relatives", "admin")
    async def exposure(request):
        admin(request)
        rid = request.path_params["id"]
        def exposure():
            if not S().store.decision(rid, with_release=False):
                raise ServiceError(404, "not_found", "no such request")
            return S().exposure(rid)
        return _j(admin_call(request.state.admin_principal, exposure))

    @route("GET", "/consent/summary", "How many donors would be eligible (counts only)",
           "requester")
    async def consent_summary(request):
        r = requester(request)
        svc = S()
        require_governed_data(svc)
        q = request.query_params
        pop = q.get("population")
        out = scoped_requester_call(
            r, svc.eligibility,
            r, q.get("purpose", "general_research"), q.get("disease") or None,
            q.get("commercial", "false").lower() == "true", q.get("data_level", "frequency"),
            {"population": pop} if pop else {},
        )
        return _j(out)

    @route("POST", "/requests/preview", "Non-consuming privacy and utility preview", "requester")
    async def preview_request(request):
        r = requester(request)
        svc = S()
        require_governed_data(svc)
        body = await _body(request)
        return _j(scoped_requester_call(r, svc.preview, r, body))

    @route("GET", "/variants/search", "Exact coordinate or variant-ID lookup; metadata only", "public")
    async def variant_search(request):
        query = request.query_params.get("q", "").strip()
        if not query or len(query) > 100:
            raise ServiceError(400, "invalid_query", "Enter a variant ID or exact coordinate such as 22:105123:A:G.")
        import re
        svc = S()
        id_match = re.fullmatch(r"[vV]?(\d+)", query)
        coord_match = re.fullmatch(r"(?:chr)?([0-9]{1,2}|X|Y|M|MT):(\d+)(?::([ACGTN]+):([ACGTN]+))?", query, re.I)
        if not svc.release_enabled:
            if not coord_match:
                raise ServiceError(
                    422, "coordinate_required",
                    "Search the verified public catalogue by exact chromosome and position.",
                )
            chrom, raw_pos, ref, alt = coord_match.groups()
            chrom = chrom.upper()
            if chrom == "M":
                chrom = "MT"
            if not raw_pos.isdigit() or not 1 <= int(raw_pos) <= 2_147_483_647:
                raise ServiceError(400, "invalid_position", "Position must be a supported positive integer.")
            search = getattr(svc.store, "verified_public_variant_search", None)
            if search is None:
                raise CatalogueUnavailableError("The store has no verified public variant search.")
            matches = await run_in_threadpool(search, chrom, int(raw_pos), ref, alt)
            return _j({
                "query": query,
                "matches": matches,
                "frequency_policy": "Cohort frequencies are shown only in a separately governed aggregate release.",
                "annotation_available": False,
            })

        matches = []
        if id_match:
            idx = int(id_match.group(1)) - 1
            if 0 <= idx < len(svc.ds.coords):
                matches = [idx]
        elif coord_match:
            chrom, pos, ref, alt = coord_match.groups()
            chrom = chrom.upper().removeprefix("CHR")
            if chrom == "M":
                chrom = "MT"
            pos = int(pos)
            matches = [i for i, (c, p, r, a) in enumerate(svc.ds.coords)
                       if c.upper().removeprefix("CHR") == chrom and p == pos
                       and (ref is None or (r.upper() == ref.upper() and a.upper() == alt.upper()))][:20]
        else:
            raise ServiceError(422, "unsupported_search", "Gene-symbol search is unavailable: this dataset has no linked annotation catalogue. Search by exact coordinate or variant ID.")
        provenance = getattr(svc, "provenance", {})
        return _j({
            "query": query,
            "matches": [{
                "variant_id": i + 1, "chromosome": str(svc.ds.coords[i][0]),
                "position": int(svc.ds.coords[i][1]), "reference_allele": str(svc.ds.coords[i][2]),
                "alternate_allele": str(svc.ds.coords[i][3]),
                "reference_assembly": provenance.get("reference_assembly") or "Not recorded",
            } for i in matches],
            "frequency_policy": "Cohort frequencies are shown only in a governed aggregate release, not by this metadata lookup.",
            "annotation_available": False,
        })

    @route(
        "GET", "/variants/population-frequency",
        "Read-only lookup in approved aggregate population references; never participant calls",
        "public",
    )
    async def population_frequency(request):
        q = request.query_params
        chromosome = q.get("chromosome", "").strip().upper().removeprefix("CHR")
        if chromosome == "M":
            chromosome = "MT"
        allowed_chromosomes = {str(n) for n in range(1, 23)} | {"X", "Y", "MT"}
        if chromosome not in allowed_chromosomes:
            raise ServiceError(400, "invalid_chromosome", "Use a chromosome from 1-22, X, Y, or MT.")
        raw_position = q.get("position", "")
        if not raw_position.isdigit() or int(raw_position) < 1:
            raise ServiceError(400, "invalid_position", "Position must be a positive integer.")
        position = int(raw_position)
        reference = q.get("reference_allele", "").strip().upper()
        alternate = q.get("alternate_allele", "").strip().upper()
        import re
        if (len(reference) > 50 or len(alternate) > 50
                or not re.fullmatch(r"[ACGTN]+", reference)
                or not re.fullmatch(r"[ACGTN]+", alternate)
                or reference == alternate):
            raise ServiceError(400, "invalid_alleles", "Reference and alternate alleles must be distinct DNA alleles.")
        assembly = q.get("assembly", "").strip()
        if assembly not in {"GRCh37", "GRCh38"}:
            raise ServiceError(400, "invalid_assembly", "Choose GRCh37 or GRCh38.")
        variant = {
            "chromosome": chromosome, "position": position,
            "reference_allele": reference, "alternate_allele": alternate,
            "reference_assembly": assembly,
        }
        svc = S()
        lookup = getattr(svc.store, "lookup_population_frequencies", None)
        if getattr(svc.store, "backend", "sqlite") != "postgresql" or lookup is None:
            return _j({
                "status": "unavailable", "variant": variant, "matches": [],
                "message": "Approved aggregate population-reference lookup is not configured for this service.",
            })
        result = await run_in_threadpool(
            lookup, chromosome, position, reference, alternate, assembly,
        )
        return _j({"variant": variant, **result})

    @route("GET", "/admin/dataset-qc", "Steward-only aggregate dataset QC and provenance summary", "admin")
    async def dataset_qc(request):
        admin(request)
        import numpy as np
        svc = S()
        g = np.asarray(svc.ds.genotypes)
        maf = np.asarray(svc.ds.maf, dtype=float)
        coords = svc.ds.coords or []
        chrom_counts = {}
        for chrom, *_ in coords:
            key = str(chrom)
            chrom_counts[key] = chrom_counts.get(key, 0) + 1
        n, v = g.shape
        provenance = getattr(svc, "provenance", {})
        return _j({
            "dataset_id": svc.dataset_id,
            "source": provenance.get("genotype_source") or provenance.get("genotypes_label") or "Unknown",
            "source_sha256": provenance.get("source_vcf_sha256"),
            "sample_count": int(n), "variant_count": int(v),
            "genotype_call_count": int(n * v),
            "matrix_missing_calls": int((g < 0).sum()),
            "missingness_note": "The active cohort matrix contains only retained genotype calls; source-level VCF missingness is not retained by this loader and cannot be reconstructed here.",
            "maf": {
                "minimum": round(float(maf.min()), 6) if maf.size else None,
                "median": round(float(np.median(maf)), 6) if maf.size else None,
                "maximum": round(float(maf.max()), 6) if maf.size else None,
                "below_1_percent": int((maf < 0.01).sum()),
                "monomorphic": int((maf == 0).sum()),
            },
            "chromosome_variant_counts": chrom_counts,
            "reference_assembly": provenance.get("reference_assembly") or "Not recorded",
            "consent_basis": provenance.get("consent_label") or "Unknown",
            "review_status": "Inspection only — not an import acceptance or production-readiness approval",
        })

    @route("POST", "/admin/vcf-qc", "Steward-only bounded VCF QC; file is processed temporarily and not retained", "admin")
    async def vcf_qc(request):
        admin(request)
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/octet-stream":
            raise ServiceError(415, "unsupported_media_type", "send one VCF as application/octet-stream")
        try:
            filename = unquote(request.headers.get("x-filename", ""), errors="strict")
        except UnicodeError:
            raise ServiceError(400, "invalid_filename", "filename must be valid UTF-8") from None
        safe_name = filename.replace("\\", "/").rsplit("/", 1)[-1]
        if (
            len(safe_name) > 200
            or not re.fullmatch(r"(?i)[^<>:\"/\\|?*\x00-\x1f]+\.vcf(?:\.gz)?", safe_name)
        ):
            raise ServiceError(400, "invalid_filename", "filename must end in .vcf or .vcf.gz")
        assembly = request.headers.get("x-reference-assembly", "")
        expected_sha256 = request.headers.get("x-expected-sha256") or None
        if assembly not in {"GRCh37", "GRCh38"}:
            raise ServiceError(400, "invalid_assembly", "select GRCh37 or GRCh38 explicitly")
        if expected_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ServiceError(400, "invalid_checksum", "expected SHA-256 must be 64 lowercase hexadecimal characters")
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError:
                raise ServiceError(400, "invalid_content_length", "invalid Content-Length header") from None
            if declared_length < 0:
                raise ServiceError(400, "invalid_content_length", "invalid Content-Length header")
            if declared_length > MAX_UPLOAD_BYTES:
                raise ServiceError(413, "file_too_large", "maximum VCF upload is 100 MiB")

        suffix = ".vcf.gz" if safe_name.lower().endswith(".vcf.gz") else ".vcf"
        with tempfile.TemporaryDirectory(prefix="genomeguard-vcf-qc-") as temporary_directory:
            staged_path = Path(temporary_directory) / ("input" + suffix)
            received = 0
            try:
                with staged_path.open("xb") as staged:
                    async for chunk in request.stream():
                        received += len(chunk)
                        if received > MAX_UPLOAD_BYTES:
                            raise ServiceError(413, "file_too_large", "maximum VCF upload is 100 MiB")
                        staged.write(chunk)
            except OSError:
                log.exception("Unable to stage temporary VCF for QC")
                raise ServiceError(500, "qc_staging_failed", "could not stage the file for temporary QC processing") from None
            if content_length and received != declared_length:
                raise ServiceError(400, "incomplete_upload", "uploaded byte count did not match Content-Length")
            try:
                with staged_path.open("rb") as staged:
                    is_gzip = staged.read(2) == b"\x1f\x8b"
            except OSError:
                raise ServiceError(400, "invalid_vcf", "could not read the uploaded file") from None
            if is_gzip != suffix.endswith(".gz"):
                raise ServiceError(400, "file_type_mismatch", "file extension does not match VCF compression")
            report = await run_in_threadpool(
                validate_vcf, staged_path, assembly, expected_sha256,
                display_name="[uploaded VCF]", max_file_bytes=MAX_UPLOAD_BYTES,
            )
            return _j(report)

    @route("GET", "/audit", "Audit log (newest first) with chain verification", "admin")
    async def audit(request):
        admin(request)
        return _j(S().audit_view(int(request.query_params.get("limit", 300))))

    @route("GET", "/audit/verify", "Recompute the hash chain; optional external anchor",
           "public")
    async def audit_verify(request):
        q = request.query_params
        anchor = None
        has_length = q.get("anchor_length") is not None
        has_hash = q.get("anchor_hash") is not None
        if has_length != has_hash:
            raise ServiceError(400, "invalid_anchor", "anchor_length and anchor_hash must be supplied together")
        if has_length:
            raw_length = q["anchor_length"]
            raw_hash = q["anchor_hash"]
            if not raw_length.isdecimal() or not re.fullmatch(r"[0-9a-f]{64}", raw_hash):
                raise ServiceError(400, "invalid_anchor", "anchor_length must be a non-negative integer and anchor_hash must be 64 lowercase hexadecimal characters")
            anchor = {"length": int(raw_length), "head_hash": raw_hash}
        return _j(S().audit.verify(anchor))

    @route("GET", "/audit/head", "Current head hash: copy it somewhere outside the system",
           "public")
    async def audit_head(request):
        return _j(S().audit.head())

    @route("GET", "/audit/checkpoint", "Export unsigned audit integrity checkpoint; signer is an attribution label only",
           "public")
    async def audit_checkpoint(request):
        signer = request.query_params.get("signer", "system")
        if not signer.strip() or len(signer) > 128:
            raise ServiceError(400, "invalid_signer_label", "signer label must contain 1–128 characters")
        return _j(S().audit.checkpoint(signed_by=signer))

    @route("POST", "/audit/verify-checkpoint", "Verify checkpoint structure, unkeyed digest, and anchored audit prefix",
           "public")
    async def audit_verify_checkpoint(request):
        body = await _body(request)
        return _j(S().audit.verify_checkpoint(body))

    @route("POST", "/admin/tamper/{idx:int}", "DEMO ONLY: corrupt one audit entry", "admin")
    async def tamper(request):
        if not settings.demo_mode:
            raise ServiceError(404, "not_found", "demo-only endpoint")
        admin(request)
        return _j(S().tamper(request.path_params["idx"]))

    @route("POST", "/admin/untamper", "DEMO ONLY: remove the tamper-demo marker", "admin")
    async def untamper(request):
        if not settings.demo_mode:
            raise ServiceError(404, "not_found", "demo-only endpoint")
        admin(request)
        return _j(S().untamper())

    @route("GET", "/anomalies", "Per-requester timelines and alerts", "admin")
    async def anomalies(request):
        admin(request)
        return _j(admin_call(request.state.admin_principal, S().anomalies))

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
        return _j(admin_call(
            request.state.admin_principal, S().compliance_report, q.get("from"), q.get("to"),
        ))

    @route("GET", "/reports/compliance/export",
           "Downloadable cryptographic compliance evidence pack (DPDP, GDPR, HIPAA)", "admin")
    async def compliance_export(request):
        admin(request)
        q = request.query_params
        evidence = admin_call(
            request.state.admin_principal, S().compliance_evidence_pack, q.get("from"), q.get("to"),
        )
        return _j(evidence)

    @route("GET", "/eval/results", "Stored red-team evaluation metrics", "public")
    async def eval_results(request):
        if not settings.demo_mode:
            raise ServiceError(404, "not_found", "synthetic evaluation results are disabled outside demo mode")
        if not EVAL_JSON.exists():
            raise ServiceError(404, "not_found", "run `make eval` first")
        return JSONResponse(json.loads(EVAL_JSON.read_text()))

    # ---- donor portal (patient side): authenticated by a per-donor key, never by the steward key
    def donor_auth(request: Request) -> int:
        if not settings.demo_mode:
            raise ServiceError(404, "not_found", "participant identity integration is not configured")
        did = request.path_params["id"]
        demo_token = request.headers.get("x-demo-donor-session")
        if demo_token:
            with demo_session_lock:
                session = demo_donor_sessions.get(demo_token)
                if session and session["expires_at"] <= time.time():
                    demo_donor_sessions.pop(demo_token, None)
                    session = None
            if not session or session["donor_id"] != did:
                raise ServiceError(401, "demo_donor_session_invalid", "demo donor session is invalid or expired")
            return did
        if not settings.allow_static_demo_keys:
            raise ServiceError(
                401, "demo_donor_session_required",
                "use a short-lived synthetic demo donor session; static donor keys are disabled",
            )
        if not S().donor_authenticated(did, request.headers.get("x-donor-key")):
            raise ServiceError(401, "unauthorized", "donor key required (X-Donor-Key)")
        return did

    @route("GET", "/demo/donors", "Synthetic donor personas (no credentials)", "public")
    async def demo_donors(request):
        if not settings.demo_mode:
            raise ServiceError(404, "not_found", "demo mode is off")
        return _j({"donors": [
            {"id": donor["id"], "label": donor["label"]}
            for donor in S().demo_donors()
        ]})

    @route("POST", "/demo/donor-session", "Issue a short-lived synthetic demo donor session", "public")
    async def demo_donor_session(request):
        if not settings.demo_mode or settings.oidc_required or settings.tenant_isolation_required:
            raise ServiceError(404, "not_found", "demo sessions are not enabled on this instance")
        data = await _body(request)
        donor_id = data.get("donor_id")
        if isinstance(donor_id, bool) or not isinstance(donor_id, int) or donor_id < 1:
            raise ServiceError(400, "invalid_demo_donor", "donor_id must be a positive integer")
        donor = next((item for item in S().demo_donors() if item["id"] == donor_id), None)
        if not donor:
            raise ServiceError(404, "demo_donor_not_found", "demo donor was not found")
        token, _expires_at = issue_demo_session(demo_donor_sessions, {"donor_id": donor_id})
        return _j({
            "session_token": token,
            "expires_in": _DEMO_SESSION_TTL_SECONDS,
            "donor": {"id": donor_id, "label": donor["label"]},
        })

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
        if not settings.demo_mode:
            raise ServiceError(
                503, "consent_authority_required",
                "participant withdrawal must be recorded by the configured authoritative consent source",
            )
        return _j(S().donor_set_withdrawn(donor_auth(request), True))

    @route("PUT", "/donor/{id:int}/consent", "Change what you agree to (use, disease, limits); "
           "applies to future requests", "donor")
    async def donor_consent(request):
        did = donor_auth(request)
        return _j(S().donor_set_consent(did, await _body(request)))

    @route("POST", "/donor/{id:int}/restore", "Give consent again after withdrawing", "donor")
    async def donor_restore(request):
        if not settings.demo_mode:
            raise ServiceError(
                503, "consent_authority_required",
                "participant re-consent must be recorded by a new signed authoritative consent event",
            )
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
        if not settings.demo_mode:
            raise ServiceError(404, "not_found", "synthetic federated demo is disabled outside demo mode")
        from app.core.federated import he_demo

        return _j(await run_in_threadpool(he_demo))

    @route("GET", "/federated/demo", "Simulated hospitals with secure aggregation (synthetic)",
           "public")
    async def federated_demo(request):
        if not settings.demo_mode:
            raise ServiceError(404, "not_found", "synthetic federated demo is disabled outside demo mode")
        from app.core.federated import demo
        return _j(await run_in_threadpool(demo))

    def documented_routes():
        if settings.demo_mode:
            return ROUTES_DOC
        hidden_prefixes = ("/demo/", "/donor/", "/federated/")
        hidden_exact = {"/eval/results", "/admin/untamper"}
        return [entry for entry in ROUTES_DOC
                if not entry[1].startswith(hidden_prefixes)
                and entry[1] not in hidden_exact
                and not entry[1].startswith("/admin/tamper/")]


    # ── catalogue endpoints: serve local dataset/chromosome data ──────────────
    # These replace the Supabase Edge Function calls that previously required
    # an external publishable key. All data comes from the local backend.

    @route("POST", "/research/open-targets/target", "Retrieve Open Targets gene-disease associations and evidence", "public")
    async def open_targets_target(request):
        """Fetch source-attributed target/disease research evidence by Ensembl ID."""
        from app.literature.open_targets import (
            OpenTargetsProviderError,
            search_target,
            validate_target_request,
        )

        data = await _body(request)
        ensembl_id = data.get("ensembl_id")
        disease_id = data.get("disease_id")
        page_index = data.get("page_index", 0)
        page_size = data.get("page_size", 20)
        evidence_size = data.get("evidence_size", 25)
        evidence_cursor = data.get("evidence_cursor")
        if disease_id == "":
            disease_id = None
        try:
            validate_target_request(
                ensembl_id, disease_id, page_index, page_size, evidence_size, evidence_cursor,
            )
        except ValueError as exc:
            raise ServiceError(400, "invalid_open_targets_query", str(exc)) from None
        if not _OPEN_TARGETS_SEARCH_SLOTS.acquire(blocking=False):
            response = _j({
                "error": "open_targets_provider_busy",
                "message": "Open Targets search is busy. Please retry shortly.",
            }, 429)
            response.headers["Retry-After"] = "2"
            response.headers["Cache-Control"] = "no-store"
            return response
        try:
            try:
                payload = await run_in_threadpool(
                    search_target,
                    ensembl_id,
                    disease_id=disease_id,
                    page_index=page_index,
                    page_size=page_size,
                    evidence_size=evidence_size,
                    evidence_cursor=evidence_cursor,
                )
            except ValueError as exc:
                raise ServiceError(400, "invalid_open_targets_query", str(exc)) from None
            except LookupError:
                raise ServiceError(
                    404, "open_targets_entity_not_found",
                    "Open Targets did not find the supplied Ensembl gene identifier.",
                ) from None
            except OpenTargetsProviderError:
                raise ServiceError(
                    503, "open_targets_provider_unavailable",
                    "Open Targets is temporarily unavailable or returned an invalid response. Please retry.",
                ) from None
        finally:
            _OPEN_TARGETS_SEARCH_SLOTS.release()
        response = _j(payload)
        response.headers["Cache-Control"] = "no-store"
        return response


    @route("POST", "/literature/pubmed/search", "Search public PubMed literature metadata", "public")
    async def pubmed_literature_search(request):
        """Retrieve public PubMed metadata without putting query text in access logs."""
        from app.literature.pubmed import (
            MAX_OFFSET,
            MAX_PAGE_SIZE,
            MAX_QUERY_LENGTH,
            PubMedProviderError,
            search_pubmed,
        )

        data = await _body(request)
        query = data.get("q", "")
        retstart = data.get("retstart", 0)
        retmax = data.get("retmax", 20)
        if not isinstance(query, str) or not query.strip() or len(query.strip()) > MAX_QUERY_LENGTH:
            raise ServiceError(
                400, "invalid_literature_query",
                f"q must contain 1 to {MAX_QUERY_LENGTH} characters",
            )
        if isinstance(retstart, bool) or not isinstance(retstart, int) or not 0 <= retstart <= MAX_OFFSET:
            raise ServiceError(
                400, "invalid_literature_query",
                f"retstart must be an integer between 0 and {MAX_OFFSET}",
            )
        if isinstance(retmax, bool) or not isinstance(retmax, int) or not 1 <= retmax <= MAX_PAGE_SIZE:
            raise ServiceError(
                400, "invalid_literature_query",
                f"retmax must be an integer between 1 and {MAX_PAGE_SIZE}",
            )
        if not _PUBMED_SEARCH_SLOTS.acquire(blocking=False):
            response = _j({
                "error": "literature_provider_busy",
                "message": "PubMed search is busy. Please retry shortly.",
            }, 429)
            response.headers["Retry-After"] = "1"
            response.headers["Cache-Control"] = "no-store"
            return response
        try:
            payload = await run_in_threadpool(
                search_pubmed, query.strip(), retstart=retstart, retmax=retmax,
            )
        except PubMedProviderError:
            raise ServiceError(
                503, "literature_provider_unavailable",
                "PubMed is temporarily unavailable. Please retry or use another literature source.",
            ) from None
        finally:
            _PUBMED_SEARCH_SLOTS.release()
        response = _j(payload)
        # Search strings can be sensitive even though callers are instructed not to send
        # patient data. POST keeps them out of request-line access logs; no-store prevents
        # browser and shared intermediary caching.
        response.headers["Cache-Control"] = "no-store"
        return response

    @route("GET", "/catalogue/sources", "External public genomic sources and review status", "public")
    async def catalogue_sources(request):
        """List source references without approving, importing, or loading datasets."""
        from app.data.public_sources import public_source_catalogue

        sources = public_source_catalogue()
        return _j({
            "sources": sources,
            "source_count": len(sources),
            "discovery_only": True,
            "provenance_note": (
                "Public availability and this catalogue entry do not establish reuse "
                "authorization, participant-specific consent, or import approval. "
                "Review the exact artifact and source terms before use."
            ),
        })

    @route("GET", "/catalogue/datasets", "Local dataset catalogue with source-backed provenance", "public")
    async def catalogue_datasets(request):
        """List only approved manifests whose normalized data rows reconcile."""
        svc = S()
        catalogue = getattr(svc.store, "verified_public_datasets", None)
        if catalogue is None:
            raise CatalogueUnavailableError("The store has no verified dataset catalogue.")
        imported = await run_in_threadpool(catalogue)
        datasets = [{
            **item,
            "source_checksum_recorded": True,
            "variant_data_loaded": True,
            "genotype_provenance": "real_vcf",
            "consent_basis": "dataset_policy",
            "consent_records_matched": 0,
            "dataset_policy_samples_scoped": item["sample_count"],
            "policy_description": (
                "Dataset-level public research terms; no individual consent records are represented."
            ),
        } for item in imported]
        return _j({
            "datasets": datasets,
            "dataset_count": len(datasets),
            "provenance_note": (
                "Only approved public manifests with reconciled normalized sample, variant, and genotype-call counts are listed. "
                "Dataset-level policy is not participant-specific consent or clinical authorization."
            ),
        })

    @route("GET", "/catalogue/chromosomes", "Reference lengths and assembly-matched local coverage", "public")
    async def catalogue_chromosomes(request):
        """Report local coverage only when the loaded cohort assembly is explicitly known."""
        assembly = request.query_params.get("assembly", "GRCh38")
        if assembly not in ("GRCh37", "GRCh38"):
            raise ServiceError(400, "invalid_assembly", "Choose GRCh37 or GRCh38.")
        svc = S()
        coverage_method = getattr(svc.store, "verified_public_chromosome_coverage", None)
        coverage_available = coverage_method is not None
        coverage = []
        if coverage_method is not None:
            try:
                coverage = await run_in_threadpool(coverage_method, assembly)
            except CatalogueUnavailableError:
                # Static reference lengths remain useful, but never imply that missing
                # coverage data means zero observed variants when the query failed.
                coverage_available = False
        positions_by_chromosome = {row["chromosome"]: row for row in coverage}
        # Standard human chromosome sizes for GRCh38 / GRCh37 (bp).
        GRCH38 = [
            ("1", "autosome", 248956422), ("2", "autosome", 242193529),
            ("3", "autosome", 198295559), ("4", "autosome", 190214555),
            ("5", "autosome", 181538259), ("6", "autosome", 170805979),
            ("7", "autosome", 159345973), ("8", "autosome", 145138636),
            ("9", "autosome", 138394717), ("10", "autosome", 133797422),
            ("11", "autosome", 135086622), ("12", "autosome", 133275309),
            ("13", "autosome", 114364328), ("14", "autosome", 107043718),
            ("15", "autosome", 101991189), ("16", "autosome", 90338345),
            ("17", "autosome", 83257441), ("18", "autosome", 80373285),
            ("19", "autosome", 58617616), ("20", "autosome", 64444167),
            ("21", "autosome", 46709983), ("22", "autosome", 50818468),
            ("X", "sex", 156040895), ("Y", "sex", 57227415), ("MT", "mitochondrial", 16569),
        ]
        GRCH37 = [
            ("1", "autosome", 249250621), ("2", "autosome", 243199373),
            ("3", "autosome", 198022430), ("4", "autosome", 191154276),
            ("5", "autosome", 180915260), ("6", "autosome", 171115067),
            ("7", "autosome", 159138663), ("8", "autosome", 146364022),
            ("9", "autosome", 141213431), ("10", "autosome", 135534747),
            ("11", "autosome", 135006516), ("12", "autosome", 133851895),
            ("13", "autosome", 115169878), ("14", "autosome", 107349540),
            ("15", "autosome", 102531392), ("16", "autosome", 90354753),
            ("17", "autosome", 81195210), ("18", "autosome", 78077248),
            ("19", "autosome", 59128983), ("20", "autosome", 63025520),
            ("21", "autosome", 48129895), ("22", "autosome", 51304566),
            ("X", "sex", 155270560), ("Y", "sex", 59373566), ("MT", "mitochondrial", 16571),
        ]
        ref = GRCH38 if assembly == "GRCh38" else GRCH37
        rows = []
        for chrom, kind, length_bp in ref:
            coordinates = positions_by_chromosome.get(chrom)
            loaded = coverage_available and coordinates is not None
            rows.append({
                "chromosome": chrom, "kind": kind, "length_bp": length_bp,
                "data_coverage": {
                    "variant_count": coordinates["variant_count"] if loaded else 0,
                    "first_position": coordinates["first_position"] if loaded else None,
                    "last_position": coordinates["last_position"] if loaded else None,
                    "variant_data_loaded": loaded,
                    "coverage_status": "available" if coverage_available else "unavailable",
                },
            })
        return _j({
            "reference_assembly": assembly, "chromosome_count": len(rows), "chromosomes": rows,
            "coverage_available": coverage_available,
            "provenance_note": (
                "Reference lengths are from the Genome Reference Consortium. Coverage comes only from normalized rows "
                "belonging to approved, reconciled public manifests with the exact requested assembly."
                if coverage_available else
                "Reference lengths are from the Genome Reference Consortium. The coverage query is unavailable, "
                "so no dataset coverage is asserted."
            ),
        })
    @route("GET", "/openapi.json", "Machine-readable endpoint list", "public")
    async def openapi(request):
        return _j({"openapi": "3.0.0-lite", "info": {"title": "GenomeGuard", "version": "0.2.0"},
                   "endpoints": [{"method": m, "path": p, "summary": s, "auth": w}
                                 for m, p, s, w in documented_routes()]})

    @route("GET", "/docs", "Human-readable endpoint list", "public")
    async def docs(request):
        rows = "".join(f"<tr><td>{m}</td><td><code>{p}</code></td><td>{s}</td><td>{w}</td></tr>"
                       for m, p, s, w in documented_routes())
        provenance = getattr(S(), "provenance", {})
        genotype_label = provenance.get("genotypes_label", "Genotype provenance unknown")
        consent_label = provenance.get("consent_label", "Consent provenance unknown")
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>GenomeGuard API</title>"
            "<style>body{font:15px system-ui;margin:2rem;max-width:60rem}td,th{padding:.3rem .8rem;"
            "text-align:left;border-bottom:1px solid #ddd}</style><h1>GenomeGuard API</h1>"
            f"<p>Genotypes: {genotype_label}. Consent: {consent_label}. "
            "These labels describe imported provenance; they do not certify legal authority.</p>"
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
