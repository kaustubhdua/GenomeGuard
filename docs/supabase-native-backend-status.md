# Supabase-native backend migration

Status: in progress (29 October 2026). Supabase project `common 1` is the target backend. The intended final architecture is Vercel static frontend + Supabase Auth + Supabase Edge Functions + the private `genomeguard` Postgres schema. Render must not be a runtime dependency in the final product.

## Deployed first slice

- Edge Function: `genomeguard-api` (version 2; deployed 29 October 2026).
- Routes implemented: `GET /health`, `GET /health/ready`, `GET /requests`, `POST /requests`. All other legacy API routes remain unported.
- Request routes verify the incoming Supabase access token with Auth before using a server-only service key to call restricted SQL RPCs.
- Requests are persisted in `genomeguard.requests`, tied to the authenticated user through `genomeguard.requesters.auth_user_id`, and are explicitly marked `pending_review`. This first slice never grants data access or fabricates a policy decision.
- Database RPCs are executable only by `service_role`; browser roles cannot access the private tables directly. A follow-up migration hardens database-level validation for nulls, whitespace-only fields, allowed data levels, and JSON-object filters.
- Readiness is deliberately HTTP 503 until policy engine, cohort loading, identity governance, backup/restore, audit anchoring, and frontend route parity have been completed and verified.

## Not yet migrated

The legacy Python/Starlette API contains the policy engine, risk calculations, privacy-budget accounting, anomaly monitoring, reviewer actions, donor consent/withdrawal flows, Beacon-style queries, encrypted cohort loading, and audit-chain logic. These are not yet fully ported. The current frontend still targets the legacy API proxy. Do not switch all frontend routes or remove Render until each endpoint has a tested Supabase implementation and the UI is migrated to Supabase Auth.

## Safety boundary

The selected Supabase project is shared with BharatSim. Keep all GenomeGuard application data and migrations inside the private `genomeguard` schema; do not alter `bharatsim`. Do not accept private/controlled-access genomic data or describe the service as production-ready until the full policy engine, source provenance, authorization, independent review, and recovery requirements pass.
