"""Institutional OIDC access-token verification.

This module accepts signed bearer access tokens from a preconfigured issuer. It does not
implement an authorization-code login UI or treat email domains as organization membership.
Organization membership must be asserted by the trusted issuer in a signed claim and matched
against an operator-maintained allow-list before an identity binding is consulted.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import jwt
from jwt import InvalidTokenError


@dataclass(frozen=True)
class OIDCIdentity:
    issuer: str
    subject: str
    organization_id: str
    claims: dict[str, Any]


class OIDCAuthenticationError(ValueError):
    """An access token or its institutional membership claims are not acceptable."""


@lru_cache(maxsize=8)
def _jwk_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300, timeout=5)


def verify_access_token(
    token: str,
    *,
    issuer: str,
    audience: str,
    jwks_url: str,
    organization_claim: str = "organization_id",
    allowed_organizations: tuple[str, ...] = (),
    jwk_client: Any | None = None,
) -> OIDCIdentity:
    """Verify signature, issuer, audience, time claims and signed org membership.

    Only asymmetric RS256/ES256 tokens are accepted. The JWKS endpoint must be HTTPS.
    """
    parsed = urlparse(jwks_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise OIDCAuthenticationError("OIDC JWKS URL must be an HTTPS URL")
    if not issuer.startswith("https://") or not audience.strip():
        raise OIDCAuthenticationError("OIDC issuer and audience must be configured")
    if not isinstance(token, str) or not token or len(token) > 16_384:
        raise OIDCAuthenticationError("missing or malformed bearer token")
    try:
        client = jwk_client or _jwk_client(jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            issuer=issuer,
            audience=audience,
            leeway=30,
            options={
                "require": ["exp", "iat", "iss", "aud", "sub"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_nbf": True,
                "verify_iss": True,
                "verify_aud": True,
            },
        )
    except (InvalidTokenError, jwt.PyJWKClientError, ValueError, TypeError) as exc:
        raise OIDCAuthenticationError("OIDC access token validation failed") from exc

    subject = claims.get("sub")
    organization_id = claims.get(organization_claim)
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise OIDCAuthenticationError("OIDC subject claim is missing or invalid")
    if not isinstance(organization_id, str) or not organization_id or len(organization_id) > 255:
        raise OIDCAuthenticationError("verified organization membership claim is missing")
    if not allowed_organizations or organization_id not in allowed_organizations:
        raise OIDCAuthenticationError("organization is not enabled for this GenomeGuard instance")
    return OIDCIdentity(
        issuer=issuer,
        subject=subject,
        organization_id=organization_id,
        claims=claims,
    )
