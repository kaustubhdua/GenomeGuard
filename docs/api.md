# HTTP API

Generated from `backend/app/api.py` (also served live at `/docs` and `/openapi.json`).

Auth: requesters send `X-API-Key`; stewards send the admin key as `X-Admin-Key`; donors send `X-Donor-Key`. Demo keys are published at `/demo/requesters` and `/demo/donors` in demo mode only.

| Method | Path | Purpose | Access |
|---|---|---|---|
| GET | `/health` | Liveness and dataset facts | public |
| GET | `/health/ready` | Production readiness gate; distinguishes liveness from safe real-data operation | public |
| GET | `/demo/requesters` | Demo accounts and keys (demo mode only) | public |
| POST | `/admin/requesters` | Provision a requester API key (returned once) | admin |
| GET | `/me` | Who am I, my budget | requester |
| POST | `/requests` | Submit a data request; returns decision, explanation, risk, transform summary and (if released) aggregate data | requester |
| GET | `/beacon/g_variants` | GA4GH Beacon v2 style allele lookup, governed by the same consent, risk and audit pipeline | requester |
| GET | `/requests` | List requests (own; all with admin key) | requester or admin |
| GET | `/requests/{id:int}` | One decision in detail | requester or admin |
| POST | `/requests/{id:int}/review` | Human approve/deny of an escalation | admin |
| POST | `/requests/{id:int}/copilot` | Steward copilot: a read-only, tool-using agent investigates one request and gives an advisory recommendation (?refresh=true to rerun) | admin |
| GET | `/requests/{id:int}/exposure` | Family-exposure graph (simulated model); steward-only because it describes withheld variants and registry relatives | admin |
| GET | `/consent/summary` | How many donors would be eligible (counts only) | requester |
| GET | `/audit` | Audit log (newest first) with chain verification | admin |
| GET | `/audit/verify` | Recompute the hash chain; optional external anchor | public |
| GET | `/audit/head` | Current head hash: copy it somewhere outside the system | public |
| GET | `/audit/checkpoint` | Export an audit checkpoint for offline or cross-system anchoring | public |
| POST | `/audit/verify-checkpoint` | Verify an exported checkpoint against the live chain | public |
| POST | `/admin/tamper/{idx:int}` | DEMO ONLY: corrupt one audit entry | admin |
| POST | `/admin/untamper` | DEMO ONLY: remove the tamper-demo marker | admin |
| GET | `/anomalies` | Per-requester timelines and alerts | admin |
| POST | `/requesters/{id:int}/freeze` | Freeze an account | admin |
| POST | `/requesters/{id:int}/unfreeze` | Human unfreeze | admin |
| GET | `/reports/compliance` | Plain-language compliance report (from/to ISO dates) | admin |
| GET | `/reports/compliance/export` | Export full regulatory evidence package (DPDP, GDPR, HIPAA) | admin |
| GET | `/eval/results` | Stored red-team evaluation metrics | public |
| GET | `/demo/donors` | Demo donor personas and keys (demo mode only) | public |
| GET | `/donor/{id:int}` | A donor's own consent, status and who used their data | donor |
| GET | `/donor/{id:int}/consent.fhir.json` | Download your consent as a FHIR R4 Consent resource (pseudonymous; tagged as simulated demo data) | donor |
| POST | `/donor/{id:int}/withdraw` | Withdraw consent for all future requests | donor |
| PUT | `/donor/{id:int}/consent` | Change what you agree to (use, disease, limits); applies to future requests | donor |
| POST | `/donor/{id:int}/restore` | Give consent again after withdrawing | donor |
| POST | `/donor/{id:int}/ask` | Ask the consent concierge one of a fixed set of questions (who_used, what_allowed, how_withdraw, relatives, security) | donor |
| GET | `/federated/he` | Homomorphic (Paillier) allele-count aggregation demo (synthetic) | public |
| GET | `/federated/demo` | Simulated hospitals with secure aggregation (synthetic) | public |
| GET | `/catalogue/datasets` | Local dataset catalogue (replaces Supabase Edge Function) | public |
| GET | `/catalogue/chromosomes` | Local chromosome reference (replaces Supabase Edge Function) | public |
| GET | `/openapi.json` | Machine-readable endpoint list | public |
| GET | `/docs` | Human-readable endpoint list | public |
