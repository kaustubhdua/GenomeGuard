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
        oidc_allowed_organizations=("org-a",),
    )
    monkeypatch.setattr("app.api.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.identity.verify_access_token",
        lambda *args, **kwargs: OIDCIdentity(
            "https://id.example.edu", "subject-1", "org-a", {},
        ),
    )
    svc = bootstrap()
    requester = svc.store.requester_by_key(hash_key("demo-researcher"))
    svc.store.add_identity_binding(
        requester["id"], "https://id.example.edu", "subject-1", "org-a",
    )
    client = TestClient(create_app(svc))

    assert client.get("/me", headers={"Authorization": "Bearer valid-token"}).status_code == 200
    svc.store.revoke_identity_binding("https://id.example.edu", "subject-1", "org-a")
    assert client.get("/me", headers={"Authorization": "Bearer valid-token"}).status_code == 403
