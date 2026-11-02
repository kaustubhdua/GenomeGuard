# GenomeGuard live-readiness audit — 3 November 2026

This audit records read-only checks of the public Vercel deployment and the connected Supabase project. No production data was inserted, modified, or deleted during the checks. The only live database change in this work was the additive steward-queue RPC migration; no organizations, users, memberships, consent records, or genomic data were seeded.

## Vercel production deployment

Project: `genome-guard` (`prj_Q2uhnuLdzXTo4JoZUXqzhW6YuICT`)  
Production deployment: `dpl_5yQmTqq4J2WC8vvbdDhChHPMows4`  
Observed deployed commit: `7ed416ce53fdbbb5269a867f55bcb8dcfbfb6d4e`  
Latest GitHub mainline at the time of this audit: newer than the deployed commit.

| Request | Result | Interpretation |
|---|---:|---|
| `GET /` | HTTP 200 | Static frontend is reachable. The page still presents the legacy API-key connection UI; Supabase Auth sign-in is not integrated into the production frontend. |
| `GET /health` | HTTP 200 | Backend is reachable, but the returned payload says `storage_backend=sqlite`; it is not using the connected Supabase PostgreSQL database. |
| Dataset-level consent provenance | Inconsistent | Health says dataset-level public-release terms are not participant-specific consent, but also reports `consent_records_matched=600`, a consent-record hash and a consent source filename. These are not evidence of 600 participant consent records. Current repository source normalizes this to zero participant records and tracks dataset-policy scope separately. |
| `GET /catalogue/datasets` | HTTP 404 | The running Render backend does not expose the current repository's verified dataset catalogue endpoint. |
| `GET /catalogue/sources` | HTTP 404 | The running Render backend does not expose the current repository's source-discovery endpoint. |
| `GET /health/ready` | HTTP 503 | Correctly fail-closed. Do not change this to ready until all release gates are verified. |

Vercel's deployment state is READY, but this proves only that the static frontend deployment completed. API requests are still rewritten to Render. The deployed frontend SHA is not the latest mainline SHA, and the backend is demonstrably stale relative to the current source.

## Supabase project `common 1`

Project ref: `hkyieaovolkethovyenb`  
Region: `ap-south-1`  
PostgreSQL: 17.11  
Project state: `ACTIVE_HEALTHY`

Read-only database inspection found:

- 23 tables in the private `genomeguard` schema.
- Zero normalized dataset manifests, dataset samples, dataset variants, or genotype calls.
- Zero organizations, organization memberships, participant-consent records, requests, decisions, review-history records, and API events.
- No schema `USAGE` for `anon`, `authenticated`, or `service_role`; no direct browser access to private GenomeGuard tables.
- The connected Python backend is not configured to use this database; the live health payload reports SQLite.

### Steward review queue change

The additive migration `genomeguard_steward_review_queue` was applied. The `genomeguard-api` Edge Function was deployed as version 8.

New route:

`GET /functions/v1/genomeguard-api/steward/requests?limit=50&offset=0`

The route validates a Supabase bearer token, then calls the service-role-only RPC `public.gg_list_review_queue(uuid,integer,integer)`. The RPC derives organization and role from active database membership, limits page size, returns only pending/clarification requests in that organization, and rejects users with no reviewer membership or multiple active reviewer organizations.

Live SQL verification confirmed:

- `SECURITY DEFINER` with an empty `search_path`.
- `EXECUTE` granted to `service_role` only; denied to `anon` and `authenticated`.
- A probe using an unprovisioned identity failed closed with SQLSTATE `42501` (`active_reviewer_membership_required`).

A successful authenticated queue read and review lifecycle are not verified because there are no active organizations or memberships. The endpoint does not grant access to genomic data.

## Supabase advisor findings

The security advisor reported informational `rls_enabled_no_policy` findings for private GenomeGuard tables and tables belonging to another application in the shared project. The private schema has no browser-role schema usage or direct table grants; do not create permissive policies merely to silence these notices. The Auth advisor reports leaked-password protection is disabled and this setting needs review in the Supabase Auth configuration.

## Release blockers

1. Deploy the latest backend code and verify `/health`, `/catalogue/datasets`, and `/catalogue/sources` against the exact current commit.
2. Configure a least-privilege server-side PostgreSQL connection for the Render backend. The connection string/password is not available through this session and must not be guessed or placed in the browser.
3. Resolve the hosted consent/provenance mismatch; the 600 count and hash must not be represented as participant-specific consent.
4. Provision trusted organization memberships through a separately authorized administrative process, then verify authenticated researcher and steward workflows end to end.
5. Import only an exact artifact whose terms have been reviewed for the intended use; reconcile its checksum, assembly, sample/variant/call counts, and provenance.
6. Verify persistent request/decision/audit behavior across restart, backup and isolated restore.
7. Implement and independently verify external audit anchoring, and complete manual accessibility, security, privacy, legal, and ethics reviews.

Until these gates are satisfied, GenomeGuard remains a research prototype. Do not upload private participant genomic data or use the application for clinical decisions. A dataset-level public-release policy is not participant-specific consent.
