# GenomeGuard live-readiness audit — 2 November 2026

This is a read-only check of the publicly reachable Render API on 2 November 2026.
It does not establish that the service is suitable for private participant data,
clinical use, or production governance. No credentials were used and no live data
or infrastructure was changed.

## Observed API status

| Check | Result | Interpretation |
| --- | --- | --- |
| `GET /health` | HTTP 200; reports 600 donors, 3,000 variants, `real_vcf`, and 1000 Genomes (IGSR) as an operator-declared source | Reachability and self-reported provenance are not independent source authentication or production readiness. |
| Dataset-level policy disclosure | The response says the policy is dataset-level and not individual consent, but also reports `consent_records_matched=600`, a consent-record hash, and a policy filename as the consent source | This conflicts with current repository behavior, which reports zero participant-consent records for dataset-policy mode and reports scoped samples separately. Do not interpret the hosted count or hash as participant consent. |
| `GET /health/ready` | HTTP 503 | The deployment is correctly not represented as production-ready. |
| `GET /catalogue/datasets` | HTTP 404 | The live API does not expose the current dataset catalogue route. |
| `GET /catalogue/sources` | HTTP 404 | The live API does not expose current public-source discovery. |
| `/#/overview` browser page | Loads, but its heading is “Govern genomic data access with auditable decisions.” | This differs from the current repository’s overview heading and is evidence of frontend deployment drift. |
| Runtime revision | Not present in the observed health response | The exact deployed commit could not be identified from the public endpoint. Current code now exposes Render's platform-provided commit SHA on health/liveness endpoints; re-check after deployment. |

The current repository is ahead of the hosted API behavior observed above. A successful
`/health` response is not evidence that the latest code is deployed. The API acceptance
check is designed to fail until the current policy metadata is visible; the live UI
smoke test now checks the dataset, source-discovery, and chromosome routes against their
expected page headings instead of treating any `h1` as proof that a page loaded.

## Build and verification boundary

The real-cohort Dockerfile previously relied on comments to imply cache invalidation;
comments do not alter a Docker `RUN` cache key. The build now consumes
`GENOMEGUARD_COHORT_BUILD_REV`, and the repository image workflow supplies the commit
SHA. Its CI image build verifies the generated cohort metadata, source checksums,
dataset-policy scope, zero participant-consent records, and removal of raw source files.
Docker is unavailable in the local environment, so this build must be verified by the
GitHub Actions workflow.

## Release status and next actions

GenomeGuard remains a research prototype. Before production or controlled-data use:

1. Deploy and verify the exact current commit; confirm route parity and source-policy
   metadata with the live acceptance checks.
2. Resolve and independently review the hosted consent/provenance discrepancy.
3. Verify the Supabase API/persistence cutover, organization isolation, durable storage,
   identity provider, external audit anchoring, and backup/restore.
4. Complete exact-artifact rights review, source-hash reconciliation, and an approved
   import before claiming a public reference or cohort is available for use.
5. Run the full browser, security, accessibility, and end-to-end acceptance suites
   against the exact deployed commit and complete independent legal, ethics, privacy,
   and security reviews.

Until then, do not upload private participant data or use this service for clinical
decisions. A public dataset policy mapping is not participant-specific consent.

## Recheck after automatic deployment was enabled

After `render.yaml` enabled automatic deployment from `main`, the public service was
probed again with the repository at `c6337ed`. `GET /health` still returned HTTP 200
without a `git_commit` value; `/health/live` returned 404; `/health/ready` returned
503; and `/catalogue/datasets` and `/catalogue/sources` both returned 404. Automatic
deployment configuration is not evidence that the current application is running.
The deployed revision and the reason for the route mismatch remain unknown without
Render deployment or log access.

## Recheck after the navigation milestone

After pushing `a4f2b563f99aeb363ef4fccd658b3eb02d779b2f` to `main`, the public service
was probed again without credentials or state-changing requests:

- `/health` returned HTTP 200 and reported 600 donors, 3,000 variants, and
  operator-declared 1000 Genomes VCF provenance. It did not include a runtime commit.
- The policy metadata again said dataset-level public-release terms are not
  participant-specific consent, while also reporting `consent_records_matched=600`
  and a consent-record hash. This remains an unresolved hosted discrepancy; the count
  and hash are not evidence of participant consent.
- `/health/live` returned 404; `/health/ready` returned 503; and
  `/catalogue/datasets` and `/catalogue/sources` returned 404.

The public service therefore still does not demonstrate that the pushed revision is
deployed. No Render credentials, deployment logs, or control-plane access were
available to diagnose or correct the mismatch. Keep readiness closed and do not use
the hosted response as proof of consent or current repository behavior.
