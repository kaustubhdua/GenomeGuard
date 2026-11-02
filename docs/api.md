# HTTP API

Generated from `backend/app/api.py` (also served live at `/docs` and `/openapi.json`).

Auth: requesters send `X-API-Key`; stewards send the admin key as `X-Admin-Key`; donors send `X-Donor-Key`. Demo keys are published at `/demo/requesters` and `/demo/donors` in demo mode only.

| Method | Path | Purpose | Access |
|---|---|---|---|
| GET | `/health` | Liveness, dataset facts, and deployment revision when provided by the host | public |
| GET | `/health/live` | Cheap process liveness and deployment revision; no database or cohort initialization | public |
| GET | `/health/ready` | Production readiness gate; distinguishes liveness from safe real-data operation | public |
| GET | `/demo/requesters` | Demo accounts and keys (demo mode only) | public |
| POST | `/admin/requesters` | Provision a requester API key (returned once) | admin |
| GET | `/me` | Who am I, my budget | requester |
| POST | `/requests` | Submit a data request; returns decision, explanation, risk, transform summary and (if released) aggregate data | requester |
| POST | `/requests/preview` | Non-consuming privacy and utility preview | requester |
| GET | `/variants/search` | Metadata-only variant lookup by ID or exact chromosome coordinate | public |
| GET | `/variants/population-frequency` | Exact-allele lookup in approved, loaded aggregate references; includes source provenance | public |
| GET | `/admin/dataset-qc` | Steward-only aggregate dataset QC and provenance summary | admin |
| POST | `/admin/vcf-qc` | Steward-only, bounded QC of a VCF uploaded as a raw request body; processed temporarily and not imported | admin |
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
| GET | `/catalogue/sources` | Curated public source references with explicit review/import status | public |
| GET | `/openapi.json` | Machine-readable endpoint list | public |
| GET | `/docs` | Human-readable endpoint list | public |

`GET /catalogue/sources` is a static discovery index. It returns official source and
policy links plus explicit pending-review/not-imported statuses; it does not fetch or
approve artifacts. `GET /catalogue/datasets` reports only source-backed real VCF
imports. Synthetic demo cohorts are not presented as verified imported datasets.

On Render, `/health` and `/health/live` return the platform and commit SHA from
Render's `RENDER` and `RENDER_GIT_COMMIT` runtime variables. The commit field is `null`
when the host does not provide a valid full SHA. These public endpoints expose no
secrets; the revision supports exact-deployment acceptance checks and does not indicate
production readiness.

## Aggregate population-reference lookup

GET /variants/population-frequency accepts chromosome, position, reference_allele, alternate_allele, and assembly (GRCh37 or GRCh38) as query parameters. It returns only exact-locus aggregate rows from manifests whose data-use review is approved_public_research and import status is loaded. Each row identifies the source, release, URL, checksum, assembly, population, AC, AN, AF, and homozygote count.

The status is available, empty, or unavailable. An empty result means no approved loaded reference matched; unavailable means the serving database, migration, or reader role is not configured. Neither state is filled with estimated values. This public reference endpoint is separate from participant-level cohort evidence and does not create or bypass a governed release.

`POST /admin/vcf-qc` requires `Content-Type: application/octet-stream`,
`X-Filename`, and `X-Reference-Assembly: GRCh37|GRCh38`; `X-Expected-Sha256` is
optional. The raw body must be one `.vcf` or `.vcf.gz`, up to 100 MiB compressed.
Validation also caps decompressed input at 1 GiB, VCF lines at 16 MiB, sample columns
at 10,000, and sample-by-split-ALT genotype cells at 10 million. The service processes
the file in a temporary directory, returns an aggregate QC report, and does not import
or persist the VCF. The configured GenomeGuard server receives the genomic file; use
only a trusted deployment. The response uses `[uploaded VCF]` rather than echoing the
source filename. Assembly selection is compared with recognized VCF header labels and
is not a reference-sequence or REF-allele verification.
