#!/usr/bin/env python3
"""Provision the first institution-bound reviewer/steward identity.

Run once per initial administrator on a trusted operator workstation after migrations have
completed. This uses only the restricted application database role; it never prints or creates
a reusable API key. Subsequent identity lifecycle operations use the authenticated admin API.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets

from app.core.audit_chain import AuditChain
from app.postgres_store import PostgresStore
from app.store import AuditStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--institution", required=True)
    parser.add_argument("--subject", required=True, help="exact OIDC sub claim")
    parser.add_argument("--organization-id", required=True, help="exact signed organization claim")
    parser.add_argument("--role", choices=("reviewer", "steward", "admin"), default="steward")
    args = parser.parse_args()

    database_url = os.environ.get("GG_DATABASE_URL", "")
    issuer = os.environ.get("GG_OIDC_ISSUER", "")
    audience = os.environ.get("GG_OIDC_AUDIENCE", "")
    allowed = {
        value.strip() for value in os.environ.get("GG_OIDC_ALLOWED_ORGANIZATIONS", "").split(",")
        if value.strip()
    }
    if not database_url.startswith(("postgres://", "postgresql://")):
        parser.error("GG_DATABASE_URL must be the restricted PostgreSQL runtime URL")
    if not issuer.startswith("https://") or not audience:
        parser.error("GG_OIDC_ISSUER and GG_OIDC_AUDIENCE must be configured")
    if os.environ.get("GG_OIDC_REQUIRED", "").lower() != "true" or (
        os.environ.get("GG_OIDC_ADMIN_REQUIRED", "").lower() != "true"
    ):
        parser.error("enable GG_OIDC_REQUIRED and GG_OIDC_ADMIN_REQUIRED before steward bootstrap")
    if not args.subject or len(args.subject) > 255 or not args.name.strip() or not args.institution.strip():
        parser.error("subject, name and institution must be non-empty and within schema limits")
    if args.organization_id not in allowed:
        parser.error("--organization-id must be in GG_OIDC_ALLOWED_ORGANIZATIONS")

    store = PostgresStore(database_url, run_migrations=False)
    try:
        with store.transaction():
            # A random one-way hash satisfies the legacy non-null column but the key is never
            # disclosed or used; OIDC is the only enabled production authentication method.
            key_hash = hashlib.sha256(secrets.token_urlsafe(48).encode("utf-8")).hexdigest()
            requester_id = store.add_requester(
                args.name.strip(), args.role, "controlled", args.institution.strip(), key_hash,
            )
            store.add_identity_binding(
                requester_id, issuer, args.subject, args.organization_id,
            )
            AuditChain(AuditStore(store)).append(
                "operator-bootstrap", "identity.initial_steward_provisioned",
                {"requester_id": requester_id, "role": args.role,
                 "organization_id": args.organization_id, "issuer": issuer,
                 "subject_sha256": hashlib.sha256(args.subject.encode()).hexdigest()},
            )
        print(f"Provisioned OIDC {args.role} identity: requester_id={requester_id}")
        print("No API key was created or displayed. Verify access with the institution's OIDC token.")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
