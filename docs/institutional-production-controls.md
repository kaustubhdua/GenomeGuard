# Institutional production controls — implementation and release gates

Updated: 10 November 2026. This document supersedes older statements that OIDC, tenant scoping, and participant-consent event handling were entirely absent. The code is an implementation foundation; it is not institutional approval or proof of a production deployment.

## 1. Institutional OIDC and organization membership

The first-party API now accepts signed OIDC bearer access tokens when configured. The browser implements Authorization Code with PKCE S256 and a transaction-specific state and nonce. It validates the returned ID-token signature against the issuer JWKS, issuer, client audience, expiry, issue time, and nonce. The API independently validates the access-token signature (RS256/ES256 only), issuer, audience, exp/iat/nbf, subject, and a signed organization claim against an operator-maintained organization allow-list.

The identity is not authorized merely because a token is valid. An administrator must provision an exact issuer + subject + organization tuple to a GenomeGuard requester. The browser cannot choose a trusted organization or role. Requester routes accept the researcher role; reviewer/steward routes require a separately provisioned reviewer/steward/admin role when `GG_OIDC_ADMIN_REQUIRED=true`. Identity revocation is exposed through the admin API and recorded in the audit chain. API-key fallback is disabled when the corresponding OIDC-required flags are enabled.

### Required provider configuration

Configure all values as server-side secrets/settings in the production deployment:

- `GG_OIDC_REQUIRED=true`
- `GG_OIDC_ADMIN_REQUIRED=true`
- `GG_TENANT_ISOLATION_REQUIRED=true`
- `GG_OIDC_ISSUER`: exact HTTPS issuer value from the institution.
- `GG_OIDC_AUDIENCE`: exact audience the API expects in access tokens.
- `GG_OIDC_CLIENT_ID`: registered public browser client ID.
- `GG_OIDC_REDIRECT_URI`: exact HTTPS callback URI registered at the provider.
- `GG_OIDC_JWKS_URL`: trusted HTTPS JWKS endpoint.
- `GG_OIDC_ALLOWED_ORGANIZATIONS`: comma-separated immutable organization IDs.
- `GG_OIDC_ORGANIZATION_CLAIM`: signed claim name, default `organization_id`.
- `GG_OIDC_SCOPES`: provider-approved scopes; configure the scope/audience mapping so the issued **access token** is a JWT for `GG_OIDC_AUDIENCE` and contains the signed organization claim.

The provider must support Authorization Code + PKCE S256 and browser token-endpoint CORS for this public client. No client secret is placed in the browser. The access token is held in tab memory only; PKCE verifier/state/nonce are short-lived sessionStorage transaction data and are removed on callback. The app does not store refresh tokens. Users sign in again after a reload. Configure the institution's session lifetime and MFA policies at the identity provider.

The API does not implement user proofing, HR lifecycle, group/organization synchronization, MFA enrollment, or provider-side conditional-access policy. The institution must validate those controls and map trusted membership claims. A signed organization claim must not be inferred from email domains or client input.

### Initial steward bootstrap

The first steward must be provisioned from a trusted operator workstation after the database migrations have been applied. Use `scripts/provision_oidc_identity.py` with the restricted runtime database URL and the exact subject/org values issued by the IdP. The script creates a steward binding and audit entry; it does not print or expose an API key. Thereafter, create researcher/reviewer accounts through the authenticated admin API and bind the exact OIDC subject. Do not enable production OIDC-required flags before the IdP settings and initial steward binding are ready, or all access will correctly fail closed.

## 2. Tenant isolation

Native PostgreSQL migration 005 enables and forces row-level security on `requests`, `decisions`, `epsilon_ledger`, and `alerts`. The API sets a transaction-local `gg.organization_id` only after verifying the OIDC token and resolving an active identity binding. Steward operations set a separate transaction-local admin context only after the steward credential/role is validated. A tenant with no context sees no tenant-owned rows. Cross-organization inserts and reads are denied by the database policies.

The unscoped compatibility path is permitted only inside synthetic demo transactions. `GG_TENANT_ISOLATION_REQUIRED=true` requires OIDC and blocks API-key-only researcher access. The RLS test suite creates a non-owner PostgreSQL role and checks same-tenant reads, cross-tenant denial, default-deny behavior, and explicit admin scope.

RLS is not a substitute for safe application SQL or database role separation. The application runtime role must not own tables, be a superuser, or have `BYPASSRLS`. Do not give browser clients a direct database URL. Review any new tenant-owned table and add an explicit policy before exposing it.

## 3. Separate database principals

The PostgreSQL adapter now accepts two distinct connection URLs:

- `GG_DATABASE_URL`: restricted runtime principal used for all normal queries.
- `GG_MIGRATION_DATABASE_URL`: schema-owner principal used only while applying numbered migrations during startup.

The migration connection is closed after migration and the privileged URL is removed from the process environment/settings. The runtime connection only sets its search_path and does not create schemas or run DDL. The provisioning script can open the runtime connection with migrations disabled.

A restricted Neon role `gg_app_runtime` was created for the synthetic staging database and directly inspected: it is not superuser, does not have BYPASSRLS, cannot CREATE in either GenomeGuard schema, and can read the synthetic donor rows. The staging Render service has **not yet been switched** to this role; its environment must be updated only after the migration-aware code is deployed and staging acceptance is repeated. Production must create its own isolated database and role; do not reuse staging credentials.

