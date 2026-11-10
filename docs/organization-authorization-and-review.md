# Institutional organization authorization and consent — implementation status

**Status: technical controls are implemented on the production-controls branch; institution-specific configuration and independent approval remain outstanding.** See [institutional production controls](institutional-production-controls.md) for deployment steps and release gates.

## Active runtime and authentication

The active application is the first-party Python/Starlette API. Supabase Auth, Edge Functions, PostgREST and browser database credentials are not used.

The production-controls branch adds:
- Browser OIDC Authorization Code flow with PKCE S256, transaction-specific state and nonce, ID-token signature/JWKS validation, and in-memory access-token handling.
- API-side JWT validation for signature (RS256/ES256), exact issuer, audience, time claims, subject, and a signed organization-membership claim.
- Explicit issuer + subject + organization binding to a provisioned GenomeGuard requester. The client cannot self-assign an organization or role.
- Separate researcher and reviewer/steward/admin roles. When OIDC-required flags are enabled, shared API/admin keys are not accepted as a fallback.
- Identity binding revocation with audit evidence.
- Forced PostgreSQL RLS policies for requests, decisions, privacy-budget ledger and alerts. Tenant context is transaction-local and set only after the API resolves the verified binding; missing scope is default-deny.

These controls are code, not a claim that a real institution has configured its IdP. The production Blueprint requires the OIDC client, issuer, JWKS, audience, redirect URI, organization allow-list and initial steward bootstrap. No institutional IdP credentials or verified organization claims have been supplied in this environment.

## Organization authorization

The institution must operate the trusted IdP and source of organization membership. The signed claim must be immutable and must represent current membership, not an email-domain guess. The operator must provision exact subject/org bindings and review role assignments. The system does not perform employee/student proofing, HR lifecycle, MFA enrollment, or institution-side conditional access. Those remain IdP/institution responsibilities.

RLS protects tenant-owned PostgreSQL records, but it is not a substitute for application-level authorization, safe SQL, least-privilege database roles, or external security review. Do not give a browser or untrusted client direct database access.

## Participant consent

The public 1000 Genomes mode uses dataset-level public-release terms; synthetic demo mode uses synthetic consent attributes. Neither is participant-specific consent for a private cohort.

The production-controls branch adds:
- Exact source-sample reconciliation using a SHA-256 hash stored in the cohort database rather than retaining the raw source identifier.
- An Ed25519-signed consent-event ingestion path for consent updates, withdrawal and re-consent.
- Trusted issuer and dataset binding, signature verification, event-id idempotency, effective-time validation and a durable consent event ledger.
- An append-only PostgreSQL consent ledger; UPDATE/DELETE are rejected by a database trigger.
- Rejection of attempts to convert dataset-level public terms into participant-specific consent.

The signed consent authority remains unconfigured. The institution must identify the authoritative consent system, establish key custody, validate participant-to-source-sample reconciliation, and approve purpose/recipient/expiry/withdrawal semantics. The API endpoint remains unavailable until a trusted issuer and Ed25519 public key are configured. A signed event proves only that the configured key signed the payload; it does not prove that the key holder has legal authority or that the source record is ethically sufficient.

## Review and release separation

A human review approval is not itself permission to expose genotypes. The release pipeline must re-check identity, organization, purpose, dataset terms, participant consent where applicable, expiry/withdrawal, policy version, and output-risk controls at release time. New participant consent events update the active cohort's consent state and are audited.

## GA4GH references

- [Data Use Ontology (DUO)](https://www.ga4gh.org/product/data-use-ontology-duo/) — standardized dataset use terms, not participant consent.
- [Machine-Readable Consent Guidance](https://www.ga4gh.org/product/machine-readable-consent-guidance-mrcg/) — mapping consent language to DUO.
- [GA4GH AAI](https://www.ga4gh.org/product/authorisation-and-authentication-infrastructure-aai/) and [Passports](https://www.ga4gh.org/product/passports/) — authorization interoperability, not drop-in identity proofing.
- [GA4GH Data Security Infrastructure Policy](https://github.com/ga4gh/data-security/blob/master/DSIP/DSIP_v4.0.md) — access-control and minimum-privilege guidance.

## Release rule

Keep real participant/controlled data disabled until institution-specific OIDC and consent-authority configuration, PostgreSQL least-privilege/RLS validation, signed external audit anchoring, provider recovery evidence, and independent privacy, legal, ethics and security review are complete. Clinical use additionally requires clinical validation and regulatory review.
