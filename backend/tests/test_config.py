import base64
from dataclasses import replace

import pytest

from app.config import Settings, validate_settings


def secure_settings(**overrides):
    base = Settings(
        demo_mode=False,
        database_url="postgresql://runtime:test@localhost:5432/genomeguard",
        migration_database_url="postgresql://owner:test@localhost:5432/genomeguard",
        admin_api_key="a-unique-admin-secret-with-more-than-32-chars",
        master_key=base64.b64encode(b"x" * 32).decode(),
        allow_tamper_demo=False,
        real_cohort_file="/tmp/authorized-real-cohort.npz",
        dataset_id="approved-cohort-2026-01",
        oidc_required=True, oidc_admin_required=True, tenant_isolation_required=True,
        oidc_issuer="https://id.example.edu", oidc_audience="genomeguard-api",
        oidc_client_id="genomeguard-browser", oidc_redirect_uri="https://genomeguard.example.edu/",
        oidc_jwks_url="https://id.example.edu/.well-known/jwks.json",
        oidc_allowed_organizations=("research-org-1",),
    )
    return replace(base, **overrides)


def test_non_demo_settings_accept_postgresql_and_secure_keys():
    validate_settings(secure_settings(
        oidc_required=True,
        oidc_admin_required=True,
        tenant_isolation_required=True,
        oidc_issuer="https://id.example.edu",
        oidc_audience="genomeguard-api",
        oidc_client_id="genomeguard-browser",
        oidc_redirect_uri="https://genomeguard.example.edu/",
        oidc_jwks_url="https://id.example.edu/.well-known/jwks.json",
        oidc_allowed_organizations=("research-org-1",),
    ))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"database_url": ""}, "GG_DATABASE_URL"),
        ({"database_url": "sqlite:///genomeguard.sqlite3"}, "GG_DATABASE_URL"),
        ({"migration_database_url": ""}, "GG_MIGRATION_DATABASE_URL"),
        ({"migration_database_url": "postgresql://runtime:test@localhost:5432/genomeguard"}, "distinct database roles"),
        ({"admin_api_key": "demo-admin-key"}, "GG_ADMIN_API_KEY"),
        ({"admin_api_key": ""}, "GG_ADMIN_API_KEY"),
        ({"admin_api_key": "short-secret"}, "GG_ADMIN_API_KEY"),
        ({"master_key": ""}, "GG_MASTER_KEY"),
        ({"master_key": "not-base64"}, "GG_MASTER_KEY"),
        ({"master_key": base64.b64encode(b"short").decode()}, "GG_MASTER_KEY"),
        ({"allow_tamper_demo": True}, "GG_ALLOW_TAMPER_DEMO"),
        ({"real_cohort_file": ""}, "GG_REAL_COHORT_FILE"),
        ({"dataset_id": "synthetic-cohort-1"}, "GG_DATASET_ID"),
    ],
)
def test_non_demo_settings_reject_unsafe_values(overrides, message):
    with pytest.raises(ValueError, match=message):
        validate_settings(secure_settings(**overrides))


def test_synthetic_demo_mode_keeps_no_key_guided_demo_available():
    validate_settings(Settings(demo_mode=True, admin_api_key="demo-admin-key",
                               master_key="", allow_tamper_demo=True))


def test_tenant_isolation_requires_fully_configured_oidc():
    with pytest.raises(ValueError, match="GG_TENANT_ISOLATION_REQUIRED"):
        validate_settings(secure_settings(tenant_isolation_required=True))
    validate_settings(secure_settings(
        tenant_isolation_required=True,
        oidc_required=True,
        oidc_admin_required=True,
        oidc_issuer="https://id.example.edu",
        oidc_audience="genomeguard-api",
        oidc_client_id="genomeguard-browser",
        oidc_redirect_uri="https://genomeguard.example.edu/",
        oidc_jwks_url="https://id.example.edu/.well-known/jwks.json",
        oidc_allowed_organizations=("research-org-1",),
    ))


def test_signed_consent_authority_requires_https_issuer_and_ed25519_key():
    with pytest.raises(ValueError, match="GG_CONSENT_AUTHORITY_PUBLIC_KEY"):
        validate_settings(secure_settings(consent_authority_required=True))
    validate_settings(secure_settings(
        consent_authority_required=True,
        consent_authority_issuer="https://consent.example.edu",
        consent_authority_public_key=base64.b64encode(b"p" * 32).decode(),
    ))