## 4. Signed participant consent and withdrawal events

The application now has a signed consent-event ingestion path. The authority signs the canonical event payload using Ed25519. The API verifies the signature against the configured trusted public key, checks the issuer and active dataset ID, validates event shape/date/use/modifiers, resolves the exact source sample, and records only a dataset-keyed HMAC-SHA-256 of the source sample identifier in the cohort database. The signed payload itself is not stored. The consent ledger records the event ID, participant row, dataset, event type, consent JSON, issuer, source-record digest, effective time, and receipt time.

Supported event types are `consent_updated`, `withdrawn`, and `restored`. Restore requires a new signed, complete consent payload; a previous consent is not silently reactivated. Event IDs are idempotent. A dataset-level public-release policy cannot be promoted into participant-specific consent. The PostgreSQL consent ledger is protected by a trigger that rejects UPDATE and DELETE; corrections are represented by superseding signed events.

### Required configuration

- `GG_CONSENT_AUTHORITY_REQUIRED=true`
- `GG_CONSENT_AUTHORITY_ISSUER`: exact trusted HTTPS source-system issuer.
- `GG_CONSENT_AUTHORITY_PUBLIC_KEY`: base64-encoded 32-byte Ed25519 public key.

The private signing key belongs in the institution's consent source system or HSM-backed signing workflow; it must never be placed in GenomeGuard. The route remains unavailable until a trusted authority and public key are configured. The data controller must prove participant-to-source-sample reconciliation, consent scope, source-system authority, withdrawal timing, and decision-time policy semantics. The current implementation does not itself certify the source authority or establish a lawful basis. Real participant data must remain disabled until the institution approves and tests the full source-system integration.

## 5. Independently signed audit checkpoints

The hash-chained audit log remains useful for tamper detection, but an unsigned checkpoint or a `signed_by` text label is not an external signature. The application now supports Ed25519-signed checkpoint envelopes and verification. `scripts/sign_audit_checkpoint.py` is designed for a separately controlled offline signing workstation: export the unsigned checkpoint, sign it with an externally held private key, and publish the signed envelope to an immutable, independently administered store. The private key is not stored in the application database or deployment environment.

Required before production: establish a public-key registry with key IDs, custody/rotation/revocation procedures, independent timestamping, WORM/object-lock retention, access logging, and a tested verification/reconciliation process. No independent immutable external anchor is configured by this PR; signing capability alone does not complete that control.

## 6. PostgreSQL durability, backups, and recovery

The current public production service remains on the older `main` deployment and uses SQLite on an ephemeral filesystem. No production PostgreSQL database has been provisioned or cut over. The checked-in production Blueprint now declares separate runtime and migration URLs and requires OIDC/tenant isolation/signed consent configuration, but these settings are not a live production migration.

A real provider recovery exercise was completed against the synthetic Neon staging database:
- Created a manual snapshot `snap-royal-tooth-a1un9r4d`.
- Restored it into a separate branch `gg-restore-drill-2026-11-10` (`br-patient-recipe-a1agz4kb`), leaving the active staging branch untouched.
- Verified 600 synthetic donors, 3,000 variants, 600 genotype rows, 16 audit rows, and 13 runtime tables in the restored branch.
- Verified audit indices were contiguous and every previous-hash link matched the preceding row.
- The restored branch is retained as recovery evidence; deleting a database branch is destructive and requires explicit operator approval.

This proves a snapshot restore path for the synthetic staging project, not production RPO/RTO or recovery of real data. The staging Neon project is on the Free v3 plan with a 6-hour history-retention window and no scheduled snapshot policy. Neon documents that the Free plan's default history window is 6 hours, paid plans have longer default retention, history can be configured up to 30 days, and scheduled snapshots require an eligible paid plan. Production needs an institution-approved plan, a suitable history window, scheduled snapshots or external encrypted backups, independent backup-key custody, monitoring, and recurring recovery drills. Do not claim PITR beyond the configured retention window.

## 7. Independent review and clinical boundary

The following approvals cannot be supplied by code or by this assistant:
- Data-controller and institutional privacy/legal approval for each dataset and jurisdiction.
- Research ethics / IRB / IEC / data-access committee approval and consent authority validation.
- Independent security architecture review, threat model, penetration testing, incident response, and key-management review.
- Clinical validation and regulatory determination before any clinical decision support or patient care use.
- Retention, deletion, data-subject rights, breach response, and vendor/processor contracts.

GenomeGuard remains a research-governance prototype, not a diagnostic, clinical decision, or participant-consent authority. Keep readiness fail-closed and real-data workflows disabled until each institution-specific gate is documented and independently signed off.

## Open-source standards and references

- [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html) — issuer, audience, ID-token, nonce and discovery requirements.
- [RFC 9700 OAuth 2.0 Security Best Current Practice](https://datatracker.ietf.org/doc/html/rfc9700) — authorization-code protections, PKCE, exact redirect URI matching and mix-up defenses.
- [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — default-deny policies, owner bypass and FORCE ROW LEVEL SECURITY behavior.
- [GA4GH Data Use Ontology](https://www.ga4gh.org/product/data-use-ontology-duo/) — standardized dataset use terms; it does not itself establish participant consent.
- [Neon point-in-time restore and snapshots](https://neon.com/blog/announcing-point-in-time-restore) — provider history retention and branch restore model.
