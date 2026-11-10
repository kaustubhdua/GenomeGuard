import pytest
from starlette.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.identity import OIDCIdentity
from app.service import hash_key
from app.store import Store


def test_oidc_binding_is_tenant_scoped_revocable_and_auditable():
    store = Store(":memory:")
    requester_id = store.add_requester(
        "Researcher", "researcher", "registered", "Example University", hash_key("api-key"),
    )
    store.add_identity_binding(
        requester_id, "https://id.example.edu", "subject-1", "org-a",
    )

    assert store.requester_by_oidc(
        "https://id.example.edu", "subject-1", "org-a",
    )["id"] == requester_id
    assert store.requester_by_oidc(
        "https://id.example.edu", "subject-1", "org-b",
    ) is None
    # Repeating the same provisioning request is idempotent, but a subject cannot
    # silently move to a different requester within the same organization.
    store.add_identity_binding(
        requester_id, "https://id.example.edu", "subject-1", "org-a",
    )
    other_id = store.add_requester(
        "Other", "researcher", "registered", "Example University", hash_key("other-key"),
    )
    with pytest.raises(ValueError, match="already bound"):
        store.add_identity_binding(
            other_id, "https://id.example.edu", "subject-1", "org-a",
        )
    request_id = store.add_request(
        requester_id, "2026-11-10T00:00:00Z", {"purpose": "disease_research"},
    )
    assert store.one("SELECT organization_id FROM requests WHERE id=?", (request_id,))[
        "organization_id"
    ] == "org-a"

    store.revoke_identity_binding("https://id.example.edu", "subject-1", "org-a")
    assert store.requester_by_oidc(
        "https://id.example.edu", "subject-1", "org-a",
    ) is None
    store.db.close()


