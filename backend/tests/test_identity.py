import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.identity import OIDCAuthenticationError, verify_access_token

class StaticJwkClient:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=self.key)


@pytest.fixture
def oidc_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def issue(private, **overrides):
    now = int(time.time())
    claims = {
        "iss": "https://id.example.edu",
        "aud": "genomeguard-api",
        "sub": "user-123",
        "organization_id": "research-org-1",
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test-key"})


def verify(token, public):
    return verify_access_token(
        token,
        issuer="https://id.example.edu",
        audience="genomeguard-api",
        jwks_url="https://id.example.edu/.well-known/jwks.json",
        allowed_organizations=("research-org-1",),
        jwk_client=StaticJwkClient(public),
    )


def test_valid_signed_token_returns_issuer_subject_and_verified_org(oidc_keys):
    private, public = oidc_keys
    identity = verify(issue(private), public)
    assert identity.issuer == "https://id.example.edu"
    assert identity.subject == "user-123"
    assert identity.organization_id == "research-org-1"


@pytest.mark.parametrize("claims", [
    {"iss": "https://attacker.example"},
    {"aud": "another-api"},
    {"exp": int(time.time()) - 120},
    {"sub": ""},
    {"organization_id": ""},
    {"organization_id": "unapproved-org"},
])
def test_invalid_claims_are_rejected(oidc_keys, claims):
    private, public = oidc_keys
    with pytest.raises(OIDCAuthenticationError):
        verify(issue(private, **claims), public)


def test_unsigned_or_wrong_key_tokens_are_rejected(oidc_keys):
    private, public = oidc_keys
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = issue(other)
    with pytest.raises(OIDCAuthenticationError):
        verify(token, public)


def test_non_https_jwks_endpoint_is_rejected(oidc_keys):
    private, public = oidc_keys
    with pytest.raises(OIDCAuthenticationError, match="HTTPS"):
        verify_access_token(
            issue(private), issuer="https://id.example.edu", audience="genomeguard-api",
            jwks_url="http://id.example.edu/jwks.json",
            allowed_organizations=("research-org-1",), jwk_client=StaticJwkClient(public),
        )