def test_api_accepts_only_bound_oidc_subject_and_tenant(monkeypatch):
    from app.service import bootstrap

    settings = Settings(
        oidc_issuer="https://id.example.edu",
        oidc_audience="genomeguard-api",
        oidc_jwks_url="https://id.example.edu/.well-known/jwks.json",
        oidc_allowed_organizations=("org-a", "org-b"),
        oidc_required=True,
        oidc_admin_required=True,
    )
    monkeypatch.setattr("app.api.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.identity.verify_access_token",
        lambda token, *args, **kwargs: OIDCIdentity(
            "https://id.example.edu", token, "org-a", {},
        ),
    )
    svc = bootstrap()
    requester = svc.store.requester_by_key(hash_key("demo-researcher"))
    svc.store.add_identity_binding(
        requester["id"], "https://id.example.edu", "researcher-sub", "org-a",
    )
    reviewer_id = svc.store.add_requester(
        "Reviewer", "reviewer", "controlled", "Example University", hash_key("unused-reviewer-key"),
    )
    svc.store.add_identity_binding(
        reviewer_id, "https://id.example.edu", "reviewer-sub", "org-a",
    )
    request_id = svc.store.add_request(
        requester["id"], "2026-11-10T00:00:00Z",
        {"purpose": "disease_research", "disease": None, "is_commercial": False,
         "data_level": "frequency", "cohort_filter": {}, "variant_filter": {}},
    )
    # Record the RLS context calls just as the PostgreSQL store would receive them.
    rls_scopes = []
    svc.store.set_tenant = lambda organization_id: rls_scopes.append(("tenant", organization_id))
    svc.store.set_admin_access = lambda: rls_scopes.append(("global_admin", None))
    client = TestClient(create_app(svc))
    # Bootstrap synthetic fixtures in demo mode, then exercise the production-only
    # provisioning route with the same non-demo guard used by an institutional instance.
    settings.demo_mode = False

    researcher_headers = {"Authorization": "Bearer researcher-sub"}
    reviewer_headers = {"Authorization": "Bearer reviewer-sub"}
    assert client.get("/me", headers=researcher_headers).status_code == 200
    assert len(client.get("/requests", headers=researcher_headers).json()["requests"]) == 1
    assert len(client.get("/requests", headers=reviewer_headers).json()["requests"]) == 1
    assert client.get(f"/requests/{request_id}", headers=reviewer_headers).status_code == 200
    assert client.get("/anomalies", headers=researcher_headers).status_code == 403
    assert client.get("/anomalies", headers=reviewer_headers).status_code == 200
    assert ("tenant", "org-a") in rls_scopes
    assert ("global_admin", None) not in rls_scopes
    assert client.get("/me", headers=reviewer_headers).status_code == 403
    # An organization-bound reviewer must not inspect the global audit ledger.
    assert client.get("/audit", headers=reviewer_headers).status_code == 403

    steward_id = svc.store.add_requester(
        "Steward", "steward", "controlled", "Example University", hash_key("unused-steward-key"),
    )
    svc.store.add_identity_binding(
        steward_id, "https://id.example.edu", "steward-sub", "org-a",
    )
    steward_headers = {"Authorization": "Bearer steward-sub"}
    # Even a steward cannot create or revoke bindings in a different allowed tenant.
    cross_org = client.post(
        "/admin/oidc-bindings",
        headers=steward_headers,
        json={"requester_id": requester["id"], "subject": "other-sub", "organization_id": "org-b"},
    )
    assert cross_org.status_code == 403
    assert cross_org.json()["error"] == "cross_organization_binding_forbidden"
    assert client.post(
        "/admin/oidc-bindings/revoke",
        headers=steward_headers,
        json={"subject": "researcher-sub", "organization_id": "org-b"},
    ).status_code == 403

    # An organization steward can provision a researcher in their own organization,
    # then bind that researcher's exact OIDC subject. Institutional mode never returns
    # a fallback API key.
    provisioned_researcher = client.post(
        "/admin/requesters",
        headers=steward_headers,
        json={
            "name": "New Org A Researcher", "institution": "Example University",
            "credential_level": "registered", "role": "researcher", "organization_id": "org-a",
        },
    )
    assert provisioned_researcher.status_code == 201
    created = provisioned_researcher.json()
    assert created["identity_binding_required"] is True
    assert "api_key" not in created
    bound = client.post(
        "/admin/oidc-bindings",
        headers=steward_headers,
        json={
            "requester_id": created["id"], "subject": "new-researcher-sub",
            "organization_id": "org-a",
        },
    )
    assert bound.status_code == 201
    assert client.get(
        "/me", headers={"Authorization": "Bearer new-researcher-sub"},
    ).status_code == 200

    # Exercise the actual authenticated researcher -> steward review lifecycle,
    # not only identity lookup and read-only queue access.
    controlled_id = svc.store.add_requester(
        "Controlled Org A Researcher", "researcher", "controlled",
        "Example University", hash_key("unused-controlled-researcher-key"),
        organization_id="org-a",
    )
    svc.store.add_identity_binding(
        controlled_id, "https://id.example.edu", "controlled-researcher-sub", "org-a",
    )
    controlled_headers = {"Authorization": "Bearer controlled-researcher-sub"}
    held_response = client.post(
        "/requests",
        headers=controlled_headers,
        json={
            "purpose": "disease_research", "disease": "diabetes", "is_commercial": False,
            "data_level": "record", "cohort_filter": {},
            "variant_filter": {"min_maf": 0.1, "limit": 20, "include_planted": 2},
        },
    )
    assert held_response.status_code == 201
    held = held_response.json()
    assert held["outcome"] == "escalate" and held["status"] == "held" and held["needs_human"] is True
    assert held.get("release") in (None, {})

    request_path = f"/requests/{held['id']}"
    assert client.get(request_path, headers=steward_headers).status_code == 200
    assert client.post(
        f"{request_path}/review",
        headers=steward_headers,
        json={"approve": False, "reviewer": "Org A Steward"},
    ).status_code == 200
    reviewed = client.get(request_path, headers=controlled_headers).json()
    assert reviewed["outcome"] == "deny" and reviewed["status"] == "denied"
    assert reviewed["reviewed_by"] == "Org A Steward"
    assert reviewed.get("release") in (None, {})
    assert client.post(
        f"{request_path}/review",
        headers=controlled_headers,
        json={"approve": True},
    ).status_code == 403
    assert client.get("/audit/verify").json()["ok"] is True

    # The same steward cannot create users in another tenant or grant a peer
    # the steward role. A reviewer cannot provision accounts at all.
    cross_org_provision = client.post(
        "/admin/requesters",
        headers=steward_headers,
        json={
            "name": "Tenant B Researcher", "institution": "Tenant B Institute",
            "credential_level": "registered", "role": "researcher", "organization_id": "org-b",
        },
    )
    assert cross_org_provision.status_code == 403
    assert cross_org_provision.json()["error"] == "cross_organization_requester_forbidden"
    peer_steward = client.post(
        "/admin/requesters",
        headers=steward_headers,
        json={
            "name": "Another Steward", "institution": "Example University",
            "credential_level": "controlled", "role": "steward", "organization_id": "org-a",
        },
    )
    assert peer_steward.status_code == 403
    assert peer_steward.json()["error"] == "steward_role_provisioning_forbidden"
    assert client.post(
        "/admin/requesters",
        headers=reviewer_headers,
        json={
            "name": "Reviewer Created User", "institution": "Example University",
            "credential_level": "registered", "role": "researcher", "organization_id": "org-a",
        },
    ).status_code == 403

    global_admin_id = svc.store.add_requester(
        "Global Administrator", "admin", "controlled", "GenomeGuard Operations",
        hash_key("unused-global-admin-key"),
    )
    svc.store.add_identity_binding(
        global_admin_id, "https://id.example.edu", "global-admin-sub", "org-a",
    )
    global_admin_headers = {"Authorization": "Bearer global-admin-sub"}
    # Even an OIDC principal provisioned with the organization-level admin role
    # cannot provision another organization or obtain the global audit ledger.
    provisioned = client.post(
        "/admin/requesters",
        headers=global_admin_headers,
        json={
            "name": "Tenant B Researcher", "institution": "Tenant B Institute",
            "credential_level": "registered", "role": "researcher", "organization_id": "org-b",
        },
    )
    assert provisioned.status_code == 403
    assert client.post(
        "/admin/oidc-bindings",
        headers=global_admin_headers,
        json={"requester_id": requester["id"], "subject": "tenant-b-sub", "organization_id": "org-b"},
    ).status_code == 403
    assert client.get("/anomalies", headers=global_admin_headers).status_code == 200
    assert client.get("/audit", headers=global_admin_headers).status_code == 403
    assert ("global_admin", None) not in rls_scopes

    svc.store.revoke_identity_binding("https://id.example.edu", "reviewer-sub", "org-a")
    assert client.get("/anomalies", headers=reviewer_headers).status_code == 403
